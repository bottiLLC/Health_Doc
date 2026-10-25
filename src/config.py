from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Final

from src.models import MANAGED_BASE_INTERVALS, ManagedInspectionType

# Root project directory
BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent

# Persistent storage directories (under ./data)
DATA_DIR: Final[Path] = BASE_DIR / "data"
PDF_DIR: Final[Path] = DATA_DIR / "pdfs"
DB_PATH: Final[Path] = DATA_DIR / "health_cmms.db"
SETTINGS_FILE: Path = DATA_DIR / "settings.json"


def ensure_directories() -> None:
    """必要なデータ保存ディレクトリ群を確実に初期化。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename_part(text: str) -> str:
    """ファイル名として使用不可能な文字を除去。"""
    return re.sub(r'[\\/*?:"<>|\s]', "", text)


def generate_pdf_filename(
    exam_date: str,
    modality: str,
    clinic_name: str,
    is_annual: bool = False,
) -> str:
    """PDF保存命名規則に従ったファイル名を生成。

    - 単一検査: {YYYYMMDD}_{modality}_{clinic}.pdf
    - 複合健診ドック: {YYYYMMDD}_ANNUAL_{clinic}.pdf
    """
    clean_date = exam_date.replace("-", "").replace("/", "")
    clean_clinic = sanitize_filename_part(clinic_name)
    clean_modality = sanitize_filename_part(modality)

    if is_annual:
        return f"{clean_date}_ANNUAL_{clean_clinic}.pdf"
    return f"{clean_date}_{clean_modality}_{clean_clinic}.pdf"


def load_settings() -> dict[str, Any]:
    """data/settings.json から設定辞書を読み込み。ファイル非存在・破損時は空辞書を返却。"""
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_settings(settings: dict[str, Any]) -> bool:
    """data/settings.json に設定辞書を保存。"""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def get_gemini_api_key() -> str | None:
    """設定ファイル、環境変数および Streamlit secrets から安全に API キーを解決。

    解決優先順位:
    1. data/settings.json ("gemini_api_key")
    2. os.getenv("GEMINI_API_KEY")
    3. st.secrets["GEMINI_API_KEY"] (Streamlit 稼働環境)
    """
    settings = load_settings()
    configured_key = settings.get("gemini_api_key")
    if isinstance(configured_key, str) and configured_key.strip():
        return configured_key.strip()

    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key.strip()

    try:
        import streamlit as st

        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            secret_key = str(st.secrets["GEMINI_API_KEY"]).strip()
            if secret_key:
                return secret_key
    except Exception:
        pass

    return None


def set_gemini_api_key(api_key: str) -> bool:
    """Gemini APIキーを data/settings.json に永続化。"""
    settings = load_settings()
    settings["gemini_api_key"] = api_key.strip()
    return save_settings(settings)


def clear_gemini_api_key() -> bool:
    """data/settings.json から Gemini APIキーを削除。"""
    settings = load_settings()
    if "gemini_api_key" in settings:
        del settings["gemini_api_key"]
        return save_settings(settings)
    return True


def get_managed_intervals() -> dict[ManagedInspectionType, float]:
    """設定ファイルから各検診の受診間隔を読み込み。未設定項目は MANAGED_BASE_INTERVALS へフォールバック。"""
    settings = load_settings()
    configured = settings.get("managed_intervals")
    resolved: dict[ManagedInspectionType, float] = dict(MANAGED_BASE_INTERVALS)
    if isinstance(configured, dict):
        for k, v in configured.items():
            if k in resolved and isinstance(v, (int, float)) and v > 0:
                resolved[k] = float(v)
    return resolved


def set_managed_intervals(intervals: dict[ManagedInspectionType, float] | dict[str, float]) -> bool:
    """各検診の受診間隔を data/settings.json の managed_intervals キーに安全に永続化。"""
    settings = load_settings()
    current = get_managed_intervals()
    for k, v in intervals.items():
        if k in current and isinstance(v, (int, float)) and v > 0:
            current[k] = float(v)
    settings["managed_intervals"] = current
    return save_settings(settings)


def reset_managed_intervals() -> bool:
    """受診間隔設定を初期化し出荷時基準値（MANAGED_BASE_INTERVALS）へ復元。"""
    settings = load_settings()
    if "managed_intervals" in settings:
        del settings["managed_intervals"]
        return save_settings(settings)
    return True
