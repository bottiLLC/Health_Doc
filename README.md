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

# 2. 環境変数の設定 (Gemini API利用時)
export GEMINI_API_KEY="your-gemini-api-key"

# 3. アプリケーション起動 (Windowsは run.bat のダブルクリックでも可)
uv run streamlit run app.py
```

## Architecture & Features
- **動的受診推奨時期エンジン (Recall Engine)**: 前回検査日と所見判定ステータス（CLEAR, BENIGN_STABLE, WATCH_SHORTENED, ACTION_REQUIRED）から次回受診日を動的算出し、ガントチャートで可視化。
- **生化学メトリクス名寄せ・時系列分析**: 表記ゆれクランプ辞書（`STANDARD_METRIC_NAMES`）による名寄せと基準値レンジ破線を伴う経年折れ線チャート。
- **マルチモーダル医療ドキュメント構造化抽出**: Gemini 3.8 Flash (`thinking_level: medium`) の Structured Outputs により、人間ドックPDFおよび各科画像レポートから検査値を自動抽出。
- **完全隔離型データ保護 & 整合性検証バックアップ**: `./data` 領域の自動ZIP圧縮、`testzip()` 破損検知、アトミック確定移動ルーチン（`backup_manager.py`）の内蔵。

## Environment Variables
| 環境変数名 | デフォルト値 / サンプル | 必須 | 説明 |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | `""` | 任意 (PDF自動抽出時必須) | Google Gemini API キー。`.streamlit/secrets.toml` でも設定可能。 |
| `BACKUP_DIR` | `./backups` | 任意 | バックアップZIPアーカイブの出力先フォルダパス（Google Drive等の同期パス指定可能）。 |

## Limits & Known Trade-offs
- **個人健康情報（PHI）のローカル限定管理**: SQLite DB (`./data/health_cmms.db`) および PDF原本は Git 除外され、外部クラウドストレージ同期はローカルディレクトリ連携に限定。
- **OCR対応フォーマット**: 抽出対象PDFはテキストレイヤ保持または高品質スキャンを前提とし、著しく解像度が低い手書き文書は手動確認を推奨。
- **次回開発スコープ**: 複数受診者アカウントのマルチプロファイル切り替え、および電子カルテ標準（HL7 FHIR形式）エクスポートの対応。

---

Copyright (c) LLC Bocchi. All rights reserved.
Licensed under the [MIT License](LICENSE).
