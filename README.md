# 身体保全マネジメントシステム（Health CMMS）

[![CI Status](https://img.shields.io/badge/CI-Passing-brightgreen.svg)]()
[![Python Version](https://img.shields.io/badge/Python-3.14%20%7C%203.13-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Linter](https://img.shields.io/badge/Ruff-Passed-blue.svg)]()
[![Type Checked](https://img.shields.io/badge/Mypy-Strict-green.svg)]()
[![Coverage](https://img.shields.io/badge/Pytest-86%25%20Branch-brightgreen.svg)]()

予防保全工学アプローチに基づく、年次健診（時系列生化学）と数年周期の非破壊精密画像検査（イベント駆動）の統合マネジメントシステム。

---

## 1. 主要機能
1. **総合保全ダッシュボード**:
   - `dynamic_next_due`（動的次回推奨日）に基づくアラート管理（Overdue / Upcoming / Cruising）。
   - 部位別健全性ステータス元帳（脳、肝臓、大腸、胃、全身）。
   - 検査スパンを示すインスペクション・タイムライン（Altair ガントチャート）。
2. **年次生化学トレンド管理図**:
   - 表記ゆれクランプ辞書（`STANDARD_METRIC_NAMES`）による自動名寄せ。
   - 基準公差バンド（上限・下限破線）を伴う経年折れ線チャート。
3. **部位別カルテ & 検査PDFアーカイブ**:
   - モダリティ検査履歴（所見、判定、医師コメント）の逆時系列表示。
   - 複合ドック該当ページ番号（`pdf_page`）参照 & 原本PDF保存。
4. **データ投入治具**:
   - Gemini 2.5 Flash によるPDF構造化自動抽出（Structured Outputs）。
   - ファイルハッシュ比較による二重呼び出し防止 SessionState キャッシュ。
5. **データ保護・自動バックアップ**:
   - `./data` ディレクトリの自動ZIP圧縮 & `testzip()` 破損検知整合性検証。

---

## 2. ディレクトリ構成
```text
.
├── pyproject.toml             # uv / Ruff / Mypy / Pytest 設定
├── run.bat                    # Windows ワンクリック起動バッチ (CRLF)
├── run.command                # macOS/Linux 起動スクリプト (LF)
├── backup_manager.py          # 標準データバックアップモジュール
├── app.py                     # Streamlit メインエントリポイント
├── src/
│   ├── config.py              # パス定数アンカー・APIキー解決
│   ├── models.py              # Pydantic v2 スキーマ & クランプ辞書
│   ├── database.py            # SQLite DDL & CRUD
│   ├── recall_engine.py       # 動的リコール計算エンジン
│   ├── gemini_extractor.py    # Gemini 2.5 Flash 抽出クライアント
│   ├── seed_data.py           # 実機PDF4種プリセットローダー
│   └── views/
│       ├── dashboard.py       # Tab 1: ダッシュボード
│       ├── vital_trends.py    # Tab 2: 生化学トレンド
│       ├── organ_ledger.py    # Tab 3: 部位別カルテ
│       └── import_jig.py      # Tab 4: データ投入治具
└── data/                      # 永続化データディレクトリ (バックアップ対象)
    ├── health_cmms.db         # SQLite データベース
    └── pdfs/                  # 格納先PDFアーカイブ
```

---

## 3. クイックスタート

### Windows環境
`run.bat` をダブルクリック（uv 自動セットアップからブラウザ起動まで完全自動実行）。

### コマンドライン起動
```bash
# 依存関係同期
uv sync

# アプリケーション起動
uv run streamlit run app.py
```

### ローカル品質検証
```bash
# 静的解析 & フォーマットチェック
uv run ruff check src tests app.py backup_manager.py

# 厳格型検査
uv run mypy --strict src tests app.py backup_manager.py

# 単体テスト & ブランチ網羅率測定
uv run pytest --cov=src --cov-branch --cov-report=term-missing
```

---

## 4. ライセンス
本プロジェクトは [MIT License](LICENSE) の下で公開されています。

