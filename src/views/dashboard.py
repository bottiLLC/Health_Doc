from __future__ import annotations

from datetime import date, datetime
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from src.database import (
    fetch_all_imaging_events,
    fetch_managed_timeline_summary,
    fetch_organ_ledger,
)
from src.models import MANAGED_INSPECTION_ITEMS, ManagedTimelineEntry


@st.cache_data
def _load_dashboard_data() -> tuple[list[ManagedTimelineEntry], list[dict[str, Any]], list[dict[str, Any]]]:
    """ダッシュボード用検査イベント（5大管理項目最新集約および全件履歴）と部位別元帳データをキャッシュ取得。"""
    return (
        fetch_managed_timeline_summary(),
        fetch_all_imaging_events(),
        fetch_organ_ledger(),
    )


@st.fragment
def _render_timeline_fragment(
    latest_timeline_data: list[dict[str, Any]],
    all_events: list[dict[str, Any]],
    today: date,
) -> None:
    """タイムライン表示切替およびチャート・テーブルの部分再描画コンポーネント。"""
    view_options = ["5大管理項目の最新受診予定のみ表示（推奨）", "過去の全受診履歴タイムラインを表示"]
    selected_mode = st.segmented_control(
        "表示対象",
        options=view_options,
        default=view_options[0],
    )
    view_mode = selected_mode if selected_mode is not None else view_options[0]

    if view_mode == "5大管理項目の最新受診予定のみ表示（推奨）":
        active_display_data = latest_timeline_data
    else:
        all_timeline_data: list[dict[str, Any]] = []
        for ev in all_events:
            due_dt = datetime.strptime(str(ev["dynamic_next_due"]), "%Y-%m-%d").date()
            days_rem = (due_dt - today).days
            if days_rem < 0:
                s_cat = "受診期限超過"
            elif days_rem <= 180:
                s_cat = "半年以内に受診推奨"
            else:
                s_cat = "受診間隔内 (順調)"

            all_timeline_data.append(
                {
                    "検査種別": str(ev["modality"]),
                    "検査部位": str(ev["target_region"]),
                    "受診医療機関": str(ev["clinic_name"]),
                    "前回検査日": str(ev["exam_date"]),
                    "次回推奨受診日": str(ev["dynamic_next_due"]),
                    "判定ステータス": str(ev["status_flag"]),
                    "次回までの日数": days_rem,
                    "状態区分": s_cat,
                    "主要所見": str(ev.get("primary_findings", "")),
                    "_chart_start": str(ev["exam_date"]),
                }
            )
        active_display_data = all_timeline_data

    if active_display_data:
        df_time = pd.DataFrame(active_display_data)
        display_columns = [col for col in df_time.columns if not col.startswith("_")]
        st.dataframe(
            df_time[display_columns],
            width="stretch",
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
        y_sort = list(MANAGED_INSPECTION_ITEMS) if view_mode.startswith("5大管理項目") else "-x"
        chart = (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                y=alt.Y("検査種別:N", title="検査種別", sort=y_sort),
                x=alt.X("_chart_start:T", title="受診間隔 (前回検査日/起点 → 次回推奨受診日)"),
                x2="次回推奨受診日:T",
                color=alt.Color(
                    "状態区分:N",
                    scale=alt.Scale(
                        domain=["受診期限超過", "半年以内に受診推奨", "受診間隔内 (順調)", "受診開始待機"],
                        range=["#FF4B4B", "#FFAA00", "#00AA66", "#4B9CD3"],
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
                    "主要所見",
                ],
            )
            .properties(height=max(180, len(chart_df) * 35))
        )
        st.altair_chart(chart, width="stretch")


def render_dashboard_view() -> None:
    """View 1: 総合健康ダッシュボード（受診ステータス & タイムライン）。"""
    st.subheader("総合健康ダッシュボード")
    st.caption("厳格な5大管理項目に基づく直近検査日（前回検査日）と次回推奨受診時期の一覧")

    managed_timeline, all_events, ledger = _load_dashboard_data()

    if not managed_timeline and not all_events and not ledger:
        st.info("検査データがまだ登録されていません。「検査結果の取り込み・登録」タブからPDFを登録してください。")
        return

    today = date.today()

    # 1. アラート集計（5大管理項目を基準に集計）
    critical_count = sum(1 for item in managed_timeline if item.alert_category == "受診期限超過")
    upcoming_count = sum(1 for item in managed_timeline if item.alert_category == "半年以内に受診推奨")
    cruising_count = sum(1 for item in managed_timeline if item.alert_category == "受診間隔内 (順調)")
    waiting_count = sum(1 for item in managed_timeline if item.alert_category == "受診開始待機")

    latest_timeline_data: list[dict[str, Any]] = []
    for item in managed_timeline:
        chart_start = item.last_exam_date if item.last_exam_date else today.strftime("%Y-%m-%d")
        latest_timeline_data.append(
            {
                "検査種別": item.modality,
                "検査部位": item.target_region,
                "受診医療機関": item.clinic_name,
                "前回検査日": item.last_exam_date or "未受診",
                "次回推奨受診日": item.dynamic_next_due,
                "判定ステータス": item.status_flag,
                "次回までの日数": item.days_remaining,
                "状態区分": item.alert_category,
                "主要所見": item.primary_findings,
                "_chart_start": chart_start,
            }
        )

    # アラート指標カード (5大管理項目)
    with st.container(border=True):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric(
                label="管理対象検査",
                value=f"{len(MANAGED_INSPECTION_ITEMS)} 種別",
                help=f"登録済み全検査レコード数: {len(all_events)} 件",
                border=True,
            )
        with col2:
            st.metric(label="受診期限超過", value=f"{critical_count} 件", border=True)
        with col3:
            st.metric(label="半年以内に受診推奨", value=f"{upcoming_count} 件", border=True)
        with col4:
            st.metric(label="受診間隔内 (順調)", value=f"{cruising_count} 件", border=True)
        with col5:
            st.metric(label="受診開始待機 (2028年〜)", value=f"{waiting_count} 件", border=True)

    st.divider()

    # 2. 次回検査スケジュール・タイムライン
    st.subheader("次回検査スケジュール・タイムライン")
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

        _ctx = get_script_run_ctx()
    except Exception:
        _ctx = None

    if _ctx is None and hasattr(_render_timeline_fragment, "__wrapped__"):
        _render_timeline_fragment.__wrapped__(latest_timeline_data, all_events, today)
    else:
        _render_timeline_fragment(latest_timeline_data, all_events, today)

    st.divider()

    # 3. 部位別検査記録・健康カルテ (Table C)
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
        st.dataframe(ledger_df, width="stretch", hide_index=True)
    else:
        st.info("部位別の検査記録はありません。")
