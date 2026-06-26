"""岗位 + 评分表本地持久化（不引入数据库）。

每个岗位连同其评分表原文与解析结果存为一个本地 JSON 文件
（``data/positions/{id}.json``），重启不丢。生产环境可替换为数据库。
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from .rubric_parse import parse_rubric_text

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "positions"
)


def _ensure_dir() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)


def _path(position_id: str) -> str:
    return os.path.join(_DATA_DIR, f"{position_id}.json")


def _slug(name: str) -> str:
    base = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fa5]+", "-", name).strip("-")
    return (base or "pos")[:24]


def list_saved_positions() -> List[Dict[str, Any]]:
    """列出已保存岗位（精简信息，按更新时间倒序）。"""
    _ensure_dir()
    out: List[Dict[str, Any]] = []
    for fname in os.listdir(_DATA_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_DATA_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        out.append(
            {
                "id": data.get("id", fname[:-5]),
                "name": data.get("name", ""),
                "language": data.get("language", "zh"),
                "item_count": len(data.get("rubric", {}).get("items", [])),
                "total_max": data.get("rubric", {}).get("total_max", 0),
                "updated_at": data.get("updated_at", 0),
            }
        )
    out.sort(key=lambda p: p.get("updated_at", 0), reverse=True)
    return out


def get_saved_position(position_id: str) -> Optional[Dict[str, Any]]:
    path = _path(position_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_position(
    name: str,
    language: str = "zh",
    rubric_text: str = "",
    position_id: Optional[str] = None,
) -> Dict[str, Any]:
    """新建或更新岗位；评分表文本会被解析为结构化评分项一并保存。"""
    _ensure_dir()
    now = time.time()
    if not position_id:
        position_id = f"{_slug(name)}-{uuid.uuid4().hex[:6]}"

    existing = get_saved_position(position_id)
    created_at = existing.get("created_at", now) if existing else now

    rubric = parse_rubric_text(rubric_text)
    data = {
        "id": position_id,
        "name": name,
        "language": language,
        "rubric_text": rubric_text,
        "rubric": rubric,
        "created_at": created_at,
        "updated_at": now,
    }
    with open(_path(position_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def delete_position(position_id: str) -> bool:
    path = _path(position_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
