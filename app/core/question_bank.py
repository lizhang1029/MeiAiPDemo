"""岗位与题库：每位考生的面试题目可不同。

提供按岗位维护的题库；同一岗位下每个评分维度可有多套候选题目，
便于为不同考生抽取不同题目。生产环境可替换为数据库 + 抽题策略。
"""
from __future__ import annotations

from typing import Dict, Any, List

from .rubric import RUBRIC


# 岗位定义：每个岗位下，按维度 key 维护候选题目列表。
POSITIONS: Dict[str, Dict[str, Any]] = {
    "guide_zh": {
        "name": "中文导游",
        "language": "zh",
        "questions": {
            "image_etiquette": ["请整理仪容仪表，面向镜头做自我展示"],
            "language_expression": [
                "请用一段话欢迎来自全国各地的游客，并介绍今天的行程安排",
                "请用普通话朗读并讲解一段关于桂林山水的导游词",
            ],
            "route_explanation": [
                "请设计并讲解一条'桂林山水'两日精华专题线路",
                "请设计并讲解一条'广西民族风情'专题线路",
            ],
            "scenic_explanation": [
                "请现场讲解象鼻山景区，突出其特色与文化内涵",
                "请现场讲解漓江景区，介绍主要观光节点",
            ],
            "service_qa": ["请简述标准导游服务流程及全程应遵守的服务规范"],
            "contingency_qa": ["行程途中一名游客突发疾病，你将如何处置？"],
            "knowledge_qa": ["请介绍广西的世界遗产与国家级非物质文化遗产代表"],
        },
    },
    "guide_en": {
        "name": "英语导游",
        "language": "en",
        "questions": {
            "image_etiquette": ["Please present yourself professionally to the camera"],
            "language_expression": [
                "Please welcome a group of foreign tourists and introduce today's itinerary in English",
            ],
            "route_explanation": [
                "Design and present a 2-day themed route highlighting Guilin's landscape",
            ],
            "scenic_explanation": [
                "Please guide tourists through the Elephant Trunk Hill scenic area in English",
            ],
            "service_qa": ["Describe the standard tour-guide service process and etiquette"],
            "contingency_qa": ["A tourist loses their passport during the trip. How do you handle it?"],
            "knowledge_qa": ["Introduce Guangxi's intangible cultural heritage to foreign guests"],
        },
    },
    "scenic_interpreter": {
        "name": "景区讲解员",
        "language": "zh",
        "questions": {
            "image_etiquette": ["请以讲解员形象面向镜头做自我展示"],
            "language_expression": ["请用富有感染力的语言介绍你所在景区的核心看点"],
            "route_explanation": ["请讲解一条景区内的主题游览动线"],
            "scenic_explanation": ["请现场讲解灵渠的历史价值与工程智慧"],
            "service_qa": ["请说明景区讲解服务规范与游客接待礼仪"],
            "contingency_qa": ["讲解途中遇到游客情绪激动投诉，你如何应对？"],
            "knowledge_qa": ["请介绍广西的红色文化资源及其教育意义"],
        },
    },
}


def list_positions() -> List[Dict[str, str]]:
    return [{"id": pid, "name": p["name"], "language": p["language"]} for pid, p in POSITIONS.items()]


def get_position(position_id: str) -> Dict[str, Any] | None:
    return POSITIONS.get(position_id)


def get_paper(position_id: str, variant: int = 0) -> List[Dict[str, str]]:
    """按岗位生成一份试卷：每个维度取一道题（variant 控制抽到第几套）。

    返回顺序与评分维度一致，便于前端逐维度展示。
    """
    pos = POSITIONS.get(position_id)
    if not pos:
        return []
    paper: List[Dict[str, str]] = []
    for dim in RUBRIC:
        qs = pos["questions"].get(dim.key, [])
        question = qs[variant % len(qs)] if qs else ""
        paper.append(
            {
                "dimension_key": dim.key,
                "dimension_name": dim.name,
                "max_score": dim.max_score,
                "question": question,
            }
        )
    return paper
