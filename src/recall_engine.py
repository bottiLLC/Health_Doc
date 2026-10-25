from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.models import (
    MANAGED_INSPECTION_ITEMS,
    MODALITY_CANONICAL_MAP,
    AlertCategoryType,
    ImagingEventPayload,
    ManagedInspectionType,
    ManagedTimelineEntry,
    OrganLedgerItem,
)


def _add_years(source_date: date, years: float) -> date:
    """指定された年数を安全に加算（閏年2/29の境界調整を含む）。"""
    whole_years = int(years)
    fraction = years - whole_years
    days_to_add = int(round(fraction * 365.25))

    new_year = source_date.year + whole_years
    try:
        calculated_date = source_date.replace(year=new_year)
    except ValueError:
        calculated_date = source_date.replace(year=new_year, day=28)

    if days_to_add > 0:
        calculated_date = date.fromordinal(calculated_date.toordinal() + days_to_add)
    return calculated_date


def compute_dynamic_next_due(
    exam_date_str: str,
    modality: str,
    status_flag: str,
    raw_comment: str = "",
    suggested_interval_years: float | None = None,
    base_intervals: dict[ManagedInspectionType, float] | None = None,
) -> str:
    """検査所見・医師コメント・モダリティに基づき次回推奨日(YYYY-MM-DD)を動的算出。

    Args:
        exam_date_str: 検査日 (YYYY-MM-DD)
        modality: 検査種別 ('大腸カメラ', '脳MRI/MRA', 'DWIBS', '心臓CT', '人間ドック(胃カメラ、腹部超音波を含む)' 等)
        status_flag: 所見判定 ('CLEAR', 'BENIGN_STABLE', 'WATCH_SHORTENED', 'ACTION_REQUIRED')
        raw_comment: 医師の所見コメント
        suggested_interval_years: 医師指定の次回インターバル年数（優先）
        base_intervals: カスタム基準インターバル辞書（未指定時は設定ファイルから取得）

    Returns:
        動的に算出された次回推奨日文字列 (YYYY-MM-DD)
    """
    exam_dt = datetime.strptime(exam_date_str, "%Y-%m-%d").date()

    if suggested_interval_years is not None and suggested_interval_years > 0:
        return _add_years(exam_dt, suggested_interval_years).strftime("%Y-%m-%d")

    from src.config import get_managed_intervals

    intervals = base_intervals if base_intervals is not None else get_managed_intervals()
    canonical = MODALITY_CANONICAL_MAP.get(modality.strip(), "人間ドック(胃カメラ、腹部超音波を含む)")
    has_one_year_recall = any(kw in raw_comment for kw in ["1年後", "１年後", "1年", "毎年"])
    configured_interval = intervals.get(canonical, 1.0)

    if canonical == "大腸カメラ":
        if status_flag == "WATCH_SHORTENED" or has_one_year_recall or status_flag == "ACTION_REQUIRED":
            return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")
        return _add_years(exam_dt, configured_interval).strftime("%Y-%m-%d")

    if canonical == "脳MRI/MRA":
        if status_flag == "WATCH_SHORTENED" or has_one_year_recall or status_flag == "ACTION_REQUIRED":
            return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")
        return _add_years(exam_dt, configured_interval).strftime("%Y-%m-%d")

    if canonical == "DWIBS":
        if status_flag == "CLEAR":
            return _add_years(exam_dt, configured_interval).strftime("%Y-%m-%d")
        return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")

    if canonical == "心臓CT":
        if exam_dt.year < 2028:
            return "2028-04-01"
        return _add_years(exam_dt, configured_interval).strftime("%Y-%m-%d")

    # 人間ドック(胃カメラ、腹部超音波を含む) および内包検査群
    return _add_years(exam_dt, configured_interval).strftime("%Y-%m-%d")


def build_managed_timeline(
    latest_events: list[dict[str, Any]],
    current_date: date | None = None,
) -> list[ManagedTimelineEntry]:
    """登録済み検査群から未受診項目を補完し厳格な5大管理項目タイムラインを構築。

    Args:
        latest_events: 各モダリティの最新イベント辞書リスト
        current_date: 判定基準日（未指定時はシステム当日）

    Returns:
        MANAGED_INSPECTION_ITEMS に準拠した5行固定のDTOリスト
    """
    today = current_date or date.today()

    event_by_canonical: dict[ManagedInspectionType, dict[str, Any]] = {}
    for ev in latest_events:
        raw_mod = str(ev.get("modality", "")).strip()
        can_mod = MODALITY_CANONICAL_MAP.get(raw_mod)
        if not can_mod:
            continue
        existing = event_by_canonical.get(can_mod)
        ev_date = str(ev.get("exam_date", ""))
        if existing is None or ev_date > str(existing.get("exam_date", "")):
            event_by_canonical[can_mod] = ev

    timeline_items: list[ManagedTimelineEntry] = []
    region_defaults: dict[ManagedInspectionType, str] = {
        "人間ドック(胃カメラ、腹部超音波を含む)": "全身・消化器・腹部",
        "脳MRI/MRA": "脳",
        "大腸カメラ": "全大腸",
        "DWIBS": "全身",
        "心臓CT": "心臓・冠動脈",
    }

    for item in MANAGED_INSPECTION_ITEMS:
        matched_ev = event_by_canonical.get(item)
        if matched_ev:
            last_date_str = str(matched_ev.get("exam_date", ""))
            due_str = str(matched_ev.get("dynamic_next_due", ""))
            due_dt = datetime.strptime(due_str, "%Y-%m-%d").date()
            days_rem = (due_dt - today).days

            if item == "心臓CT" and today < date(2028, 1, 1) and due_dt.year == 2028:
                cat: AlertCategoryType = "受診開始待機"
            elif days_rem < 0:
                cat = "受診期限超過"
            elif days_rem <= 180:
                cat = "半年以内に受診推奨"
            else:
                cat = "受診間隔内 (順調)"

            timeline_items.append(
                ManagedTimelineEntry(
                    modality=item,
                    target_region=str(matched_ev.get("target_region", region_defaults[item])),
                    last_exam_date=last_date_str,
                    dynamic_next_due=due_str,
                    status_flag=str(matched_ev.get("status_flag", "CLEAR")),
                    days_remaining=days_rem,
                    alert_category=cat,
                    clinic_name=str(matched_ev.get("clinic_name", "")),
                    primary_findings=str(matched_ev.get("primary_findings", "")),
                )
            )
        else:
            if item == "心臓CT":
                due_dt = date(2028, 4, 1)
                due_str = "2028-04-01"
                cat = "受診開始待機" if today < date(2028, 1, 1) else "受診期限超過"
            else:
                due_dt = today
                due_str = today.strftime("%Y-%m-%d")
                cat = "受診期限超過"

            days_rem = (due_dt - today).days
            timeline_items.append(
                ManagedTimelineEntry(
                    modality=item,
                    target_region=region_defaults[item],
                    last_exam_date=None,
                    dynamic_next_due=due_str,
                    status_flag="ACTION_REQUIRED" if cat == "受診期限超過" else "CLEAR",
                    days_remaining=days_rem,
                    alert_category=cat,
                    clinic_name="未受診",
                    primary_findings="未受診（次回推奨時期を設定済み）",
                )
            )

    return timeline_items


def derive_organ_ledger_update(event: ImagingEventPayload, dynamic_next_due: str) -> OrganLedgerItem:
    """画像検査イベントからTable C(部位別ステータス元帳)への更新エントリを生成。"""
    region_mapping: dict[str, str] = {
        "全大腸": "大腸",
        "大腸": "大腸",
        "脳": "脳",
        "全身": "全身",
        "胸腹部": "肝臓",
        "胃": "胃",
        "上部消化管": "胃",
        "腹部": "肝臓",
        "心臓": "心臓",
        "冠動脈": "心臓",
    }
    organ_key = region_mapping.get(event.target_region, event.target_region)
    return OrganLedgerItem(
        organ=organ_key,
        last_exam_date=event.exam_date,
        current_status=f"{event.primary_findings} ({event.status_flag})",
        next_action_due=dynamic_next_due,
    )
