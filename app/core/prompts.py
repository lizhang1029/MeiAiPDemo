"""Prompt 工程：System / Scoring / Evaluation / Evidence / Review。

所有 Prompt 均面向生产环境设计，要求模型严格返回 JSON，便于结构化解析与证据链回溯。
"""
from __future__ import annotations

import json
from typing import Dict, Any, List

from .rubric import Dimension


SYSTEM_PROMPT = """你是一名拥有10年以上经验的导游资格面试评委与AI测评专家。
你的职责是依据《导游面试评分标准》对候选人的表现进行客观、公正、可解释的评分。

严格遵守以下原则：
1. 只依据提供的【转写内容/多模态特征/知识库证据】进行评分，不得臆测未提供的信息。
2. 每一项扣分都必须给出明确的【扣分原因】和【引用证据】（引用转写原文片段或多模态指标）。
3. 评分必须落在评分项允许的分值区间内，且不得超过该项满分；**所有分数与扣分值必须为整数，不得出现小数**。
4. 输出必须是合法 JSON，不得包含 JSON 之外的任何解释性文字、Markdown 代码块标记。
5. AI 仅提供评分建议，最终分数由人类评委确认；请给出 confidence（0~1）反映你的置信度。
6. 保持评分校准一致性：相同表现给相同分数，避免过宽或过严。
"""


def _dimension_brief(dim: Dimension) -> str:
    lines = [f"维度: {dim.name} (key={dim.key}, 满分={dim.max_score}, 模态={dim.modality})"]
    if dim.items:
        lines.append("评分项:")
        for it in dim.items:
            crit = "；".join(it.criteria)
            lines.append(f"  - {it.name} (key={it.key}, 满分={it.max_score}): {crit}")
    if dim.requirements:
        lines.append("评分要求: " + "；".join(dim.requirements))
    if dim.levels:
        lvls = "，".join(f"{l.name}({l.min_score}~{l.max_score})" for l in dim.levels)
        lines.append("评分等级: " + lvls)
    return "\n".join(lines)


def build_scoring_prompt(
    dimension: Dimension,
    *,
    question: str,
    answer_transcript: str,
    multimodal_features: Dict[str, Any] | None = None,
    rag_evidence: List[Dict[str, Any]] | None = None,
    reference_answer: str | None = None,
) -> str:
    """针对单个维度构造评分 Prompt，要求返回结构化 JSON。"""
    parts: List[str] = []
    parts.append("# 评分任务")
    parts.append(_dimension_brief(dimension))

    parts.append("\n# 面试题目")
    parts.append(question or "（无）")

    parts.append("\n# 候选人回答（ASR转写，已剔除考官读题，仅含考生作答）")
    parts.append(answer_transcript or "（无转写内容）")

    if multimodal_features:
        parts.append("\n# 多模态特征指标")
        parts.append(json.dumps(multimodal_features, ensure_ascii=False, indent=2))

    if reference_answer:
        parts.append("\n# 标准答案 / 评分参考")
        parts.append(reference_answer)

    if rag_evidence:
        parts.append("\n# RAG 知识库证据")
        for i, ev in enumerate(rag_evidence, 1):
            parts.append(f"[证据{i}] 来源={ev.get('source','')} 内容={ev.get('content','')}")

    parts.append("\n# 输出要求")
    item_schema = (
        '[{"item_key":"...","item_name":"...","max_score":整数,"score":整数,'
        '"deductions":[{"reason":"扣分原因","points":整数,"evidence":"引用证据原文"}],'
        '"rationale":"评分依据"}]'
        if dimension.items
        else "（该维度无细分评分项，items 返回空数组 []）"
    )
    schema = {
        "dimension_key": dimension.key,
        "dimension_name": dimension.name,
        "max_score": dimension.max_score,
        "score": "整数（0~该维度满分，不得为小数）",
        "level": "优秀/良好/合格/不合格",
        "items": item_schema,
        "deductions": '[{"reason":"扣分原因","points":整数,"evidence":"引用证据"}]',
        "rationale": "本维度总体评分依据",
        "evidence": '[{"type":"transcript|video|audio|rag","content":"证据内容","ref":"定位信息如时间戳/段落"}]',
        "confidence": "0~1 之间的小数",
    }
    parts.append("严格按以下 JSON 结构输出（不要输出多余文字）：")
    parts.append(json.dumps(schema, ensure_ascii=False, indent=2))
    return "\n".join(parts)


def build_review_prompt(scores: List[Dict[str, Any]], total: float) -> str:
    """汇总评审 Prompt：生成总体评语与改进建议。"""
    return (
        "你是面试评委组长。以下是各维度AI评分结果（JSON）。\n"
        "请基于这些结果生成一段面向考生的总体评语与改进建议，并复核是否存在评分不一致。\n"
        f"总分: {total}\n各维度: {json.dumps(scores, ensure_ascii=False)}\n\n"
        '严格返回 JSON: {"summary":"总体评语","strengths":["..."],"improvements":["..."],'
        '"risk_flags":["评分一致性/合规风险提示"]}'
    )
