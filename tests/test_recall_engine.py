from __future__ import annotations

from src.models import ImagingEventPayload
from src.recall_engine import compute_dynamic_next_due, derive_organ_ledger_update


def test_colonoscopy_recall() -> None:
    # CLEAR -> 5年（新基準）
    due_clear = compute_dynamic_next_due(
        exam_date_str="2026-09-16",
        modality="大腸カメラ",
        status_flag="CLEAR",
        raw_comment="回腸末端まで挿入。外痔核のみ。",
    )
    assert due_clear == "2031-09-16"

    # エイリアス「大腸内視鏡」も同一に5年
    due_alias = compute_dynamic_next_due(
        exam_date_str="2026-09-16",
        modality="大腸内視鏡",
        status_flag="CLEAR",
    )
    assert due_alias == "2031-09-16"

    # WATCH_SHORTENED や 1年後コメントがあっても設定間隔（デフォルト5年）が適用される
    due_watch = compute_dynamic_next_due(
        exam_date_str="2026-09-16",
        modality="大腸カメラ",
        status_flag="WATCH_SHORTENED",
        raw_comment="腺腫切除。1年後に再検推奨。",
    )
    assert due_watch == "2031-09-16"


def test_brain_mri_recall() -> None:
    # CLEAR -> 5年
    due_clear = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="脳MRI/MRA",
        status_flag="CLEAR",
        raw_comment="異常所見なし。",
    )
    assert due_clear == "2031-04-22"

    # BENIGN_STABLE + 1年後再検コメントがあっても設定間隔（デフォルト5年）が適用される
    due_benign_1y = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="脳MRI/MRA",
        status_flag="BENIGN_STABLE",
        raw_comment="透明中隔腔、ベルガ腔を認めます。1年後の健康診断にて再度チェックしていきましょう。",
    )
    assert due_benign_1y == "2031-04-22"

    # BENIGN_STABLE without 1y comment -> 5年
    due_benign_stable = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="脳MRI/MRA",
        status_flag="BENIGN_STABLE",
        raw_comment="微小血管性変化。経過観察。",
    )
    assert due_benign_stable == "2031-04-22"


def test_dwibs_recall() -> None:
    due_clear = compute_dynamic_next_due(
        exam_date_str="2026-05-02",
        modality="DWIBS",
        status_flag="CLEAR",
        raw_comment="悪性腫瘍を疑う異常信号は認めません。",
    )
    assert due_clear == "2028-05-02"


def test_ct_and_gastroscopy_recall() -> None:
    # 心臓CT・胸腹部CT: 2028年以前は 2028-04-01 が次回推奨日
    due_ct = compute_dynamic_next_due(
        exam_date_str="2026-09-21",
        modality="胸腹部CT",
        status_flag="BENIGN_STABLE",
        raw_comment="肝嚢胞が認められます。良性の変化です。",
    )
    assert due_ct == "2028-04-01"

    # 2028年以降の心臓CT受診: 5年後
    due_ct_2028 = compute_dynamic_next_due(
        exam_date_str="2028-05-15",
        modality="心臓CT",
        status_flag="CLEAR",
    )
    assert due_ct_2028 == "2033-05-15"

    # 胃カメラ・人間ドック: 1年後
    due_gastro = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="胃カメラ",
        status_flag="BENIGN_STABLE",
        raw_comment="胃底腺ポリープを認めます。毎年定期的に胃カメラの検査を受けましょう。",
    )
    assert due_gastro == "2027-04-22"

    due_dock = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="人間ドック(胃カメラ、腹部超音波を含む)",
        status_flag="CLEAR",
    )
    assert due_dock == "2027-04-22"


def test_explicit_suggested_interval_override() -> None:
    """医師の個別指定年数（suggested_interval_years）によらず設定された受診頻度で管理されることを検証。"""
    due_override = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="大腸カメラ",
        status_flag="CLEAR",
        raw_comment="",
        suggested_interval_years=3.0,
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
        modality="大腸カメラ",
        target_region="全大腸",
        clinic_name="青葉台かなざわ内科・内視鏡クリニック",
        status_flag="CLEAR",
        primary_findings="外痔核のみ",
        pdf_page=1,
    )
    ledger_item = derive_organ_ledger_update(event, "2031-09-16")
    assert ledger_item.organ == "大腸"
    assert ledger_item.last_exam_date == "2026-09-16"
    assert "CLEAR" in ledger_item.current_status
    assert ledger_item.next_action_due == "2031-09-16"


def test_recall_engine_uncovered_branches() -> None:
    """未網羅ブランチ（端数年数、超音波、各モダリティの要精検、未定義部位）を検証。"""
    due_half = compute_dynamic_next_due("2026-01-01", "DWIBS", "CLEAR", base_intervals={"DWIBS": 1.5})
    assert due_half.startswith("2027-")

    due_echo = compute_dynamic_next_due("2026-05-10", "腹部エコー", "CLEAR")
    assert due_echo == "2027-05-10"

    due_us = compute_dynamic_next_due("2026-05-10", "超音波", "BENIGN_STABLE")
    assert due_us == "2027-05-10"

    due_other = compute_dynamic_next_due("2026-05-10", "PET-CT", "CLEAR")
    assert due_other == "2027-05-10"

    due_colon_action = compute_dynamic_next_due("2026-05-10", "大腸カメラ", "ACTION_REQUIRED")
    assert due_colon_action == "2031-05-10"

    due_brain_action = compute_dynamic_next_due("2026-05-10", "脳MRI/MRA", "ACTION_REQUIRED")
    assert due_brain_action == "2031-05-10"

    due_dwibs_action = compute_dynamic_next_due("2026-05-10", "DWIBS", "WATCH_SHORTENED")
    assert due_dwibs_action == "2028-05-10"

    # 2028年以前の心臓CT
    due_ct_pre2028 = compute_dynamic_next_due("2026-05-10", "胸腹部CT", "ACTION_REQUIRED")
    assert due_ct_pre2028 == "2028-04-01"

    # 各種部位マッピング
    for reg, expected_organ in [
        ("全身", "全身"),
        ("胸腹部", "肝臓"),
        ("胃", "胃"),
        ("上部消化管", "胃"),
        ("腹部", "肝臓"),
        ("心臓", "心臓"),
        ("未知の部位", "未知の部位"),
    ]:
        ev = ImagingEventPayload(
            exam_date="2026-05-10",
            modality="腹部エコー",
            target_region=reg,
            clinic_name="クリニック",
            status_flag="CLEAR",
            primary_findings="所見なし",
        )
        assert derive_organ_ledger_update(ev, "2027-05-10").organ == expected_organ


def test_build_managed_timeline() -> None:
    """5大管理項目が完全に包含・集約され、未受診項目も含め常に5行生成されることを検証。"""
    from datetime import date

    from src.recall_engine import build_managed_timeline

    current_test_date = date(2026, 10, 25)

    sample_events = [
        {
            "modality": "胃カメラ",
            "exam_date": "2026-04-22",
            "dynamic_next_due": "2027-04-22",
            "status_flag": "CLEAR",
            "target_region": "胃",
            "clinic_name": "medock",
            "primary_findings": "胃底腺ポリープ",
        },
        {
            "modality": "定期健康診断",
            "exam_date": "2026-04-22",
            "dynamic_next_due": "2027-04-22",
            "status_flag": "CLEAR",
            "target_region": "全身",
            "clinic_name": "medock",
            "primary_findings": "年次健診",
        },
        {
            "modality": "脳MRI/MRA",
            "exam_date": "2026-04-22",
            "dynamic_next_due": "2031-04-22",
            "status_flag": "BENIGN_STABLE",
            "target_region": "脳",
            "clinic_name": "medock",
            "primary_findings": "透明中隔腔",
        },
        {
            "modality": "大腸内視鏡",
            "exam_date": "2026-09-16",
            "dynamic_next_due": "2031-09-16",
            "status_flag": "CLEAR",
            "target_region": "全大腸",
            "clinic_name": "かなざわ内科",
            "primary_findings": "外痔核のみ",
        },
        {
            "modality": "DWIBS",
            "exam_date": "2026-05-02",
            "dynamic_next_due": "2028-05-02",
            "status_flag": "CLEAR",
            "target_region": "全身",
            "clinic_name": "きくち総合",
            "primary_findings": "異常なし",
        },
    ]

    timeline = build_managed_timeline(sample_events, current_date=current_test_date)
    assert len(timeline) == 5

    names = [item.modality for item in timeline]
    assert names == [
        "人間ドック(胃カメラ、腹部超音波を含む)",
        "脳MRI/MRA",
        "大腸カメラ",
        "DWIBS",
        "心臓CT",
    ]

    # 人間ドック（健診・胃カメラが統合。2027-04-22まで179日 -> 半年以内）
    dock_item = timeline[0]
    assert dock_item.last_exam_date == "2026-04-22"
    assert dock_item.dynamic_next_due == "2027-04-22"
    assert dock_item.alert_category == "半年以内に受診推奨"

    # 大腸カメラ（5年後）
    colon_item = timeline[2]
    assert colon_item.last_exam_date == "2026-09-16"
    assert colon_item.dynamic_next_due == "2031-09-16"
    assert colon_item.alert_category == "受診間隔内 (順調)"

    # 心臓CT（未受診、2026年時点では待機）
    heart_item = timeline[4]
    assert heart_item.last_exam_date is None
    assert heart_item.dynamic_next_due == "2028-04-01"
    assert heart_item.alert_category == "受診開始待機"


def test_compute_dynamic_next_due_custom_intervals() -> None:
    """カスタム基準インターバルが渡された場合にその年数が次回推奨日に適用されることを検証。"""
    from src.models import MANAGED_BASE_INTERVALS, ManagedInspectionType

    custom_intervals: dict[ManagedInspectionType, float] = dict(MANAGED_BASE_INTERVALS)
    custom_intervals["脳MRI/MRA"] = 3.0
    custom_intervals["大腸カメラ"] = 7.0
    custom_intervals["DWIBS"] = 1.5

    # 脳MRI/MRA -> 3年
    due_brain = compute_dynamic_next_due(
        exam_date_str="2026-04-22",
        modality="脳MRI/MRA",
        status_flag="CLEAR",
        base_intervals=custom_intervals,
    )
    assert due_brain == "2029-04-22"

    # 大腸カメラ -> 7年
    due_colon = compute_dynamic_next_due(
        exam_date_str="2026-09-16",
        modality="大腸カメラ",
        status_flag="CLEAR",
        base_intervals=custom_intervals,
    )
    assert due_colon == "2033-09-16"

    # 短縮所見がある場合でも設定されたカスタム受診間隔（7年）が維持される
    due_watch = compute_dynamic_next_due(
        exam_date_str="2026-09-16",
        modality="大腸カメラ",
        status_flag="WATCH_SHORTENED",
        base_intervals=custom_intervals,
    )
    assert due_watch == "2033-09-16"
