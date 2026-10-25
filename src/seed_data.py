from __future__ import annotations

from pathlib import Path

from src.config import ensure_directories
from src.database import (
    init_db,
    insert_imaging_event,
    insert_qualitative_items,
    insert_vital_metrics,
    rebuild_organ_ledger,
    upsert_organ_ledger,
)
from src.models import (
    ImagingEventPayload,
    QualitativeCheckupItem,
    VitalMetricItem,
)
from src.recall_engine import compute_dynamic_next_due, derive_organ_ledger_update


def load_seed_data(target_path: Path | str | None = None) -> dict[str, int]:
    """実機PDF4種の完全解析データをデータベースへ投入。

    投入対象:
    1. 人間ドック結果報告書 (medock 総合健診クリニック: 2024, 2025, 2026の3年分時系列 + 内包画像検査)
    2. 全身がんドック (医療法人ONE きくち総合診療クリニック: 2026-05-02 DWIBS)
    3. 内視鏡検査結果報告書 (青葉台かなざわ内科・内視鏡クリニック: 2026-09-16 大腸内視鏡)
    4. CT検査結果レポート (新宿三丁目メディカルクリニック: 2026-09-21 胸腹部CT)
    """
    ensure_directories()
    init_db(target_path)

    # -------------------------------------------------------------
    # 1. 人間ドック (medock) 3年分時系列生化学メトリクス
    # -------------------------------------------------------------
    vitals_2026 = [
        VitalMetricItem(
            category="身体計測", metric_name="身長", val=176.2, unit="cm", ref_min=None, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="身体計測", metric_name="体重", val=66.7, unit="kg", ref_min=None, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="身体計測", metric_name="BMI", val=21.5, unit="kg/㎡", ref_min=18.5, ref_max=24.9, grade="A"
        ),
        VitalMetricItem(
            category="身体計測", metric_name="腹囲", val=82.0, unit="cm", ref_min=None, ref_max=85.0, grade="A"
        ),
        VitalMetricItem(
            category="血圧", metric_name="最高血圧", val=88.0, unit="mmHg", ref_min=None, ref_max=130.0, grade="A"
        ),
        VitalMetricItem(
            category="血圧", metric_name="最低血圧", val=59.0, unit="mmHg", ref_min=None, ref_max=85.0, grade="A"
        ),
        VitalMetricItem(
            category="視力", metric_name="視力(右)", val=1.0, unit="", ref_min=1.0, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="視力", metric_name="視力(左)", val=0.9, unit="", ref_min=1.0, ref_max=None, grade="C"
        ),
        VitalMetricItem(
            category="眼圧", metric_name="眼圧(右)", val=14.0, unit="mmHg", ref_min=9.0, ref_max=21.9, grade="A"
        ),
        VitalMetricItem(
            category="眼圧", metric_name="眼圧(左)", val=13.0, unit="mmHg", ref_min=9.0, ref_max=21.9, grade="A"
        ),
        VitalMetricItem(
            category="肺機能", metric_name="肺活量", val=5.23, unit="L", ref_min=None, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="肺機能", metric_name="%肺活量", val=110.8, unit="%", ref_min=80.0, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="肺機能", metric_name="1秒量", val=4.59, unit="L", ref_min=None, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="肺機能", metric_name="1秒率", val=87.8, unit="%", ref_min=70.0, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="血液学",
            metric_name="赤血球数",
            val=439.0,
            unit="10^4/mm3",
            ref_min=400.0,
            ref_max=539.0,
            grade="A",
        ),
        VitalMetricItem(
            category="血液学", metric_name="ヘモグロビン", val=13.7, unit="g/dL", ref_min=13.1, ref_max=16.3, grade="A"
        ),
        VitalMetricItem(
            category="血液学", metric_name="ヘマトクリット", val=43.0, unit="%", ref_min=38.5, ref_max=48.9, grade="A"
        ),
        VitalMetricItem(
            category="血液学", metric_name="白血球数", val=3500.0, unit="/uL", ref_min=3100.0, ref_max=8499.0, grade="A"
        ),
        VitalMetricItem(
            category="血液学", metric_name="血小板数", val=17.3, unit="10^4/mm3", ref_min=14.5, ref_max=32.9, grade="A"
        ),
        VitalMetricItem(
            category="血液学", metric_name="MCV", val=97.9, unit="fL", ref_min=83.0, ref_max=102.9, grade="A"
        ),
        VitalMetricItem(
            category="血液学", metric_name="MCH", val=31.2, unit="pg", ref_min=27.9, ref_max=34.5, grade="A"
        ),
        VitalMetricItem(
            category="血液学", metric_name="MCHC", val=31.9, unit="%", ref_min=31.4, ref_max=35.5, grade="A"
        ),
        VitalMetricItem(
            category="炎症", metric_name="CRP", val=0.005, unit="mg/dL", ref_min=None, ref_max=0.30, grade="A"
        ),
        VitalMetricItem(
            category="脂質",
            metric_name="総コレステロール",
            val=166.0,
            unit="mg/dL",
            ref_min=None,
            ref_max=None,
            grade="A",
        ),
        VitalMetricItem(
            category="脂質",
            metric_name="HDLコレステロール",
            val=60.0,
            unit="mg/dL",
            ref_min=40.0,
            ref_max=None,
            grade="A",
        ),
        VitalMetricItem(
            category="脂質",
            metric_name="LDLコレステロール",
            val=96.0,
            unit="mg/dL",
            ref_min=60.0,
            ref_max=139.0,
            grade="A",
        ),
        VitalMetricItem(
            category="脂質", metric_name="nonHDL-cho", val=106.0, unit="mg/dL", ref_min=90.0, ref_max=149.0, grade="A"
        ),
        VitalMetricItem(
            category="脂質", metric_name="中性脂肪", val=48.0, unit="mg/dL", ref_min=30.0, ref_max=149.0, grade="A"
        ),
        VitalMetricItem(
            category="糖代謝", metric_name="空腹時血糖", val=84.0, unit="mg/dL", ref_min=None, ref_max=100.0, grade="A"
        ),
        VitalMetricItem(
            category="糖代謝", metric_name="HbA1c", val=5.8, unit="%", ref_min=None, ref_max=5.5, grade="B"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="総ビリルビン", val=0.6, unit="mg/dL", ref_min=0.3, ref_max=1.2, grade="A"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="AST", val=21.0, unit="U/L", ref_min=None, ref_max=30.0, grade="A"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="ALT", val=31.0, unit="U/L", ref_min=None, ref_max=30.0, grade="B"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="γ-GTP", val=21.0, unit="U/L", ref_min=None, ref_max=50.0, grade="A"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="ALP", val=61.0, unit="U/L", ref_min=38.0, ref_max=113.0, grade="A"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="総蛋白", val=7.0, unit="g/dL", ref_min=6.5, ref_max=7.9, grade="A"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="アルブミン", val=4.3, unit="g/dL", ref_min=3.9, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="CHE", val=294.0, unit="U/L", ref_min=243.0, ref_max=494.0, grade="A"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="LDH", val=173.0, unit="U/L", ref_min=124.0, ref_max=222.0, grade="A"
        ),
        VitalMetricItem(
            category="腎機能", metric_name="クレアチニン", val=0.80, unit="mg/dL", ref_min=None, ref_max=1.00, grade="A"
        ),
        VitalMetricItem(
            category="腎機能", metric_name="尿素窒素", val=14.0, unit="mg/dL", ref_min=8.0, ref_max=22.0, grade="A"
        ),
        VitalMetricItem(
            category="腎機能", metric_name="e-GFR", val=85.3, unit="mL/min", ref_min=60.0, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="痛風", metric_name="尿酸", val=5.0, unit="mg/dL", ref_min=2.1, ref_max=7.0, grade="A"
        ),
    ]

    vitals_2025 = [
        VitalMetricItem(
            category="身体計測", metric_name="身長", val=176.3, unit="cm", ref_min=None, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="身体計測", metric_name="体重", val=70.8, unit="kg", ref_min=None, ref_max=None, grade="C"
        ),
        VitalMetricItem(
            category="身体計測", metric_name="BMI", val=22.8, unit="kg/㎡", ref_min=18.5, ref_max=24.9, grade="A"
        ),
        VitalMetricItem(
            category="身体計測", metric_name="腹囲", val=88.0, unit="cm", ref_min=None, ref_max=85.0, grade="C"
        ),
        VitalMetricItem(
            category="血圧", metric_name="最高血圧", val=96.0, unit="mmHg", ref_min=None, ref_max=130.0, grade="A"
        ),
        VitalMetricItem(
            category="血圧", metric_name="最低血圧", val=67.0, unit="mmHg", ref_min=None, ref_max=85.0, grade="A"
        ),
        VitalMetricItem(
            category="脂質",
            metric_name="総コレステロール",
            val=211.0,
            unit="mg/dL",
            ref_min=None,
            ref_max=None,
            grade="A",
        ),
        VitalMetricItem(
            category="脂質",
            metric_name="HDLコレステロール",
            val=63.0,
            unit="mg/dL",
            ref_min=40.0,
            ref_max=None,
            grade="A",
        ),
        VitalMetricItem(
            category="脂質",
            metric_name="LDLコレステロール",
            val=138.0,
            unit="mg/dL",
            ref_min=60.0,
            ref_max=139.0,
            grade="A",
        ),
        VitalMetricItem(
            category="脂質", metric_name="中性脂肪", val=61.0, unit="mg/dL", ref_min=30.0, ref_max=149.0, grade="A"
        ),
        VitalMetricItem(
            category="糖代謝", metric_name="空腹時血糖", val=86.0, unit="mg/dL", ref_min=None, ref_max=100.0, grade="A"
        ),
        VitalMetricItem(
            category="糖代謝", metric_name="HbA1c", val=6.1, unit="%", ref_min=None, ref_max=5.5, grade="C"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="AST", val=32.0, unit="U/L", ref_min=None, ref_max=30.0, grade="B"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="ALT", val=61.0, unit="U/L", ref_min=None, ref_max=30.0, grade="D2"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="γ-GTP", val=43.0, unit="U/L", ref_min=None, ref_max=50.0, grade="A"
        ),
        VitalMetricItem(
            category="腎機能", metric_name="クレアチニン", val=0.84, unit="mg/dL", ref_min=None, ref_max=1.00, grade="A"
        ),
        VitalMetricItem(
            category="腎機能", metric_name="e-GFR", val=81.4, unit="mL/min", ref_min=60.0, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="痛風", metric_name="尿酸", val=5.4, unit="mg/dL", ref_min=2.1, ref_max=7.0, grade="A"
        ),
    ]

    vitals_2024 = [
        VitalMetricItem(
            category="身体計測", metric_name="身長", val=176.7, unit="cm", ref_min=None, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="身体計測", metric_name="体重", val=76.4, unit="kg", ref_min=None, ref_max=None, grade="C"
        ),
        VitalMetricItem(
            category="身体計測", metric_name="BMI", val=24.5, unit="kg/㎡", ref_min=18.5, ref_max=24.9, grade="A"
        ),
        VitalMetricItem(
            category="身体計測", metric_name="腹囲", val=92.0, unit="cm", ref_min=None, ref_max=85.0, grade="C"
        ),
        VitalMetricItem(
            category="血圧", metric_name="最高血圧", val=96.0, unit="mmHg", ref_min=None, ref_max=130.0, grade="A"
        ),
        VitalMetricItem(
            category="血圧", metric_name="最低血圧", val=66.0, unit="mmHg", ref_min=None, ref_max=85.0, grade="A"
        ),
        VitalMetricItem(
            category="脂質",
            metric_name="総コレステロール",
            val=216.0,
            unit="mg/dL",
            ref_min=None,
            ref_max=None,
            grade="C",
        ),
        VitalMetricItem(
            category="脂質",
            metric_name="HDLコレステロール",
            val=57.0,
            unit="mg/dL",
            ref_min=40.0,
            ref_max=None,
            grade="A",
        ),
        VitalMetricItem(
            category="脂質",
            metric_name="LDLコレステロール",
            val=159.0,
            unit="mg/dL",
            ref_min=60.0,
            ref_max=139.0,
            grade="C",
        ),
        VitalMetricItem(
            category="脂質", metric_name="中性脂肪", val=59.0, unit="mg/dL", ref_min=30.0, ref_max=149.0, grade="A"
        ),
        VitalMetricItem(
            category="糖代謝", metric_name="空腹時血糖", val=95.0, unit="mg/dL", ref_min=None, ref_max=100.0, grade="A"
        ),
        VitalMetricItem(
            category="糖代謝", metric_name="HbA1c", val=6.1, unit="%", ref_min=None, ref_max=5.5, grade="C"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="AST", val=29.0, unit="U/L", ref_min=None, ref_max=30.0, grade="A"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="ALT", val=51.0, unit="U/L", ref_min=None, ref_max=30.0, grade="C"
        ),
        VitalMetricItem(
            category="肝機能", metric_name="γ-GTP", val=44.0, unit="U/L", ref_min=None, ref_max=50.0, grade="A"
        ),
        VitalMetricItem(
            category="腎機能", metric_name="クレアチニン", val=0.87, unit="mg/dL", ref_min=None, ref_max=1.00, grade="A"
        ),
        VitalMetricItem(
            category="腎機能", metric_name="e-GFR", val=78.9, unit="mL/min", ref_min=60.0, ref_max=None, grade="A"
        ),
        VitalMetricItem(
            category="痛風", metric_name="尿酸", val=5.9, unit="mg/dL", ref_min=2.1, ref_max=7.0, grade="A"
        ),
    ]

    total_vitals = 0
    total_vitals += insert_vital_metrics(vitals_2026, "2026-04-22", target_path=target_path)
    total_vitals += insert_vital_metrics(vitals_2025, "2025-04-30", target_path=target_path)
    total_vitals += insert_vital_metrics(vitals_2024, "2024-05-01", target_path=target_path)

    # -------------------------------------------------------------
    # 2. 人間ドック (medock) 3年分定性検査・所見・各科総合判定
    # -------------------------------------------------------------
    qualitative_2026 = [
        # 各科総合判定
        QualitativeCheckupItem(
            category="総合判定",
            item_name="総合判定",
            finding="経過観察あるいは生活習慣改善を要します",
            grade="C",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="診察",
            item_name="診察判定",
            finding="今回の診察では異常ありません",
            grade="A",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="身体計測", item_name="身体計測判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="血圧", item_name="血圧判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="視力", item_name="視力判定", finding="経過観察", grade="C", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="眼底", item_name="眼底判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="眼圧", item_name="眼圧判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="聴力", item_name="聴力判定", finding="所見なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="血液学検査", item_name="血液学判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="脂質", item_name="脂質判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="糖代謝", item_name="糖代謝判定", finding="軽度異常", grade="B", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="肝機能", item_name="肝機能判定", finding="軽度異常", grade="B", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="肝炎", item_name="肝炎判定", finding="陰性", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="腎機能", item_name="腎機能判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="痛風", item_name="痛風判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="尿検査", item_name="尿検査判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="免疫・炎症反応",
            item_name="免疫炎症判定",
            finding="基準範囲内",
            grade="A",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="胸部", item_name="胸部判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="肺機能", item_name="肺機能判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="上部消化管", item_name="上部消化管判定", finding="軽度異常", grade="B", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="便潜血", item_name="便潜血判定", finding="陰性", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="腹部", item_name="腹部判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="心臓", item_name="心臓判定", finding="正常", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="頭部", item_name="頭部判定", finding="軽度異常", grade="B", is_category_summary=True
        ),
        # 個別詳細所見
        QualitativeCheckupItem(category="聴力", item_name="1000Hz(右)", finding="所見なし", grade="A"),
        QualitativeCheckupItem(category="聴力", item_name="4000Hz(右)", finding="所見なし", grade="A"),
        QualitativeCheckupItem(category="聴力", item_name="1000Hz(左)", finding="所見なし", grade="A"),
        QualitativeCheckupItem(category="聴力", item_name="4000Hz(左)", finding="所見なし", grade="A"),
        QualitativeCheckupItem(
            category="眼底", item_name="Scheie分類", finding="0/0", grade="A", details="H:高血圧性 0 / S:動脈硬化性 0"
        ),
        QualitativeCheckupItem(category="眼底", item_name="改変Davis", finding="網膜症なし", grade="A"),
        QualitativeCheckupItem(category="眼底", item_name="眼底所見", finding="(両)異常なし", grade="A"),
        QualitativeCheckupItem(
            category="視力",
            item_name="矯正視力(右/左)",
            finding="1.0 / 0.9",
            grade="C",
            details="右:1.0, 左:0.9 (視力低下所見あり)",
        ),
        QualitativeCheckupItem(category="尿検査", item_name="尿蛋白", finding="(-)", grade="A"),
        QualitativeCheckupItem(category="尿検査", item_name="尿潜血", finding="(-)", grade="A"),
        QualitativeCheckupItem(category="便潜血", item_name="便潜血1回目", finding="(-)", grade="A"),
        QualitativeCheckupItem(category="便潜血", item_name="便潜血2回目", finding="(-)", grade="A"),
        QualitativeCheckupItem(
            category="診察", item_name="内科診療", finding="今回の診察では異常ありません", grade="A"
        ),
        QualitativeCheckupItem(category="心臓", item_name="心電図", finding="正常", grade="A", details="心拍数: 59"),
        QualitativeCheckupItem(
            category="胸部", item_name="胸部X線", finding="異常なし", grade="A", details="X線(デジタル)"
        ),
    ]

    qualitative_2025 = [
        # 各科総合判定
        QualitativeCheckupItem(
            category="総合判定",
            item_name="総合判定",
            finding="二次検査（精密検査）を要します",
            grade="D2",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="診察",
            item_name="診察判定",
            finding="今回の診察では異常ありません",
            grade="A",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="身体計測", item_name="身体計測判定", finding="経過観察", grade="C", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="血圧", item_name="血圧判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="視力", item_name="視力判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="眼底", item_name="眼底判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="眼圧", item_name="眼圧判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="聴力", item_name="聴力判定", finding="所見なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="血液学検査", item_name="血液学判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="脂質", item_name="脂質判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="糖代謝", item_name="糖代謝判定", finding="経過観察", grade="C", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="肝機能",
            item_name="肝機能判定",
            finding="二次検査（精密検査）を要します",
            grade="D2",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="肝炎", item_name="肝炎判定", finding="陰性", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="腎機能", item_name="腎機能判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="痛風", item_name="痛風判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="尿検査", item_name="尿検査判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="免疫・炎症反応",
            item_name="免疫炎症判定",
            finding="基準範囲内",
            grade="A",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="胸部", item_name="胸部判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="肺機能", item_name="肺機能判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="上部消化管", item_name="上部消化管判定", finding="軽度異常", grade="B", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="便潜血", item_name="便潜血判定", finding="陰性", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="腹部", item_name="腹部判定", finding="軽度異常", grade="B", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="心臓", item_name="心臓判定", finding="正常", grade="A", is_category_summary=True
        ),
        # 個別詳細所見
        QualitativeCheckupItem(
            category="聴力", item_name="聴力検査(左右)", finding="1000Hz/4000Hz 所見なし", grade="A"
        ),
        QualitativeCheckupItem(
            category="眼底",
            item_name="眼底所見",
            finding="(右)異常なし (左)異常なし",
            grade="A",
            details="Scheie: 0/0, Davis: 網膜症なし",
        ),
        QualitativeCheckupItem(category="視力", item_name="矯正視力(右/左)", finding="1.0 / 1.0", grade="A"),
        QualitativeCheckupItem(category="尿検査", item_name="尿蛋白", finding="(-)", grade="A"),
        QualitativeCheckupItem(category="尿検査", item_name="尿潜血", finding="(-)", grade="A"),
        QualitativeCheckupItem(category="便潜血", item_name="便潜血(1/2回目)", finding="(-)/(-)", grade="A"),
        QualitativeCheckupItem(
            category="診察", item_name="内科診療", finding="今回の診察では異常ありません", grade="A"
        ),
        QualitativeCheckupItem(category="心臓", item_name="心電図", finding="正常", grade="A", details="心拍数: 58"),
        QualitativeCheckupItem(category="胸部", item_name="胸部X線", finding="異常なし", grade="A"),
    ]

    qualitative_2024 = [
        # 各科総合判定
        QualitativeCheckupItem(
            category="総合判定",
            item_name="総合判定",
            finding="経過観察あるいは生活習慣改善を要します",
            grade="C",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="診察",
            item_name="診察判定",
            finding="今回の診察では異常ありません",
            grade="A",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="身体計測", item_name="身体計測判定", finding="経過観察", grade="C", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="血圧", item_name="血圧判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="視力", item_name="視力判定", finding="経過観察", grade="C", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="眼底", item_name="眼底判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="眼圧", item_name="眼圧判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="聴力", item_name="聴力判定", finding="所見なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="血液学検査", item_name="血液学判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="脂質", item_name="脂質判定", finding="経過観察", grade="C", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="糖代謝", item_name="糖代謝判定", finding="経過観察", grade="C", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="肝機能", item_name="肝機能判定", finding="経過観察", grade="C", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="肝炎", item_name="肝炎判定", finding="陰性", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="腎機能", item_name="腎機能判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="痛風", item_name="痛風判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="尿検査", item_name="尿検査判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="免疫・炎症反応",
            item_name="免疫炎症判定",
            finding="基準範囲内",
            grade="A",
            is_category_summary=True,
        ),
        QualitativeCheckupItem(
            category="胸部", item_name="胸部判定", finding="異常なし", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="肺機能", item_name="肺機能判定", finding="基準範囲内", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="上部消化管", item_name="上部消化管判定", finding="軽度異常", grade="B", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="便潜血", item_name="便潜血判定", finding="陰性", grade="A", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="腹部", item_name="腹部判定", finding="軽度異常", grade="B", is_category_summary=True
        ),
        QualitativeCheckupItem(
            category="心臓", item_name="心臓判定", finding="正常", grade="A", is_category_summary=True
        ),
        # 個別詳細所見
        QualitativeCheckupItem(
            category="聴力", item_name="聴力検査(左右)", finding="1000Hz/4000Hz 所見なし", grade="A"
        ),
        QualitativeCheckupItem(
            category="眼底",
            item_name="眼底所見",
            finding="(右)異常なし (左)異常なし",
            grade="A",
            details="Scheie: 0/0, Davis: 網膜症なし",
        ),
        QualitativeCheckupItem(
            category="視力", item_name="矯正視力(右/左)", finding="1.2 / 0.6", grade="C", details="左眼低下"
        ),
        QualitativeCheckupItem(category="尿検査", item_name="尿蛋白", finding="(-)", grade="A"),
        QualitativeCheckupItem(category="尿検査", item_name="尿潜血", finding="(-)", grade="A"),
        QualitativeCheckupItem(category="便潜血", item_name="便潜血(1/2回目)", finding="(-)/(-)", grade="A"),
        QualitativeCheckupItem(
            category="診察", item_name="内科診療", finding="今回の診察では異常ありません", grade="A"
        ),
        QualitativeCheckupItem(category="心臓", item_name="心電図", finding="正常", grade="A", details="心拍数: 53"),
        QualitativeCheckupItem(category="胸部", item_name="胸部X線", finding="異常なし", grade="A"),
    ]

    total_qualitative = 0
    total_qualitative += insert_qualitative_items(qualitative_2026, "2026-04-22", target_path=target_path)
    total_qualitative += insert_qualitative_items(qualitative_2025, "2025-04-30", target_path=target_path)
    total_qualitative += insert_qualitative_items(qualitative_2024, "2024-05-01", target_path=target_path)

    # -------------------------------------------------------------
    # 3. 画像・内視鏡精密検査イベント（実機4件 + ドック内包分）
    # -------------------------------------------------------------
    annual_pdf_path = "data/pdfs/20260422_ANNUAL_medock総合健診クリニック.pdf"
    dwibs_pdf_path = "data/pdfs/20260502_DWIBS_医療法人ONEきくち総合診療クリニック.pdf"
    colon_pdf_path = "data/pdfs/20260916_大腸内視鏡_青葉台かなざわ内科内視鏡クリニック.pdf"
    ct_pdf_path = "data/pdfs/20260921_胸腹部CT_新宿三丁目メディカルクリニック.pdf"

    # ダミーPDF実体の作成（ダウンロードリンクテスト用）
    for p in [annual_pdf_path, dwibs_pdf_path, colon_pdf_path, ct_pdf_path]:
        pdf_file = Path(p)
        pdf_file.parent.mkdir(parents=True, exist_ok=True)
        if not pdf_file.exists():
            pdf_file.write_bytes(b"%PDF-1.4\n% Health CMMS Stored Medical Report Artifact\n")

    events = [
        # 人間ドック総合（生化学・定性・胃カメラ・腹部超音波包含）
        (
            ImagingEventPayload(
                exam_date="2026-04-22",
                modality="人間ドック(胃カメラ、腹部超音波を含む)",
                target_region="全身",
                clinic_name="medock 総合健診クリニック",
                status_flag="CLEAR",
                primary_findings="年次人間ドック（生化学・身体測定・定性判定・胃カメラ・腹部超音波包含）",
                raw_comment="人間ドック（次回推奨受診時期: 1年後）",
                pdf_page=1,
                suggested_interval_years=1.0,
            ),
            annual_pdf_path,
        ),
        # ドック内包: 胃カメラ
        (
            ImagingEventPayload(
                exam_date="2026-04-22",
                modality="胃カメラ",
                target_region="胃",
                clinic_name="medock 総合健診クリニック",
                status_flag="BENIGN_STABLE",
                primary_findings="胃底腺ポリープ (良性)",
                raw_comment="胃部内視鏡検査にて、胃底腺ポリープを認めます。良性のポリープです。毎年定期的に胃カメラの検査を受けましょう。",
                pdf_page=9,
                suggested_interval_years=1.0,
            ),
            annual_pdf_path,
        ),
        # ドック内包: 脳MRI/MRA
        (
            ImagingEventPayload(
                exam_date="2026-04-22",
                modality="脳MRI/MRA",
                target_region="脳",
                clinic_name="medock 総合健診クリニック",
                status_flag="BENIGN_STABLE",
                primary_findings="透明中隔腔、ベルガ腔 (正常変異)",
                raw_comment="透明中隔腔、ベルガ腔を認めます。加齢とともに消失するものが正常変異として残ったもので心配ありません。1年後の健康診断にて再度チェックしていきましょう。脳血管に異常なし。",
                pdf_page=17,
                suggested_interval_years=1.0,
            ),
            annual_pdf_path,
        ),
        # ドック内包: 腹部超音波
        (
            ImagingEventPayload(
                exam_date="2026-04-22",
                modality="腹部エコー",
                target_region="腹部",
                clinic_name="medock 総合健診クリニック",
                status_flag="CLEAR",
                primary_findings="肝臓・胆のう・膵臓・腎臓・脾臓 異常なし (前回脂肪肝・嚢胞は消失)",
                raw_comment="今回の検査では肝臓・胆のう・膵臓・腎臓・脾臓などの腹部臓器に明らかな異常所見は認められませんでした。",
                pdf_page=11,
                suggested_interval_years=1.0,
            ),
            annual_pdf_path,
        ),
        # 実機PDF 2: 全身がんドック DWIBS
        (
            ImagingEventPayload(
                exam_date="2026-05-02",
                modality="DWIBS",
                target_region="全身",
                clinic_name="医療法人ONE きくち総合診療クリニック",
                status_flag="CLEAR",
                primary_findings="頭頂〜骨盤部 悪性腫瘍疑う異常信号なし (CLEAR)",
                raw_comment="頭頂〜骨盤部において、悪性腫瘍を疑う異常信号は認めません。その他、有意所見は認めません。正常範囲内です。次回以降も当クリニックで定期的な検査をよろしくお願いします。",
                pdf_page=1,
                suggested_interval_years=2.0,
            ),
            dwibs_pdf_path,
        ),
        # 実機PDF 3: 大腸カメラ (5年周期)
        (
            ImagingEventPayload(
                exam_date="2026-09-16",
                modality="大腸カメラ",
                target_region="全大腸",
                clinic_name="青葉台かなざわ内科・内視鏡クリニック",
                status_flag="CLEAR",
                primary_findings="回腸末端まで挿入、ポリープなし、外痔核のみ",
                raw_comment="鎮静剤使用。回腸末端まで挿入。外痔核を認めるがポリープ等の病的病変なし（CLEAR）。次回推奨: 5年後。",
                pdf_page=1,
                suggested_interval_years=5.0,
            ),
            colon_pdf_path,
        ),
        # 実機PDF 1: 胸腹部CT
        (
            ImagingEventPayload(
                exam_date="2026-09-21",
                modality="胸腹部CT",
                target_region="胸腹部",
                clinic_name="新宿三丁目メディカルクリニック",
                status_flag="BENIGN_STABLE",
                primary_findings="肝嚢胞（良性・典型例）",
                raw_comment="肝臓に液体がたまった袋状の変化（肝嚢胞）が認められます。典型的な嚢胞で症状がなければ通常は経過観察となります。消化管、泌尿器、腹部大血管に異常なし。",
                pdf_page=1,
                suggested_interval_years=None,
            ),
            ct_pdf_path,
        ),
    ]

    total_events = 0
    for payload, path_str in events:
        due_date = compute_dynamic_next_due(
            exam_date_str=payload.exam_date,
            modality=payload.modality,
            status_flag=payload.status_flag,
            raw_comment=payload.raw_comment,
            suggested_interval_years=payload.suggested_interval_years,
        )
        insert_imaging_event(payload, due_date, path_str, target_path=target_path)
        ledger_update = derive_organ_ledger_update(payload, due_date)
        upsert_organ_ledger(ledger_update, target_path)
        total_events += 1

    rebuild_organ_ledger(target_path)

    return {
        "vital_metrics_count": total_vitals,
        "qualitative_items_count": total_qualitative,
        "imaging_events_count": total_events,
    }
