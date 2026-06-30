"""把评分表各评分项与录音分段（自动分离出的「考官提问」）对齐。

需求背景：评分项数量与录音题目数量不一定一致，且不是所有评分项都对应某道题：
- 「按题评分」项（讲解/问答/口译…）：应对应某一段录音的考官提问与考生回答；
- 「整场评分」项（语言表达、专业知识/系统思维等抽象能力）：无对应单题，
  用全部转写/多段问答作为评分依据；
- 「人工录入」项（形象礼仪等）：音频无法判断，评委手填。

对齐策略（无导入试题时）：
1. 人工/整场项不参与对齐，直接保留其评分来源。
2. 「按题评分」项依据「评分项名称/题型关键词」与各段「考官提问」做字面（2-gram）
   语义匹配，贪心地为每项挑选最匹配且尚未占用的录音段。
3. 匹配度过低（无相关录音段）的「按题评分」项，回退为「整场评分」（用全部转写）。
4. 导入试题且「试题数 == 按题评分项数」时，按顺序 1:1 严格对应（题干来自 JSON、只读）。

匹配为纯字面实现（离线、无需 API Key）；后续可在不改接口的前提下升级为
百炼语义向量匹配。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_PUNCT_RE = re.compile(r"[\s，。,.\?？!！、：:;；\"'“”()（）【】\[\]]")

# 默认匹配阈值：评分项名称的 2-gram 有约 1/3 命中考官提问即视为相关。
_MATCH_THRESHOLD = 0.34


def _norm(s: str) -> str:
    return _PUNCT_RE.sub("", s or "").lower()


def _bigrams(s: str) -> set:
    s = _norm(s)
    if len(s) >= 2:
        return {s[i : i + 2] for i in range(len(s) - 1)}
    return {s} if s else set()


def _criteria_keywords(item: Dict[str, Any]) -> List[str]:
    return [c.get("name", "") for c in (item.get("criteria") or []) if c.get("name")]


def match_score(item: Dict[str, Any], seg: Dict[str, Any]) -> float:
    """评分项与某录音段的字面匹配分（0~1）。

    以评分项名称的 2-gram 在该段「考官提问」中的命中比例为主；考官提问为空时
    退而在该段开头文本（通常含考官读题）中匹配。评分点（子项）名称命中可加成。
    """
    name_bg = _bigrams(item.get("name", ""))
    if not name_bg:
        return 0.0
    question = (seg.get("question") or "").strip()
    target = question if question else (seg.get("text") or "")[:60]
    tg = _bigrams(target)
    if not tg:
        return 0.0
    base = len(name_bg & tg) / len(name_bg)
    # 评分点关键词命中加成（每命中一个子项名 +0.1，最多 +0.3）
    bonus = 0.0
    for kw in _criteria_keywords(item):
        if _norm(kw) and _norm(kw) in _norm(target):
            bonus += 0.1
    return min(1.0, base + min(bonus, 0.3))


def align_items_segments(
    items: List[Dict[str, Any]],
    segments: List[Dict[str, Any]],
    qstems: Optional[List[Dict[str, Any]]] = None,
    threshold: float = _MATCH_THRESHOLD,
) -> Dict[str, Any]:
    """返回与 items 顺序一致的对齐结果。

    每项：{item_index, key, name, parsed_source, effective_source, modality,
    max_score, seg_index, question, question_editable, matched, match_score, note}
    """
    qstems = qstems or []
    pq_positions = [i for i, it in enumerate(items) if it.get("source") == "per_question"]
    # 导入试题且数量与「按题评分」项一致 → 严格按顺序 1:1 对应
    paper_mode = bool(qstems) and len(qstems) == len(pq_positions)

    alignment: List[Dict[str, Any]] = []
    used_segs: set = set()
    # 预先为「按题评分」项贪心匹配最优录音段（非导入试题模式）
    pq_seg: Dict[int, int] = {}
    if not paper_mode and segments:
        scored: List[tuple] = []  # (score, item_index, seg_index)
        for i in pq_positions:
            for s_idx, seg in enumerate(segments):
                sc = match_score(items[i], seg)
                if sc >= threshold:
                    scored.append((sc, i, s_idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        assigned_items: set = set()
        for sc, i, s_idx in scored:
            if i in assigned_items or s_idx in used_segs:
                continue
            pq_seg[i] = s_idx
            used_segs.add(s_idx)
            assigned_items.add(i)

    pq_counter = -1
    for i, it in enumerate(items):
        src = it.get("source", "per_question")
        base = {
            "item_index": i,
            "key": it.get("key"),
            "name": it.get("name", ""),
            "parsed_source": src,
            "modality": it.get("modality", "qa"),
            "max_score": it.get("max_score"),
        }
        if src == "manual":
            alignment.append({**base, "effective_source": "manual", "seg_index": None,
                              "question": "", "question_editable": False, "matched": False,
                              "match_score": 0.0, "note": "人工录入（音频无法判断）"})
            continue
        if src == "whole":
            alignment.append({**base, "effective_source": "whole", "seg_index": None,
                              "question": "", "question_editable": False, "matched": False,
                              "match_score": 0.0, "note": "整场评分：用全部转写/多段问答作为依据"})
            continue

        # per_question
        pq_counter += 1
        if paper_mode:
            seg_idx = pq_counter if pq_counter < len(segments) else None
            q = qstems[pq_counter].get("question", "") if pq_counter < len(qstems) else ""
            alignment.append({**base, "effective_source": "per_question", "seg_index": seg_idx,
                              "question": q, "question_editable": False, "matched": True,
                              "match_score": 1.0, "note": "题干来自导入试题（只读），按顺序对应"})
            continue

        seg_idx = pq_seg.get(i)
        if seg_idx is not None:
            seg = segments[seg_idx]
            alignment.append({**base, "effective_source": "per_question", "seg_index": seg_idx,
                              "question": seg.get("question", ""), "question_editable": True,
                              "matched": True, "match_score": round(match_score(it, seg), 3),
                              "note": "已按考官提问语义匹配到录音段（题干可修改）"})
        else:
            # 无相关录音段：回退为整场评分
            alignment.append({**base, "effective_source": "whole", "seg_index": None,
                              "question": "", "question_editable": False, "matched": False,
                              "match_score": 0.0,
                              "note": "未匹配到对应考官提问，已改为整场评分（用全部转写）"})

    pq_total = len(pq_positions)
    pq_matched = sum(1 for a in alignment if a["parsed_source"] == "per_question" and a["matched"])
    pq_to_whole = sum(1 for a in alignment if a["parsed_source"] == "per_question"
                      and a["effective_source"] == "whole")
    return {
        "alignment": alignment,
        "paper_mode": paper_mode,
        "segments": len(segments),
        "per_question_total": pq_total,
        "per_question_matched": pq_matched,
        "per_question_to_whole": pq_to_whole,
    }
