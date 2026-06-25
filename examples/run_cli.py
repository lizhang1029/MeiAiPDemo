"""命令行 demo：直接调用评分引擎对一份样例面试进行评分并打印报告。

用法:
    python -m examples.run_cli          # mock 模式
    DASHSCOPE_API_KEY=sk-xxx python -m examples.run_cli   # 接入百炼
"""
from __future__ import annotations

import json

from app.core.scoring_engine import ScoringEngine

SAMPLE_ITEMS = [
    {
        "dimension_key": "language_expression",
        "question": "请做一段自我介绍并欢迎游客",
        "answer_transcript": "大家好，我是导游张三。今天非常高兴为各位服务，我会用清晰流畅的普通话带大家领略广西的山水之美，希望大家旅途愉快。",
    },
    {
        "dimension_key": "route_explanation",
        "question": "请讲解一条专题旅游线路",
        "answer_transcript": "本次专题线路以漓江山水为主题。首先从象鼻山出发，它是桂林城徽；其次乘船游览漓江百里画廊，欣赏九马画山；最后到达兴安灵渠，感受秦代水利智慧。",
    },
    {
        "dimension_key": "scenic_explanation",
        "question": "请讲解象鼻山景区",
        "answer_transcript": "象鼻山位于漓江与桃花江汇流处，因山形似巨象临江饮水而得名。我们沿江边动线讲解，先观全景，再看水月洞，最后讲述象山传说，传递桂林山水文化价值。",
    },
    {
        "dimension_key": "service_qa",
        "question": "请描述标准导游服务流程",
        "answer_transcript": "导游服务流程包括接团准备、首站接待、行程讲解、安全提示和送团总结，全程主动告知、规范礼仪，依据导游管理条例不得擅自改变行程或诱导购物。",
    },
    {
        "dimension_key": "contingency_qa",
        "question": "游客突发疾病如何处理",
        "answer_transcript": "我会立即停止行程，拨打120，保护现场并安抚其他游客，同时上报旅行社，确保人身安全优先。",
    },
    {
        "dimension_key": "knowledge_qa",
        "question": "介绍广西旅游文化",
        "answer_transcript": "广西是中国唯一沿海的少数民族自治区，壮族三月三是国家级非遗，湘江战役纪念馆是红色教育基地，灵渠是世界灌溉工程遗产。",
    },
    {
        "dimension_key": "image_etiquette",
        "question": "形象礼仪（基于视频分析）",
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


def main() -> None:
    engine = ScoringEngine()
    print(f"== 评分引擎模式: {engine.mode} ==\n")
    result = engine.score_interview(
        {"name": "张三", "candidate_no": "GX2026-001"}, SAMPLE_ITEMS
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
