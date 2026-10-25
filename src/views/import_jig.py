from __future__ import annotations

import hashlib
from datetime import datetime

import pandas as pd
import streamlit as st

from src.config import (
    PDF_DIR,
    generate_pdf_filename,
    get_gemini_api_key,
    set_gemini_api_key,
)
from src.database import (
    fetch_all_registered_files,
    fetch_latest_exam_for_modality_or_region,
    insert_imaging_event,
    insert_qualitative_items,
    insert_vital_metrics,
    rebuild_organ_ledger,
    register_file,
    upsert_organ_ledger,
)
from src.gemini_extractor import extract_health_doc_from_pdf
from src.models import (
    HealthDocExtractionResult,
    ImagingEventPayload,
    RegisteredFileRecord,
)
from src.recall_engine import compute_dynamic_next_due, derive_organ_ledger_update


def render_import_jig_view() -> None:
    """View 4: 検査結果の自動取り込み・登録。"""
    st.subheader("検査結果の取り込み・登録")
    st.caption(
        "健診・検査結果のPDFをアップロードし、Gemini 3.8 Flash（思考レベル: medium）で自動抽出・新旧確認・データベース登録"
    )

    # 登録完了メッセージの表示
    if success_msg := st.session_state.pop("registration_success_msg", None):
        st.success(success_msg)

    # ファイル一覧タブへの案内
    st.info("💡 登録済みの検査原本ファイル一覧の確認や削除は「ファイル一覧」タブをご利用ください。")

    # セッションステートの初期化
    if "uploaded_file_hash" not in st.session_state:
        st.session_state["uploaded_file_hash"] = None
    if "extraction_result" not in st.session_state:
        st.session_state["extraction_result"] = None
    if "uploaded_pdf_bytes" not in st.session_state:
        st.session_state["uploaded_pdf_bytes"] = None
    if "uploader_key" not in st.session_state:
        st.session_state["uploader_key"] = 0

    # 2. API キーの確認
    active_api_key = get_gemini_api_key()
    if not active_api_key:
        manual_key = st.text_input(
            "Gemini API キーを入力 (GEMINI_API_KEY 環境変数が未設定の場合)",
            type="password",
            help="Google AI Studio から取得した API キー",
        )
        if manual_key:
            active_api_key = manual_key.strip()
            if st.checkbox("このAPIキーを保存 (data/settings.json に永続化)", value=True):
                set_gemini_api_key(active_api_key)
        else:
            st.info("💡 PDFの自動解析を実行するには Gemini API キーが必要です（サイドバーからも設定可能）。")
    else:
        st.success("✅ Gemini API キーは設定済みです（PDF自動解析利用可能）")

    # 3. PDFファイルアップローダー
    uploaded_file = st.file_uploader(
        "新しい健康診断・精密検査結果のPDFをアップロード",
        type=["pdf"],
        key=f"pdf_uploader_{st.session_state['uploader_key']}",
        help="人間ドック結果報告書、CT検査レポート、内視鏡報告書、DWIBSレポート等に対応",
    )

    if uploaded_file is None:
        st.session_state["uploaded_file_hash"] = None
        st.session_state["uploaded_pdf_bytes"] = None
        st.session_state["extraction_result"] = None
    else:
        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # 重複ファイル照合チェック
        all_registered = fetch_all_registered_files()
        already_reg = next((f for f in all_registered if f["file_hash"] == file_hash), None)
        if already_reg:
            st.warning(
                f"⚠️ このファイルは既に登録されています。\n\n"
                f"- ファイル名: **{already_reg['file_name']}**\n"
                f"- 検査日: **{already_reg['exam_date']}** | 医療機関: **{already_reg['clinic_name']}**\n"
                f"- 登録日時: **{already_reg['registered_at']}**\n\n"
                f"再度登録する必要はありません。誤登録の場合は上の一覧から削除してください。"
            )

        # ファイルハッシュの比較による API 二重呼び出しガード
        if file_hash != st.session_state["uploaded_file_hash"]:
            st.session_state["uploaded_file_hash"] = file_hash
            st.session_state["uploaded_pdf_bytes"] = file_bytes
            st.session_state["extraction_result"] = None

            if not active_api_key:
                st.error("Gemini APIキーを入力してください。")
            else:
                with st.spinner("Gemini 3.8 Flash（思考レベル: medium）でPDF解析中..."):
                    try:
                        result = extract_health_doc_from_pdf(file_bytes, api_key=active_api_key)
                        st.session_state["extraction_result"] = result
                        st.toast("PDFの解析が完了しました！")
                    except Exception as e:
                        st.error(f"解析エラー: {e!s}")

    # 4. 抽出結果のプレビュー & 新旧確認フォーム
    ext_result: HealthDocExtractionResult | None = st.session_state.get("extraction_result")
    if ext_result is not None:
        st.subheader("抽出結果プレビュー & 新旧検査日照合・登録確認")

        with st.form("commit_form", clear_on_submit=False):
            st.info(f"書類種別の自動判別結果: **{ext_result.doc_type}**")

            # A. 年次ドック・生化学データ
            if ext_result.checkup_data:
                cd = ext_result.checkup_data
                st.markdown("#### 1. 定期健診・生化学検査データ")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.text_input("受診日 (YYYY-MM-DD)", value=cd.exam_date, disabled=True)
                with col_c2:
                    st.text_input("受診医療機関", value=cd.clinic_name, disabled=True)

                # 人間ドック（総合・胃カメラ・腹部超音波含む）の既存前回検査日との照合
                existing_annual = fetch_latest_exam_for_modality_or_region(
                    "人間ドック(胃カメラ、腹部超音波を含む)", "全身"
                )
                if existing_annual:
                    old_date = existing_annual["exam_date"]
                    if cd.exam_date > old_date:
                        st.success(
                            f"✅ 【人間ドック(胃カメラ、腹部超音波を含む)】既存の前回検査日（**{old_date}**）より新しい受診日（**{cd.exam_date}**）です。"
                            f"次回推奨日は新たに 1年後（**{cd.exam_date[:4]}年の同時期**）へ更新されます。"
                        )
                    elif cd.exam_date < old_date:
                        st.info(
                            f"ℹ️ 【人間ドック(胃カメラ、腹部超音波を含む)】既存の最新検査日（**{old_date}**）より過去の受診記録です。"
                            f"検査履歴として蓄積されますが、最新の前回検査日（**{old_date}**）は維持されます。"
                        )
                    else:
                        st.warning(
                            f"⚠️ 【人間ドック(胃カメラ、腹部超音波を含む)】同日（**{cd.exam_date}**）の健診記録が既に存在します。上書き更新されます。"
                        )
                else:
                    st.info(
                        "🆕 【人間ドック(胃カメラ、腹部超音波を含む)】システム初のドック記録として登録されます。次回予定は1年後となります。"
                    )

                metrics_df = pd.DataFrame([m.model_dump() for m in cd.metrics])
                st.dataframe(metrics_df, use_container_width=True, hide_index=True)

                if cd.qualitative_items:
                    st.markdown(f"#### 2. 定性検査・所見・各科判定データ ({len(cd.qualitative_items)} 件)")
                    q_df = pd.DataFrame([q.model_dump() for q in cd.qualitative_items])
                    st.dataframe(q_df, use_container_width=True, hide_index=True)

            # B. 単一画像検査データ
            if ext_result.imaging_data:
                im = ext_result.imaging_data
                st.markdown("#### 精密画像・内視鏡検査データ")
                col_i1, col_i2, col_i3 = st.columns(3)
                with col_i1:
                    st.text_input("検査日", value=im.exam_date, disabled=True)
                    st.text_input("検査種別", value=im.modality, disabled=True)
                with col_i2:
                    st.text_input("検査部位", value=im.target_region, disabled=True)
                    st.text_input("受診医療機関", value=im.clinic_name, disabled=True)
                with col_i3:
                    st.text_input("判定ステータス", value=im.status_flag, disabled=True)
                    st.text_input("該当ページ", value=str(im.pdf_page or 1), disabled=True)

                st.text_area("主要所見", value=im.primary_findings, disabled=True)
                st.text_area("医師コメント", value=im.raw_comment, disabled=True)

                # 既存の前回検査日との照合判定
                existing_single = fetch_latest_exam_for_modality_or_region(im.modality, im.target_region)
                calcd_due = compute_dynamic_next_due(
                    im.exam_date, im.modality, im.status_flag, im.raw_comment, im.suggested_interval_years
                )
                if existing_single:
                    old_exam = existing_single["exam_date"]
                    old_due = existing_single["dynamic_next_due"]
                    if im.exam_date > old_exam:
                        st.success(
                            f"✅ 【{im.modality}（部位: {im.target_region}）】既存の前回検査日（**{old_exam}** / 次回: {old_due}）より新しい検査です。\n\n"
                            f"→ 今回の受診日（**{im.exam_date}**）を新たな「前回検査日」とし、次回推奨受診日を **{calcd_due}** に更新します。"
                        )
                    elif im.exam_date < old_exam:
                        st.info(
                            f"ℹ️ 【{im.modality}（部位: {im.target_region}）】既存の最新検査日（**{old_exam}** / 次回: {old_due}）より過去の受診記録です。\n\n"
                            f"→ 過去履歴として保存されますが、現在のアクティブな前回検査日および次回受診推奨日は最新の記録（**{old_exam}**）が維持されます。"
                        )
                    else:
                        st.warning(f"⚠️ 同日（**{im.exam_date}**）の検査記録が存在します。上書き更新されます。")
                else:
                    st.info(
                        f"🆕 【{im.modality}（部位: {im.target_region}）】システム初の検査記録です。"
                        f"前回検査日: **{im.exam_date}** → 次回推奨受診日: **{calcd_due}** として登録されます。"
                    )

            # C. 内包された画像検査データ
            if ext_result.embedded_imaging_events:
                st.markdown(f"#### 3. 人間ドック内包の精密画像検査 ({len(ext_result.embedded_imaging_events)} 件)")
                for _idx, emb in enumerate(ext_result.embedded_imaging_events):
                    emb_due = compute_dynamic_next_due(
                        emb.exam_date, emb.modality, emb.status_flag, emb.raw_comment, emb.suggested_interval_years
                    )
                    st.write(
                        f"- **{emb.modality}** ({emb.target_region}) | "
                        f"所見: {emb.primary_findings} [{emb.status_flag}] | 次回推奨: **{emb_due}** | P.{emb.pdf_page or 1}"
                    )
                    # 各内包検査の既存前回検査日との照合
                    existing_emb = fetch_latest_exam_for_modality_or_region(emb.modality, emb.target_region)
                    if existing_emb:
                        old_dt = existing_emb["exam_date"]
                        if emb.exam_date > old_dt:
                            st.caption(f"  └ 既存前回検査日（{old_dt}）を今回の検査日（{emb.exam_date}）へ更新します。")
                        elif emb.exam_date < old_dt:
                            st.caption(
                                f"  └ 既存の最新検査日（{old_dt}）より過去の受診記録です（過去履歴として保存）。"
                            )

            force_overwrite = st.checkbox(
                "過去日付の検査記録であっても、既存の最新検査日・次回受診日を強制的にこの日付で上書きする（通常はOFF）",
                value=False,
                help="過去日付の記録を修正・差し替え登録したい場合のみチェックしてください。",
            )

            submit_commit = st.form_submit_button("検査結果をデータベースへ登録・原本保存", type="primary")

        if submit_commit:
            with st.spinner("データベースへ登録中..."):
                pdf_bytes_to_save = st.session_state.get("uploaded_pdf_bytes")
                if not pdf_bytes_to_save:
                    st.error("保存対象のPDFデータが見つかりません。")
                    return

                file_hash_val = hashlib.sha256(pdf_bytes_to_save).hexdigest()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if ext_result.doc_type == "ANNUAL_CHECKUP" and ext_result.checkup_data:
                    c_date = ext_result.checkup_data.exam_date
                    c_clinic = ext_result.checkup_data.clinic_name
                    saved_pdf_name = generate_pdf_filename(c_date, "ANNUAL", c_clinic, is_annual=True)
                    saved_pdf_path = PDF_DIR / saved_pdf_name
                    saved_pdf_path.write_bytes(pdf_bytes_to_save)

                    # 1. registered_files へ登録
                    file_record = RegisteredFileRecord(
                        file_name=saved_pdf_name,
                        original_name=uploaded_file.name if uploaded_file else saved_pdf_name,
                        file_hash=file_hash_val,
                        doc_type="ANNUAL_CHECKUP",
                        exam_date=c_date,
                        clinic_name=c_clinic,
                        registered_at=now_str,
                        file_size=len(pdf_bytes_to_save),
                        storage_path=str(saved_pdf_path),
                    )
                    new_file_id = register_file(file_record)

                    # 2. メトリクス登録
                    insert_vital_metrics(ext_result.checkup_data.metrics, c_date, file_id=new_file_id)

                    # 3. 定性検査・所見・判定項目の登録
                    if ext_result.checkup_data.qualitative_items:
                        insert_qualitative_items(ext_result.checkup_data.qualitative_items, c_date, file_id=new_file_id)

                    # 4. 人間ドック(胃カメラ、腹部超音波を含む) イベント自体の登録（次回推奨日: 1年後）
                    annual_event = ImagingEventPayload(
                        exam_date=c_date,
                        modality="人間ドック(胃カメラ、腹部超音波を含む)",
                        target_region="全身",
                        clinic_name=c_clinic,
                        status_flag="CLEAR",
                        primary_findings="人間ドック（生化学・身体測定・定性判定・胃カメラ・腹部超音波包含）",
                        raw_comment="人間ドック（次回推奨受診時期: 1年後）",
                        pdf_page=1,
                        suggested_interval_years=1.0,
                    )
                    annual_due = compute_dynamic_next_due(
                        c_date,
                        "人間ドック(胃カメラ、腹部超音波を含む)",
                        "CLEAR",
                        suggested_interval_years=1.0,
                    )
                    insert_imaging_event(annual_event, annual_due, str(saved_pdf_path), file_id=new_file_id)
                    annual_ledger = derive_organ_ledger_update(annual_event, annual_due)
                    if force_overwrite:
                        upsert_organ_ledger(annual_ledger)
                    else:
                        existing_a = fetch_latest_exam_for_modality_or_region(
                            "人間ドック(胃カメラ、腹部超音波を含む)", "全身"
                        )
                        if not existing_a or c_date >= existing_a["exam_date"]:
                            upsert_organ_ledger(annual_ledger)

                    # 5. 内包画像検査の登録
                    for emb in ext_result.embedded_imaging_events:
                        due = compute_dynamic_next_due(
                            emb.exam_date,
                            emb.modality,
                            emb.status_flag,
                            emb.raw_comment,
                            emb.suggested_interval_years,
                        )
                        insert_imaging_event(emb, due, str(saved_pdf_path), file_id=new_file_id)
                        ledger_item = derive_organ_ledger_update(emb, due)
                        if force_overwrite:
                            upsert_organ_ledger(ledger_item)
                        else:
                            existing_emb = fetch_latest_exam_for_modality_or_region(emb.modality, emb.target_region)
                            if not existing_emb or emb.exam_date >= existing_emb["exam_date"]:
                                upsert_organ_ledger(ledger_item)

                elif ext_result.imaging_data:
                    im_data = ext_result.imaging_data
                    saved_pdf_name = generate_pdf_filename(
                        im_data.exam_date, im_data.modality, im_data.clinic_name, is_annual=False
                    )
                    saved_pdf_path = PDF_DIR / saved_pdf_name
                    saved_pdf_path.write_bytes(pdf_bytes_to_save)

                    # 1. registered_files へ登録
                    file_record = RegisteredFileRecord(
                        file_name=saved_pdf_name,
                        original_name=uploaded_file.name if uploaded_file else saved_pdf_name,
                        file_hash=file_hash_val,
                        doc_type="SINGLE_IMAGING",
                        exam_date=im_data.exam_date,
                        clinic_name=im_data.clinic_name,
                        registered_at=now_str,
                        file_size=len(pdf_bytes_to_save),
                        storage_path=str(saved_pdf_path),
                    )
                    new_file_id = register_file(file_record)

                    # 2. 画像検査の登録
                    due = compute_dynamic_next_due(
                        im_data.exam_date,
                        im_data.modality,
                        im_data.status_flag,
                        im_data.raw_comment,
                        im_data.suggested_interval_years,
                    )
                    insert_imaging_event(im_data, due, str(saved_pdf_path), file_id=new_file_id)

                    # 3. 元帳更新（最新日または強制上書き時のみ）
                    ledger_item = derive_organ_ledger_update(im_data, due)
                    if force_overwrite:
                        upsert_organ_ledger(ledger_item)
                    else:
                        existing_rec = fetch_latest_exam_for_modality_or_region(im_data.modality, im_data.target_region)
                        if not existing_rec or im_data.exam_date >= existing_rec["exam_date"]:
                            upsert_organ_ledger(ledger_item)

                # 整合性確保のための再同期
                rebuild_organ_ledger()

                st.session_state["registration_success_msg"] = (
                    "データベースへの登録および原本ファイルの保存が正常に完了しました！"
                )
                st.session_state["extraction_result"] = None
                st.session_state["uploaded_file_hash"] = None
                st.session_state["uploaded_pdf_bytes"] = None
                st.session_state["uploader_key"] = int(st.session_state.get("uploader_key", 0)) + 1
                st.cache_data.clear()
                st.rerun()
