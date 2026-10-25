from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backup_manager import get_backup_dir, run_backup, set_backup_dir


def test_get_backup_dir_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """設定ファイルおよび環境変数が存在しない場合のデフォルトパス解決を検証。"""
    import backup_manager

    fake_config = tmp_path / "non_existent_config.json"
    monkeypatch.setattr(backup_manager, "_CONFIG_FILE", fake_config)
    monkeypatch.delenv("BACKUP_DIR", raising=False)

    default_dir = get_backup_dir()
    assert default_dir == backup_manager._DEFAULT_BACKUP_DIR.resolve()


def test_get_backup_dir_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """設定ファイルに記載されたカスタムパスが正しく解決されるかを検証。"""
    import backup_manager

    fake_config = tmp_path / "backup_config.json"
    custom_target = tmp_path / "my_custom_backups"
    fake_config.write_text(json.dumps({"backup_dir": str(custom_target)}), encoding="utf-8")
    monkeypatch.setattr(backup_manager, "_CONFIG_FILE", fake_config)

    resolved = get_backup_dir()
    assert resolved == custom_target.resolve()


def test_get_backup_dir_empty_custom_path_falls_back_to_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """設定ファイル内の backup_dir が空文字列の場合に環境変数へフォールバックすることを検証。"""
    import backup_manager

    fake_config = tmp_path / "empty_dir_config.json"
    fake_config.write_text(json.dumps({"backup_dir": ""}), encoding="utf-8")
    monkeypatch.setattr(backup_manager, "_CONFIG_FILE", fake_config)

    env_target = tmp_path / "env_backups_empty_fallback"
    monkeypatch.setenv("BACKUP_DIR", str(env_target))

    resolved = get_backup_dir()
    assert resolved == env_target.resolve()


def test_get_backup_dir_corrupt_config_falls_back_to_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """設定ファイルが破損している場合に環境変数へフォールバックすることを検証。"""
    import backup_manager

    fake_config = tmp_path / "corrupt_config.json"
    fake_config.write_text("NOT_VALID_JSON{", encoding="utf-8")
    monkeypatch.setattr(backup_manager, "_CONFIG_FILE", fake_config)

    env_target = tmp_path / "env_backups"
    monkeypatch.setenv("BACKUP_DIR", str(env_target))

    resolved = get_backup_dir()
    assert resolved == env_target.resolve()


def test_set_backup_dir_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """有効なパスを指定した場合の設定保存処理を検証。"""
    import backup_manager

    fake_config = tmp_path / "data" / "backup_config.json"
    monkeypatch.setattr(backup_manager, "_CONFIG_FILE", fake_config)

    new_dir = tmp_path / "new_destination"
    res = set_backup_dir(str(new_dir))
    assert res["success"] is True
    assert "バックアップ先を設定しました" in str(res["message"])
    assert fake_config.exists()

    data = json.loads(fake_config.read_text(encoding="utf-8"))
    assert data["backup_dir"] == str(new_dir.resolve())


def test_set_backup_dir_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """無効なパスや権限エラー発生時のエラーハンドリングを検証。"""
    with patch("pathlib.Path.mkdir", side_effect=OSError("Permission Denied")):
        res = set_backup_dir("/invalid/path")
        assert res["success"] is False
        assert "保存先パスが無効" in str(res["message"])


def test_run_backup_empty_or_missing_source(tmp_path: Path) -> None:
    """ソースディレクトリが存在しない、または空の場合のインターロックを検証。"""
    non_existent = tmp_path / "no_such_dir"
    res = run_backup(source_dir=str(non_existent))
    assert res["success"] is False
    assert "バックアップ対象が存在しないか空欄です" in str(res["message"])

    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    res2 = run_backup(source_dir=str(empty_dir))
    assert res2["success"] is False
    assert "バックアップ対象が存在しないか空欄です" in str(res2["message"])


def test_run_backup_destination_mkdir_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """保存先ディレクトリの作成に失敗した場合のエラーハンドリングを検証。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("sample content", encoding="utf-8")

    with patch("pathlib.Path.mkdir", side_effect=OSError("Disk Full")):
        res = run_backup(source_dir=str(source_dir))
        assert res["success"] is False
        assert "保存先フォルダの作成に失敗しました" in str(res["message"])


def test_run_backup_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """アトミックZIP作成、testzip検証、設定ファイル包含および確定移動の正常系を検証。"""
    import backup_manager

    source_dir = tmp_path / "data"
    source_dir.mkdir()
    (source_dir / "record.txt").write_text("health data", encoding="utf-8")
    (source_dir / "settings.json").write_text(json.dumps({"gemini_api_key": "test_key"}), encoding="utf-8")
    sub_dir = source_dir / "pdfs"
    sub_dir.mkdir()
    (sub_dir / "doc.pdf").write_bytes(b"%PDF-1.4\n")

    fake_config = source_dir / "backup_config.json"
    fake_config.write_text(json.dumps({"backup_dir": str(tmp_path / "backups")}), encoding="utf-8")
    monkeypatch.setattr(backup_manager, "_CONFIG_FILE", fake_config)

    backup_dest = tmp_path / "backups"
    monkeypatch.setenv("BACKUP_DIR", str(backup_dest))

    res = run_backup(app_name="test_app", source_dir=str(source_dir))
    assert res["success"] is True
    assert "バックアップ完了" in str(res["message"])
    assert Path(str(res["destination"])).exists()

    # ZIP内に record.txt、backup_config.json、settings.json が漏れなく包含されていることを検証
    import zipfile

    with zipfile.ZipFile(str(res["destination"]), "r") as zf:
        namelist = zf.namelist()
        assert "record.txt" in namelist
        assert "backup_config.json" in namelist
        assert "settings.json" in namelist
        assert any("doc.pdf" in p for p in namelist)


def test_run_backup_corrupted_zip(tmp_path: Path) -> None:
    """testzip による破損検知インターロックを検証。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("data", encoding="utf-8")

    mock_zipfile = MagicMock()
    mock_zipfile.testzip.return_value = "test.txt"

    with patch("zipfile.ZipFile", return_value=mock_zipfile):
        mock_zipfile.__enter__.return_value = mock_zipfile
        res = run_backup(source_dir=str(source_dir))
        assert res["success"] is False
        assert "整合性チェック失敗（破損検知）" in str(res["message"])


def test_run_backup_move_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """確定移動時におけるOSエラー検知を検証。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("data", encoding="utf-8")

    with patch("shutil.move", side_effect=OSError("Permission Denied")):
        res = run_backup(source_dir=str(source_dir))
        assert res["success"] is False
        assert "確定移動に失敗しました" in str(res["message"])
