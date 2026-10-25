from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.database import (
    delete_registered_files_cascade,
    fetch_all_registered_files,
    fetch_latest_exam_for_modality_or_region,
    fetch_latest_imaging_events_by_modality,
    fetch_organ_ledger,
    init_db,
    insert_imaging_event,
    insert_qualitative_items,
    insert_vital_metrics,
    rebuild_organ_ledger,
    register_file,
)
from src.models import (
    ImagingEventPayload,
    QualitativeCheckupItem,
    RegisteredFileRecord,
    VitalMetricItem,
)


def test_file_registration_and_cascade_delete() -> None:
    """ファイルの登録、件数集計、カスケード削除および元帳自動再同期のテスト。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        pdf_file1 = Path(tmp_dir) / "20240415_胃カメラ_クリニックA.pdf"
        pdf_file2 = Path(tmp_dir) / "20250520_胃カメラ_クリニックB.pdf"
        pdf_file1.write_bytes(b"%PDF-1.4 dummy 1")
        pdf_file2.write_bytes(b"%PDF-1.4 dummy 2")

        init_db(db_path)

        # 1. 2024年のファイルを登録
        f1_rec = RegisteredFileRecord(
            file_name=pdf_file1.name,
            original_name="2024_report.pdf",
            file_hash="hash2024",
            doc_type="SINGLE_IMAGING",
            exam_date="2024-04-15",
            clinic_name="クリニックA",
            registered_at="2024-04-16 10:00:00",
            file_size=len(pdf_file1.read_bytes()),
            storage_path=str(pdf_file1),
        )
        f1_id = register_file(f1_rec, db_path)
        assert f1_id > 0

        # 2024年の画像イベント投入
        im2024 = ImagingEventPayload(
            exam_date="2024-04-15",
            modality="胃カメラ",
            target_region="胃",
            clinic_name="クリニックA",
            status_flag="CLEAR",
            primary_findings="表層性胃炎のみ",
            raw_comment="1年後に定期検査を推奨",
            suggested_interval_years=1.0,
        )
        insert_imaging_event(im2024, "2025-04-15", str(pdf_file1), file_id=f1_id, target_path=db_path)
        rebuild_organ_ledger(db_path)

        ledger1 = fetch_organ_ledger(db_path)
        assert len(ledger1) == 1
        assert ledger1[0]["organ"] == "胃"
        assert ledger1[0]["last_exam_date"] == "2024-04-15"
        assert ledger1[0]["next_action_due"] == "2025-04-15"

        # 2. 2025年の最新ファイルを登録
        f2_rec = RegisteredFileRecord(
            file_name=pdf_file2.name,
            original_name="2025_report.pdf",
            file_hash="hash2025",
            doc_type="SINGLE_IMAGING",
            exam_date="2025-05-20",
            clinic_name="クリニックB",
            registered_at="2025-05-21 10:00:00",
            file_size=len(pdf_file2.read_bytes()),
            storage_path=str(pdf_file2),
        )
        f2_id = register_file(f2_rec, db_path)

        im2025 = ImagingEventPayload(
            exam_date="2025-05-20",
            modality="胃カメラ",
            target_region="胃",
            clinic_name="クリニックB",
            status_flag="BENIGN_STABLE",
            primary_findings="良性ポリープあり、経過観察",
            raw_comment="次回は1年後に受診してください",
            suggested_interval_years=1.0,
        )
        insert_imaging_event(im2025, "2026-05-20", str(pdf_file2), file_id=f2_id, target_path=db_path)
        rebuild_organ_ledger(db_path)

        # 元帳が2025年の最新データに更新されていること
        ledger2 = fetch_organ_ledger(db_path)
        assert len(ledger2) == 1
        assert ledger2[0]["last_exam_date"] == "2025-05-20"
        assert ledger2[0]["next_action_due"] == "2026-05-20"

        # 最新集約取得（最新の前回検査日のみが取得されること）
        latest_evs = fetch_latest_imaging_events_by_modality(db_path)
        assert len(latest_evs) == 1
        assert latest_evs[0]["exam_date"] == "2025-05-20"
        assert latest_evs[0]["dynamic_next_due"] == "2026-05-20"

        # 3. 2025年の最新ファイルをカスケード削除
        del_res = delete_registered_files_cascade([f2_id], db_path)
        assert del_res["files"] == 1
        assert del_res["imaging_events"] == 1
        assert not pdf_file2.exists()
        assert pdf_file1.exists()

        # 元帳が2024年の過去直近レコードへ自動ロールバック復元されていること！
        ledger3 = fetch_organ_ledger(db_path)
        assert len(ledger3) == 1
        assert ledger3[0]["organ"] == "胃"
        assert ledger3[0]["last_exam_date"] == "2024-04-15"
        assert ledger3[0]["next_action_due"] == "2025-04-15"

        # 4. 2024年のファイルも削除した場合は元帳から消去されること
        del_res2 = delete_registered_files_cascade([f1_id], db_path)
        assert del_res2["files"] == 1
        ledger4 = fetch_organ_ledger(db_path)
        assert len(ledger4) == 0


def test_order_independent_registration() -> None:
    """時系列の逆順（2025年→2023年の順）に登録しても最新集約および照合が正しく機能することを検証。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_order.db"
        init_db(db_path)

        # 1. 先に2025年のCTを登録
        ct2025 = ImagingEventPayload(
            exam_date="2025-06-01",
            modality="胸腹部CT",
            target_region="胸腹部",
            clinic_name="病院A",
            status_flag="CLEAR",
            primary_findings="異常なし",
            suggested_interval_years=3.0,
        )
        insert_imaging_event(ct2025, "2028-06-01", target_path=db_path)
        rebuild_organ_ledger(db_path)

        # 2. 後から2023年の過去CTを登録
        # 登録前の照合で、既存の2025年が検出できること
        existing = fetch_latest_exam_for_modality_or_region("胸腹部CT", "胸腹部", db_path)
        assert existing is not None
        assert existing["exam_date"] == "2025-06-01"

        ct2023 = ImagingEventPayload(
            exam_date="2023-05-10",
            modality="胸腹部CT",
            target_region="胸腹部",
            clinic_name="病院B",
            status_flag="BENIGN_STABLE",
            primary_findings="微小結節（良性）",
            suggested_interval_years=1.0,
        )
        insert_imaging_event(ct2023, "2024-05-10", target_path=db_path)
        rebuild_organ_ledger(db_path)

        # 3. 元帳および次回予定集約は2025年の最新が維持されていること（2023年で壊されないこと）
        ledger = fetch_organ_ledger(db_path)
        assert len(ledger) == 1
        assert ledger[0]["last_exam_date"] == "2025-06-01"
        assert ledger[0]["next_action_due"] == "2028-06-01"

        latest_list = fetch_latest_imaging_events_by_modality(db_path)
        assert len(latest_list) == 1
        assert latest_list[0]["exam_date"] == "2025-06-01"
        assert latest_list[0]["dynamic_next_due"] == "2028-06-01"


def test_annual_checkup_cascade() -> None:
    """定期健診ドック（生化学、定性、画像内包）の登録と件数集計・カスケード削除のテスト。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_annual.db"
        pdf_path = Path(tmp_dir) / "20260422_ANNUAL_medock総合健診クリニック.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 dummy annual")

        init_db(db_path)

        file_rec = RegisteredFileRecord(
            file_name=pdf_path.name,
            original_name="annual.pdf",
            file_hash="hash_annual",
            doc_type="ANNUAL_CHECKUP",
            exam_date="2026-04-22",
            clinic_name="medock総合健診クリニック",
            registered_at="2026-04-23 10:00:00",
            file_size=len(pdf_path.read_bytes()),
            storage_path=str(pdf_path),
        )
        fid = register_file(file_rec, db_path)

        # 生化学メトリクス
        vitals = [
            VitalMetricItem(category="肝機能", metric_name="ALT", val=22.0, unit="U/L"),
            VitalMetricItem(category="脂質", metric_name="LDLコレステロール", val=110.0, unit="mg/dL"),
        ]
        insert_vital_metrics(vitals, "2026-04-22", file_id=fid, target_path=db_path)

        # 定性項目
        qual = [
            QualitativeCheckupItem(category="尿検査", item_name="尿蛋白", finding="(-)"),
        ]
        insert_qualitative_items(qual, "2026-04-22", file_id=fid, target_path=db_path)

        # 内包画像
        im = ImagingEventPayload(
            exam_date="2026-04-22",
            modality="腹部エコー",
            target_region="腹部",
            clinic_name="medock総合健診クリニック",
            status_flag="CLEAR",
            primary_findings="異常なし",
            suggested_interval_years=1.0,
        )
        insert_imaging_event(im, "2027-04-22", str(pdf_path), file_id=fid, target_path=db_path)
        rebuild_organ_ledger(db_path)

        # 一覧取得と件数確認
        files = fetch_all_registered_files(db_path)
        assert len(files) == 1
        assert files[0]["vital_count"] == 2
        assert files[0]["qualitative_count"] == 1
        assert files[0]["imaging_count"] == 1

        # カスケード削除
        del_res = delete_registered_files_cascade([fid], db_path)
        assert del_res["files"] == 1
        assert del_res["vital_metrics"] == 2
        assert del_res["qualitative_items"] == 1
        assert del_res["imaging_events"] == 1

        # 削除後の全テーブル検証
        files_after = fetch_all_registered_files(db_path)
        assert len(files_after) == 0
        ledger_after = fetch_organ_ledger(db_path)
        assert len(ledger_after) == 0


def test_modality_migration_and_managed_timeline_integration() -> None:
    """旧モダリティ名（定期健康診断、大腸内視鏡）の自動マイグレーションと5大管理項目集約を検証。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_migration.db"
        init_db(db_path)

        # 旧モダリティのレコードを手動投入
        im_annual = ImagingEventPayload(
            exam_date="2025-04-20",
            modality="定期健康診断",
            target_region="全身",
            clinic_name="旧健診センター",
            status_flag="CLEAR",
            primary_findings="年次健診",
        )
        insert_imaging_event(im_annual, "2026-04-20", target_path=db_path)

        im_colon = ImagingEventPayload(
            exam_date="2025-05-10",
            modality="大腸内視鏡",
            target_region="全大腸",
            clinic_name="内視鏡クリニック",
            status_flag="CLEAR",
            primary_findings="ポリープなし",
        )
        insert_imaging_event(im_colon, "2028-05-10", target_path=db_path)  # 旧3年周期

        # マイグレーション実行（init_dbの再呼出）
        init_db(db_path)

        # 5大管理項目タイムライン取得
        from datetime import date

        from src.database import fetch_all_imaging_events, fetch_managed_timeline_summary

        events = fetch_all_imaging_events(db_path)
        mod_names = [e["modality"] for e in events]
        assert "人間ドック(胃カメラ、腹部超音波を含む)" in mod_names
        assert "大腸カメラ" in mod_names
        assert "定期健康診断" not in mod_names
        assert "大腸内視鏡" not in mod_names

        # 大腸カメラが5年（2030-05-10）へ再計算されたことを検証
        colon_event = next(e for e in events if e["modality"] == "大腸カメラ")
        assert colon_event["dynamic_next_due"] == "2030-05-10"

        # 5行固定集約の検証（2026年基準）
        summary = fetch_managed_timeline_summary(db_path, current_date=date(2026, 10, 25))
        assert len(summary) == 5

        heart_entry = next(s for s in summary if s.modality == "心臓CT")
        assert heart_entry.alert_category == "受診開始待機"
        assert heart_entry.dynamic_next_due == "2028-04-01"


def test_recompute_all_dynamic_next_dues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """受診間隔設定変更に伴う全検査イベントの次回推奨日再計算と元帳同期を検証。"""
    import src.config as cfg
    from src.config import set_managed_intervals
    from src.database import (
        fetch_all_imaging_events,
        fetch_organ_ledger,
        recompute_all_dynamic_next_dues,
    )

    test_settings = tmp_path / "settings.json"
    monkeypatch.setattr(cfg, "SETTINGS_FILE", test_settings)

    db_path = tmp_path / "test_recompute.db"
    init_db(db_path)

    im_brain = ImagingEventPayload(
        exam_date="2026-04-22",
        modality="脳MRI/MRA",
        target_region="脳",
        clinic_name="健診クリニック",
        status_flag="CLEAR",
        primary_findings="異常所見なし",
    )
    # 初期登録: デフォルト5年 (2031-04-22)
    insert_imaging_event(im_brain, "2031-04-22", target_path=db_path)

    # 間隔を3年に変更
    set_managed_intervals({"脳MRI/MRA": 3.0})

    # 再計算
    updated = recompute_all_dynamic_next_dues(target_path=db_path)
    assert updated == 1

    events = fetch_all_imaging_events(target_path=db_path)
    assert events[0]["dynamic_next_due"] == "2029-04-22"

    ledger = fetch_organ_ledger(target_path=db_path)
    brain_ledger = next(item for item in ledger if item["organ"] == "脳")
    assert brain_ledger["next_action_due"] == "2029-04-22"
