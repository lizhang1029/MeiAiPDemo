"""转写清洗：剔除与考生作答无关的内容，仅保留考生回答。

面试录音/录像转写时，除考生回答外，常混入考官读题与考务口令
（如「听到提示音后可以开始作答」「下一题」「时间到」）；这些内容
不应计入考生评分。本模块通过三类信号识别并剔除：
1. 说话人标注：行首形如「考官：」「主考官:」「Examiner:」等。
2. 题目相似度：未标注说话人时，与题目高度相似的行视为考官读题。
3. 考务口令：匹配「开始作答/时间到/下一题」等与答题无关的提示语。
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

# 与考生作答无关的考务口令/提示（音频中可能无说话人标注，也需剔除）
_PROMPT_PATTERNS = [
    r"听到提示音.{0,6}(可以|请)?开始",
    r"(现在|可以|请|那么)\s*(可以)?开始(作答|答题|回答|讲解|表演)",
    r"请开始(你的)?(作答|答题|回答|讲解|表演)?",
    r"准备时间",
    r"(答题|作答|讲解)时间(为|是|还)?",
    r"还(剩|有).{0,4}分钟",
    r"时间到",
    r"停止(作答|答题|回答)",
    r"^下\s*(一|1)?\s*题",
    r"请看(大屏幕|屏幕|题目|试题|大屏)",
    r"^请考生",
    r"宣读.{0,4}(纪律|须知)",
    r"考试(正式)?(开始|结束)",
    r"(抽|抽到).{0,4}第?\s*\d+\s*题",
    r"请(听题|看题|作答|开始)",
]
_PROMPT_RE = re.compile("|".join(_PROMPT_PATTERNS), re.IGNORECASE)


def _is_prompt(text: str) -> bool:
    """是否为与答题无关的考务口令/提示语。"""
    return bool(_PROMPT_RE.search(text or ""))


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
          "removed": [{"text": "...", "reason": "examiner_label|question_reading|examiner_prompt"}],
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
            # 考生标注：保留正文，但其中夹带的考务口令仍剔除
            if body and _is_prompt(body):
                removed.append({"text": body, "reason": "examiner_prompt"})
                continue
            if body:
                kept.append(body)
            continue

        # 无说话人标注：若与题目高度相似，判为考官读题
        if question and _similar(line, question) >= similarity_threshold:
            removed.append({"text": line.strip(), "reason": "question_reading"})
            continue
        # 无说话人标注：考务口令/提示语，与答题无关
        if _is_prompt(line):
            removed.append({"text": line.strip(), "reason": "examiner_prompt"})
            continue
        kept.append(line.strip())

    answer = "".join(kept) if has_speaker_label else " ".join(kept)
    answer = re.sub(r"\s+", " ", answer).strip()
    return {"answer": answer, "removed": removed, "kept_segments": kept}
