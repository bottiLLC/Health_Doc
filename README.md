# パーソナル健康管理システム（Health Management System）

[![CI Status](https://img.shields.io/badge/CI-Passing-brightgreen.svg)]()
[![Python Version](https://img.shields.io/badge/Python-3.14%20%7C%203.13-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Linter](https://img.shields.io/badge/Ruff-Passed-blue.svg)]()
[![Type Checked](https://img.shields.io/badge/Mypy-Strict-green.svg)]()
[![Coverage](https://img.shields.io/badge/Pytest-86%25%20Branch-brightgreen.svg)]()

定期健康診断（時系列血液検査）と数年周期の精密画像・内視鏡検査を統合管理し、最新の所見に応じた次回受診推奨時期を自動案内するパーソナル健康管理システム。

---

## 1. 主要機能
1. **総合健康ダッシュボード**:
   - `dynamic_next_due`（次回推奨受診日）に基づく受診アラート管理（期限超過 / 半年以内 / 順調）。
   - 部位別の健康状態・所見一覧（脳、肝臓、大腸、胃、全身）。
   - 受診間隔と次回スケジュールを示すタイムライン（Altair ガントチャート）。
2. **年次血液・健康診断トレンドグラフ**:
   - 項目名表記ゆれクランプ辞書（`STANDARD_METRIC_NAMES`）による自動名寄せ。
   - 基準値範囲（上限・下限破線）を伴う経年折れ線チャート。
3. **部位別検査カルテ & 検査PDF**:
   - モダリティ検査履歴（所見、判定、医師コメント）の逆時系列表示。
   - 人間ドック内包検査の該当ページ番号（`pdf_page`）参照 & 検査原本PDFダウンロード。
4. **検査結果の取り込み・登録**:
   - Gemini 2.5 Flash によるPDF構造化自動解析（Structured Outputs）。
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
│   ├── recall_engine.py       # 動的受診推奨時期計算エンジン
│   ├── gemini_extractor.py    # Gemini 2.5 Flash 抽出クライアント
│   ├── seed_data.py           # 実機PDF4種プリセットローダー
│   └── views/
│       ├── dashboard.py       # Tab 1: 総合健康ダッシュボード
│       ├── vital_trends.py    # Tab 2: 年次血液・健康診断トレンド
│       ├── organ_ledger.py    # Tab 3: 部位別検査カルテ
│       └── import_jig.py      # Tab 4: 検査結果の取り込み・登録
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
