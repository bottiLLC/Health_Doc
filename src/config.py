from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final

# Root project directory
BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent

# Persistent storage directories (under ./data)
DATA_DIR: Final[Path] = BASE_DIR / "data"
PDF_DIR: Final[Path] = DATA_DIR / "pdfs"
DB_PATH: Final[Path] = DATA_DIR / "health_cmms.db"


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


def get_gemini_api_key() -> str | None:
    """環境変数および Streamlit secrets から安全に API キーを解決。

    解決優先順位:
    1. os.getenv("GEMINI_API_KEY")
    2. st.secrets["GEMINI_API_KEY"] (Streamlit 稼働環境)
    """
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
