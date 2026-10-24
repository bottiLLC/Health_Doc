from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from google.genai import types

from src.gemini_extractor import (
    _clean_json_text,
    extract_health_doc_from_pdf,
)
from src.models import (
    HealthDocExtractionResult,
    ImagingEventPayload,
)


def test_clean_json_text() -> None:
    raw_with_fence = '```json\n{"doc_type": "ANNUAL_CHECKUP"}\n```'
    assert _clean_json_text(raw_with_fence) == '{"doc_type": "ANNUAL_CHECKUP"}'

    raw_plain = '{"doc_type": "ANNUAL_CHECKUP"}'
    assert _clean_json_text(raw_plain) == '{"doc_type": "ANNUAL_CHECKUP"}'


def test_extract_empty_pdf_raises_value_error() -> None:
    with pytest.raises(ValueError, match="PDFデータが空です"):
        extract_health_doc_from_pdf(b"", api_key="test-key")


def test_extract_missing_api_key_raises_value_error() -> None:
    with (
        patch("src.gemini_extractor.get_gemini_api_key", return_value=None),
        pytest.raises(ValueError, match="Gemini APIキーが設定されていません"),
    ):
        extract_health_doc_from_pdf(b"%PDF-test", api_key=None)


def test_extract_via_sdk_parsed() -> None:
    sample_payload = HealthDocExtractionResult(
        doc_type="IMAGING_EVENT",
        imaging_data=ImagingEventPayload(
            exam_date="2026-09-21",
            modality="胸腹部CT",
            target_region="胸腹部",
            clinic_name="メディカルクリニック",
            status_flag="BENIGN_STABLE",
            primary_findings="右肺結節（陳旧性変化）",
            raw_comment="1年後に経過観察を推奨",
            pdf_page=1,
            suggested_interval_years=1.0,
        ),
    )

    mock_response = MagicMock(spec=types.GenerateContentResponse)
    mock_response.parsed = sample_payload
    mock_response.text = None

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("src.gemini_extractor.genai.Client", return_value=mock_client):
        result = extract_health_doc_from_pdf(b"%PDF-dummy", api_key="valid-api-key")

    assert result.doc_type == "IMAGING_EVENT"
    assert result.imaging_data is not None
    assert result.imaging_data.modality == "胸腹部CT"
    assert result.imaging_data.status_flag == "BENIGN_STABLE"


def test_extract_via_parsed_dict() -> None:
    dict_payload = {
        "doc_type": "ANNUAL_CHECKUP",
        "checkup_data": {
            "exam_date": "2026-04-22",
            "clinic_name": "総合健診クリニック",
            "metrics": [
                {
                    "category": "肝機能",
                    "metric_name": "ALT(GPT)",
                    "val": 32.0,
                    "unit": "U/L",
                    "ref_min": None,
                    "ref_max": 30.0,
                    "grade": "B",
                }
            ],
        },
        "embedded_imaging_events": [],
    }

    mock_response = MagicMock(spec=types.GenerateContentResponse)
    mock_response.parsed = dict_payload
    mock_response.text = None

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("src.gemini_extractor.genai.Client", return_value=mock_client):
        result = extract_health_doc_from_pdf(b"%PDF-dummy", api_key="valid-api-key")

    assert result.doc_type == "ANNUAL_CHECKUP"
    assert result.checkup_data is not None
    assert len(result.checkup_data.metrics) == 1
    # Check metric normalization
    assert result.checkup_data.metrics[0].metric_name == "ALT"


def test_extract_fallback_raw_text_with_markdown_fence() -> None:
    raw_json_with_fence = """```json
{
  "doc_type": "ANNUAL_CHECKUP",
  "checkup_data": {
    "exam_date": "2026-04-22",
    "clinic_name": "総合健診クリニック",
    "metrics": [
      {
        "category": "糖代謝",
        "metric_name": "HbA1c(NGSP)",
        "val": 5.8,
        "unit": "%",
        "ref_min": null,
        "ref_max": 5.5,
        "grade": "B"
      }
    ],
    "qualitative_items": [
      {
        "category": "聴力",
        "item_name": "1000Hz(右)",
        "finding": "所見なし",
        "grade": "A",
        "details": "",
        "is_category_summary": false
      },
      {
        "category": "総合判定",
        "item_name": "総合判定",
        "finding": "経過観察",
        "grade": "C",
        "details": "",
        "is_category_summary": true
      }
    ]
  },
  "embedded_imaging_events": []
}
```"""

    mock_response = MagicMock(spec=types.GenerateContentResponse)
    mock_response.parsed = None
    mock_response.text = raw_json_with_fence

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("src.gemini_extractor.genai.Client", return_value=mock_client):
        result = extract_health_doc_from_pdf(b"%PDF-dummy", api_key="valid-api-key")

    assert result.doc_type == "ANNUAL_CHECKUP"
    assert result.checkup_data is not None
    # Check metric normalization
    assert result.checkup_data.metrics[0].metric_name == "HbA1c"
    # Check qualitative items
    assert len(result.checkup_data.qualitative_items) == 2
    assert result.checkup_data.qualitative_items[0].category == "聴力"
    assert result.checkup_data.qualitative_items[0].finding == "所見なし"
    assert result.checkup_data.qualitative_items[1].is_category_summary is True


def test_extract_invalid_json_raises_runtime_error() -> None:
    mock_response = MagicMock(spec=types.GenerateContentResponse)
    mock_response.parsed = None
    mock_response.text = "NOT_A_VALID_JSON"

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with (
        patch("src.gemini_extractor.genai.Client", return_value=mock_client),
        pytest.raises(RuntimeError, match="Gemini APIによるPDF構造化抽出中にスキーマ検証エラーが発生しました"),
    ):
        extract_health_doc_from_pdf(b"%PDF-dummy", api_key="valid-api-key")


def test_extract_empty_response_raises_runtime_error() -> None:
    mock_response = MagicMock(spec=types.GenerateContentResponse)
    mock_response.parsed = None
    mock_response.text = "   "

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with (
        patch("src.gemini_extractor.genai.Client", return_value=mock_client),
        pytest.raises(RuntimeError, match="Gemini APIから空の応答が返却されました"),
    ):
        extract_health_doc_from_pdf(b"%PDF-dummy", api_key="valid-api-key")


def test_extract_unexpected_exception_raises_runtime_error() -> None:
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = ConnectionError("Connection refused")

    with (
        patch("src.gemini_extractor.genai.Client", return_value=mock_client),
        pytest.raises(RuntimeError, match="Gemini APIによるPDF構造化抽出中にエラーが発生しました"),
    ):
        extract_health_doc_from_pdf(b"%PDF-dummy", api_key="valid-api-key")
