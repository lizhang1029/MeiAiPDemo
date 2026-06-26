"""导游面试评分体系（Rubric）定义。

总分 100 分，7 个一级维度。每个维度包含若干评分项与等级标准。
该结构既用于构造大模型评分 Prompt，也用于校验模型返回结果。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ScoreLevel:
    """评分等级描述：等级名称 + 分数区间 + 描述。"""

    name: str
    min_score: float
    max_score: float
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "min_score": self.min_score,
            "max_score": self.max_score,
            "description": self.description,
        }


@dataclass
class ScoreItem:
    """评分项（二级指标）。"""

    key: str
    name: str
    max_score: float
    criteria: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "max_score": self.max_score,
            "criteria": self.criteria,
        }


@dataclass
class Dimension:
    """一级评分维度。"""

    key: str
    name: str
    max_score: float
    modality: str  # video | audio | content | qa | translation
    items: List[ScoreItem] = field(default_factory=list)
    levels: List[ScoreLevel] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)
    weight: float = 1.0  # 权重：仅用于展示，总分=各项得分直接相加
    scoring_source: str = "per_question"  # per_question | whole | manual

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "max_score": self.max_score,
            "modality": self.modality,
            "items": [i.to_dict() for i in self.items],
            "levels": [l.to_dict() for l in self.levels],
            "requirements": self.requirements,
            "weight": self.weight,
            "scoring_source": self.scoring_source,
        }


RUBRIC: List[Dimension] = [
    Dimension(
        key="image_etiquette",
        name="形象礼仪",
        max_score=5,
        modality="video",
        items=[
            ScoreItem("appearance", "形象气质", 1, ["贴合导游职业形象", "精神饱满", "举止端庄"]),
            ScoreItem("grooming", "发型妆容", 1, ["整洁大方", "无夸张造型", "无浓妆艳抹"]),
            ScoreItem("dress", "着装规范", 2, ["整洁得体", "合身协调", "无污渍", "无破损"]),
            ScoreItem("expression", "表情仪态", 1, ["自然亲和", "眼神交流适度", "无不当仪态"]),
        ],
        levels=[
            ScoreLevel("优秀", 5, 5),
            ScoreLevel("良好", 4, 4),
            ScoreLevel("合格", 3, 3),
            ScoreLevel("不合格", 0, 2),
        ],
    ),
    Dimension(
        key="language_expression",
        name="语言表达",
        max_score=15,
        modality="audio",
        items=[
            ScoreItem("standard", "语言标准", 4, ["普通话标准", "无明显方言", "口齿清晰"]),
            ScoreItem("logic", "用词逻辑", 5, ["用词精准", "思路连贯", "主次分明"]),
            ScoreItem("fluency", "流畅生动", 6, ["表达流畅", "无频繁卡顿", "富有感染力"]),
        ],
        levels=[
            ScoreLevel("优秀", 13, 15),
            ScoreLevel("良好", 9, 12),
            ScoreLevel("合格", 6, 8),
            ScoreLevel("不合格", 0, 5),
        ],
    ),
    Dimension(
        key="route_explanation",
        name="专题线路讲解",
        max_score=25,
        modality="content",
        items=[
            ScoreItem("theme", "主题特色", 6, ["主题鲜明", "特色突出"]),
            ScoreItem("route_content", "线路内容", 7, ["内容完整", "节点清晰"]),
            ScoreItem("info_logic", "信息逻辑", 6, ["信息准确", "逻辑严密"]),
            ScoreItem("vividness", "生动内涵", 6, ["生动形象", "文化内涵丰富"]),
        ],
        levels=[
            ScoreLevel("优秀", 21, 25),
            ScoreLevel("良好", 15, 20),
            ScoreLevel("合格", 9, 14),
            ScoreLevel("不合格", 0, 8),
        ],
    ),
    Dimension(
        key="scenic_explanation",
        name="旅游景区讲解",
        max_score=25,
        modality="content",
        items=[
            ScoreItem("scenic_feature", "景区特色", 6, ["特色鲜明", "亮点突出"]),
            ScoreItem("route_line", "动线内容", 7, ["动线合理", "讲解完整"]),
            ScoreItem("info_logic", "信息逻辑", 6, ["信息准确", "逻辑清晰"]),
            ScoreItem("culture", "文化传达", 6, ["文化传达到位", "价值传递清晰"]),
        ],
        levels=[
            ScoreLevel("优秀", 21, 25),
            ScoreLevel("良好", 15, 20),
            ScoreLevel("合格", 9, 14),
            ScoreLevel("不合格", 0, 8),
        ],
    ),
    Dimension(
        key="service_qa",
        name="服务规范问答",
        max_score=10,
        modality="qa",
        requirements=["准确掌握导游服务流程", "礼仪规范", "专业知识"],
        levels=[
            ScoreLevel("优秀", 9, 10),
            ScoreLevel("良好", 6, 8),
            ScoreLevel("合格", 3, 5),
            ScoreLevel("不合格", 0, 2),
        ],
    ),
    Dimension(
        key="contingency_qa",
        name="应变能力问答",
        max_score=10,
        modality="qa",
        requirements=["准确判断场景", "方案合法合规", "切实可行"],
        levels=[
            ScoreLevel("优秀", 9, 10),
            ScoreLevel("良好", 6, 8),
            ScoreLevel("合格", 3, 5),
            ScoreLevel("不合格", 0, 2),
        ],
    ),
    Dimension(
        key="knowledge_qa",
        name="综合知识问答",
        max_score=10,
        modality="qa",
        requirements=["广西旅游文化", "历史地理", "民俗风情"],
        levels=[
            ScoreLevel("优秀", 9, 10),
            ScoreLevel("良好", 6, 8),
            ScoreLevel("合格", 3, 5),
            ScoreLevel("不合格", 0, 2),
        ],
    ),
]

TOTAL_SCORE = sum(d.max_score for d in RUBRIC)  # 100

DIMENSION_BY_KEY: Dict[str, Dimension] = {d.key: d for d in RUBRIC}


def rubric_to_dict() -> Dict[str, Any]:
    return {
        "total_score": TOTAL_SCORE,
        "dimensions": [d.to_dict() for d in RUBRIC],
    }


def level_for(dimension: Dimension, score: float) -> str:
    """根据分数定位等级名称。"""
    for level in dimension.levels:
        if level.min_score <= score <= level.max_score:
            return level.name
    return "不合格"
