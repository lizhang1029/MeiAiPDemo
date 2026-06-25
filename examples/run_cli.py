"""命令行 demo：直接调用评分引擎对一份样例面试进行评分并打印报告。

用法:
    python -m examples.run_cli                 # 岗位题库 mock 评分
    python -m examples.run_cli --import-paper  # 演示「接口下发试题 JSON」导入评分
    DASHSCOPE_API_KEY=sk-xxx python -m examples.run_cli   # 接入百炼
"""
from __future__ import annotations

import json
import os
import sys

from app.core.paper_import import build_rubric, parse_exam_paper
from app.core.scoring_engine import ScoringEngine

_HERE = os.path.dirname(__file__)

# 回答转写故意包含「考官：」读题行，演示自动剔除考官读题
SAMPLE_ITEMS = [
    {
        "dimension_key": "language_expression",
        "question": "请用一段话欢迎来自全国各地的游客，并介绍今天的行程安排",
        "answer_transcript": "考官：请用一段话欢迎来自全国各地的游客，并介绍今天的行程安排。\n考生：各位游客大家好，我是导游张三，非常高兴为大家服务，我会用清晰流畅的普通话带大家领略广西的山水之美，希望大家旅途愉快。",
    },
    {
        "dimension_key": "route_explanation",
        "question": "请设计并讲解一条'桂林山水'两日精华专题线路",
        "answer_transcript": "考官：请设计并讲解一条桂林山水两日精华专题线路。\n考生：本次专题线路以漓江山水为主题。首先从象鼻山出发，它是桂林城徽；其次乘船游览漓江百里画廊，欣赏九马画山；最后到达兴安灵渠，感受秦代水利智慧。",
    },
    {
        "dimension_key": "scenic_explanation",
        "question": "请现场讲解象鼻山景区，突出其特色与文化内涵",
        "answer_transcript": "考官：请现场讲解象鼻山景区。\n考生：象鼻山位于漓江与桃花江汇流处，因山形似巨象临江饮水而得名。我们沿江边动线讲解，先观全景，再看水月洞，最后讲述象山传说，传递桂林山水文化价值。",
    },
    {
        "dimension_key": "service_qa",
        "question": "请简述标准导游服务流程及全程应遵守的服务规范",
        "answer_transcript": "考官：请简述标准导游服务流程。\n考生：导游服务流程包括接团准备、首站接待、行程讲解、安全提示和送团总结，全程主动告知、规范礼仪，依据导游管理条例不得擅自改变行程或诱导购物。",
    },
    {
        "dimension_key": "contingency_qa",
        "question": "行程途中一名游客突发疾病，你将如何处置？",
        "answer_transcript": "考官：游客突发疾病如何处理？\n考生：我会立即停止行程，拨打120，保护现场并安抚其他游客，同时上报旅行社，确保人身安全优先。",
    },
    {
        "dimension_key": "knowledge_qa",
        "question": "请介绍广西的世界遗产与国家级非物质文化遗产代表",
        "answer_transcript": "考官：介绍广西旅游文化。\n考生：广西是中国唯一沿海的少数民族自治区，壮族三月三是国家级非遗，湘江战役纪念馆是红色教育基地，灵渠是世界灌溉工程遗产。",
    },
    {
        "dimension_key": "image_etiquette",
        "question": "请整理仪容仪表，面向镜头做自我展示",
        "answer_transcript": "",
        "multimodal_features": {
            "face_detected": True,
            "smile_ratio": 0.62,
            "eye_contact_ratio": 0.71,
            "posture_score": 0.8,
            "dress_formal": True,
            "grooming_clean": True,
        },
    },
]


def run_bank(engine: ScoringEngine) -> None:
    """岗位题库评分（内置 7 维 Rubric）。"""
    result = engine.score_interview(
        {"name": "张三", "candidate_no": "GX2026-001", "position": "guide_zh"},
        SAMPLE_ITEMS,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_import(engine: ScoringEngine, sample: str = "sample_paper_vi.json") -> None:
    """演示「接口下发试题 JSON」：解析试题 → 动态维度评分。"""
    data = json.load(open(os.path.join(_HERE, sample), encoding="utf-8"))
    paper = parse_exam_paper(data)
    print(f"== 导入试卷: {paper['paper_name']} | 维度 {len(paper['dimensions'])} | 满分 {paper['total_max']} ==")
    items = [
        {
            **dim,
            "answer_transcript": "考官：" + dim["question"]
            + "\n考生：各位游客大家好，我是导游，首先介绍广西漓江山水，其次讲解壮族三月三非遗文化，最后提示安全注意事项，内容完整、逻辑清晰。",
        }
        for dim in paper["dimensions"]
    ]
    rubric = build_rubric(paper["dimensions"])
    result = engine.score_interview(
        {"name": "李四", "candidate_no": "GX-VI-001", "position": paper["paper_name"]},
        items,
        rubric=rubric,
        total_max=paper["total_max"],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    engine = ScoringEngine()
    print(f"== 评分引擎模式: {engine.mode} ==\n")
    if "--import-paper" in sys.argv:
        run_import(engine)
    else:
        run_bank(engine)


if __name__ == "__main__":
    main()
