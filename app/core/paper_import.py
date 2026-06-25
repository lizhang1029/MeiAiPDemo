"""试题导入：解析考试平台（ezinterview）下发的试题 JSON，转换为评分用试卷。

真实场景：题目通过接口以 JSON 下发（结构为 sections → groups → items）。
本模块负责把该结构转换成评分引擎可直接使用的「动态试卷」：

1. 按 group 名称映射评分维度（中文/外语题型不同，外语含「中译外/外译中」）；
2. 依据 selection 抽题规则取每个维度实际作答的题目（复合题 mq-lr 再抽取小题）；
3. 从题干 HTML 抽取纯文本，并保留图片题的图片 URL；
4. 以实际作答题目的分值作为该维度满分，生成可直接评分的试卷。

生产环境可在此基础上接入 OCR（图片题）、抽题留痕、与考务系统对接。
"""
from __future__ import annotations

import math
import random
import re
from html import unescape
from typing import Any, Dict, List, Optional, Tuple

from .rubric import Dimension, ScoreLevel


# group 名称 → (评分维度 key, 模态)。同义名做归一处理。
GROUP_DIMENSION_MAP: Dict[str, Tuple[str, str]] = {
    "形象礼仪": ("image_etiquette", "video"),
    "语言表达": ("language_expression", "audio"),
    "普通话": ("language_expression", "audio"),
    "专题路线讲解": ("route_explanation", "content"),
    "专题线路讲解": ("route_explanation", "content"),
    "旅游景区讲解": ("scenic_explanation", "content"),
    "服务规范问答": ("service_qa", "qa"),
    "应变能力问答": ("contingency_qa", "qa"),
    "综合知识问答": ("knowledge_qa", "qa"),
    "中译外": ("translation_out", "translation"),
    "外译中": ("translation_in", "translation"),
}

_IMG_RE = re.compile(r'<img[^>]*\bsrc="([^"]+)"', re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _extract_text(html: str) -> str:
    """去除 HTML 标签，返回纯文本题干。"""
    text = _TAG_RE.sub(" ", html or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_images(html: str) -> List[str]:
    return _IMG_RE.findall(html or "")


def _pick(items: List[Dict[str, Any]], rng: random.Random, pick: str) -> Optional[Dict[str, Any]]:
    """按抽题策略从候选题中选 1 题。pick=first（确定性）| random（随机）。"""
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    if pick == "random":
        return rng.choice(items)
    return items[0]


def _resolve_item(item: Dict[str, Any], rng: random.Random, pick: str) -> Dict[str, Any]:
    """解析单题，复合题（mq-lr）再抽取一道小题。返回题干文本/图片/分值/题号。"""
    content = item.get("content") or {}
    if item.get("type") == "mq-lr":
        sub_items = content.get("items") or []
        main_stem = _extract_text(content.get("main_stem", ""))
        sub = _pick(sub_items, rng, pick)
        if not sub:
            return {"question": main_stem, "images": [], "point": item.get("point") or 0, "item_id": item.get("id", "")}
        stem = (sub.get("content") or {}).get("stem", "")
        text = _extract_text(stem)
        question = "　".join(x for x in [main_stem, text] if x)
        return {
            "question": question,
            "images": _extract_images(stem),
            "point": sub.get("point") or item.get("point") or 0,
            "item_id": sub.get("id", ""),
        }
    stem = content.get("stem", "")
    return {
        "question": _extract_text(stem),
        "images": _extract_images(stem),
        "point": item.get("point") or 0,
        "item_id": item.get("id", ""),
    }


def _guess_language(name: str) -> str:
    if any(k in name for k in ("英语", "English")):
        return "en"
    if "越南" in name:
        return "vi"
    if any(k in name for k in ("外语", "泰", "日", "韩", "法", "德", "俄", "西班牙")):
        return "foreign"
    return "zh"


def parse_exam_paper(data: Dict[str, Any], pick: str = "first", seed: Optional[int] = None) -> Dict[str, Any]:
    """解析考务接口下发的试题 JSON，生成动态试卷。

    返回：{paper_name, language, total_max, dimensions:[{dimension_key, dimension_name,
    modality, max_score, question, images, item_id}]}
    """
    rng = random.Random(seed)
    name = data.get("name", "")
    dims: List[Dict[str, Any]] = []
    used_keys: Dict[str, int] = {}

    for section in data.get("sections") or []:
        for group in section.get("groups") or []:
            gname = group.get("name", "")
            key, modality = GROUP_DIMENSION_MAP.get(gname, ("", ""))
            if not key:
                key, modality = f"dim_{len(dims) + 1}", "qa"
            # 维度 key 去重（极少数试卷可能出现重名分组）
            if key in used_keys:
                used_keys[key] += 1
                key = f"{key}_{used_keys[key]}"
            else:
                used_keys[key] = 0

            chosen = _pick(group.get("items") or [], rng, pick)
            if not chosen:
                continue
            resolved = _resolve_item(chosen, rng, pick)
            max_score = int(round(float(resolved["point"] or group.get("point") or 0)))
            question = resolved["question"]
            if not question and resolved["images"]:
                question = "（图片题，题干见附图，需 OCR / 人工录入）"

            dims.append(
                {
                    "dimension_key": key,
                    "dimension_name": gname,
                    "modality": modality,
                    "max_score": max_score,
                    "question": question,
                    "images": resolved["images"],
                    "item_id": resolved["item_id"],
                }
            )

    return {
        "paper_name": name,
        "language": _guess_language(name),
        "total_max": sum(d["max_score"] for d in dims),
        "dimensions": dims,
    }


def _proportional_levels(max_score: int) -> List[ScoreLevel]:
    """按满分比例生成 优秀/良好/合格/不合格 等级区间（整数边界）。"""
    excellent = math.ceil(max_score * 0.85)
    good = math.ceil(max_score * 0.70)
    pass_ = math.ceil(max_score * 0.60)
    return [
        ScoreLevel("优秀", excellent, max_score),
        ScoreLevel("良好", good, max(good, excellent - 1)),
        ScoreLevel("合格", pass_, max(pass_, good - 1)),
        ScoreLevel("不合格", 0, max(0, pass_ - 1)),
    ]


def make_dimension(key: str, name: str, max_score: int, modality: str = "qa") -> Dimension:
    """由维度规格构造用于评分的 Dimension（动态满分 + 比例等级）。"""
    ms = int(max_score)
    return Dimension(
        key=key,
        name=name,
        max_score=ms,
        modality=modality or "qa",
        items=[],
        levels=_proportional_levels(ms),
    )


def build_rubric(dimensions: List[Dict[str, Any]]) -> Dict[str, Dimension]:
    """由动态试卷的维度列表构造 {key: Dimension} 评分表。"""
    rubric: Dict[str, Dimension] = {}
    for d in dimensions:
        rubric[d["dimension_key"]] = make_dimension(
            d["dimension_key"], d.get("dimension_name", d["dimension_key"]), d["max_score"], d.get("modality", "qa")
        )
    return rubric
