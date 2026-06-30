"""FastAPI 应用入口：AI 辅助导游面试评分系统 Demo。

REST API:
- GET  /rubric              查看评分体系
- GET  /positions          岗位列表
- GET  /positions/{id}/paper  按岗位生成试卷（每位考生题目可不同）
- GET  /kb/search?q=...     RAG 知识库检索
- POST /transcribe         上传音/视频，调用百炼 Paraformer 转写为文本
- POST /transcribe_full    上传整段面试录音，转写并按题前停顿切分为多段回答
- POST /interviews         创建面试 + 提交评分（一步式，便于 demo）
- POST /interviews/custom  基于导入试卷 + 手动评分维度评分（动态维度）
- GET  /interviews/{id}    获取评分结果
- GET  /interviews/{id}/evidence  获取证据链
- GET  /interviews/{id}/report    生成评分报告（Markdown）
- GET  /health
Web UI: GET /
"""
from __future__ import annotations

import json
import os
import time
from typing import Dict, Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse

from .core.asr import ASRClient
from .core.knowledge_base import KnowledgeBase
from .core.align import align_items_segments
from .core.paper_import import build_rubric, parse_exam_paper
from .core.positions_store import (
    delete_position,
    get_saved_position,
    list_saved_positions,
    save_position,
)
from .core.question_bank import get_paper, list_positions
from .core.rubric import rubric_to_dict
from .core.rubric_parse import parse_rubric_text
from .core.schemas import (
    AlignRequest,
    CustomScoreRequest,
    RubricParseRequest,
    SavePositionRequest,
    ScoreRequest,
    ScoreResult,
)
from .core.scoring_engine import ScoringEngine

_EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")

app = FastAPI(
    title="AI 辅助导游面试评分系统 Demo",
    description="接入阿里百炼（DashScope/Qwen）的 AI 辅助判分演示。无 Key 时自动 mock。",
    version="0.1.0",
)

engine = ScoringEngine()
kb = KnowledgeBase()
asr = ASRClient()

# 简单内存存储（demo 用）
_STORE: Dict[str, Dict[str, Any]] = {}


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "engine_mode": engine.mode}


@app.get("/rubric")
def get_rubric() -> Dict[str, Any]:
    return rubric_to_dict()


@app.get("/positions")
def get_positions() -> Dict[str, Any]:
    return {"positions": list_positions()}


# --------------------------------------------------------------------------- #
# 岗位（含评分表）本地持久化：选择/新建/保存/删除
# --------------------------------------------------------------------------- #
@app.get("/positions/saved")
def get_saved_positions() -> Dict[str, Any]:
    """列出本地已保存岗位（含评分表）。"""
    return {"positions": list_saved_positions()}


@app.post("/positions/saved")
def create_saved_position(req: SavePositionRequest) -> Dict[str, Any]:
    """新建/更新岗位并解析其评分表，持久化为本地 JSON。"""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="岗位名称不能为空")
    return save_position(req.name.strip(), req.language, req.rubric_text, req.id)


@app.get("/positions/saved/{position_id}")
def read_saved_position(position_id: str) -> Dict[str, Any]:
    pos = get_saved_position(position_id)
    if not pos:
        raise HTTPException(status_code=404, detail="未找到该岗位")
    return pos


@app.delete("/positions/saved/{position_id}")
def remove_saved_position(position_id: str) -> Dict[str, Any]:
    if not delete_position(position_id):
        raise HTTPException(status_code=404, detail="未找到该岗位")
    return {"deleted": position_id}


# --------------------------------------------------------------------------- #
# 评分表文本解析
# --------------------------------------------------------------------------- #
@app.post("/rubrics/parse")
def parse_rubric(req: RubricParseRequest) -> Dict[str, Any]:
    """解析粘贴的整张评分表文本，返回结构化评分项。"""
    parsed = parse_rubric_text(req.text)
    if not parsed["items"]:
        raise HTTPException(status_code=400, detail="未从文本中解析出任何评分项，请检查格式")
    return parsed


@app.get("/rubrics/samples")
def get_rubric_samples() -> Dict[str, Any]:
    """返回内置评分表文本样例（外语导游评分表）。"""
    samples: Dict[str, str] = {}
    for key, fname in (("foreign", "sample_rubric_foreign.txt"),):
        path = os.path.join(_EXAMPLES_DIR, fname)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                samples[key] = f.read()
    return {"samples": samples}


@app.post("/align")
def align(req: AlignRequest) -> Dict[str, Any]:
    """把评分项与录音分段对齐：自动判定按题/整场，并按考官提问语义匹配录音段。"""
    return align_items_segments(req.items, req.segments, req.qstems)


@app.get("/positions/{position_id}/paper")
def get_position_paper(position_id: str, variant: int = 0) -> Dict[str, Any]:
    paper = get_paper(position_id, variant=variant)
    if not paper:
        raise HTTPException(status_code=404, detail="未找到该岗位")
    return {"position": position_id, "variant": variant, "paper": paper}


@app.get("/papers/samples")
def get_paper_samples() -> Dict[str, Any]:
    """返回内置的考务接口试题样例（普通话 / 越南语）。"""
    samples: Dict[str, Any] = {}
    for key, fname in (("zh", "sample_paper_zh.json"), ("vi", "sample_paper_vi.json")):
        path = os.path.join(_EXAMPLES_DIR, fname)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                samples[key] = json.load(f)
    return {"samples": samples}


@app.post("/papers/import")
def import_paper(
    paper: Dict[str, Any] = Body(..., description="考务接口下发的试题 JSON"),
    pick: str = "first",
    seed: int | None = None,
) -> Dict[str, Any]:
    """解析考务接口下发的试题 JSON，返回评分用动态试卷（维度/题目/分值）。"""
    if not paper.get("sections"):
        raise HTTPException(status_code=400, detail="试题 JSON 缺少 sections")
    parsed = parse_exam_paper(paper, pick=pick, seed=seed)
    if not parsed["dimensions"]:
        raise HTTPException(status_code=400, detail="未从试题中解析出任何维度")
    return parsed


@app.post("/interviews/custom", response_model=ScoreResult)
def create_interview_custom(req: CustomScoreRequest) -> Any:
    """基于导入试卷评分：维度与满分随接口下发的试题动态变化。"""
    if not req.items:
        raise HTTPException(status_code=400, detail="items 不能为空")
    dim_specs = [i.model_dump() for i in req.items]
    rubric = build_rubric(dim_specs)
    total_max = sum(int(i.max_score) for i in req.items)
    t0 = time.perf_counter()
    result = engine.score_interview(
        req.candidate.model_dump(),
        dim_specs,
        rubric=rubric,
        total_max=total_max,
    )
    result["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    _STORE[result["interview_id"]] = result
    return result


@app.get("/kb/search")
def kb_search(q: str, top_k: int = 3) -> Dict[str, Any]:
    return {"query": q, "results": kb.search(q, top_k=top_k)}


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(..., description="面试录音或录像文件"),
    language: str = Form("zh", description="语言：zh|vi|en"),
) -> Dict[str, Any]:
    """上传音/视频，调用百炼 Paraformer 转写为文本（无 Key 时降级 mock）。

    返回的 text 为原始转写（可能含考官读题）；剔除考官读题、仅留考生回答在
    评分阶段由后端自动完成。
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    return asr.transcribe(data, file.filename or "upload", language=language)


@app.post("/transcribe_full")
async def transcribe_full(
    file: UploadFile = File(..., description="一名考生整段面试的录音/录像文件"),
    language: str = Form("zh", description="语言：zh|vi|en"),
    pause_ms: int = Form(2000, description="题前停顿阈值（毫秒），超过则切分为新题"),
) -> Dict[str, Any]:
    """上传一名考生整段面试录音/录像，转写并按「题前明显停顿」切分为多段回答。

    返回 segments（按题目顺序），每段为原始转写（可能含考官读题/口令）；剔除
    与答题无关内容、仅留考生回答在评分阶段由后端自动完成。
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    t0 = time.perf_counter()
    result = asr.transcribe_segments(
        data, file.filename or "upload", language=language, pause_ms=pause_ms
    )
    result["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return result


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
                "question": dim.get("question", ""),
                "score": dim["score"],
                "max_score": dim["max_score"],
                "deductions": dim["deductions"],
                "evidence": dim["evidence"],
                "confidence": dim["confidence"],
                "removed_examiner_segments": dim.get("removed_segments", []),
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
        f"- 报考岗位: {c.get('position','')}",
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
        if d.get("question"):
            lines.append(f"- 题目: {d['question']}")
        if d.get("removed_segments"):
            lines.append("- 已剔除考官读题/无关内容:")
            for seg in d["removed_segments"]:
                lines.append(f"  - [{seg.get('reason','')}] {seg.get('text','')}")
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
