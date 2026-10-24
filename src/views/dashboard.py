from __future__ import annotations

from datetime import date, datetime

import altair as alt
import pandas as pd
import streamlit as st

from src.database import fetch_all_imaging_events, fetch_organ_ledger


def render_dashboard_view() -> None:
    """View 1: 総合保全ダッシュボード（保全ステータス & タイムライン）。"""
    st.subheader("総合保全ダッシュボード")
    st.caption("非破壊検査・画像診断に基づく動的リコール周期および部位別健全性ステータス")

    events = fetch_all_imaging_events()
    ledger = fetch_organ_ledger()

    if not events and not ledger:
        st.info("検査データがまだ登録されていません。「データ投入治具」タブからPDFをインポートしてください。")
        return

    today = date.today()

    # 1. アラート集計
    critical_count = 0
    upcoming_count = 0
    cruising_count = 0

    timeline_data = []
    for ev in events:
        due_dt = datetime.strptime(ev["dynamic_next_due"], "%Y-%m-%d").date()
        days_rem = (due_dt - today).days

        if days_rem < 0:
            status_cat = "期限超過 (Overdue)"
            critical_count += 1
        elif days_rem <= 180:
            status_cat = "半年以内 (Upcoming)"
            upcoming_count += 1
        else:
            status_cat = "巡航中 (Cruising)"
            cruising_count += 1

        timeline_data.append({
            "モダリティ": ev["modality"],
            "部位": ev["target_region"],
            "受診施設": ev["clinic_name"],
            "前回検査日": ev["exam_date"],
            "次回推奨日": ev["dynamic_next_due"],
            "ステータス": ev["status_flag"],
            "残り日数": days_rem,
            "状態区分": status_cat,
        })

    # アラート指標カード
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("登録検査件数", f"{len(events)} 件")
    with col2:
        st.metric("期限超過 (Overdue)", f"{critical_count} 件")
    with col3:
        st.metric("半年以内 (Upcoming)", f"{upcoming_count} 件")
    with col4:
        st.metric("巡航健全中 (Cruising)", f"{cruising_count} 件")

    st.divider()

    # 2. 部位別ステータス元帳 (Table C)
    st.subheader("部位別ステータス元帳 (Organ Status Ledger)")
    if ledger:
        ledger_df = pd.DataFrame(ledger)
        ledger_df = ledger_df.rename(
            columns={
                "organ": "対象部位",
                "last_exam_date": "直近検査日",
                "current_status": "直近ステータス・所見",
                "next_action_due": "次回推奨期日",
            }
        )
        st.dataframe(ledger_df, use_container_width=True, hide_index=True)
    else:
        st.info("部位元帳エントリはありません。")

    st.divider()

    # 3. インスペクション・タイムライン
    st.subheader("インスペクション・タイムライン")
    if timeline_data:
        df_time = pd.DataFrame(timeline_data)
        st.dataframe(
            df_time,
            use_container_width=True,
            hide_index=True,
            column_config={
                "残り日数": st.column_config.NumberColumn(
                    "次回まで残り日数",
                    help="本日から次回推奨日までの日数",
                    format="%d 日",
                ),
            },
        )

        # Altair タイムライン棒グラフ
        chart_df = df_time.copy()
        chart = (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                y=alt.Y("モダリティ:N", title="モダリティ", sort="-x"),
                x=alt.X("前回検査日:T", title="検査スパン (前回検査日 → 次回推奨日)"),
                x2="次回推奨日:T",
                color=alt.Color(
                    "状態区分:N",
                    scale=alt.Scale(
                        domain=["期限超過 (Overdue)", "半年以内 (Upcoming)", "巡航中 (Cruising)"],
                        range=["#FF4B4B", "#FFAA00", "#00AA66"],
                    ),
                    legend=alt.Legend(title="ステータス"),
                ),
                tooltip=[
                    "モダリティ",
                    "部位",
                    "受診施設",
                    "前回検査日",
                    "次回推奨日",
                    "残り日数",
                ],
            )
            .properties(height=240)
        )
        st.altair_chart(chart, use_container_width=True)
