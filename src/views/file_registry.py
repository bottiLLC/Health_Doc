from __future__ import annotations

from pathlib import Path

import streamlit as st

from backup_manager import run_backup
from src.database import (
    delete_registered_files_cascade,
    fetch_all_registered_files,
)


def render_file_registry_view() -> None:
    """View 5: 登録済み検査原本ファイルの管理・一覧表示・選択削除。"""
    st.subheader("登録済み検査原本ファイル一覧")
    st.caption(
        "システムに登録されている健診結果報告書・画像検査レポートの原本ファイル一覧です。"
        "原本PDFのダウンロードや、誤って登録したファイルの安全な選択削除が行えます。"
    )

    # 削除完了メッセージの表示
    if success_msg := st.session_state.pop("file_deletion_success_msg", None):
        st.toast(success_msg, icon=":material/check_circle:")

    registered_files = fetch_all_registered_files()
    if not registered_files:
        st.info("登録済みの原本ファイルはありません。「登録」タブから健診・検査結果のPDFを登録してください。")
        return

    st.write(f"登録ファイル数: **{len(registered_files)} 件**")

    # 選択チェックボックス用のテーブルヘッダー
    col_hdr1, col_hdr2, col_hdr3, col_hdr4, col_hdr5, col_hdr6 = st.columns([1, 4, 2, 3, 3, 2])
    col_hdr1.markdown("**選択**")
    col_hdr2.markdown("**ファイル名 / 原本**")
    col_hdr3.markdown("**受診日**")
    col_hdr4.markdown("**書類種別 / 機関**")
    col_hdr5.markdown("**取り込み件数**")
    col_hdr6.markdown("**登録日時**")
    st.divider()

    selected_ids: list[int] = []
    for f_item in registered_files:
        fid = int(f_item["file_id"])
        c1, c2, c3, c4, c5, c6 = st.columns([1, 4, 2, 3, 3, 2])

        with c1:
            is_selected = st.checkbox("", key=f"sel_reg_file_{fid}", label_visibility="collapsed")
            if is_selected:
                selected_ids.append(fid)

        with c2:
            st.write(f":material/description: **{f_item['file_name']}**")
            file_path = Path(str(f_item["storage_path"]))
            if file_path.exists():
                st.download_button(
                    label="原本PDF保存",
                    icon=":material/download:",
                    data=file_path.read_bytes(),
                    file_name=file_path.name,
                    mime="application/pdf",
                    key=f"dl_reg_file_{fid}",
                    type="secondary",
                    width="content",
                )
            else:
                st.caption("（ファイル未配置）")

        with c3:
            st.write(f_item["exam_date"] or "-")

        with c4:
            doc_lbl = "定期健診ドック" if f_item["doc_type"] == "ANNUAL_CHECKUP" else "精密画像検査"
            st.write(f"{doc_lbl}")
            st.caption(f_item["clinic_name"])

        with c5:
            v_cnt = f_item.get("vital_count", 0)
            q_cnt = f_item.get("qualitative_count", 0)
            i_cnt = f_item.get("imaging_count", 0)
            st.write(f"生化学: {v_cnt} | 定性: {q_cnt} | 画像: {i_cnt}")

        with c6:
            st.caption(f_item["registered_at"][:16])

        st.divider()

    # 選択削除アクション（Popover による安全な二段確認）
    if selected_ids:
        with st.container(border=True):
            st.warning(f":material/warning: {len(selected_ids)} 件のファイルが選択されています。")
            st.caption(
                "削除を実行すると、原本ファイルおよび紐付く全検査データ（生化学値・定性所見・画像記録）が完全に削除され、カルテ元帳が最新残存状態へ再集約されます。"
            )
            with st.popover("選択ファイルを完全削除", icon=":material/delete:"):
                st.error("【注意】この操作は取り消せません。直前に自動安全バックアップが生成されます。")
                if st.button("完全削除を実行する", type="primary", icon=":material/delete_forever:", width="stretch"):
                    with st.spinner("自動安全バックアップを作成し、カスケード削除と元帳再同期を実行中..."):
                        run_backup(app_name="health_cmms_before_delete")
                        res = delete_registered_files_cascade(selected_ids)
                        st.cache_data.clear()
                    st.session_state["file_deletion_success_msg"] = (
                        f"ファイル {res['files']} 件および紐付く全検査データ"
                        f"（生化学: {res['vital_metrics']}件, 定性: {res['qualitative_items']}件, "
                        f"画像: {res['imaging_events']}件）を完全に削除し、カルテ元帳を再同期しました。"
                    )
                    st.rerun()
