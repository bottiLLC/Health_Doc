from __future__ import annotations

import tempfile
from pathlib import Path

from src.database import fetch_all_qualitative_items
from src.seed_data import load_seed_data


def test_load_seed_data_execution() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db = Path(tmp_dir) / "test_seed.db"
        counts = load_seed_data(target_path=test_db)

        assert counts["vital_metrics_count"] == 79
        assert counts["qualitative_items_count"] == 103
        assert counts["imaging_events_count"] == 7

        # 聴力や眼底の個別所見が正しく入っているか検証
        hearing = fetch_all_qualitative_items(category="聴力", exam_date="2026-04-22", target_path=test_db)
        assert len(hearing) >= 4  # 4周波数 + 科判定
        findings = [h["finding"] for h in hearing]
        assert "所見なし" in findings

        # 眼底
        fundus = fetch_all_qualitative_items(category="眼底", exam_date="2026-04-22", target_path=test_db)
        item_names = [f["item_name"] for f in fundus]
        assert "Scheie分類" in item_names
        assert "改変Davis" in item_names

        # 総合判定
        summaries = fetch_all_qualitative_items(is_summary=True, target_path=test_db)
        assert len(summaries) >= 20

        # 5大管理項目の完全生成を検証
        from src.database import fetch_managed_timeline_summary

        managed = fetch_managed_timeline_summary(target_path=test_db)
        assert len(managed) == 5
        assert [m.modality for m in managed] == [
            "人間ドック(胃カメラ、腹部超音波を含む)",
            "脳MRI/MRA",
            "大腸カメラ",
            "DWIBS",
            "心臓CT",
        ]
