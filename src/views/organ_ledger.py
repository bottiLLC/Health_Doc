from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.database import fetch_all_imaging_events


def render_organ_ledger_view() -> None:
    """View 3: 部位別検査カルテ & 検査PDF。"""
    st.subheader("部位別検査カルテ & 検査PDF")
    st.caption("精密画像・内視鏡検査の受診履歴（所見、判定、医師コメント）および原本PDF")

    events = fetch_all_imaging_events()
    if not events:
        st.info("画像検査データがありません。「検査結果の取り込み・登録」タブからPDFを登録してください。")
        return

    # 部位リストの取得
    regions = sorted({ev["target_region"] for ev in events if ev.get("target_region")})
    selected_region = st.selectbox(
        "対象部位で絞り込み",
        options=["全部位表示"] + regions,
        index=0,
    )

    filtered_events = [ev for ev in events if selected_region == "全部位表示" or ev["target_region"] == selected_region]

    st.write(f"該当レコード: {len(filtered_events)} 件")
    st.divider()

    for idx, ev in enumerate(filtered_events):
        with st.container():
            col_header1, col_header2 = st.columns([3, 1])
            with col_header1:
                st.markdown(f"### {ev['modality']} （部位: {ev['target_region']}）")
                st.caption(f"受診日: {ev['exam_date']} | 医療機関: {ev['clinic_name']}")
            with col_header2:
                flag = ev["status_flag"]
                status_color = "🟢" if flag == "CLEAR" else "🟡" if flag == "BENIGN_STABLE" else "🔴"
                st.metric(label="判定ステータス", value=f"{status_color} {flag}")

            # 所見と医師コメント
            col_body1, col_body2 = st.columns([2, 1])
            with col_body1:
                st.write("**主要所見要約:**")
                st.info(ev["primary_findings"])
                if ev.get("raw_comment"):
                    st.write("**医師コメント / アドバイス:**")
                    st.text(ev["raw_comment"])
            with col_body2:
                st.metric(label="次回受診推奨時期", value=ev["dynamic_next_due"])
                if ev.get("pdf_page"):
                    st.caption(f"📄 元PDF参照ページ: **P.{ev['pdf_page']}**")

                # PDFダウンロード
                pdf_path_str = ev.get("pdf_path")
                if pdf_path_str:
                    pdf_file = Path(pdf_path_str)
                    if pdf_file.exists():
                        with open(pdf_file, "rb") as f:
                            st.download_button(
                                label="📥 検査原本PDFを保存",
                                data=f.read(),
                                file_name=pdf_file.name,
                                mime="application/pdf",
                                key=f"dl_pdf_{idx}_{ev['event_id']}",
                                type="secondary",
                            )
                    else:
                        st.caption(f"PDFパス: {pdf_path_str} (未配置)")

            st.divider()
