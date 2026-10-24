from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from src.config import DB_PATH, ensure_directories
from src.models import (
    ImagingEventPayload,
    OrganLedgerItem,
    QualitativeCheckupItem,
    VitalMetricItem,
    normalize_metric_name,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS vital_metrics (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_date TEXT NOT NULL,
    category TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    val REAL NOT NULL,
    unit TEXT NOT NULL,
    ref_min REAL,
    ref_max REAL,
    grade TEXT
);

CREATE INDEX IF NOT EXISTS idx_vital_metrics_date_metric 
ON vital_metrics(metric_name, exam_date);

CREATE TABLE IF NOT EXISTS imaging_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_date TEXT NOT NULL,
    modality TEXT NOT NULL,
    target_region TEXT NOT NULL,
    clinic_name TEXT NOT NULL,
    status_flag TEXT NOT NULL CHECK(status_flag IN ('CLEAR', 'BENIGN_STABLE', 'WATCH_SHORTENED', 'ACTION_REQUIRED')),
    primary_findings TEXT NOT NULL,
    raw_comment TEXT,
    pdf_path TEXT,
    pdf_page INTEGER,
    dynamic_next_due TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_imaging_events_modality 
ON imaging_events(modality, exam_date);

CREATE TABLE IF NOT EXISTS organ_status_ledger (
    organ TEXT PRIMARY KEY,
    last_exam_date TEXT NOT NULL,
    current_status TEXT NOT NULL,
    next_action_due TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qualitative_checkup_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_date TEXT NOT NULL,
    category TEXT NOT NULL,
    item_name TEXT NOT NULL,
    finding TEXT NOT NULL,
    grade TEXT,
    details TEXT DEFAULT '',
    is_category_summary INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_qualitative_items_unique 
ON qualitative_checkup_items(exam_date, category, item_name);

CREATE INDEX IF NOT EXISTS idx_qualitative_items_cat_date 
ON qualitative_checkup_items(category, exam_date);
"""


@contextmanager
def get_db_connection(target_path: Path | str | None = None) -> Generator[sqlite3.Connection]:
    """SQLite 接続をコンテキストマネージャとして安全に管理。"""
    ensure_directories()
    path = Path(target_path) if target_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(target_path: Path | str | None = None) -> None:
    """テーブルDDLを実行しデータベーススキーマを初期化。"""
    with get_db_connection(target_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def insert_vital_metrics(
    metrics: list[VitalMetricItem],
    exam_date: str,
    target_path: Path | str | None = None,
) -> int:
    """生化学メトリクス群を標準化処理を適用した上でDBへ一括挿入。"""
    if not metrics:
        return 0

    records: list[tuple[str, str, str, float, str, float | None, float | None, str | None]] = []
    for item in metrics:
        normalized_name = normalize_metric_name(item.metric_name)
        records.append(
            (
                exam_date,
                item.category,
                normalized_name,
                item.val,
                item.unit,
                item.ref_min,
                item.ref_max,
                item.grade,
            )
        )

    insert_sql = """
    INSERT INTO vital_metrics (
        exam_date, category, metric_name, val, unit, ref_min, ref_max, grade
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.executemany(insert_sql, records)
        conn.commit()
        return cursor.rowcount


def insert_imaging_event(
    payload: ImagingEventPayload,
    dynamic_next_due: str,
    pdf_path: str | None = None,
    target_path: Path | str | None = None,
) -> int:
    """画像検査イベントを登録し、生成されたevent_idを返却。"""
    insert_sql = """
    INSERT INTO imaging_events (
        exam_date, modality, target_region, clinic_name, status_flag,
        primary_findings, raw_comment, pdf_path, pdf_page, dynamic_next_due
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            insert_sql,
            (
                payload.exam_date,
                payload.modality,
                payload.target_region,
                payload.clinic_name,
                payload.status_flag,
                payload.primary_findings,
                payload.raw_comment,
                pdf_path,
                payload.pdf_page,
                dynamic_next_due,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)


def upsert_organ_ledger(
    item: OrganLedgerItem,
    target_path: Path | str | None = None,
) -> None:
    """部位別ステータス元帳（organ_status_ledger）をUPSERT更新。"""
    upsert_sql = """
    INSERT INTO organ_status_ledger (
        organ, last_exam_date, current_status, next_action_due
    ) VALUES (?, ?, ?, ?)
    ON CONFLICT(organ) DO UPDATE SET
        last_exam_date = excluded.last_exam_date,
        current_status = excluded.current_status,
        next_action_due = excluded.next_action_due
    WHERE excluded.last_exam_date >= organ_status_ledger.last_exam_date
    """
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            upsert_sql,
            (
                item.organ,
                item.last_exam_date,
                item.current_status,
                item.next_action_due,
            ),
        )
        conn.commit()


def fetch_all_vital_metrics(
    metric_name: str | None = None,
    category: str | None = None,
    target_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """生化学メトリクスを取得（項目名および大分類による絞り込み可能、検査日昇順）。"""
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        if category and metric_name:
            norm_name = normalize_metric_name(metric_name)
            cursor.execute(
                "SELECT * FROM vital_metrics WHERE category = ? AND metric_name = ? ORDER BY exam_date ASC",
                (category, norm_name),
            )
        elif metric_name:
            norm_name = normalize_metric_name(metric_name)
            cursor.execute(
                "SELECT * FROM vital_metrics WHERE metric_name = ? ORDER BY exam_date ASC",
                (norm_name,),
            )
        elif category:
            cursor.execute(
                "SELECT * FROM vital_metrics WHERE category = ? ORDER BY exam_date ASC, record_id ASC",
                (category,),
            )
        else:
            cursor.execute("SELECT * FROM vital_metrics ORDER BY exam_date ASC, record_id ASC")
        return [dict(row) for row in cursor.fetchall()]


def fetch_distinct_metric_names(target_path: Path | str | None = None) -> list[str]:
    """登録されているユニークなメトリクス名一覧を取得。"""
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT metric_name FROM vital_metrics ORDER BY metric_name ASC")
        return [str(row["metric_name"]) for row in cursor.fetchall()]


def fetch_distinct_metric_categories(
    target_path: Path | str | None = None,
) -> list[tuple[str, str]]:
    """登録されている (category, metric_name) のユニークなタプル一覧を取得。"""
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT category, metric_name FROM vital_metrics ORDER BY category ASC, metric_name ASC"
        )
        return [(str(row["category"]), str(row["metric_name"])) for row in cursor.fetchall()]


def insert_qualitative_items(
    items: list[QualitativeCheckupItem],
    exam_date: str,
    target_path: Path | str | None = None,
) -> int:
    """定性所見・判定項目群をDBへ一括挿入（UPSERT対応）。"""
    if not items:
        return 0

    insert_sql = """
    INSERT INTO qualitative_checkup_items (
        exam_date, category, item_name, finding, grade, details, is_category_summary
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(exam_date, category, item_name) DO UPDATE SET
        finding = excluded.finding,
        grade = excluded.grade,
        details = excluded.details,
        is_category_summary = excluded.is_category_summary;
    """

    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        rows_to_insert = [
            (
                exam_date,
                item.category.strip(),
                item.item_name.strip(),
                item.finding.strip(),
                item.grade.strip() if item.grade else None,
                item.details.strip() if item.details else "",
                1 if item.is_category_summary else 0,
            )
            for item in items
        ]
        cursor.executemany(insert_sql, rows_to_insert)
        conn.commit()
        return len(rows_to_insert)


def fetch_all_qualitative_items(
    category: str | None = None,
    exam_date: str | None = None,
    is_summary: bool | None = None,
    target_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """定性検査・所見・判定項目を取得。"""
    conditions: list[str] = []
    params: list[Any] = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if exam_date:
        conditions.append("exam_date = ?")
        params.append(exam_date)
    if is_summary is not None:
        conditions.append("is_category_summary = ?")
        params.append(1 if is_summary else 0)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM qualitative_checkup_items {where_clause} ORDER BY exam_date ASC, item_id ASC"

    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def fetch_distinct_qualitative_categories(
    target_path: Path | str | None = None,
) -> list[str]:
    """登録されている定性検査の大分類カテゴリ一覧を取得。"""
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM qualitative_checkup_items ORDER BY category ASC")
        return [str(row["category"]) for row in cursor.fetchall()]


def fetch_all_imaging_events(
    target_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """全画像・精密検査イベントを取得（検査日降順）。"""
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM imaging_events ORDER BY exam_date DESC, event_id DESC")
        return [dict(row) for row in cursor.fetchall()]


def fetch_organ_ledger(
    target_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """部位別ステータス元帳の全レコードを取得（次回推奨日昇順）。"""
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM organ_status_ledger ORDER BY next_action_due ASC")
        return [dict(row) for row in cursor.fetchall()]
