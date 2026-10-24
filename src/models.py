from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, Field

ModalityType = Literal[
    "大腸内視鏡",
    "脳MRI/MRA",
    "DWIBS",
    "胸腹部CT",
    "胃カメラ",
    "腹部エコー",
    "定期健康診断",
    "その他",
]

StatusFlagType = Literal[
    "CLEAR",
    "BENIGN_STABLE",
    "WATCH_SHORTENED",
    "ACTION_REQUIRED",
]

DocTypeLiteral = Literal[
    "ANNUAL_CHECKUP",
    "IMAGING_EVENT",
]

# 生化学メトリクス標準化クランプ辞書（表記ゆれ吸収用）
STANDARD_METRIC_NAMES: Final[dict[str, list[str]]] = {
    # 肝機能
    "ALT": ["ALT", "ALT(GPT)", "GPT", "ＡＬＴ", "ＡＬＴ（ＧＰＴ）"],
    "AST": ["AST", "AST(GOT)", "GOT", "ＡＳＴ", "ＡＳＴ（ＧＯＴ）"],
    "γ-GTP": ["γ-GTP", "γ-GT", "ガンマGTP", "γーＧＴＰ", "γ-gtp"],
    "ALP": ["ALP", "ＡＬＰ"],
    "CHE": ["CHE", "コリンエステラーゼ", "ＣＨＥ"],
    "LDH": ["LDH", "乳酸脱水素酵素", "ＬＤＨ"],
    "総ビリルビン": ["総ビリルビン", "T-BIL", "総ﾋﾞﾘﾙﾋﾞﾝ"],
    "総蛋白": ["総蛋白", "TP", "総タンパク"],
    "アルブミン": ["アルブミン", "ALB", "ｱﾙﾌﾞﾐﾝ"],
    # 糖代謝
    "HbA1c": ["HbA1c", "HbA1c(NGSP)", "ヘモグロビンA1c", "A1C", "ＨｂＡ１ｃ", "HbA1c（NGSP値）"],
    "空腹時血糖": ["空腹時血糖", "血糖", "FPG", "血糖値"],
    # 脂質
    "LDLコレステロール": ["LDLコレステロール", "LDL-C", "LDL", "悪玉コレステロール", "LDLｺﾚｽﾃﾛｰﾙ"],
    "HDLコレステロール": ["HDLコレステロール", "HDL-C", "HDL", "善玉コレステロール", "HDLｺﾚｽﾃﾛｰﾙ"],
    "中性脂肪": ["中性脂肪", "TG", "トリグリセライド"],
    "総コレステロール": ["総コレステロール", "TC", "総ｺﾚｽﾃﾛｰﾙ"],
    "nonHDL-cho": ["nonHDL-cho", "Non-HDLコレステロール", "non-HDLコレステロール"],
    # 腎・痛風
    "クレアチニン": ["クレアチニン", "CRE", "Cr", "ｸﾚｱﾁﾆﾝ"],
    "e-GFR": ["e-GFR", "eGFR", "e - G F R"],
    "尿素窒素": ["尿素窒素", "BUN"],
    "尿酸": ["尿酸", "UA"],
    # 身体計測
    "体重": ["体重", "Body Weight", "WT"],
    "身長": ["身長", "Height", "HT"],
    "BMI": ["BMI", "ＢＭＩ"],
    "腹囲": ["腹囲", "腹部周囲長", "ウエスト"],
}


def normalize_metric_name(raw_name: str) -> str:
    """生化学メトリクス名の表記ゆれをクランプ辞書に基づき標準キーへ正規化。

    Args:
        raw_name: PDF等から抽出された生の項目名

    Returns:
        正規化された標準項目名（辞書に未登録の場合は前後の空白を除去した生名）
    """
    clean_target = raw_name.strip()
    clean_target_upper = clean_target.upper().replace(" ", "").replace("　", "")

    for standard_name, aliases in STANDARD_METRIC_NAMES.items():
        for alias in aliases:
            clean_alias = alias.upper().replace(" ", "").replace("　", "")
            if clean_target_upper == clean_alias or clean_target_upper.startswith(clean_alias):
                return standard_name

    return clean_target


# 生化学大分類標準化クランプ辞書（表記ゆれ吸収用）
STANDARD_CATEGORY_NAMES: Final[dict[str, list[str]]] = {
    "血液学": ["血液学", "血液学検査", "血液一般", "血算", "血液"],
    "肝機能": ["肝機能", "肝機能検査", "肝・胆", "肝・胆・膵", "肝胆膵", "肝臓"],
    "糖代謝": ["糖代謝", "糖代謝検査", "糖尿病", "糖質", "血糖"],
    "脂質": ["脂質", "脂質代謝", "脂質検査"],
    "腎機能": ["腎機能", "腎機能検査", "腎・尿酸", "腎"],
    "痛風": ["痛風", "尿酸", "痛風・代謝", "痛風・尿酸"],
    "身体計測": ["身体計測", "身体測定", "体格", "計測"],
    "血圧": ["血圧", "血圧測定"],
    "肺機能": ["肺機能", "呼吸機能", "呼吸器"],
    "炎症": ["炎症", "免疫・炎症", "血清学", "免疫血清"],
    "尿検査": ["尿検査", "検尿", "尿・便"],
}


def normalize_category_name(raw_name: str) -> str:
    """生化学大分類名の表記ゆれをクランプ辞書に基づき標準キーへ正規化。

    Args:
        raw_name: PDF等から抽出された生のカテゴリ名

    Returns:
        正規化された標準カテゴリ名（辞書に未登録の場合は前後の空白を除去した生名）
    """
    clean_target = raw_name.strip()
    clean_target_upper = clean_target.upper().replace(" ", "").replace("　", "")

    for standard_name, aliases in STANDARD_CATEGORY_NAMES.items():
        for alias in aliases:
            clean_alias = alias.upper().replace(" ", "").replace("　", "")
            if clean_target_upper == clean_alias or clean_target_upper.startswith(clean_alias):
                return standard_name

    return clean_target


class VitalMetricItem(BaseModel):

    """年次健診の単一測定値モデル（Table A: vital_metrics）。"""

    category: str = Field(description="検査カテゴリ（例: 肝機能, 脂質, 糖代謝, 身体計測, 血液学, 腎機能, 痛風）")
    metric_name: str = Field(description="項目名（例: ALT, AST, HbA1c, LDLコレステロール, 体重）")
    val: float = Field(description="測定値（数値のみ抽出）")
    unit: str = Field(description="単位（例: U/L, mg/dL, %, kg）")
    ref_min: float | None = Field(default=None, description="基準値下限")
    ref_max: float | None = Field(default=None, description="基準値上限")
    grade: str | None = Field(default=None, description="判定記号（A, B, C, D2など）")


class QualitativeCheckupItem(BaseModel):
    """年次健診の定性所見・判定項目モデル（Table: qualitative_checkup_items）。"""

    category: str = Field(
        description="大分類カテゴリ（例: 聴力, 眼底, 視力, 尿検査, 便潜血, 心臓, 胸部, 診察, 総合判定）"
    )
    item_name: str = Field(
        description="検査項目名（例: 聴力判定, 1000Hz(右), 眼底所見, Scheie分類, 改変Davis, 尿蛋白, 便潜血1回目, 総合判定）"
    )
    finding: str = Field(
        description="所見・定性結果（例: 所見なし, 網膜症なし, (-), 正常, 今回の診察では異常ありません）"
    )
    grade: str | None = Field(default=None, description="判定記号（例: A, B, C, D1, D2, E）")
    details: str = Field(default="", description="補足説明・付帯情報（例: 矯正 1.0 / 0.9, 心拍数 59 等）")
    is_category_summary: bool = Field(default=False, description="大分類カテゴリ全体の総合判定レコードか否か")


class AnnualCheckupPayload(BaseModel):
    """年次健診レポートのペイロード。"""

    exam_date: str = Field(description="検査日 (YYYY-MM-DD形式。和暦の場合は西暦換算)")
    clinic_name: str = Field(description="受診医療機関名")
    metrics: list[VitalMetricItem] = Field(default_factory=list, description="健診メトリクス一覧")
    qualitative_items: list[QualitativeCheckupItem] = Field(
        default_factory=list,
        description="定性検査・所見・判定一覧（聴力、眼底、尿定性、便潜血、診察、総合判定等）",
    )


class ImagingEventPayload(BaseModel):
    """画像・内視鏡等の精密検査イベントペイロード（Table B: imaging_events）。"""

    exam_date: str = Field(description="検査日 (YYYY-MM-DD形式。和暦の場合は西暦換算)")
    modality: ModalityType = Field(description="モダリティ種別")
    target_region: str = Field(description="部位（例: 全大腸, 脳, 全身, 胸腹部, 胃, 腹部）")
    clinic_name: str = Field(description="受診医療機関名")
    status_flag: StatusFlagType = Field(description="所見ステータス")
    primary_findings: str = Field(description="主要所見の簡潔な要約（例: 肝嚢胞あり、大腸ポリープなし）")
    raw_comment: str = Field(default="", description="医師の総評・推奨コメントの抜粋")
    pdf_page: int | None = Field(
        default=None,
        description="当該モダリティの所見が記載されているPDFの元ページ番号（1から始まるページ番号）",
    )
    suggested_interval_years: float | None = Field(
        default=None,
        description="医師コメントに明記された次回インターバル（年）",
    )


class HealthDocExtractionResult(BaseModel):
    """Gemini APIによる健康診断・精密検査PDF解析統合抽出モデル。"""

    doc_type: DocTypeLiteral = Field(description="書類種別の自動判別結果")
    checkup_data: AnnualCheckupPayload | None = Field(default=None, description="年次ドックの場合のデータ")
    imaging_data: ImagingEventPayload | None = Field(default=None, description="単一画像・精密検査の場合のデータ")
    embedded_imaging_events: list[ImagingEventPayload] = Field(
        default_factory=list,
        description="人間ドック等に含まれる複数の画像検査（胃カメラ、頭部MRI、腹部超音波など）",
    )


class OrganLedgerItem(BaseModel):
    """部位別ステータス元帳モデル（Table C: organ_status_ledger）。"""

    organ: str = Field(description="部位名（'脳', '肝臓', '大腸', '胃', '全身' 等）")
    last_exam_date: str = Field(description="直近検査日 (YYYY-MM-DD)")
    current_status: str = Field(description="直近ステータス要約")
    next_action_due: str = Field(description="次回推奨日 (YYYY-MM-DD)")


class InspectionTimelineItem(BaseModel):
    """総合保全ダッシュボードのタイムライン表示用DTO。"""

    modality: str
    target_region: str
    last_exam_date: str
    dynamic_next_due: str
    status_flag: StatusFlagType
    days_remaining: int
    alert_level: Literal["CRITICAL", "UPCOMING", "CRUISING"]


class RegisteredFileRecord(BaseModel):
    """登録済み検査原本ファイルのメタデータモデル（Table: registered_files）。"""

    file_id: int | None = Field(default=None, description="ファイル登録ID（自動採番）")
    file_name: str = Field(description="保存ファイル名（例: 20260422_ANNUAL_medock総合健診クリニック.pdf）")
    original_name: str = Field(description="アップロード時の元ファイル名")
    file_hash: str = Field(description="SHA-256ハッシュ（重複検知用）")
    doc_type: str = Field(description="書類種別（ANNUAL_CHECKUP / SINGLE_IMAGING）")
    exam_date: str = Field(description="検査日 (YYYY-MM-DD)")
    clinic_name: str = Field(description="受診医療機関名")
    registered_at: str = Field(description="登録日時 (YYYY-MM-DD HH:MM:SS)")
    file_size: int = Field(description="ファイルサイズ (bytes)")
    storage_path: str = Field(description="ディスク保存先パス")

