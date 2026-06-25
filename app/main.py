"""FastAPI 应用入口：AI 辅助导游面试评分系统 Demo。

REST API:
- GET  /rubric              查看评分体系
- GET  /kb/search?q=...     RAG 知识库检索
- POST /interviews         创建面试 + 提交评分（一步式，便于 demo）
- GET  /interviews/{id}    获取评分结果
- GET  /interviews/{id}/evidence  获取证据链
- GET  /interviews/{id}/report    生成评分报告（Markdown）
- GET  /health
Web UI: GET /
"""
from __future__ import annotations

import os
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from .core.knowledge_base import KnowledgeBase
from .core.rubric import rubric_to_dict
from .core.schemas import ScoreRequest, ScoreResult
from .core.scoring_engine import ScoringEngine

app = FastAPI(
    title="AI 辅助导游面试评分系统 Demo",
    description="接入阿里百炼（DashScope/Qwen）的 AI 辅助判分演示。无 Key 时自动 mock。",
    version="0.1.0",
)

engine = ScoringEngine()
kb = KnowledgeBase()

# 简单内存存储（demo 用）
_STORE: Dict[str, Dict[str, Any]] = {}


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "engine_mode": engine.mode}


@app.get("/rubric")
def get_rubric() -> Dict[str, Any]:
    return rubric_to_dict()


@app.get("/kb/search")
def kb_search(q: str, top_k: int = 3) -> Dict[str, Any]:
    return {"query": q, "results": kb.search(q, top_k=top_k)}


@app.post("/interviews", response_model=ScoreResult)
def create_interview(req: ScoreRequest) -> Any:
    if not req.items:
        raise HTTPException(status_code=400, detail="items 不能为空")
    result = engine.score_interview(
        req.candidate.model_dump(),
        [i.model_dump() for i in req.items],
    )
    _STORE[result["interview_id"]] = result
    return result


@app.get("/interviews/{interview_id}", response_model=ScoreResult)
def get_interview(interview_id: str) -> Any:
    result = _STORE.get(interview_id)
    if not result:
        raise HTTPException(status_code=404, detail="未找到该面试记录")
    return result


@app.get("/interviews/{interview_id}/evidence")
def get_evidence(interview_id: str) -> Dict[str, Any]:
    result = _STORE.get(interview_id)
    if not result:
        raise HTTPException(status_code=404, detail="未找到该面试记录")
    chain = []
    for dim in result["dimensions"]:
        chain.append(
            {
                "dimension": dim["dimension_name"],
                "score": dim["score"],
                "max_score": dim["max_score"],
                "deductions": dim["deductions"],
                "evidence": dim["evidence"],
                "confidence": dim["confidence"],
            }
        )
    return {"interview_id": interview_id, "evidence_chain": chain}


@app.get("/interviews/{interview_id}/report", response_class=PlainTextResponse)
def get_report(interview_id: str) -> str:
    result = _STORE.get(interview_id)
    if not result:
        raise HTTPException(status_code=404, detail="未找到该面试记录")
    return _render_report(result)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "web", "index.html"), encoding="utf-8") as f:
        return f.read()


def _render_report(result: Dict[str, Any]) -> str:
    c = result["candidate"]
    lines = [
        f"# AI 辅助评分报告（建议分，需评委确认）",
        "",
        f"- 考生: {c.get('name','')} ({c.get('candidate_no','')})",
        f"- 总分: **{result['total_score']} / {result['max_total']}** —— {result['overall_level']}",
        f"- 评分引擎模式: {result['engine_mode']}",
        f"- 生成时间: {result['created_at']}",
        "",
        "## 分项得分",
        "",
        "| 维度 | 得分 | 满分 | 等级 | 置信度 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for d in result["dimensions"]:
        lines.append(
            f"| {d['dimension_name']} | {d['score']} | {d['max_score']} | {d['level']} | {d['confidence']} |"
        )
    lines += ["", "## 扣分与证据链", ""]
    for d in result["dimensions"]:
        lines.append(f"### {d['dimension_name']}（{d['score']}/{d['max_score']}）")
        lines.append(f"- 评分依据: {d['rationale']}")
        if d["deductions"]:
            lines.append("- 扣分项:")
            for ded in d["deductions"]:
                lines.append(
                    f"  - -{ded['points']}：{ded['reason']}（证据: {ded.get('evidence','')}）"
                )
        if d["evidence"]:
            lines.append("- 引用证据:")
            for ev in d["evidence"]:
                lines.append(f"  - [{ev['type']}] {ev['content']}（{ev.get('ref','')}）")
        lines.append("")
    review = result.get("review", {})
    if review:
        lines += ["## 总体评语", "", review.get("summary", "")]
        if review.get("improvements"):
            lines += ["", "### 改进建议"]
            lines += [f"- {x}" for x in review["improvements"]]
    return "\n".join(lines)
