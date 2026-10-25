from __future__ import annotations

import tempfile
from pathlib import Path

from src.database import (
    fetch_all_vital_metrics,
    fetch_distinct_metric_categories,
    get_db_connection,
    init_db,
    insert_vital_metrics,
)
from src.models import (
    VitalMetricItem,
    normalize_category_name,
)
from src.views.file_registry import render_file_registry_view


def test_normalize_category_name() -> None:
    """大分類名の表記ゆれ正規化関数のテスト。"""
    # 血液学
    assert normalize_category_name("血液一般") == "血液学"
    assert normalize_category_name("血液学検査") == "血液学"
    assert normalize_category_name("血算") == "血液学"
    assert normalize_category_name("血液") == "血液学"
    assert normalize_category_name("　血液一般　") == "血液学"

    # 肝機能
    assert normalize_category_name("肝機能検査") == "肝機能"
    assert normalize_category_name("肝・胆") == "肝機能"
    assert normalize_category_name("肝・胆・膵") == "肝機能"

    # 糖代謝
    assert normalize_category_name("糖尿病検査") == "糖代謝"
    assert normalize_category_name("糖代謝検査") == "糖代謝"
    assert normalize_category_name("糖質") == "糖代謝"

    # 脂質
    assert normalize_category_name("脂質代謝") == "脂質"
    assert normalize_category_name("脂質検査") == "脂質"

    # 腎機能
    assert normalize_category_name("腎機能検査") == "腎機能"
    assert normalize_category_name("腎・尿酸") == "腎機能"

    # 身体計測・血圧・呼吸
    assert normalize_category_name("身体測定") == "身体計測"
    assert normalize_category_name("血圧測定") == "血圧"
    assert normalize_category_name("呼吸機能") == "肺機能"

    # 未登録カテゴリ
    assert normalize_category_name("特殊免疫マーカー") == "特殊免疫マーカー"


def test_vital_metrics_category_normalization_on_insert() -> None:
    """insert_vital_metrics時に大分類が自動正規化されることのテスト。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_norm.db"
        init_db(db_path)

        # 施設A: 「血液一般」で登録
        items_a = [
            VitalMetricItem(category="血液一般", metric_name="白血球数", val=4500.0, unit="/uL"),
        ]
        insert_vital_metrics(items_a, "2024-05-01", target_path=db_path)

        # 施設B: 「血液学検査」で登録
        items_b = [
            VitalMetricItem(category="血液学検査", metric_name="白血球数", val=4800.0, unit="/uL"),
        ]
        insert_vital_metrics(items_b, "2025-05-01", target_path=db_path)

        # ユニークカテゴリ・項目名一覧の確認（「血液学」1つに集約されていること）
        distinct_pairs = fetch_distinct_metric_categories(db_path)
        assert len(distinct_pairs) == 1
        assert distinct_pairs[0] == ("血液学", "白血球数")

        # 取得時（2件とも血液学・白血球数として集約取得できること）
        records = fetch_all_vital_metrics(category="血液学", metric_name="白血球数", target_path=db_path)
        assert len(records) == 2
        assert records[0]["category"] == "血液学"
        assert records[0]["exam_date"] == "2024-05-01"
        assert records[1]["category"] == "血液学"
        assert records[1]["exam_date"] == "2025-05-01"


def test_database_category_migration_for_existing_records() -> None:
    """既存DB内の表記ゆれがマイグレーションによって自動標準化されるテスト。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_mig.db"

        # 1. 初期スキーマのみ作成
        init_db(db_path)

        # 2. 手動で正規化前の表記ゆれレコードを直接挿入
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO vital_metrics (exam_date, category, metric_name, val, unit) VALUES (?, ?, ?, ?, ?)",
                ("2023-04-10", "血液一般", "ヘモグロビン", 14.2, "g/dL"),
            )
            cursor.execute(
                "INSERT INTO vital_metrics (exam_date, category, metric_name, val, unit) VALUES (?, ?, ?, ?, ?)",
                ("2023-04-10", "肝・胆", "ALT", 25.0, "U/L"),
            )
            conn.commit()

        # 3. 再度init_dbを呼んでマイグレーションを実行
        init_db(db_path)

        # 4. 正規化されていることを検証
        records = fetch_all_vital_metrics(target_path=db_path)
        assert len(records) == 2
        cat_map = {r["metric_name"]: r["category"] for r in records}
        assert cat_map["ヘモグロビン"] == "血液学"
        assert cat_map["ALT"] == "肝機能"


def test_file_registry_view_renders_without_crash() -> None:
    """新規独立Viewのrender_file_registry_viewが正常に起動すること。"""
    init_db()
    render_file_registry_view()
