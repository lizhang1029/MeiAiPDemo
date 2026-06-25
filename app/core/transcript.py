"""转写清洗：剔除考官读题内容，仅保留考生回答。

面试录像转写时，考官常会朗读题目；这些内容不应计入考生评分。
本模块通过两种信号识别并剔除考官内容：
1. 说话人标注：行首形如「考官：」「主考官:」「Examiner:」等。
2. 题目相似度：未标注说话人时，与题目高度相似的行视为考官读题。
"""
from __future__ import annotations

import re
from typing import Dict, Any, List, Optional


# 说话人标注正则：分组1=角色，分组2=正文
_SPEAKER_RE = re.compile(
    r"^\s*(考官|主考官|面试官|考评员|监考|examiner|interviewer|考生|应试者|候选人|考生答|candidate|answer)\s*[：:＞>\-、\.]\s*(.*)$",
    re.IGNORECASE,
)

_EXAMINER_ROLES = {"考官", "主考官", "面试官", "考评员", "监考", "examiner", "interviewer"}


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。,.\?？!！、：:;；\"'“”]", "", text).lower()


def _similar(a: str, b: str) -> float:
    """基于字符集合的 Jaccard 相似度，轻量判断读题行。"""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    sa, sb = set(na), set(nb)
    inter = len(sa & sb)
    union = len(sa | sb)
    contain = inter / min(len(sa), len(sb))  # 包含度
    jaccard = inter / union if union else 0.0
    return max(jaccard, contain)


def clean_transcript(
    raw: str,
    question: str = "",
    similarity_threshold: float = 0.8,
) -> Dict[str, Any]:
    """清洗转写文本。

    返回:
        {
          "answer": "仅含考生回答的文本",
          "removed": [{"text": "...", "reason": "examiner_label|question_reading"}],
          "kept_segments": [...],
        }
    """
    if not raw:
        return {"answer": "", "removed": [], "kept_segments": []}

    # 按换行或显式说话人切分；若整体一行，则按句号粗切以便识别读题句
    lines = [l for l in re.split(r"[\r\n]+", raw) if l.strip()]
    if len(lines) <= 1 and question:
        lines = [s for s in re.split(r"(?<=[。?？!！])", raw) if s.strip()]

    kept: List[str] = []
    removed: List[Dict[str, str]] = []
    has_speaker_label = any(_SPEAKER_RE.match(l) for l in lines)

    for line in lines:
        m = _SPEAKER_RE.match(line)
        if m:
            role = m.group(1).lower()
            body = m.group(2).strip()
            if role in _EXAMINER_ROLES:
                removed.append({"text": body or line.strip(), "reason": "examiner_label"})
                continue
            # 考生标注，保留正文
            if body:
                kept.append(body)
            continue

        # 无说话人标注：若与题目高度相似，判为考官读题
        if question and _similar(line, question) >= similarity_threshold:
            removed.append({"text": line.strip(), "reason": "question_reading"})
            continue
        kept.append(line.strip())

    answer = "".join(kept) if has_speaker_label else " ".join(kept)
    answer = re.sub(r"\s+", " ", answer).strip()
    return {"answer": answer, "removed": removed, "kept_segments": kept}
