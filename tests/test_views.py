from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from src.database import init_db, insert_qualitative_items, insert_vital_metrics
from src.models import QualitativeCheckupItem, VitalMetricItem
from src.views.import_jig import render_import_jig_view
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


def test_import_jig_view_session_state_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session_state: dict[str, object] = {"registration_success_msg": "登録完了テスト"}
    mock_st = MagicMock()
    mock_st.session_state = fake_session_state
    mock_st.file_uploader.return_value = None

    monkeypatch.setattr("src.views.import_jig.st", mock_st)
    monkeypatch.setattr("src.views.import_jig.get_gemini_api_key", lambda: "dummy_key")

    render_import_jig_view()

    mock_st.success.assert_any_call("登録完了テスト")
    mock_st.success.assert_any_call("✅ Gemini API キーは設定済みです（PDF自動解析利用可能）")
    assert "registration_success_msg" not in fake_session_state
    assert fake_session_state["uploader_key"] == 0
    assert fake_session_state["uploaded_file_hash"] is None


def test_dashboard_view_renders_5_managed_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """5大管理項目および受診開始待機ステータスを含むダッシュボードが正常に描画されることを検証。"""
    mock_st = MagicMock()
    mock_st.columns.return_value = [MagicMock() for _ in range(5)]
    mock_st.radio.return_value = "5大管理項目の最新受診予定のみ表示（推奨）"
    monkeypatch.setattr("src.views.dashboard.st", mock_st)

    from src.models import ManagedTimelineEntry

    mock_timeline = [
        ManagedTimelineEntry(
            modality="人間ドック(胃カメラ、腹部超音波を含む)",
            target_region="全身",
            last_exam_date="2026-04-22",
            dynamic_next_due="2027-04-22",
            status_flag="CLEAR",
            days_remaining=180,
            alert_category="半年以内に受診推奨",
        ),
        ManagedTimelineEntry(
            modality="脳MRI/MRA",
            target_region="脳",
            last_exam_date="2026-04-22",
            dynamic_next_due="2031-04-22",
            status_flag="CLEAR",
            days_remaining=1800,
            alert_category="受診間隔内 (順調)",
        ),
        ManagedTimelineEntry(
            modality="大腸カメラ",
            target_region="全大腸",
            last_exam_date="2026-09-16",
            dynamic_next_due="2031-09-16",
            status_flag="CLEAR",
            days_remaining=1800,
            alert_category="受診間隔内 (順調)",
        ),
        ManagedTimelineEntry(
            modality="DWIBS",
            target_region="全身",
            last_exam_date="2026-05-02",
            dynamic_next_due="2028-05-02",
            status_flag="CLEAR",
            days_remaining=550,
            alert_category="受診間隔内 (順調)",
        ),
        ManagedTimelineEntry(
            modality="心臓CT",
            target_region="心臓",
            last_exam_date=None,
            dynamic_next_due="2028-04-01",
            status_flag="CLEAR",
            days_remaining=520,
            alert_category="受診開始待機",
        ),
    ]
    monkeypatch.setattr("src.views.dashboard._load_dashboard_data", lambda: (mock_timeline, [], []))

    from src.views.dashboard import render_dashboard_view

    render_dashboard_view()

    mock_st.subheader.assert_any_call("総合健康ダッシュボード")
    mock_st.altair_chart.assert_called_once()
    assert mock_st.metric.call_count == 5
