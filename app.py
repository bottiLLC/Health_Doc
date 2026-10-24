from __future__ import annotations

import sys
from pathlib import Path

# Deterministic sys.path insertion for standalone execution
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from backup_manager import get_backup_dir, run_backup, set_backup_dir
from src.config import DB_PATH, ensure_directories
from src.database import (
    fetch_all_imaging_events,
    fetch_all_qualitative_items,
    fetch_all_vital_metrics,
    init_db,
)
from src.views.dashboard import render_dashboard_view
from src.views.import_jig import render_import_jig_view
from src.views.organ_ledger import render_organ_ledger_view
from src.views.vital_trends import render_vital_trends_view

# Streamlit Page Configuration
st.set_page_config(
    page_title="パーソナル健康管理システム (Health Management System)",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 起動時ディレクトリ・DB初期化
ensure_directories()
init_db()

@st.cache_data
def get_db_summary_counts() -> tuple[int, int, int]:
    """データベース登録件数の集計結果をキャッシュ取得。"""
    return (
        len(fetch_all_vital_metrics()),
        len(fetch_all_qualitative_items()),
        len(fetch_all_imaging_events()),
    )


# -------------------------------------------------------------
# ゾーン1: サイドバー (設定・データ保護バックアップ)
# -------------------------------------------------------------
with st.sidebar:
    st.header("🏥 健康管理システム")
    st.caption("パーソナル健康管理システム v0.1.0")
    st.divider()

    # データベース状態表示
    st.subheader("データ管理状況")
    vital_count, qualitative_count, imaging_count = get_db_summary_counts()
    st.write(f"- データベース: **正常稼働** (`{DB_PATH.name}`)")
    st.write(f"- 登録生化学データ: **{vital_count} 件**")
    st.write(f"- 登録定性・判定項目: **{qualitative_count} 件**")
    st.write(f"- 登録精密画像検査: **{imaging_count} 件**")

    # 標準バックアップマネージャー (Python-backup-script 準拠)
    st.divider()
    st.subheader("データ保護・バックアップ")

    current_dir = str(get_backup_dir())
    new_dir = st.text_input("保存先フォルダ", value=current_dir, help="Google Drive等のローカル同期先パスを指定可能")
    if new_dir != current_dir and st.button("保存先パスを更新", use_container_width=True):
        save_res = set_backup_dir(new_dir)
        if save_res["success"]:
            st.success(str(save_res["message"]))
            st.rerun()
        else:
            st.error(str(save_res["message"]))

    if st.button("今すぐバックアップを実行", use_container_width=True):
        with st.spinner("圧縮・整合性検証中..."):
            res = run_backup(app_name="health_cmms")
        if res["success"]:
            st.success(str(res["message"]))
            st.caption(f"完了日時: {res['timestamp']}")
            st.caption(f"保存先: {res['destination']}")
        else:
            st.error(str(res["message"]))


# -------------------------------------------------------------
# ゾーン2 & 3: メインワークスペース (ヘッダー & タブナビゲーション)
# -------------------------------------------------------------
st.title("🏥 パーソナル健康管理システム（Health Management System）")
st.caption("定期健康診断（時系列血液検査）と精密画像検査の統合管理・次回受診案内システム")

tab_dash, tab_trend, tab_ledger, tab_import = st.tabs(
    [
        "📊 総合健康ダッシュボード",
        "📈 年次血液・健康診断トレンド",
        "🗂️ 部位別検査カルテ & 検査PDF",
        "📥 検査結果の取り込み・登録",
    ]
)

with tab_dash:
    render_dashboard_view()

with tab_trend:
    render_vital_trends_view()

with tab_ledger:
    render_organ_ledger_view()

with tab_import:
    render_import_jig_view()
