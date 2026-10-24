from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config import (
    ensure_directories,
    generate_pdf_filename,
    get_gemini_api_key,
    sanitize_filename_part,
)


def test_ensure_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """データ保存用ディレクトリが未存在時に作成されることを検証。"""
    import src.config as cfg

    test_data = tmp_path / "data"
    test_pdf = test_data / "pdfs"

    monkeypatch.setattr(cfg, "DATA_DIR", test_data)
    monkeypatch.setattr(cfg, "PDF_DIR", test_pdf)

    assert not test_data.exists()
    assert not test_pdf.exists()

    ensure_directories()

    assert test_data.exists()
    assert test_pdf.exists()


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("Clinic:A/B\\C*D?E<F>G|H I", "ClinicABCDEFGHI"),
        ("東京 健診 クリニック", "東京健診クリニック"),
        ("CleanClinic123", "CleanClinic123"),
        ("", ""),
    ],
)
def test_sanitize_filename_part(input_text: str, expected: str) -> None:
    """ファイル名として使用不可な記号および空白が除去されることを検証。"""
    assert sanitize_filename_part(input_text) == expected


def test_generate_pdf_filename_single_modality() -> None:
    """単一検査のPDFファイル名生成規則を検証。"""
    res1 = generate_pdf_filename("2026-05-10", "脳MRI/MRA", "銀座 クリニック", is_annual=False)
    assert res1 == "20260510_脳MRIMRA_銀座クリニック.pdf"

    res2 = generate_pdf_filename("2026/11/03", "大腸内視鏡", "新宿消化器内科", is_annual=False)
    assert res2 == "20261103_大腸内視鏡_新宿消化器内科.pdf"


def test_generate_pdf_filename_annual() -> None:
    """人間ドック・年次健診のPDFファイル名生成規則を検証。"""
    res = generate_pdf_filename("2026-04-15", "総合健診", "東京ミッドタウンクリニック", is_annual=True)
    assert res == "20260415_ANNUAL_東京ミッドタウンクリニック.pdf"


def test_get_gemini_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数からのAPIキー取得を最優先として解決することを検証。"""
    monkeypatch.setenv("GEMINI_API_KEY", "env_secret_key_12345  ")
    key = get_gemini_api_key()
    assert key == "env_secret_key_12345"


def test_get_gemini_api_key_from_streamlit_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数未設定時にStreamlit secretsから取得することを検証。"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    fake_st = MagicMock()
    fake_st.secrets = {"GEMINI_API_KEY": "streamlit_secret_key_9999"}
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    key = get_gemini_api_key()
    assert key == "streamlit_secret_key_9999"


def test_get_gemini_api_key_empty_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streamlit secrets が空文字の場合に None を返却することを検証。"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    fake_st = MagicMock()
    fake_st.secrets = {"GEMINI_API_KEY": "   "}
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    key = get_gemini_api_key()
    assert key is None


def test_get_gemini_api_key_exception_handled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streamlit 参照時に例外が発生しても安全に None へフォールバックすることを検証。"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    fake_st = MagicMock()
    type(fake_st).secrets = property(lambda self: (_ for _ in ()).throw(RuntimeError("Secrets unavailable")))
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    key = get_gemini_api_key()
    assert key is None


def test_get_gemini_api_key_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数・secretsのいずれにもキーが存在しない場合にNoneを返却することを検証。"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    fake_st = MagicMock()
    fake_st.secrets = {}
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    key = get_gemini_api_key()
    assert key is None
