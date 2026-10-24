from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from src.config import PDF_DIR, generate_pdf_filename, get_gemini_api_key
from src.database import (
    insert_imaging_event,
    insert_vital_metrics,
    upsert_organ_ledger,
)
from src.gemini_extractor import extract_health_doc_from_pdf
from src.models import (
    HealthDocExtractionResult,
)
from src.recall_engine import compute_dynamic_next_due, derive_organ_ledger_update
from src.seed_data import load_seed_data


def render_import_jig_view() -> None:
    """View 4: 検査結果の自動取り込み・登録。"""
    st.subheader("検査結果の取り込み・登録")
    st.caption(
        "健診・検査結果のPDFをアップロードし、Gemini 3.8 Flash（思考レベル: medium）で自動抽出・内容確認・データベース登録"
    )

    # セッションステートの初期化
    if "uploaded_file_hash" not in st.session_state:
        st.session_state["uploaded_file_hash"] = None
    if "extraction_result" not in st.session_state:
        st.session_state["extraction_result"] = None
    if "uploaded_pdf_bytes" not in st.session_state:
        st.session_state["uploaded_pdf_bytes"] = None

    # 実機サンプル一括登録機能（デモ・動作確認用）
    with st.expander("⚡ クイックアクション: 4種のサンプル検査結果を一括登録", expanded=False):
        st.write("添付された4件の実データ（CT・DWIBS・大腸内視鏡・人間ドック3年分）を一括初期化・再登録します。")
        if st.button("サンプル検査結果を一括登録実行", type="secondary"):
            with st.spinner("検査結果データを登録中..."):
                counts = load_seed_data()
            st.success(
                f"登録完了: 生化学検査データ {counts['vital_metrics_count']} 件, "
                f"精密画像検査 {counts['imaging_events_count']} 件"
            )
            st.rerun()

    st.divider()

    # 1. API キーの確認
    active_api_key = get_gemini_api_key()
    if not active_api_key:
        manual_key = st.text_input(
            "Gemini API キーを入力 (GEMINI_API_KEY 環境変数が未設定の場合)",
            type="password",
            help="Google AI Studio から取得した API キー",
        )
        if manual_key:
            active_api_key = manual_key.strip()
        else:
            st.info("💡 PDFの自動解析を実行するには Gemini API キーが必要です。")

    # 2. PDFファイルアップローダー
    uploaded_file = st.file_uploader(
        "健康診断・精密検査結果のPDFをアップロード",
        type=["pdf"],
        help="人間ドック結果報告書、CT検査レポート、内視鏡報告書、DWIBSレポート等に対応",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

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

    # 3. 抽出結果のプレビュー & 登録確認フォーム
    ext_result: HealthDocExtractionResult | None = st.session_state.get("extraction_result")
    if ext_result is not None:
        st.subheader("抽出結果プレビュー & 確定登録")

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

                metrics_df = pd.DataFrame([m.model_dump() for m in cd.metrics])
                st.dataframe(metrics_df, use_container_width=True, hide_index=True)

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

            # C. 内包された画像検査データ
            if ext_result.embedded_imaging_events:
                st.markdown(f"#### 2. 人間ドック内包の精密画像検査 ({len(ext_result.embedded_imaging_events)} 件)")
                for _idx, emb in enumerate(ext_result.embedded_imaging_events):
                    st.write(
                        f"- **{emb.modality}** ({emb.target_region}) | "
                        f"所見: {emb.primary_findings} [{emb.status_flag}] | P.{emb.pdf_page or 1}"
                    )

            submit_commit = st.form_submit_button("検査結果をデータベースへ登録・原本保存", type="primary")

        if submit_commit:
            with st.spinner("データベースへ登録中..."):
                pdf_bytes_to_save = st.session_state.get("uploaded_pdf_bytes")

                if ext_result.doc_type == "ANNUAL_CHECKUP" and ext_result.checkup_data:
                    c_date = ext_result.checkup_data.exam_date
                    c_clinic = ext_result.checkup_data.clinic_name
                    saved_pdf_name = generate_pdf_filename(c_date, "ANNUAL", c_clinic, is_annual=True)
                    saved_pdf_path = PDF_DIR / saved_pdf_name

                    if pdf_bytes_to_save:
                        saved_pdf_path.write_bytes(pdf_bytes_to_save)

                    # メトリクス登録
                    insert_vital_metrics(ext_result.checkup_data.metrics, c_date)

                    # 内包画像検査の登録
                    for emb in ext_result.embedded_imaging_events:
                        due = compute_dynamic_next_due(
                            emb.exam_date,
                            emb.modality,
                            emb.status_flag,
                            emb.raw_comment,
                            emb.suggested_interval_years,
                        )
                        insert_imaging_event(emb, due, str(saved_pdf_path))
                        ledger_item = derive_organ_ledger_update(emb, due)
                        upsert_organ_ledger(ledger_item)

                elif ext_result.imaging_data:
                    im_data = ext_result.imaging_data
                    saved_pdf_name = generate_pdf_filename(
                        im_data.exam_date, im_data.modality, im_data.clinic_name, is_annual=False
                    )
                    saved_pdf_path = PDF_DIR / saved_pdf_name

                    if pdf_bytes_to_save:
                        saved_pdf_path.write_bytes(pdf_bytes_to_save)

                    due = compute_dynamic_next_due(
                        im_data.exam_date,
                        im_data.modality,
                        im_data.status_flag,
                        im_data.raw_comment,
                        im_data.suggested_interval_years,
                    )
                    insert_imaging_event(im_data, due, str(saved_pdf_path))
                    ledger_item = derive_organ_ledger_update(im_data, due)
                    upsert_organ_ledger(ledger_item)

                st.success("データベースへの登録および検査原本PDFの保存が正常に完了しました！")
                st.session_state["extraction_result"] = None
                st.session_state["uploaded_file_hash"] = None
                st.rerun()
