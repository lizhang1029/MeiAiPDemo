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
