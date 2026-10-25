from __future__ import annotations

import streamlit as st

from src.config import (
    clear_gemini_api_key,
    get_gemini_api_key,
    get_managed_intervals,
    load_settings,
    reset_managed_intervals,
    set_gemini_api_key,
    set_managed_intervals,
)
from src.database import recompute_all_dynamic_next_dues
from src.models import (
    MANAGED_BASE_INTERVALS,
    MANAGED_INSPECTION_ITEMS,
    ManagedInspectionType,
)


def render_settings_view() -> None:
    """View 6: システム設定（Gemini APIキー管理および受診間隔カスタマイズ）。"""
    st.subheader("⚙️ システム・受診間隔設定")
    st.caption("Gemini API連携設定および5大管理項目の次回推奨受診インターバル（受診頻度）をカスタマイズ管理します。")

    # -------------------------------------------------------------
    # セクション 1: Gemini API 設定
    # -------------------------------------------------------------
    with st.container(border=True):
        st.markdown("### :material/key: Gemini API 設定")
        st.caption("PDF自動抽出エンジン（Google GenAI SDK）が利用するAPIキーを管理します。")

        saved_settings = load_settings()
        stored_key = saved_settings.get("gemini_api_key")
        resolved_key = get_gemini_api_key()

        if isinstance(stored_key, str) and stored_key.strip():
            st.success("設定先: **`data/settings.json`**（永続化済み・バックアップ対象）")
        elif resolved_key:
            st.info("設定先: **環境変数 / secrets**（実行時参照）")
        else:
            st.warning("設定状態: **未設定**（PDFのAI自動解析には API キーの設定が必要です）")

        api_key_input = st.text_input(
            "Gemini API キー",
            value=stored_key if isinstance(stored_key, str) else "",
            type="password",
            placeholder="AIza...",
            help=(
                "Google AI Studioで取得したAPIキー。data/settings.json に安全に保存され、"
                "外部Gitリポジトリからは除外されます。"
            ),
            key="settings_tab_api_key_input",
        )

        with st.container(horizontal=True, horizontal_alignment="left"):
            if st.button(
                "APIキーを保存",
                icon=":material/save:",
                type="primary",
                width="content",
                key="btn_save_key_tab",
            ):
                clean_key = api_key_input.strip()
                if not clean_key:
                    st.warning("APIキーを入力してください。")
                elif set_gemini_api_key(clean_key):
                    st.success("APIキーを保存しました。")
                    st.rerun()
                else:
                    st.error("APIキーの保存に失敗しました。")

            has_stored_key = bool(isinstance(stored_key, str) and stored_key.strip())
            if has_stored_key and st.button(
                "APIキーを削除",
                icon=":material/delete:",
                width="content",
                key="btn_del_key_tab",
            ):
                if clear_gemini_api_key():
                    st.info("保存済みAPIキーを削除しました。")
                    st.rerun()
                else:
                    st.error("APIキーの削除に失敗しました。")

    st.divider()

    # -------------------------------------------------------------
    # セクション 2: 受診スケジュール管理・検診頻度設定
    # -------------------------------------------------------------
    with st.container(border=True):
        st.markdown("### :material/timer: 受診スケジュール管理・検診頻度設定")
        st.caption(
            "ダッシュボードの次回受診推奨時期（Recall Engine）で用いる各検診・検査の標準受診間隔（年数）を設定します。"
        )

        current_intervals = get_managed_intervals()
        item_descriptions: dict[ManagedInspectionType, str] = {
            "人間ドック(胃カメラ、腹部超音波を含む)": (
                "年次総合血液・定性判定・胃カメラ・腹部超音波を包含する年次包括健診（基準: 1.0年）"
            ),
            "脳MRI/MRA": "頭部・頭蓋内血管病変のスクリーニング検査（基準: 5.0年）",
            "大腸カメラ": "全大腸内視鏡検査・ポリープ予防観察（基準: 5.0年）",
            "DWIBS": "全身がんスクリーニングMR画像検査（基準: 2.0年）",
            "心臓CT": "冠動脈石灰化・心血管疾患リスク精密検査（2028年以降開始、基準: 5.0年）",
        }

        new_intervals: dict[ManagedInspectionType, float] = {}

        st.write("#### 5大管理項目の受診間隔（年数）")
        for item in MANAGED_INSPECTION_ITEMS:
            col_lbl, col_input = st.columns([5, 2])
            default_val = MANAGED_BASE_INTERVALS.get(item, 1.0)
            curr_val = current_intervals.get(item, default_val)

            with col_lbl:
                st.markdown(f"**{item}**")
                st.caption(item_descriptions.get(item, ""))

            with col_input:
                input_val = st.number_input(
                    f"{item} 受診間隔（年）",
                    min_value=0.5,
                    max_value=10.0,
                    value=float(curr_val),
                    step=0.5,
                    format="%.1f",
                    key=f"interval_input_{item}",
                    label_visibility="collapsed",
                )
                new_intervals[item] = float(input_val)

        with st.container(horizontal=True, horizontal_alignment="left"):
            if st.button(
                "受診間隔設定を保存",
                icon=":material/save:",
                type="primary",
                width="content",
                key="btn_save_intervals",
            ):
                if set_managed_intervals(new_intervals):
                    updated_count = recompute_all_dynamic_next_dues()
                    st.cache_data.clear()
                    st.success(f"受診間隔設定を保存しました。（既存検査 {updated_count} 件の次回推奨日を再計算完了）")
                    st.rerun()
                else:
                    st.error("受診間隔設定の保存に失敗しました。")

            if st.button(
                "出荷時デフォルトにリセット",
                icon=":material/restart_alt:",
                width="content",
                key="btn_reset_intervals",
            ):
                if reset_managed_intervals():
                    updated_count = recompute_all_dynamic_next_dues()
                    st.cache_data.clear()
                    st.info(f"出荷時基準値に復元しました。（既存検査 {updated_count} 件の次回推奨日を再計算完了）")
                    st.rerun()
                else:
                    st.error("設定のリセットに失敗しました。")
