"""AI 评分引擎：编排 RAG 检索 + 百炼推理 + 校准 + 证据链汇总。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

from .bailian_client import BailianClient
from .knowledge_base import KnowledgeBase
from .prompts import SYSTEM_PROMPT, build_scoring_prompt, build_review_prompt
from .rubric import DIMENSION_BY_KEY, TOTAL_SCORE, Dimension, level_for
from .transcript import clean_transcript


class ScoringEngine:
    def __init__(self, client: BailianClient | None = None, kb: KnowledgeBase | None = None):
        self.client = client or BailianClient()
        self.kb = kb or KnowledgeBase()

    @property
    def mode(self) -> str:
        return self.client.mode

    def score_dimension(self, dim: Dimension, item: Dict[str, Any]) -> Dict[str, Any]:
        question = item.get("question", "")
        raw_answer = item.get("answer_transcript", "")
        features = item.get("multimodal_features")
        reference = item.get("reference_answer")

        # 剔除考官读题，仅保留考生回答
        cleaned = clean_transcript(raw_answer, question=question)
        answer = cleaned["answer"]
        removed = cleaned["removed"]

        # 内容类/问答类维度引入 RAG 证据
        rag_evidence: List[Dict[str, Any]] = []
        if dim.modality in ("content", "qa"):
            rag_evidence = self.kb.search(f"{question} {answer}", top_k=3)

        prompt = build_scoring_prompt(
            dim,
            question=question,
            answer_transcript=answer,
            multimodal_features=features,
            rag_evidence=rag_evidence,
            reference_answer=reference,
        )
        raw = self.client.chat_json(SYSTEM_PROMPT, prompt)
        return self._normalize(dim, raw, rag_evidence, question=question, removed=removed)

    def _normalize(
        self,
        dim: Dimension,
        raw: Dict[str, Any],
        rag_evidence: List[Dict[str, Any]],
        question: str = "",
        removed: List[Dict[str, str]] | None = None,
    ) -> Dict[str, Any]:
        """校验/约束模型输出，确保分数为合法整数并补全字段（校准机制）。"""
        max_score = int(dim.max_score)
        score = _to_int(raw.get("score"), 0)
        score = max(0, min(max_score, score))  # 约束到合法整数区间

        # 校准：分项分之和不得超过维度满分
        items = raw.get("items") or []
        if items:
            for it in items:
                it["score"] = _to_int(it.get("score"), 0)
            item_sum = sum(_to_int(i.get("score"), 0) for i in items)
            if item_sum > 0 and abs(item_sum - score) >= 1:
                score = min(max_score, item_sum)

        # 扣分取整数
        deductions = []
        for d in raw.get("deductions") or []:
            deductions.append(
                {
                    "reason": d.get("reason", ""),
                    "points": _to_int(d.get("points"), 0),
                    "evidence": d.get("evidence", ""),
                }
            )

        evidence = raw.get("evidence") or []
        if not evidence and rag_evidence:
            evidence = [
                {"type": "rag", "content": e["content"], "ref": e["source"]}
                for e in rag_evidence[:2]
            ]

        return {
            "dimension_key": dim.key,
            "dimension_name": dim.name,
            "question": question,
            "max_score": max_score,
            "score": score,
            "level": raw.get("level") or level_for(dim, score),
            "items": items,
            "deductions": deductions,
            "rationale": raw.get("rationale", ""),
            "evidence": evidence,
            "confidence": _to_float(raw.get("confidence"), 0.6),
            "removed_segments": removed or [],
        }

    def score_interview(
        self, candidate: Dict[str, Any], items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        dim_scores: List[Dict[str, Any]] = []
        for item in items:
            key = item.get("dimension_key")
            dim = DIMENSION_BY_KEY.get(key)
            if not dim:
                continue
            dim_scores.append(self.score_dimension(dim, item))

        total = int(sum(d["score"] for d in dim_scores))
        overall = _overall_level(total)

        review = self.client.chat_json(
            SYSTEM_PROMPT, build_review_prompt(dim_scores, total)
        )
        if review.get("_parse_error"):
            review = _mock_review(dim_scores, total)

        return {
            "interview_id": uuid.uuid4().hex[:12],
            "candidate": candidate,
            "total_score": total,
            "max_total": TOTAL_SCORE,
            "overall_level": overall,
            "dimensions": dim_scores,
            "review": review,
            "engine_mode": self.mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


def _overall_level(total: float) -> str:
    if total >= 85:
        return "优秀"
    if total >= 70:
        return "良好"
    if total >= 60:
        return "合格"
    return "不合格"


def _mock_review(dim_scores: List[Dict[str, Any]], total: float) -> Dict[str, Any]:
    weakest = min(dim_scores, key=lambda d: d["score"] / d["max_score"]) if dim_scores else None
    strongest = max(dim_scores, key=lambda d: d["score"] / d["max_score"]) if dim_scores else None
    return {
        "summary": f"候选人总分 {total}/100，整体评定为「{_overall_level(total)}」。"
        + (f"在「{strongest['dimension_name']}」表现突出。" if strongest else ""),
        "strengths": [strongest["dimension_name"]] if strongest else [],
        "improvements": [
            f"建议加强「{weakest['dimension_name']}」：{weakest.get('rationale','')}"
        ]
        if weakest
        else [],
        "risk_flags": [],
        "_mock": True,
    }


def _to_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v: Any, default: int) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default
