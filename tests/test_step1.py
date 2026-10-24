from __future__ import annotations

import tempfile
from pathlib import Path

from src.config import generate_pdf_filename, sanitize_filename_part
from src.database import (
    fetch_all_imaging_events,
    fetch_all_qualitative_items,
    fetch_all_vital_metrics,
    fetch_distinct_metric_categories,
    fetch_distinct_metric_names,
    fetch_distinct_qualitative_categories,
    fetch_organ_ledger,
    init_db,
    insert_imaging_event,
    insert_qualitative_items,
    insert_vital_metrics,
    upsert_organ_ledger,
)
from src.models import (
    ImagingEventPayload,
    OrganLedgerItem,
    QualitativeCheckupItem,
    VitalMetricItem,
    normalize_metric_name,
)


def test_normalize_metric_name() -> None:
    # 肝機能
    assert normalize_metric_name("ALT(GPT)") == "ALT"
    assert normalize_metric_name("GPT") == "ALT"
    assert normalize_metric_name("ＡＬＴ") == "ALT"
    assert normalize_metric_name("AST(GOT)") == "AST"
    assert normalize_metric_name("γーＧＴＰ") == "γ-GTP"
    assert normalize_metric_name("コリンエステラーゼ") == "CHE"

    # 糖代謝
    assert normalize_metric_name("HbA1c(NGSP)") == "HbA1c"
    assert normalize_metric_name("ヘモグロビンA1c") == "HbA1c"
    assert normalize_metric_name("空腹時血糖") == "空腹時血糖"
    assert normalize_metric_name("血糖値") == "空腹時血糖"

    # 脂質
    assert normalize_metric_name("LDL-C") == "LDLコレステロール"
    assert normalize_metric_name("悪玉コレステロール") == "LDLコレステロール"
    assert normalize_metric_name("HDL-C") == "HDLコレステロール"
    assert normalize_metric_name("TG") == "中性脂肪"

    # 腎・痛風・身体計測
    assert normalize_metric_name("CRE") == "クレアチニン"
    assert normalize_metric_name("eGFR") == "e-GFR"
    assert normalize_metric_name("Body Weight") == "体重"
    assert normalize_metric_name("ウエスト") == "腹囲"

    # 未定義項目
    assert normalize_metric_name("未知の特殊マーカー") == "未知の特殊マーカー"


def test_pdf_filename_generation() -> None:
    fn_annual = generate_pdf_filename(
        exam_date="2026-04-22",
        modality="人間ドック",
        clinic_name="medock 総合健診クリニック",
        is_annual=True,
    )
    assert fn_annual == "20260422_ANNUAL_medock総合健診クリニック.pdf"

    fn_ct = generate_pdf_filename(
        exam_date="2026-09-21",
        modality="胸腹部CT",
        clinic_name="新宿三丁目メディカルクリニック",
        is_annual=False,
    )
    assert fn_ct == "20260921_胸腹部CT_新宿三丁目メディカルクリニック.pdf"

    sanitized = sanitize_filename_part("Clinic/Name:Special*Clinic?")
    assert "/" not in sanitized
    assert ":" not in sanitized
    assert "*" not in sanitized
    assert "?" not in sanitized


def test_database_crud_operations() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db = Path(tmp_dir) / "test_health.db"
        init_db(test_db)

        # 1. Vital Metrics (with normalization check)
        metrics = [
            VitalMetricItem(
                category="肝機能",
                metric_name="ALT(GPT)",
                val=31.0,
                unit="U/L",
                ref_min=None,
                ref_max=30.0,
                grade="B",
            ),
            VitalMetricItem(
                category="糖代謝",
                metric_name="HbA1c(NGSP)",
                val=5.8,
                unit="%",
                ref_min=None,
                ref_max=5.5,
                grade="B",
            ),
        ]
        count = insert_vital_metrics(metrics, exam_date="2026-04-22", target_path=test_db)
        assert count == 2

        all_vitals = fetch_all_vital_metrics(target_path=test_db)
        assert len(all_vitals) == 2
        assert all_vitals[0]["metric_name"] == "ALT"
        assert all_vitals[1]["metric_name"] == "HbA1c"

        alt_vitals = fetch_all_vital_metrics(metric_name="ALT(GPT)", target_path=test_db)
        assert len(alt_vitals) == 1
        assert alt_vitals[0]["val"] == 31.0

        distinct_names = fetch_distinct_metric_names(target_path=test_db)
        assert distinct_names == ["ALT", "HbA1c"]

        # 2. Imaging Events (with pdf_page check)
        event_payload = ImagingEventPayload(
            exam_date="2026-04-22",
            modality="胃カメラ",
            target_region="胃",
            clinic_name="medock 総合健診クリニック",
            status_flag="BENIGN_STABLE",
            primary_findings="胃底腺ポリープ",
            raw_comment="毎年定期的に胃カメラの検査を受けましょう。",
            pdf_page=9,
            suggested_interval_years=1.0,
        )
        event_id = insert_imaging_event(
            payload=event_payload,
            dynamic_next_due="2027-04-22",
            pdf_path="data/pdfs/20260422_ANNUAL_medock総合健診クリニック.pdf",
            target_path=test_db,
        )
        assert event_id > 0

        events = fetch_all_imaging_events(target_path=test_db)
        assert len(events) == 1
        assert events[0]["modality"] == "胃カメラ"
        assert events[0]["pdf_page"] == 9
        assert events[0]["pdf_path"] == "data/pdfs/20260422_ANNUAL_medock総合健診クリニック.pdf"
        assert events[0]["dynamic_next_due"] == "2027-04-22"

        # 3. Organ Status Ledger (UPSERT check)
        ledger_entry = OrganLedgerItem(
            organ="胃",
            last_exam_date="2026-04-22",
            current_status="胃底腺ポリープ(良性)",
            next_action_due="2027-04-22",
        )
        upsert_organ_ledger(ledger_entry, target_path=test_db)

        ledger = fetch_organ_ledger(target_path=test_db)
        assert len(ledger) == 1
        assert ledger[0]["organ"] == "胃"
        assert ledger[0]["next_action_due"] == "2027-04-22"

        # Update with newer exam date
        ledger_entry_newer = OrganLedgerItem(
            organ="胃",
            last_exam_date="2027-04-25",
            current_status="異常なし(CLEAR)",
            next_action_due="2028-04-25",
        )
        upsert_organ_ledger(ledger_entry_newer, target_path=test_db)

        updated_ledger = fetch_organ_ledger(target_path=test_db)
        assert len(updated_ledger) == 1
        assert updated_ledger[0]["last_exam_date"] == "2027-04-25"
        assert updated_ledger[0]["current_status"] == "異常なし(CLEAR)"
        assert updated_ledger[0]["next_action_due"] == "2028-04-25"

        # 4. Metric categories & category-metric filtering
        pairs = fetch_distinct_metric_categories(target_path=test_db)
        assert set(pairs) == {("肝機能", "ALT"), ("糖代謝", "HbA1c")}

        filtered_pair = fetch_all_vital_metrics(category="肝機能", metric_name="ALT", target_path=test_db)
        assert len(filtered_pair) == 1
        assert filtered_pair[0]["val"] == 31.0

        filtered_cat = fetch_all_vital_metrics(category="糖代謝", target_path=test_db)
        assert len(filtered_cat) == 1
        assert filtered_cat[0]["metric_name"] == "HbA1c"


def test_qualitative_items_crud_operations() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db = Path(tmp_dir) / "test_qualitative.db"
        init_db(test_db)

        # 空リスト挿入
        assert insert_qualitative_items([], "2026-04-22", target_path=test_db) == 0

        items = [
            QualitativeCheckupItem(
                category="聴力",
                item_name="1000Hz(右)",
                finding="所見なし",
                grade="A",
            ),
            QualitativeCheckupItem(
                category="眼底",
                item_name="Scheie分類",
                finding="0/0",
                grade="A",
                details="H:0 S:0",
            ),
            QualitativeCheckupItem(
                category="総合判定",
                item_name="総合判定",
                finding="経過観察",
                grade="C",
                is_category_summary=True,
            ),
        ]

        count = insert_qualitative_items(items, "2026-04-22", target_path=test_db)
        assert count == 3

        # 全件取得
        all_items = fetch_all_qualitative_items(target_path=test_db)
        assert len(all_items) == 3

        # is_summary で絞り込み
        summaries = fetch_all_qualitative_items(is_summary=True, target_path=test_db)
        assert len(summaries) == 1
        assert summaries[0]["category"] == "総合判定"
        assert summaries[0]["grade"] == "C"

        details = fetch_all_qualitative_items(is_summary=False, target_path=test_db)
        assert len(details) == 2

        # category で絞り込み
        hearing = fetch_all_qualitative_items(category="聴力", target_path=test_db)
        assert len(hearing) == 1
        assert hearing[0]["finding"] == "所見なし"

        # カテゴリ一覧取得
        cats = fetch_distinct_qualitative_categories(target_path=test_db)
        assert "聴力" in cats
        assert "眼底" in cats
        assert "総合判定" in cats

        # UPSERT（同一キーで再挿入して内容更新確認）
        updated_items = [
            QualitativeCheckupItem(
                category="聴力",
                item_name="1000Hz(右)",
                finding="軽度所見あり",
                grade="B",
                details="再検推奨",
            )
        ]
        insert_qualitative_items(updated_items, "2026-04-22", target_path=test_db)
        rechecked_hearing = fetch_all_qualitative_items(category="聴力", target_path=test_db)
        assert len(rechecked_hearing) == 1
        assert rechecked_hearing[0]["finding"] == "軽度所見あり"
        assert rechecked_hearing[0]["grade"] == "B"
