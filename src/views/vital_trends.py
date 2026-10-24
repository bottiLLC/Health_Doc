from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.database import fetch_all_vital_metrics, fetch_distinct_metric_names


def render_vital_trends_view() -> None:
    """View 2: 年次生化学トレンド（管理図）。"""
    st.subheader("年次生化学トレンド管理図")
    st.caption("血液・尿・身体計測の経年変化と基準値公差バンドによる予防保全トラッキング")

    metrics_list = fetch_distinct_metric_names()
    if not metrics_list:
        st.info("生化学メトリクスデータがありません。「データ投入治具」から健康診断データをインポートしてください。")
        return

    # 主要項目の優先ソート
    priority_metrics = ["ALT", "HbA1c", "体重", "LDLコレステロール", "AST", "γ-GTP", "腹囲", "空腹時血糖", "中性脂肪"]
    sorted_metrics = [m for m in priority_metrics if m in metrics_list] + [
        m for m in metrics_list if m not in priority_metrics
    ]

    selected_metric = st.selectbox(
        "トラッキング対象項目を選択",
        options=sorted_metrics,
        index=0,
        help="表示する検査項目を選択してください。クランプ辞書により名称統一済みです。",
    )

    records = fetch_all_vital_metrics(metric_name=selected_metric)
    if not records:
        st.warning(f"項目 '{selected_metric}' のデータが見つかりません。")
        return

    df = pd.DataFrame(records)
    df["exam_date"] = pd.to_datetime(df["exam_date"])
    df = df.sort_values("exam_date")

    # 1. サマリー指標カード
    latest_row = df.iloc[-1]
    unit_str = str(latest_row["unit"])
    latest_val = float(latest_row["val"])
    latest_date_str = latest_row["exam_date"].strftime("%Y-%m-%d")

    is_inverse = (
        "コレステロール" in selected_metric or "ALT" in selected_metric or "HbA1c" in selected_metric
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label=f"最新測定値 ({latest_date_str})",
            value=f"{latest_val} {unit_str}",
            delta=f"{latest_val - float(df.iloc[-2]['val']):.1f} {unit_str}" if len(df) > 1 else None,
            delta_color="inverse" if is_inverse else "normal",
        )
    with col2:
        ref_min = latest_row["ref_min"]
        ref_max = latest_row["ref_max"]
        ref_display = f"{ref_min if ref_min is not None else '-'} 〜 {ref_max if ref_max is not None else '-'}"
        st.metric(label="基準公差範囲", value=f"{ref_display} {unit_str}")
    with col3:
        st.metric(label="直近判定グレード", value=str(latest_row["grade"] or "A"))

    st.divider()

    # 2. 管理図グラフ（Altair）
    chart_base = alt.Chart(df).encode(
        x=alt.X("exam_date:T", title="検査年月日", axis=alt.Axis(format="%Y-%m-%d")),
    )

    line = chart_base.mark_line(point=True, color="#1f77b4", size=3).encode(
        y=alt.Y("val:Q", title=f"測定値 ({unit_str})", scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("exam_date:T", title="検査日", format="%Y-%m-%d"),
            alt.Tooltip("val:Q", title="測定値"),
            alt.Tooltip("grade:N", title="判定"),
            alt.Tooltip("category:N", title="区分"),
        ],
    )

    layers = [line]

    # 基準上限ライン
    if ref_max is not None and not pd.isna(ref_max):
        max_rule = alt.Chart(pd.DataFrame({"ref_max": [float(ref_max)]})).mark_rule(
            color="#FF4B4B", strokeDash=[4, 4], size=2
        ).encode(y="ref_max:Q")
        layers.append(max_rule)

    # 基準下限ライン
    if ref_min is not None and not pd.isna(ref_min):
        min_rule = alt.Chart(pd.DataFrame({"ref_min": [float(ref_min)]})).mark_rule(
            color="#FFAA00", strokeDash=[4, 4], size=2
        ).encode(y="ref_min:Q")
        layers.append(min_rule)

    final_chart = alt.layer(*layers).properties(height=360)
    st.altair_chart(final_chart, use_container_width=True)

    # 3. 履歴テーブル
    st.subheader("経年測定履歴一覧")
    display_df = df[["exam_date", "val", "unit", "grade", "ref_min", "ref_max", "category"]].copy()
    display_df["exam_date"] = display_df["exam_date"].dt.strftime("%Y-%m-%d")
    display_df = display_df.rename(
        columns={
            "exam_date": "検査日",
            "val": "測定値",
            "unit": "単位",
            "grade": "判定",
            "ref_min": "基準下限",
            "ref_max": "基準上限",
            "category": "カテゴリ",
        }
    )
    st.dataframe(display_df, use_container_width=True, hide_index=True)
