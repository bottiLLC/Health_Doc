# パーソナル健康管理システム（Health CMMS）

[![CI](https://img.shields.io/badge/CI-Passing-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/Python-3.14%20%7C%203.13-blue.svg)]()
[![Streamlit](https://img.shields.io/badge/Streamlit-1.42.0-FF4B4B.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/badge/Ruff-Passed-blue.svg)]()
[![Mypy](https://img.shields.io/badge/Mypy-Strict-green.svg)]()
[![Coverage](https://img.shields.io/badge/Coverage-100%25%20Branch-brightgreen.svg)]()

## Overview
定期健康診断の時系列血液検査と数年周期の精密画像・内視鏡検査を統合管理し、最新所見に応じた次回推奨受診時期（Recall Engine）を自動案内する健康保全マネジメントシステム。

## Quick Start (TL;DR)
```bash
# 1. 依存関係の同期
uv sync

# 2. アプリケーション起動 (Windowsは run.bat のダブルクリックでも可)
uv run streamlit run app.py
```
> [!TIP]
> Gemini APIキーは起動後、アプリ内の新設「設定」タブから安全に設定・保存できます（環境変数 `GEMINI_API_KEY` による指定も引き続き有効です）。

## Architecture & Features
- **厳格な5大保全管理項目 (Recall Engine)**:
  - **人間ドック(胃カメラ、腹部超音波を含む)**: 基準1年毎（年次血液・定性判定・胃カメラ・腹部超音波を包含一元化）
  - **脳MRI/MRA**: 基準5年毎（ドック内包および単独検査の統合集約）
  - **大腸カメラ**: 基準5年毎（ポリープ切除等の医師指示・短縮所見時は1年後等を動的優先）
  - **DWIBS**: 基準2年毎（全身がんドック）
  - **心臓CT**: 2028年から基準5年毎（2028年開始境界ロジックによる待機制御）
- **「設定」タブによる受診間隔・検診頻度カスタマイズ**:
  - 新設された「設定」タブから、5大管理項目の標準受診間隔（年数）を0.5年単位で自由に調整可能。
  - 設定変更時は既存検査データの次回推奨受診時期（`dynamic_next_due`）および部位別元帳を自動一括再計算。
  - 医師指示（「1年後再検」「要精検」等）が存在する場合は安全短縮インターバルを最優先する医療安全インターロックを完備。
- **生化学メトリクス名寄せ・時系列分析**: 表記ゆれクランプ辞書（`STANDARD_METRIC_NAMES`）による名寄せと基準値レンジ破線を伴う経年折れ線チャート。
- **マルチモーダル医療ドキュメント構造化抽出**: Gemini 3.8 Flash (`thinking_level: medium`) の Structured Outputs により、人間ドックPDFおよび各科画像レポートから検査値を自動抽出。
- **完全隔離型データ保護 & 整合性検証バックアップ**: `./data` 領域の全ユーザーデータ・全設定ファイル（DB, 原本PDF, API設定, 受診間隔設定, バックアップ先設定）の自動ZIP圧縮、`testzip()` 破損検知、アトミック確定移動ルーチン（`backup_manager.py`）の内蔵。

## Settings & Environment Variables
| 設定項目 / 環境変数名 | デフォルト値 / サンプル | 必須 | 説明 |
| :--- | :--- | :--- | :--- |
| `data/settings.json` (`gemini_api_key`) | `""` | 任意 (PDF自動抽出時推奨) | 「設定」タブから永続設定可能なGoogle Gemini API キー。バックアップ対象に含まれます。 |
| `data/settings.json` (`managed_intervals`) | 基準値辞書 | 任意 | 「設定」タブから変更可能な各検診の受診間隔設定（年数）。 |
| `GEMINI_API_KEY` | `""` | 任意 (PDF自動抽出時フォールバック) | 環境変数による Google Gemini API キー。`.streamlit/secrets.toml` でも設定可能。 |
| `BACKUP_DIR` | `./backups` | 任意 | バックアップZIPアーカイブの出力先フォルダパス（UI設定またはGoogle Drive等の同期パス指定可能）。 |

## Limits & Known Trade-offs
- **個人健康情報（PHI）のローカル限定管理**: SQLite DB (`./data/health_cmms.db`) および PDF原本は Git 除外され、外部クラウドストレージ同期はローカルディレクトリ連携に限定。
- **OCR対応フォーマット**: 抽出対象PDFはテキストレイヤ保持または高品質スキャンを前提とし、著しく解像度が低い手書き文書は手動確認を推奨。
- **次回開発スコープ**: 複数受診者アカウントのマルチプロファイル切り替え、および電子カルテ標準（HL7 FHIR形式）エクスポートの対応。

---

Copyright (c) LLC Bocchi. All rights reserved.
Licensed under the [MIT License](LICENSE).
