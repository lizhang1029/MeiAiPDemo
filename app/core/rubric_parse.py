"""评分表文本解析：把评委手工录入的整张评分表（纯文本）解析为结构化评分项。

真实使用场景：评委直接粘贴一张如下格式的评分表（评分项 / 满分 / 权重 / 评分点 /
等级档位），系统据此逐项辅助打分。示例：

    评分项 总分:0~100.0分
    1.形象礼仪 - 5分0~5分 【权重：1】
    1. 形象气质（1分）：贴合导游职业形象，精神饱满、举止端庄
    ...
    优秀（5分）：完全符合标准，无瑕疵
    良好（4分）：1项轻微不达标，扣1分
    合格（3分）：2项轻微或1项明显不达标，扣2分
    不合格（0-2分）：3项及以上不达标或严重违规，扣3-5分。
    2.语言表达 - 25分0~25分 【权重：1】
    ...

解析产物用于：
1. 生成评分维度（维度名/满分/权重/等级档位/评分点），驱动评分引擎逐项打分；
2. 按「评分来源」把维度区分为：按题打分（讲解/问答/口译，用对应题的回答）、
   整场打分（语言表达，用全部转写）、人工录入（形象礼仪等音频无法判断的项）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# 一级评分项表头，兼容两种常见写法（均带【权重】标记）：
#   "1.形象礼仪 - 5分0~5分 【权重：1】"  （名称 - 满分 + 区间）
#   "1.专业知识0~55分 【权重：1】"        （名称 + 区间，无破折号）
# 满分取「分」前的数值；若为区间（0~55）取上界。名称为序号后、分值/破折号前的文字。
_ITEM_RE = re.compile(
    r"^\s*(\d+)\s*[\.、]\s*(.+?)\s*"
    r"(?:[-—]\s*\d+(?:\.\d+)?\s*分\s*)?"          # 可选 "- 5分"
    r"(?:\d+(?:\.\d+)?\s*[~～至]\s*)?"             # 可选区间下界 "0~"
    r"(\d+(?:\.\d+)?)\s*分",                       # 满分（区间上界或单值）
)
_WEIGHT_RE = re.compile(r"权重\s*[：:]\s*(\d+(?:\.\d+)?)")

# 评分点（子项）：形如 "1. 形象气质（1分）：贴合导游职业形象…"
_CRITERION_RE = re.compile(
    r"^\s*\d+\s*[\.、]\s*(.+?)\s*[（(]\s*(\d+(?:\.\d+)?)\s*分\s*[)）]\s*[：:]\s*(.*)$",
)

# 等级档位：形如 "优秀（5分）：…" / "良好（23-25分）：…" / "不合格（0-2分）：…"
_LEVEL_RE = re.compile(
    r"^\s*(优秀|良好|合格|不合格)\s*[（(]\s*(\d+(?:\.\d+)?)\s*(?:[-~至]\s*(\d+(?:\.\d+)?))?\s*分?\s*[)）]\s*[：:]\s*(.*)$",
)

# 无名等级档位：形如 "9-10分：表达准确" / "5分：思路清晰"（无 优秀/良好 等名称、无括号）
_LEVEL_NONAME_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(?:[-~至]\s*(\d+(?:\.\d+)?))?\s*分\s*[：:]\s*(.*)$",
)

_TOTAL_RE = re.compile(r"总分\s*[：:]?\s*\d+(?:\.\d+)?\s*[~～-]\s*(\d+(?:\.\d+)?)")


def _to_num(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _infer_source_modality(name: str) -> tuple[str, str]:
    """根据评分项名称推断「评分来源」与模态。

    - 形象/礼仪/着装/妆容/仪态 → 人工录入(manual)，音频无法判断；
    - 语言表达/普通话/语音 → 整场评分(whole)，贯穿全部回答；
    - 含「讲解」→ 按题(content)；含「译」→ 按题(translation)；其余 → 按题(qa)。
    """
    if any(k in name for k in ("形象", "礼仪", "仪容", "仪表", "着装", "妆容", "仪态")):
        return "manual", "video"
    if any(k in name for k in ("语言表达", "普通话", "语音", "语调")):
        return "whole", "audio"
    if "讲解" in name:
        return "per_question", "content"
    if "译" in name:
        return "per_question", "translation"
    return "per_question", "qa"


_NONAME_LEVEL_NAMES = ["优秀", "良好", "合格", "不合格"]


def _standards_text(desc: List[str], criteria: List[Dict[str, Any]], levels: List[Dict[str, Any]]) -> str:
    """把总体描述、评分点与等级档位拼成给评分引擎的评分标准文本。"""
    parts: List[str] = []
    if desc:
        parts.append("".join(desc))
    if criteria:
        parts.append(
            "评分点：" + "；".join(f"{c['name']}({int(c['points'])}分){('：' + c['desc']) if c['desc'] else ''}" for c in criteria)
        )
    if levels:
        parts.append(
            "等级档位：" + "；".join(
                f"{l['name']}({int(l['min'])}{('-' + str(int(l['max']))) if l['max'] != l['min'] else ''}分)"
                + (f"：{l['desc']}" if l.get("desc") else "")
                for l in levels
            )
        )
    return "\n".join(parts)


def parse_rubric_text(text: str) -> Dict[str, Any]:
    """解析粘贴的评分表文本，返回结构化评分项。

    返回：{rubric_name, total_max, items:[{key, name, max_score, weight, source,
    modality, criteria:[{name,points,desc}], levels:[{name,min,max,desc}],
    standards_text}]}
    """
    if not text or not text.strip():
        return {"rubric_name": "", "total_max": 0, "items": []}

    lines = text.splitlines()
    declared_total: Optional[float] = None
    items: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None

    def _flush() -> None:
        if cur is not None:
            cur["standards_text"] = _standards_text(cur.pop("_desc"), cur["criteria"], cur["levels"])
            items.append(cur)

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if declared_total is None:
            mt = _TOTAL_RE.search(line)
            if mt:
                declared_total = _to_num(mt.group(1))

        # 评分项表头以【权重】标记区分（评分点/等级档位行不含「权重」），
        # 避免无破折号的宽松匹配把「1. 形象气质（1分）：…」误判为评分项。
        m_item = _ITEM_RE.match(line) if "权重" in line else None
        if m_item:
            _flush()
            # 去掉可能被非贪婪分组吞入名称的拖尾破折号（如"形象礼仪 -"→"形象礼仪"）
            name = m_item.group(2).strip().rstrip("-—").strip()
            max_score = _to_num(m_item.group(3))
            mw = _WEIGHT_RE.search(line)
            weight = _to_num(mw.group(1)) if mw else 1.0
            source, modality = _infer_source_modality(name)
            cur = {
                "key": f"item_{len(items) + 1}",
                "name": name,
                "max_score": int(round(max_score)),
                "weight": weight,
                "source": source,
                "modality": modality,
                "criteria": [],
                "levels": [],
                "standards_text": "",
                "_desc": [],
            }
            continue

        if cur is None:
            continue

        m_level = _LEVEL_RE.match(line)
        if m_level:
            lo = _to_num(m_level.group(2))
            hi = _to_num(m_level.group(3)) if m_level.group(3) else lo
            cur["levels"].append(
                {"name": m_level.group(1), "min": int(round(lo)), "max": int(round(hi)), "desc": m_level.group(4).strip()}
            )
            continue

        m_crit = _CRITERION_RE.match(line)
        if m_crit:
            cur["criteria"].append(
                {"name": m_crit.group(1).strip(), "points": int(round(_to_num(m_crit.group(2)))), "desc": m_crit.group(3).strip()}
            )
            continue

        m_lvl2 = _LEVEL_NONAME_RE.match(line)
        if m_lvl2:
            lo = _to_num(m_lvl2.group(1))
            hi = _to_num(m_lvl2.group(2)) if m_lvl2.group(2) else lo
            name = _NONAME_LEVEL_NAMES[len(cur["levels"])] if len(cur["levels"]) < len(_NONAME_LEVEL_NAMES) else f"{int(lo)}分档"
            cur["levels"].append(
                {"name": name, "min": int(round(lo)), "max": int(round(hi)), "desc": m_lvl2.group(3).strip()}
            )
            continue

        cur["_desc"].append(line)

    _flush()

    total_max = int(round(declared_total)) if declared_total is not None else sum(i["max_score"] for i in items)
    return {"rubric_name": "", "total_max": total_max, "items": items}
