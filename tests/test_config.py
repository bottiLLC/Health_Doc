from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import (
    clear_gemini_api_key,
    ensure_directories,
    generate_pdf_filename,
    get_gemini_api_key,
    get_managed_intervals,
    load_settings,
    reset_managed_intervals,
    sanitize_filename_part,
    save_settings,
    set_gemini_api_key,
    set_managed_intervals,
)


@pytest.fixture(autouse=True)
def isolate_settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """テスト実行時に実環境の settings.json に影響を与えないよう一時ディレクトリへ隔離。"""
    import src.config as cfg

    fake_settings = tmp_path / "settings.json"
    monkeypatch.setattr(cfg, "SETTINGS_FILE", fake_settings)


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


def test_load_settings_non_existent() -> None:
    """settings.json が存在しない場合に空辞書を返却することを検証。"""
    assert load_settings() == {}


def test_load_settings_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """settings.json から正しく設定辞書を読み込めることを検証。"""
    import src.config as cfg

    target = tmp_path / "custom_settings.json"
    target.write_text(json.dumps({"gemini_api_key": "AIzaTest", "theme": "dark"}), encoding="utf-8")
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    loaded = load_settings()
    assert loaded == {"gemini_api_key": "AIzaTest", "theme": "dark"}


def test_load_settings_corrupted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """破損したJSONファイルが存在する場合に安全に空辞書を返却することを検証。"""
    import src.config as cfg

    target = tmp_path / "corrupt_settings.json"
    target.write_text("INVALID_JSON{", encoding="utf-8")
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    assert load_settings() == {}


def test_load_settings_non_dict_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """JSONトップレベルが辞書でない（リスト等）の場合に空辞書を返却することを検証。"""
    import src.config as cfg

    target = tmp_path / "list_settings.json"
    target.write_text(json.dumps(["item1", "item2"]), encoding="utf-8")
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    assert load_settings() == {}


def test_save_settings_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """設定の保存が正常に行われ、ファイルが書き込まれることを検証。"""
    import src.config as cfg

    target = tmp_path / "sub" / "settings.json"
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    success = save_settings({"key": "value"})
    assert success is True
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"key": "value"}


def test_save_settings_oserror() -> None:
    """保存先作成時にOSErrorが発生した場合にFalseを返却することを検証。"""
    with patch("pathlib.Path.mkdir", side_effect=OSError("Read-only file system")):
        assert save_settings({"key": "value"}) is False


def test_get_gemini_api_key_from_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """data/settings.json に設定されたAPIキーが正しく取得できることを検証。"""
    import src.config as cfg

    target = tmp_path / "settings.json"
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    set_gemini_api_key("settings_secret_key_123")
    assert get_gemini_api_key() == "settings_secret_key_123"


def test_get_gemini_api_key_settings_precedence_over_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """settings.json のAPIキーが環境変数よりも優先して解決されることを検証。"""
    import src.config as cfg

    target = tmp_path / "settings.json"
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    set_gemini_api_key("settings_key_priority")
    monkeypatch.setenv("GEMINI_API_KEY", "env_key_fallback")

    assert get_gemini_api_key() == "settings_key_priority"


def test_clear_gemini_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """APIキーのクリア処理が正しく動作することを検証。"""
    import src.config as cfg

    target = tmp_path / "settings.json"
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    set_gemini_api_key("to_be_deleted")
    assert get_gemini_api_key() == "to_be_deleted"

    success = clear_gemini_api_key()
    assert success is True
    assert get_gemini_api_key() is None

    # すでにキーが存在しない場合のクリアもTrue
    assert clear_gemini_api_key() is True


def test_get_managed_intervals_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """設定ファイルが存在しない場合に基準インターバル（MANAGED_BASE_INTERVALS）を返却することを検証。"""
    import src.config as cfg
    from src.models import MANAGED_BASE_INTERVALS

    target = tmp_path / "empty_settings.json"
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    intervals = get_managed_intervals()
    assert intervals == MANAGED_BASE_INTERVALS


def test_get_managed_intervals_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """設定ファイルにカスタム値が保存されている場合に正しくマージ取得されることを検証。"""
    import src.config as cfg

    target = tmp_path / "custom_intervals_settings.json"
    target.write_text(
        json.dumps(
            {
                "managed_intervals": {
                    "脳MRI/MRA": 3.0,
                    "大腸カメラ": 7.0,
                    "不正キー": 99.0,
                    "人間ドック(胃カメラ、腹部超音波を含む)": -1.0,  # 負数は無視される
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    intervals = get_managed_intervals()
    assert intervals["脳MRI/MRA"] == 3.0
    assert intervals["大腸カメラ"] == 7.0
    assert intervals["人間ドック(胃カメラ、腹部超音波を含む)"] == 1.0  # デフォルト維持
    assert intervals["DWIBS"] == 2.0


def test_set_and_reset_managed_intervals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """受診間隔設定の更新およびデフォルトへのリセットが正常に動作することを検証。"""
    import src.config as cfg
    from src.models import MANAGED_BASE_INTERVALS

    target = tmp_path / "intervals_crud_settings.json"
    monkeypatch.setattr(cfg, "SETTINGS_FILE", target)

    # 1. 更新
    success = set_managed_intervals({"脳MRI/MRA": 2.5, "大腸カメラ": 3.0})
    assert success is True
    updated = get_managed_intervals()
    assert updated["脳MRI/MRA"] == 2.5
    assert updated["大腸カメラ"] == 3.0
    assert updated["DWIBS"] == 2.0

    # 2. リセット
    reset_success = reset_managed_intervals()
    assert reset_success is True
    reverted = get_managed_intervals()
    assert reverted == MANAGED_BASE_INTERVALS
