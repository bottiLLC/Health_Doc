from __future__ import annotations

from datetime import date, datetime
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from src.database import fetch_all_imaging_events, fetch_organ_ledger


@st.cache_data
def _load_dashboard_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """ダッシュボード用検査イベントおよび部位別元帳データをキャッシュ取得。"""
    return fetch_all_imaging_events(), fetch_organ_ledger()


def render_dashboard_view() -> None:
    """View 1: 総合健康ダッシュボード（受診ステータス & タイムライン）。"""
    st.subheader("総合健康ダッシュボード")
    st.caption("画像診断・精密検査結果に基づく次回推奨受診時期および部位別の健康状態一覧")

    events, ledger = _load_dashboard_data()

    if not events and not ledger:
        st.info("検査データがまだ登録されていません。「検査結果の取り込み・登録」タブからPDFを登録してください。")
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
            status_cat = "受診期限超過"
            critical_count += 1
        elif days_rem <= 180:
            status_cat = "半年以内に受診推奨"
            upcoming_count += 1
        else:
            status_cat = "受診間隔内 (順調)"
            cruising_count += 1

        timeline_data.append(
            {
                "検査種別": ev["modality"],
                "検査部位": ev["target_region"],
                "受診医療機関": ev["clinic_name"],
                "前回検査日": ev["exam_date"],
                "次回推奨受診日": ev["dynamic_next_due"],
                "判定ステータス": ev["status_flag"],
                "次回までの日数": days_rem,
                "状態区分": status_cat,
            }
        )

    # アラート指標カード
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("登録済み検査", f"{len(events)} 件")
    with col2:
        st.metric("受診期限超過", f"{critical_count} 件")
    with col3:
        st.metric("半年以内に受診推奨", f"{upcoming_count} 件")
    with col4:
        st.metric("受診間隔内 (順調)", f"{cruising_count} 件")

    st.divider()

    # 2. 部位別健康カルテ (Table C)
    st.subheader("部位別検査記録・健康カルテ")
    if ledger:
        ledger_df = pd.DataFrame(ledger)
        ledger_df = ledger_df.rename(
            columns={
                "organ": "対象部位",
                "last_exam_date": "直近検査日",
                "current_status": "直近の検査所見・状態",
                "next_action_due": "次回受診推奨日",
            }
        )
        st.dataframe(ledger_df, use_container_width=True, hide_index=True)
    else:
        st.info("部位別の検査記録はありません。")

    st.divider()

    # 3. 次回検査スケジュール・タイムライン
    st.subheader("次回検査スケジュール・タイムライン")
    if timeline_data:
        df_time = pd.DataFrame(timeline_data)
        st.dataframe(
            df_time,
            use_container_width=True,
            hide_index=True,
            column_config={
                "次回までの日数": st.column_config.NumberColumn(
                    "次回推奨日までの日数",
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
                y=alt.Y("検査種別:N", title="検査種別", sort="-x"),
                x=alt.X("前回検査日:T", title="受診間隔 (前回検査日 → 次回推奨受診日)"),
                x2="次回推奨受診日:T",
                color=alt.Color(
                    "状態区分:N",
                    scale=alt.Scale(
                        domain=["受診期限超過", "半年以内に受診推奨", "受診間隔内 (順調)"],
                        range=["#FF4B4B", "#FFAA00", "#00AA66"],
                    ),
                    legend=alt.Legend(title="状態区分"),
                ),
                tooltip=[
                    "検査種別",
                    "検査部位",
                    "受診医療機関",
                    "前回検査日",
                    "次回推奨受診日",
                    "次回までの日数",
                ],
            )
            .properties(height=240)
        )
        st.altair_chart(chart, use_container_width=True)
