from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from src.config import DB_PATH, PDF_DIR, ensure_directories
from src.models import (
    ImagingEventPayload,
    OrganLedgerItem,
    QualitativeCheckupItem,
    RegisteredFileRecord,
    VitalMetricItem,
    normalize_metric_name,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS registered_files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT UNIQUE NOT NULL,
    original_name TEXT NOT NULL,
    file_hash TEXT UNIQUE NOT NULL,
    doc_type TEXT NOT NULL,
    exam_date TEXT NOT NULL,
    clinic_name TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    storage_path TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reg_files_date 
ON registered_files(exam_date);

CREATE TABLE IF NOT EXISTS vital_metrics (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    exam_date TEXT NOT NULL,
    category TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    val REAL NOT NULL,
    unit TEXT NOT NULL,
    ref_min REAL,
    ref_max REAL,
    grade TEXT,
    FOREIGN KEY(file_id) REFERENCES registered_files(file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_vital_metrics_date_metric 
ON vital_metrics(metric_name, exam_date);

CREATE INDEX IF NOT EXISTS idx_vital_metrics_file_id 
ON vital_metrics(file_id);

CREATE TABLE IF NOT EXISTS imaging_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    exam_date TEXT NOT NULL,
    modality TEXT NOT NULL,
    target_region TEXT NOT NULL,
    clinic_name TEXT NOT NULL,
    status_flag TEXT NOT NULL CHECK(status_flag IN ('CLEAR', 'BENIGN_STABLE', 'WATCH_SHORTENED', 'ACTION_REQUIRED')),
    primary_findings TEXT NOT NULL,
    raw_comment TEXT,
    pdf_path TEXT,
    pdf_page INTEGER,
    dynamic_next_due TEXT NOT NULL,
    FOREIGN KEY(file_id) REFERENCES registered_files(file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_imaging_events_modality 
ON imaging_events(modality, exam_date);

CREATE INDEX IF NOT EXISTS idx_imaging_events_file_id 
ON imaging_events(file_id);

CREATE TABLE IF NOT EXISTS organ_status_ledger (
    organ TEXT PRIMARY KEY,
    last_exam_date TEXT NOT NULL,
    current_status TEXT NOT NULL,
    next_action_due TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qualitative_checkup_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    exam_date TEXT NOT NULL,
    category TEXT NOT NULL,
    item_name TEXT NOT NULL,
    finding TEXT NOT NULL,
    grade TEXT,
    details TEXT DEFAULT '',
    is_category_summary INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(file_id) REFERENCES registered_files(file_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_qualitative_items_unique 
ON qualitative_checkup_items(exam_date, category, item_name);

CREATE INDEX IF NOT EXISTS idx_qualitative_items_cat_date 
ON qualitative_checkup_items(category, exam_date);

CREATE INDEX IF NOT EXISTS idx_qualitative_items_file_id 
ON qualitative_checkup_items(file_id);
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


def _migrate_db(conn: sqlite3.Connection) -> None:
    """既存テーブルにfile_idカラムが存在しない場合に自動追加。"""
    cursor = conn.cursor()
    tables = ["vital_metrics", "imaging_events", "qualitative_checkup_items"]
    for tbl in tables:
        cursor.execute(f"PRAGMA table_info({tbl})")
        columns = [str(row["name"]) for row in cursor.fetchall()]
        if "file_id" not in columns:
            cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN file_id INTEGER")
    conn.commit()


def _sync_initial_registered_files(
    conn: sqlite3.Connection,
    target_path: Path | str | None = None,
) -> None:
    """起動時に既存PDFファイルとDBレコードを照合しregistered_filesおよびfile_idを初期補完。"""
    # テスト用一時DBなど、本番DB以外の初期化時はローカルPDFの同期を抑止
    if target_path is not None and Path(target_path) != DB_PATH:
        return

    if not PDF_DIR.exists():
        return

    cursor = conn.cursor()
    cursor.execute("SELECT file_name, file_id FROM registered_files")
    existing_map = {str(row["file_name"]): int(row["file_id"]) for row in cursor.fetchall()}

    for pdf_file in PDF_DIR.glob("*.pdf"):
        file_name = pdf_file.name
        if file_name in existing_map:
            continue

        file_bytes = pdf_file.read_bytes()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        file_size = len(file_bytes)

        parts = file_name.replace(".pdf", "").split("_")
        exam_date_str = ""
        if len(parts) >= 1 and len(parts[0]) == 8 and parts[0].isdigit():
            exam_date_str = f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:]}"

        doc_type = "ANNUAL_CHECKUP" if "ANNUAL" in file_name else "SINGLE_IMAGING"
        clinic_name = parts[-1] if len(parts) >= 3 else "医療機関"

        insert_file_sql = """
        INSERT OR IGNORE INTO registered_files (
            file_name, original_name, file_hash, doc_type, exam_date,
            clinic_name, registered_at, file_size, storage_path
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, ?)
        """
        cursor.execute(
            insert_file_sql,
            (
                file_name,
                file_name,
                file_hash,
                doc_type,
                exam_date_str,
                clinic_name,
                file_size,
                str(pdf_file),
            ),
        )
        new_file_id = int(cursor.lastrowid or 0)
        if new_file_id > 0:
            existing_map[file_name] = new_file_id

            if exam_date_str:
                cursor.execute(
                    "UPDATE vital_metrics SET file_id = ? WHERE file_id IS NULL AND exam_date = ?",
                    (new_file_id, exam_date_str),
                )
                cursor.execute(
                    "UPDATE qualitative_checkup_items SET file_id = ? WHERE file_id IS NULL AND exam_date = ?",
                    (new_file_id, exam_date_str),
                )
            cursor.execute(
                "UPDATE imaging_events SET file_id = ? WHERE file_id IS NULL AND (pdf_path LIKE ? OR exam_date = ?)",
                (new_file_id, f"%{file_name}", exam_date_str),
            )

    conn.commit()


def init_db(target_path: Path | str | None = None) -> None:
    """テーブルDDLを実行しデータベーススキーマおよび初期マイグレーションを実行。"""
    with get_db_connection(target_path) as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate_db(conn)
        _sync_initial_registered_files(conn, target_path)
        conn.commit()


def register_file(
    record: RegisteredFileRecord,
    target_path: Path | str | None = None,
) -> int:
    """検査原本ファイルメタデータをregistered_filesへ登録し採番されたfile_idを返却。"""
    insert_sql = """
    INSERT INTO registered_files (
        file_name, original_name, file_hash, doc_type, exam_date,
        clinic_name, registered_at, file_size, storage_path
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            insert_sql,
            (
                record.file_name,
                record.original_name,
                record.file_hash,
                record.doc_type,
                record.exam_date,
                record.clinic_name,
                record.registered_at,
                record.file_size,
                record.storage_path,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)


def fetch_all_registered_files(
    target_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """登録済みファイル一覧をデータ件数集計付きで取得（検査日降順）。"""
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registered_files'")
        if not cursor.fetchone():
            return []

        query = """
        SELECT 
            rf.file_id,
            rf.file_name,
            rf.original_name,
            rf.file_hash,
            rf.doc_type,
            rf.exam_date,
            rf.clinic_name,
            rf.registered_at,
            rf.file_size,
            rf.storage_path,
            (SELECT COUNT(*) FROM vital_metrics vm WHERE vm.file_id = rf.file_id) AS vital_count,
            (SELECT COUNT(*) FROM qualitative_checkup_items qc WHERE qc.file_id = rf.file_id) AS qualitative_count,
            (SELECT COUNT(*) FROM imaging_events ie WHERE ie.file_id = rf.file_id) AS imaging_count
        FROM registered_files rf
        ORDER BY rf.exam_date DESC, rf.file_id DESC
        """
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]



def insert_vital_metrics(
    metrics: list[VitalMetricItem],
    exam_date: str,
    file_id: int | None = None,
    target_path: Path | str | None = None,
) -> int:
    """生化学メトリクス群を標準化処理を適用した上でDBへ一括挿入。"""
    if not metrics:
        return 0

    records: list[tuple[int | None, str, str, str, float, str, float | None, float | None, str | None]] = []
    for item in metrics:
        normalized_name = normalize_metric_name(item.metric_name)
        records.append(
            (
                file_id,
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
        file_id, exam_date, category, metric_name, val, unit, ref_min, ref_max, grade
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    file_id: int | None = None,
    target_path: Path | str | None = None,
) -> int:
    """画像検査イベントを登録し、生成されたevent_idを返却。"""
    insert_sql = """
    INSERT INTO imaging_events (
        file_id, exam_date, modality, target_region, clinic_name, status_flag,
        primary_findings, raw_comment, pdf_path, pdf_page, dynamic_next_due
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            insert_sql,
            (
                file_id,
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
    file_id: int | None = None,
    target_path: Path | str | None = None,
) -> int:
    """定性所見・判定項目群をDBへ一括挿入（UPSERT対応）。"""
    if not items:
        return 0

    insert_sql = """
    INSERT INTO qualitative_checkup_items (
        file_id, exam_date, category, item_name, finding, grade, details, is_category_summary
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(exam_date, category, item_name) DO UPDATE SET
        file_id = excluded.file_id,
        finding = excluded.finding,
        grade = excluded.grade,
        details = excluded.details,
        is_category_summary = excluded.is_category_summary;
    """

    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        rows_to_insert = [
            (
                file_id,
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


def fetch_latest_imaging_events_by_modality(
    target_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """検査種別（モダリティ）・部位ごとに最新の検査日（前回検査日）を持つレコードのみを集約取得。"""
    query = """
    SELECT 
        event_id, file_id, exam_date, modality, target_region, clinic_name,
        status_flag, primary_findings, raw_comment, pdf_path, pdf_page, dynamic_next_due
    FROM (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY modality, target_region 
            ORDER BY exam_date DESC, event_id DESC
        ) AS rn
        FROM imaging_events
    )
    WHERE rn = 1
    ORDER BY dynamic_next_due ASC, exam_date DESC
    """
    with get_db_connection(target_path) as conn:

        cursor = conn.cursor()
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def fetch_latest_exam_for_modality_or_region(
    modality: str,
    target_region: str,
    target_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """指定されたモダリティまたは対象部位の既存の最新検査イベント（前回検査日照合用）を取得。"""
    query = """
    SELECT * FROM imaging_events 
    WHERE modality = ? OR target_region = ?
    ORDER BY exam_date DESC, event_id DESC
    LIMIT 1
    """
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (modality, target_region))
        row = cursor.fetchone()
        return dict(row) if row else None


ORGAN_REGION_MAP: dict[str, str] = {
    "全大腸": "大腸",
    "大腸": "大腸",
    "脳": "脳",
    "全身": "全身",
    "胸腹部": "肝臓",
    "胃": "胃",
    "上部消化管": "胃",
    "腹部": "肝臓",
}


def _execute_rebuild_organ_ledger(conn: sqlite3.Connection) -> None:
    """SQLite接続上で organ_status_ledger を再集計更新。"""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM organ_status_ledger")

    cursor.execute("SELECT * FROM imaging_events ORDER BY exam_date DESC, event_id DESC")
    all_events = [dict(row) for row in cursor.fetchall()]

    latest_by_organ: dict[str, dict[str, Any]] = {}
    for ev in all_events:
        target_region = str(ev.get("target_region", ""))
        organ_key = ORGAN_REGION_MAP.get(target_region, target_region)
        if not organ_key:
            continue
        if organ_key not in latest_by_organ:
            latest_by_organ[organ_key] = ev

    insert_sql = """
    INSERT INTO organ_status_ledger (
        organ, last_exam_date, current_status, next_action_due
    ) VALUES (?, ?, ?, ?)
    """
    for organ_key, ev in latest_by_organ.items():
        summary_status = f"{ev['status_flag']}: {ev['primary_findings']}"
        cursor.execute(
            insert_sql,
            (
                organ_key,
                ev["exam_date"],
                summary_status,
                ev["dynamic_next_due"],
            ),
        )


def rebuild_organ_ledger(
    conn_or_target: sqlite3.Connection | Path | str | None = None,
) -> None:
    """残存する imaging_events から部位別ステータス元帳（organ_status_ledger）を完全再同期・再構築。"""
    if isinstance(conn_or_target, sqlite3.Connection):
        _execute_rebuild_organ_ledger(conn_or_target)
    else:
        with get_db_connection(conn_or_target) as conn:
            _execute_rebuild_organ_ledger(conn)
            conn.commit()


def delete_registered_files_cascade(
    file_ids: list[int],
    target_path: Path | str | None = None,
) -> dict[str, int]:
    """指定された file_id 群に紐付く全DBレコードおよび実体PDFを原子的にカスケード削除し元帳を再同期。"""
    if not file_ids:
        return {"files": 0, "vital_metrics": 0, "qualitative_items": 0, "imaging_events": 0}

    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(file_ids))

        cursor.execute(
            f"SELECT storage_path FROM registered_files WHERE file_id IN ({placeholders})",
            file_ids,
        )
        pdf_paths = [str(row["storage_path"]) for row in cursor.fetchall()]

        cursor.execute(
            f"DELETE FROM vital_metrics WHERE file_id IN ({placeholders})",
            file_ids,
        )
        deleted_vitals = cursor.rowcount

        cursor.execute(
            f"DELETE FROM qualitative_checkup_items WHERE file_id IN ({placeholders})",
            file_ids,
        )
        deleted_qualitative = cursor.rowcount

        cursor.execute(
            f"DELETE FROM imaging_events WHERE file_id IN ({placeholders})",
            file_ids,
        )
        deleted_imaging = cursor.rowcount

        cursor.execute(
            f"DELETE FROM registered_files WHERE file_id IN ({placeholders})",
            file_ids,
        )
        deleted_files = cursor.rowcount

        _execute_rebuild_organ_ledger(conn)
        conn.commit()

        for p in pdf_paths:
            path_obj = Path(p)
            if path_obj.exists():
                with suppress(OSError):
                    path_obj.unlink()

        return {
            "files": deleted_files,
            "vital_metrics": deleted_vitals,
            "qualitative_items": deleted_qualitative,
            "imaging_events": deleted_imaging,
        }


def fetch_organ_ledger(
    target_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """部位別ステータス元帳の全レコードを取得（次回推奨日昇順）。"""
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM organ_status_ledger ORDER BY next_action_due ASC")
        return [dict(row) for row in cursor.fetchall()]

