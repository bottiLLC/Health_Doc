from __future__ import annotations

from google import genai
from google.genai import types

from src.config import get_gemini_api_key
from src.models import HealthDocExtractionResult

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
   - 生化学メトリクス群は checkup_data.metrics に抽出してください。複数年（前回・前々回）の記載がある場合、今回（最新の検査日）の数値を優先して抽出してください。
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


def extract_health_doc_from_pdf(
    pdf_bytes: bytes,
    api_key: str | None = None,
) -> HealthDocExtractionResult:
    """Gemini 2.5 Flash の Structured Outputs を利用してPDFから健康診断データを抽出。

    Args:
        pdf_bytes: PDFファイルの生バイトデータ
        api_key: Gemini APIキー（未指定時は環境変数またはsecretsから自動解決）

    Returns:
        HealthDocExtractionResult: パースされた構造化データ

    Raises:
        ValueError: APIキーが未設定の場合
        RuntimeError: Gemini API呼び出しまたはパース失敗時
    """
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
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        pdf_part,
                        types.Part.from_text(
                            text="この健康診断・検査レポートPDFを解析し、スキーマに従ってJSONを出力してください。"
                        ),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=EXTRACTION_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=HealthDocExtractionResult,
                temperature=0.1,
            ),
        )

        response_text = response.text
        if not response_text:
            raise RuntimeError("Gemini APIから空の応答が返却されました。")

        return HealthDocExtractionResult.model_validate_json(response_text)

    except Exception as e:
        raise RuntimeError(f"Gemini APIによるPDF解析中にエラーが発生しました: {e!s}") from e
