"""API 数据结构（Pydantic 模型）。"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class QAItem(BaseModel):
    """一个维度对应的题目与候选人回答 + 可选多模态特征。"""

    dimension_key: str = Field(..., description="评分维度 key，见 /rubric")
    question: str = Field("", description="面试题目（每位考生可不同）")
    answer_transcript: str = Field(
        "",
        description="候选人回答（ASR 转写文本，可含「考官：」读题行，将被自动剔除）",
    )
    multimodal_features: Optional[Dict[str, Any]] = Field(
        None, description="视频/语音分析得到的特征指标"
    )
    reference_answer: Optional[str] = Field(None, description="标准答案/评分参考")


class CandidateInfo(BaseModel):
    name: str = ""
    candidate_no: str = ""
    position: str = Field("", description="报考岗位 id，见 /positions")
    language: str = "zh"


class ScoreRequest(BaseModel):
    candidate: CandidateInfo = Field(default_factory=CandidateInfo)
    items: List[QAItem] = Field(..., description="各维度的题目与回答")


class CustomQAItem(BaseModel):
    """评分表的一个评分项与对应回答（维度/满分由录入的评分表决定）。"""

    dimension_key: str = Field(..., description="评分项 key（由评分表解析得到）")
    dimension_name: str = Field("", description="评分项名称")
    modality: str = Field("qa", description="模态：video|audio|content|qa|translation")
    max_score: int = Field(10, description="该项满分（来自评分表）")
    question: str = Field("", description="题目（按题评分时与该项对应）")
    answer_transcript: str = Field("", description="候选人回答转写，可含「考官：」读题行")
    reference_answer: Optional[str] = None
    weight: float = Field(1.0, description="权重：仅展示，总分=各项得分直接相加")
    scoring_source: str = Field(
        "per_question", description="评分来源：per_question 按题 | whole 整场 | manual 人工录入"
    )
    manual_score: Optional[int] = Field(None, description="人工录入项的分数（scoring_source=manual 时使用）")
    levels: Optional[List[Dict[str, Any]]] = Field(None, description="等级档位 [{name,min,max,desc}]")
    criteria: Optional[List[Dict[str, Any]]] = Field(None, description="评分点 [{name,points,desc}]")


class CustomScoreRequest(BaseModel):
    """基于录入评分表的评分请求：维度/满分/等级随评分表动态变化。"""

    candidate: CandidateInfo = Field(default_factory=CandidateInfo)
    items: List[CustomQAItem] = Field(..., description="评分表各评分项与对应回答")


class RubricParseRequest(BaseModel):
    """评分表文本解析请求。"""

    text: str = Field(..., description="粘贴的整张评分表文本")


class SavePositionRequest(BaseModel):
    """保存（新建/更新）岗位及其评分表。"""

    id: Optional[str] = Field(None, description="岗位 id；为空则新建")
    name: str = Field(..., description="岗位名称")
    language: str = Field("zh", description="语言：zh|vi|en|foreign")
    rubric_text: str = Field("", description="该岗位的评分表原文（可解析）")


class Deduction(BaseModel):
    reason: str
    points: int
    evidence: str = ""


class EvidenceRef(BaseModel):
    type: str
    content: str
    ref: str = ""


class RemovedSegment(BaseModel):
    text: str
    reason: str  # examiner_label | question_reading


class DimensionScore(BaseModel):
    dimension_key: str
    dimension_name: str
    question: str = ""
    max_score: int
    score: int
    level: str
    items: List[Dict[str, Any]] = []
    deductions: List[Deduction] = []
    rationale: str = ""
    evidence: List[EvidenceRef] = []
    confidence: float = 0.0
    removed_segments: List[RemovedSegment] = []
    weight: float = 1.0
    scoring_source: str = "per_question"


class ScoreResult(BaseModel):
    interview_id: str
    candidate: CandidateInfo
    total_score: int
    max_total: int
    overall_level: str
    dimensions: List[DimensionScore]
    review: Dict[str, Any] = {}
    engine_mode: str = "mock"
    created_at: str = ""
