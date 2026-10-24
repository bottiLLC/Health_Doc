from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.database import init_db, insert_qualitative_items, insert_vital_metrics
from src.models import QualitativeCheckupItem, VitalMetricItem
from src.views.vital_trends import _format_grade_badge


def test_format_grade_badge() -> None:
    assert _format_grade_badge(None) == "-"
    assert _format_grade_badge("") == "-"
    assert _format_grade_badge("A") == "A 🟢"
    assert _format_grade_badge("B") == "B 🔵"
    assert _format_grade_badge("C") == "C 🟡"
    assert _format_grade_badge("C1") == "C1 🟡"
    assert _format_grade_badge("D1") == "D1 🟠"
    assert _format_grade_badge("D2") == "D2 🟠"
    assert _format_grade_badge("E") == "E 🔴"
    assert _format_grade_badge("UNKNOWN") == "UNKNOWN"


def test_format_grade_badge_edge_cases() -> None:
    assert _format_grade_badge(float("nan")) == "-"
    assert _format_grade_badge(np.nan) == "-"
    assert _format_grade_badge(pd.NA) == "-"
    assert _format_grade_badge("nan") == "-"
    assert _format_grade_badge("NaN") == "-"
    assert _format_grade_badge("None") == "-"
    assert _format_grade_badge("-") == "-"
    assert _format_grade_badge("null") == "-"
    assert _format_grade_badge("   ") == "-"
    assert _format_grade_badge(" A ") == "A 🟢"
    assert _format_grade_badge(1.5) == "1.5"


def test_format_grade_badge_pandas_series_apply() -> None:
    s = pd.Series([None, float("nan"), np.nan, "A", "B", "C1", "D2", "E", "未実施"])
    res = s.apply(_format_grade_badge)
    assert res.tolist() == ["-", "-", "-", "A 🟢", "B 🔵", "C1 🟡", "D2 🟠", "E 🔴", "未実施"]


def test_views_data_integrity() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db = Path(tmp_dir) / "test_views.db"
        init_db(test_db)

        vitals = [
            VitalMetricItem(
                category="肺機能",
                metric_name="1秒量",
                val=4.59,
                unit="L",
                ref_min=None,
                ref_max=None,
                grade="A",
            ),
            VitalMetricItem(
                category="肺機能",
                metric_name="1秒率",
                val=87.8,
                unit="%",
                ref_min=70.0,
                ref_max=None,
                grade="A",
            ),
        ]
        insert_vital_metrics(vitals, "2026-04-22", target_path=test_db)

        qualitatives = [
            QualitativeCheckupItem(
                category="聴力",
                item_name="1000Hz(右)",
                finding="所見なし",
                grade="A",
            ),
            QualitativeCheckupItem(
                category="総合判定",
                item_name="総合判定",
                finding="経過観察",
                grade="C",
                is_category_summary=True,
            ),
        ]
        insert_qualitative_items(qualitatives, "2026-04-22", target_path=test_db)

        from src.database import (
            fetch_all_qualitative_items,
            fetch_all_vital_metrics,
            fetch_distinct_metric_categories,
        )

        pairs = fetch_distinct_metric_categories(target_path=test_db)
        assert ("肺機能", "1秒量") in pairs
        assert ("肺機能", "1秒率") in pairs

        records = fetch_all_vital_metrics(category="肺機能", metric_name="1秒量", target_path=test_db)
        assert len(records) == 1
        assert records[0]["val"] == 4.59

        summaries = fetch_all_qualitative_items(is_summary=True, target_path=test_db)
        assert len(summaries) == 1
        assert summaries[0]["category"] == "総合判定"
