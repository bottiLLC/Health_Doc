from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.database import (
    fetch_all_qualitative_items,
    fetch_all_vital_metrics,
    fetch_distinct_metric_categories,
)


def _format_grade_badge(grade: str | None) -> str:
    """判定記号に視覚的ステータスアイコンを付与。"""
    if not grade:
        return "-"
    g = grade.strip().upper()
    if g == "A":
        return f"{grade} 🟢"
    if g == "B":
        return f"{grade} 🔵"
    if g.startswith("C"):
        return f"{grade} 🟡"
    if "D" in g:
        return f"{grade} 🟠"
    if g == "E":
        return f"{grade} 🔴"
    return grade


def render_vital_trends_view() -> None:
    """View 2: 年次血液・健康診断トレンドグラフ & 定性カルテ。"""
    st.subheader("年次血液・健康診断トレンドグラフ & 定性カルテ")
    st.caption("血液・尿・肺機能・身体計測の経年数値推移および聴力・眼底・総合判定の完全トラッキング")

    tab_numeric, tab_qualitative = st.tabs(["📈 数値トレンド推移", "📋 定性検査・総合判定カルテ"])

    # =========================================================
    # タブ 1: 数値トレンド推移（大分類　小分類 併記対応）
    # =========================================================
    with tab_numeric:
        metric_pairs = fetch_distinct_metric_categories()
        if not metric_pairs:
            st.info(
                "健康診断データがありません。「検査結果の取り込み・登録」タブから健康診断データを登録してください。"
            )
        else:
            # 主要項目の優先ソート
            priority_pairs = [
                ("肝機能", "ALT"),
                ("糖代謝", "HbA1c"),
                ("身体計測", "体重"),
                ("脂質", "LDLコレステロール"),
                ("肝機能", "AST"),
                ("肝機能", "γ-GTP"),
                ("身体計測", "腹囲"),
                ("糖代謝", "空腹時血糖"),
                ("脂質", "中性脂肪"),
                ("肺機能", "1秒量"),
                ("肺機能", "1秒率"),
                ("肺機能", "肺活量"),
                ("腎機能", "クレアチニン"),
                ("痛風", "尿酸"),
            ]
            sorted_pairs = [p for p in priority_pairs if p in metric_pairs] + [
                p for p in metric_pairs if p not in priority_pairs
            ]

            selected_pair = st.selectbox(
                "検査項目を選択（大分類　小分類）",
                options=sorted_pairs,
                index=0,
                format_func=lambda x: f"{x[0]}　{x[1]}",
                help="推移を確認する検査項目を選択してください。大分類と小分類を併記しています。",
            )

            selected_category, selected_metric = selected_pair
            records = fetch_all_vital_metrics(category=selected_category, metric_name=selected_metric)

            if not records:
                st.warning(f"項目 '{selected_category}　{selected_metric}' のデータが見つかりません。")
            else:
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
                        label=f"{selected_category}　{selected_metric} 最新値 ({latest_date_str})",
                        value=f"{latest_val} {unit_str}",
                        delta=f"{latest_val - float(df.iloc[-2]['val']):.1f} {unit_str}" if len(df) > 1 else None,
                        delta_color="inverse" if is_inverse else "normal",
                    )
                with col2:
                    ref_min = latest_row["ref_min"]
                    ref_max = latest_row["ref_max"]
                    ref_display = (
                        f"{ref_min if ref_min is not None else '-'} 〜 {ref_max if ref_max is not None else '-'}"
                    )
                    st.metric(label="基準値範囲", value=f"{ref_display} {unit_str}")
                with col3:
                    grade_val = latest_row["grade"] or "A"
                    st.metric(label="直近判定グレード", value=_format_grade_badge(str(grade_val)))

                st.divider()

                # 2. 推移グラフ（Altair）
                chart_base = alt.Chart(df).encode(
                    x=alt.X("exam_date:T", title="検査年月日", axis=alt.Axis(format="%Y-%m-%d")),
                )

                line = chart_base.mark_line(point=True, color="#1f77b4", size=3).encode(
                    y=alt.Y(
                        "val:Q",
                        title=f"{selected_category}　{selected_metric} ({unit_str})",
                        scale=alt.Scale(zero=False),
                    ),
                    tooltip=[
                        alt.Tooltip("exam_date:T", title="検査日", format="%Y-%m-%d"),
                        alt.Tooltip("category:N", title="大分類"),
                        alt.Tooltip("metric_name:N", title="小分類"),
                        alt.Tooltip("val:Q", title="測定値"),
                        alt.Tooltip("unit:N", title="単位"),
                        alt.Tooltip("grade:N", title="判定"),
                    ],
                )

                layers = [line]

                # 基準上限ライン
                if ref_max is not None and not pd.isna(ref_max):
                    max_rule = (
                        alt.Chart(pd.DataFrame({"ref_max": [float(ref_max)]}))
                        .mark_rule(color="#FF4B4B", strokeDash=[4, 4], size=2)
                        .encode(y="ref_max:Q")
                    )
                    layers.append(max_rule)

                # 基準下限ライン
                if ref_min is not None and not pd.isna(ref_min):
                    min_rule = (
                        alt.Chart(pd.DataFrame({"ref_min": [float(ref_min)]}))
                        .mark_rule(color="#FFAA00", strokeDash=[4, 4], size=2)
                        .encode(y="ref_min:Q")
                    )
                    layers.append(min_rule)

                final_chart = alt.layer(*layers).properties(height=360)
                st.altair_chart(final_chart, use_container_width=True)

                # 3. 履歴テーブル
                st.subheader("経年検査データ一覧")
                display_df = df[
                    ["exam_date", "category", "metric_name", "val", "unit", "grade", "ref_min", "ref_max"]
                ].copy()
                display_df["exam_date"] = display_df["exam_date"].dt.strftime("%Y-%m-%d")
                display_df = display_df.rename(
                    columns={
                        "exam_date": "検査日",
                        "category": "大分類",
                        "metric_name": "小分類",
                        "val": "測定値",
                        "unit": "単位",
                        "grade": "判定",
                        "ref_min": "基準下限",
                        "ref_max": "基準上限",
                    }
                )
                st.dataframe(display_df, use_container_width=True, hide_index=True)

    # =========================================================
    # タブ 2: 定性検査・総合判定カルテ（聴力、眼底、尿定性、便潜血、各科判定）
    # =========================================================
    with tab_qualitative:
        st.markdown("#### 各科判定一覧（経年マトリクス）")
        st.caption("人間ドック結果報告書に記載された各科目判定（A〜E）の年次推移一覧")

        summary_records = fetch_all_qualitative_items(is_summary=True)
        if not summary_records:
            st.info("定性検査・各科判定データが登録されていません。")
        else:
            sum_df = pd.DataFrame(summary_records)
            # 各年・各科目の判定ピボット表を作成
            dates = sorted(sum_df["exam_date"].unique())
            pivot_data: dict[str, dict[str, str]] = {}

            # 科目の標準順序
            cat_order = [
                "総合判定",
                "診察",
                "身体計測",
                "血圧",
                "視力",
                "眼底",
                "眼圧",
                "聴力",
                "血液学検査",
                "脂質",
                "糖代謝",
                "肝機能",
                "肝炎",
                "腎機能",
                "痛風",
                "尿検査",
                "免疫・炎症反応",
                "胸部",
                "肺機能",
                "上部消化管",
                "便潜血",
                "腹部",
                "心臓",
                "頭部",
            ]

            all_cats = list(
                dict.fromkeys(
                    [c for c in cat_order if c in sum_df["category"].values] + list(sum_df["category"].unique())
                )
            )

            for cat in all_cats:
                pivot_data[cat] = {}
                for d in dates:
                    row = sum_df[(sum_df["category"] == cat) & (sum_df["exam_date"] == d)]
                    if not row.empty:
                        g = str(row.iloc[0]["grade"] or "-")
                        pivot_data[cat][d] = _format_grade_badge(g)
                    else:
                        pivot_data[cat][d] = "-"

            matrix_rows = []
            for cat, date_vals in pivot_data.items():
                row_dict: dict[str, str] = {"検査科目": cat}
                row_dict.update(date_vals)
                matrix_rows.append(row_dict)

            matrix_df = pd.DataFrame(matrix_rows)
            st.dataframe(matrix_df, use_container_width=True, hide_index=True)

        st.divider()

        # 個別定性所見詳細一覧
        st.markdown("#### 聴力・眼底・定性検査の個別所見カルテ")
        st.caption("周波数別聴力、Scheie/改変Davis眼底分類、尿定性、便潜血、内科診察などの詳細所見記録")

        detail_records = fetch_all_qualitative_items(is_summary=False)
        if not detail_records:
            st.info("個別所見データがありません。")
        else:
            detail_df = pd.DataFrame(detail_records)
            categories = ["全部門表示"] + sorted(detail_df["category"].unique())

            col_filter, _ = st.columns([2, 2])
            with col_filter:
                filter_cat = st.selectbox("部門で絞り込み", options=categories, index=0)

            filtered_df = detail_df if filter_cat == "全部門表示" else detail_df[detail_df["category"] == filter_cat]

            view_df = filtered_df[["exam_date", "category", "item_name", "finding", "grade", "details"]].copy()
            view_df = view_df.rename(
                columns={
                    "exam_date": "検査日",
                    "category": "大分類",
                    "item_name": "検査項目",
                    "finding": "所見・定性結果",
                    "grade": "判定",
                    "details": "補足詳細",
                }
            )
            view_df["判定"] = view_df["判定"].apply(_format_grade_badge)
            st.dataframe(view_df, use_container_width=True, hide_index=True)
