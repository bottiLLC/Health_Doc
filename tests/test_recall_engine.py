from __future__ import annotations

from src.models import ImagingEventPayload
from src.recall_engine import compute_dynamic_next_due, derive_organ_ledger_update


def test_colonoscopy_recall() -> None:
    # CLEAR -> 3年
    due_clear = compute_dynamic_next_due(
        exam_date_str="2026-09-16",
        modality="大腸内視鏡",
        status_flag="CLEAR",
        raw_comment="回腸末端まで挿入。外痔核のみ。",
    )
    assert due_clear == "2029-09-16"

    # WATCH_SHORTENED -> 1年
    due_watch = compute_dynamic_next_due(
        exam_date_str="2026-09-16",
        modality="大腸内視鏡",
        status_flag="WATCH_SHORTENED",
        raw_comment="腺腫切除。1年後に再検推奨。",
    )
    assert due_watch == "2027-09-16"


def test_brain_mri_recall() -> None:
    # CLEAR -> 3年
    due_clear = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="脳MRI/MRA",
        status_flag="CLEAR",
        raw_comment="異常所見なし。",
    )
    assert due_clear == "2029-04-22"

    # BENIGN_STABLE + 1年後再検コメント -> 1年
    due_benign_1y = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="脳MRI/MRA",
        status_flag="BENIGN_STABLE",
        raw_comment="透明中隔腔、ベルガ腔を認めます。1年後の健康診断にて再度チェックしていきましょう。",
    )
    assert due_benign_1y == "2027-04-22"

    # BENIGN_STABLE without 1y comment -> 3年
    due_benign_stable = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="脳MRI/MRA",
        status_flag="BENIGN_STABLE",
        raw_comment="微小血管性変化。経過観察。",
    )
    assert due_benign_stable == "2029-04-22"


def test_dwibs_recall() -> None:
    due_clear = compute_dynamic_next_due(
        exam_date_str="2026-05-02",
        modality="DWIBS",
        status_flag="CLEAR",
        raw_comment="悪性腫瘍を疑う異常信号は認めません。",
    )
    assert due_clear == "2028-05-02"


def test_ct_and_gastroscopy_recall() -> None:
    due_ct = compute_dynamic_next_due(
        exam_date_str="2026-09-21",
        modality="胸腹部CT",
        status_flag="BENIGN_STABLE",
        raw_comment="肝嚢胞が認められます。良性の変化です。",
    )
    assert due_ct == "2029-09-21"

    due_gastro = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="胃カメラ",
        status_flag="BENIGN_STABLE",
        raw_comment="胃底腺ポリープを認めます。毎年定期的に胃カメラの検査を受けましょう。",
    )
    assert due_gastro == "2027-04-22"


def test_explicit_suggested_interval_override() -> None:
    due_override = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="大腸内視鏡",
        status_flag="CLEAR",
        raw_comment="",
        suggested_interval_years=5.0,
    )
    assert due_override == "2031-04-22"


def test_leap_year_boundary() -> None:
    # 2024-02-29 + 1 year -> 2025-02-28
    due_leap = compute_dynamic_next_due(
        exam_date_str="2024-02-29",
        modality="胃カメラ",
        status_flag="CLEAR",
    )
    assert due_leap == "2025-02-28"


def test_derive_organ_ledger_update() -> None:
    event = ImagingEventPayload(
        exam_date="2026-09-16",
        modality="大腸内視鏡",
        target_region="全大腸",
        clinic_name="青葉台かなざわ内科・内視鏡クリニック",
        status_flag="CLEAR",
        primary_findings="外痔核のみ",
        pdf_page=1,
    )
    ledger_item = derive_organ_ledger_update(event, "2029-09-16")
    assert ledger_item.organ == "大腸"
    assert ledger_item.last_exam_date == "2026-09-16"
    assert "CLEAR" in ledger_item.current_status
    assert ledger_item.next_action_due == "2029-09-16"
