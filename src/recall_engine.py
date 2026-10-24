from __future__ import annotations

from datetime import date, datetime

from src.models import ImagingEventPayload, OrganLedgerItem


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
) -> str:
    """検査所見・医師コメント・モダリティに基づき次回推奨日(YYYY-MM-DD)を動的算出。

    Args:
        exam_date_str: 検査日 (YYYY-MM-DD)
        modality: 検査種別 ('大腸内視鏡', '脳MRI/MRA', 'DWIBS', '胸腹部CT', '胃カメラ', '腹部エコー' 等)
        status_flag: 所見判定 ('CLEAR', 'BENIGN_STABLE', 'WATCH_SHORTENED', 'ACTION_REQUIRED')
        raw_comment: 医師の所見コメント
        suggested_interval_years: 医師指定の次回インターバル年数（優先）

    Returns:
        動的に算出された次回推奨日文字列 (YYYY-MM-DD)
    """
    exam_dt = datetime.strptime(exam_date_str, "%Y-%m-%d").date()

    if suggested_interval_years is not None and suggested_interval_years > 0:
        return _add_years(exam_dt, suggested_interval_years).strftime("%Y-%m-%d")

    has_one_year_recall = any(kw in raw_comment for kw in ["1年後", "１年後", "1年", "毎年"])

    if modality == "大腸内視鏡":
        if status_flag == "CLEAR":
            return _add_years(exam_dt, 3.0).strftime("%Y-%m-%d")
        if status_flag == "WATCH_SHORTENED":
            return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")
        return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")

    if modality == "脳MRI/MRA":
        if status_flag == "CLEAR":
            return _add_years(exam_dt, 3.0).strftime("%Y-%m-%d")
        if status_flag == "BENIGN_STABLE" and has_one_year_recall:
            return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")
        if status_flag == "BENIGN_STABLE":
            return _add_years(exam_dt, 3.0).strftime("%Y-%m-%d")
        return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")

    if modality == "DWIBS":
        if status_flag == "CLEAR":
            return _add_years(exam_dt, 2.0).strftime("%Y-%m-%d")
        return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")

    if modality == "胸腹部CT":
        if status_flag in ("CLEAR", "BENIGN_STABLE"):
            return _add_years(exam_dt, 3.0).strftime("%Y-%m-%d")
        return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")

    if modality in ("胃カメラ", "上部消化管内視鏡"):
        return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")

    if modality in ("腹部エコー", "超音波"):
        return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")

    return _add_years(exam_dt, 1.0).strftime("%Y-%m-%d")


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
    }
    organ_key = region_mapping.get(event.target_region, event.target_region)
    return OrganLedgerItem(
        organ=organ_key,
        last_exam_date=event.exam_date,
        current_status=f"{event.primary_findings} ({event.status_flag})",
        next_action_due=dynamic_next_due,
    )
