# Public Repository Security & License Invariants (Health CMMS)

## 1. Protected Health Information (PHI) & Data Leak Prevention
- **Absolute Exclusion of Dynamic & Clinical Artifacts**:
  - 本システムは個人健康診断記録、内視鏡・CT・MRI画像診断所見、および時系列生化学データを扱う。
  - いかなる理由があっても、以下のファイルを Git 追跡対象（インデックスおよびコミット履歴）に含めることを固く禁じる：
    - `./data/health_cmms.db` およびすべての SQLite 関連ファイル（`*.db-wal`, `*.db-shm` 等）
    - `./data/pdfs/*.pdf`（受診者の生データPDF、内視鏡画像、診断レポート等）
    - `./data/backup_config.json`（ローカル環境依存パス設定）
    - `./backups/*.zip`（自動生成されたバックアップアーカイブ）
  - リポジトリのクローン直後に正常稼働できるよう、ディレクトリ維持用の `data/.gitkeep` および `data/pdfs/.gitkeep` のみが追跡を許可される。
- **Force Add 禁止**:
  - `git add -f` や `.gitignore` をバイパスするステージング操作を恒久的に禁止する。
  - テストおよびデモは、完全に合成・匿名化されたコード上のフィクスチャ（`src/seed_data.py`）のみを使用すること。

## 2. Secrets & API Credential Zero-Exposure
- **APIキーのハードコード厳禁**:
  - `GEMINI_API_KEY` をはじめとする機密情報は、ソースコード、Markdownドキュメント、コミットメッセージに一切記述してはならない。
  - 認証情報は常に `os.getenv("GEMINI_API_KEY")` または `.gitignore` された `.streamlit/secrets.toml` からのみ実行時に動的注入すること。

## 3. MIT License & Open Source Compliance
- **ライセンス遵守**:
  - 本プロジェクトの全ソースコードは MIT License に基づき公開される。
  - リポジトリルートに `LICENSE`（MIT License）を常時維持し、`README.md` にライセンスバッジを掲示すること。
  - コミット前に `git status` を確認し、意図しない個人データやバイナリがステージングされていないことを検証すること。
