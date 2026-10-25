from __future__ import annotations

import re

import pydantic
from google import genai
from google.genai import types

from src.config import get_gemini_api_key
from src.models import HealthDocExtractionResult, normalize_metric_name

EXTRACTION_SYSTEM_INSTRUCTION = """
あなたは医療文書・健康診断報告書・画像診断レポートの解析を行う専門AIです。
入力されたPDFの内容を精査し、指定されたJSONスキーマに従って厳密に構造化抽出を行ってください。

【抽出ルール】
1. 書類種別の判別:
   - 総合健診・人間ドック（血液・尿・生化学データが主体のもの）: doc_type = "ANNUAL_CHECKUP"
   - 単一の画像・内視鏡・生理検査レポート（CT, DWIBS, 大腸内視鏡, MRI単体等）: doc_type = "IMAGING_EVENT"
2. 日付の西暦統一:
   - 検査日は必ず YYYY-MM-DD 形式に統一してください。
   - 令和などの和暦表記は西暦に変換してください（例: 令和08年05月02日 -> 2026-05-02）。
3. 複合ドック（人間ドック結果報告書等）の処理:
   - 生化学メトリクス群（数値測定値）は checkup_data.metrics に抽出してください。複数年（前回・前々回）の記載がある場合、今回（最新の検査日）の数値を優先して抽出してください。
   - 数値を持たない定性検査や各科判定結果・所見は checkup_data.qualitative_items に漏れなく抽出してください:
     - 聴力: 各周波数（1000Hz, 4000Hz 左右）の所見（「所見なし」等）および聴力科判定。
     - 眼底: Scheie分類（S/H）、改変Davis分類、所見（「異常なし」等）、眼底科判定。
     - 視力: 矯正/裸眼所見および視力科判定。
     - 尿検査: 蛋白、潜血の定性記号（「-」等）および尿検査科判定。
     - 便潜血: 1回目、2回目の定性記号（「-」等）および便潜血科判定。
     - 診察: 内科診療所見（「今回の診察では異常ありません」等）および診察科判定。
     - 心臓・胸部: 心電図所見、胸部X線所見および各科判定。
     - 各科判定一覧表（総合判定、身体計測、血圧、視力、眼底、眼圧、聴力、血液学、脂質、糖代謝、肝機能、肝炎、腎機能、痛風、尿検査、免疫、胸部、肺機能、上部消化管、便潜血、腹部、心臓、頭部）に記載された大分類判定は is_category_summary = True として抽出してください。
   - ドック内に含まれる精密画像・内視鏡検査（例: 上部消化管内視鏡/胃カメラ、頭部MRI/MRA、腹部超音波など）は、embedded_imaging_events に個別の ImagingEventPayload としてすべて抽出してください。
   - 各画像検査が記載されている元のPDFページ番号（1-indexed）を必ず pdf_page に設定してください。
4. 単一画像検査の処理:
   - imaging_data に詳細を設定してください。
   - status_flag は以下から厳密に選択してください:
     - CLEAR: 異常所見なし、正常範囲内、または外痔核などの病的意義のない軽微所見
     - BENIGN_STABLE: 肝嚢胞、胃底腺ポリープ、正常変異（透明中隔腔・ベルガ腔）などの良性確定・安定所見
     - WATCH_SHORTENED: ポリープ切除後や1〜2年後の短縮再検が推奨される所見
     - ACTION_REQUIRED: 要精密検査、要受診、悪性疑い等
"""


def _clean_json_text(raw_text: str) -> str:
    """Markdownコードブロックフェンス等を除去し、純粋なJSON文字列を抽出。"""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _normalize_extracted_metrics(result: HealthDocExtractionResult) -> HealthDocExtractionResult:
    """抽出された生化学メトリクスの項目名を標準クランプ辞書で正規化。"""
    if result.checkup_data and result.checkup_data.metrics:
        for item in result.checkup_data.metrics:
            item.metric_name = normalize_metric_name(item.metric_name)
    return result


def extract_health_doc_from_pdf(
    pdf_bytes: bytes,
    api_key: str | None = None,
) -> HealthDocExtractionResult:
    """Gemini 3.8 Flash (thinking_level: medium) の Structured Outputs を利用してPDFから健康診断データを抽出。

    Args:
        pdf_bytes: PDFファイルの生バイトデータ
        api_key: Gemini APIキー（未指定時は環境変数またはsecretsから自動解決）

    Returns:
        HealthDocExtractionResult: パースおよび正規化済みの構造化データ

    Raises:
        ValueError: PDFデータが空またはAPIキーが未設定の場合
        RuntimeError: Gemini API呼び出しまたはスキーマ検証失敗時
    """
    if not pdf_bytes:
        raise ValueError("PDFデータが空です。有効なPDFバイナリを指定してください。")

    resolved_key = api_key or get_gemini_api_key()
    if not resolved_key:
        raise ValueError(
            "Gemini APIキーが設定されていません。環境変数 GEMINI_API_KEY または Streamlit secrets に設定してください。"
        )

    client = genai.Client(api_key=resolved_key)

    pdf_part = types.Part.from_bytes(
        data=pdf_bytes,
        mime_type="application/pdf",
    )

    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=types.Content(
                role="user",
                parts=[
                    pdf_part,
                    types.Part.from_text(text="健康診断・検査レポートPDFから指示に従ってデータを抽出してください。"),
                ],
            ),
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MEDIUM),
                system_instruction=EXTRACTION_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=HealthDocExtractionResult,
                temperature=0.0,
            ),
        )

        # 1. SDKネイティブの parsed を優先評価
        if isinstance(response.parsed, HealthDocExtractionResult):
            return _normalize_extracted_metrics(response.parsed)

        if isinstance(response.parsed, dict):
            parsed_model = HealthDocExtractionResult.model_validate(response.parsed)
            return _normalize_extracted_metrics(parsed_model)

        # 2. parsed が None の場合のフォールバック（マークダウンフェンス除去と model_validate_json）
        raw_text = response.text
        if not raw_text or not raw_text.strip():
            raise RuntimeError("Gemini APIから空の応答が返却されました。")

        cleaned_text = _clean_json_text(raw_text)
        validated = HealthDocExtractionResult.model_validate_json(cleaned_text)
        return _normalize_extracted_metrics(validated)

    except pydantic.ValidationError as e:
        raise RuntimeError(f"Gemini APIによるPDF構造化抽出中にスキーマ検証エラーが発生しました: {e!s}") from e
    except (ValueError, RuntimeError):
        raise
    except Exception as e:
        raise RuntimeError(f"Gemini APIによるPDF構造化抽出中にエラーが発生しました: {e!s}") from e
