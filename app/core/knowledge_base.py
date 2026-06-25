"""轻量 RAG 知识库（广西旅游文化 + 导游服务规范）。

Demo 采用内存化关键词检索（BM25-lite）。生产环境可替换为向量库
（DashScope text-embedding + Milvus/PGVector），接口保持一致。
"""
from __future__ import annotations

import re
from typing import List, Dict, Any


# 知识条目：category 对应 RAG 体系分类
KB_DOCS: List[Dict[str, str]] = [
    {
        "id": "gx_scenic_lijiang",
        "category": "景区",
        "source": "广西/景区/漓江",
        "content": "漓江是桂林山水的代表，被誉为'百里画廊'，以喀斯特峰林、清澈江水著称，代表景观有九马画山、黄布倒影，是导游讲解线路的核心节点。",
    },
    {
        "id": "gx_scenic_xiangbi",
        "category": "景区",
        "source": "广西/景区/象鼻山",
        "content": "象鼻山位于桂林市区漓江与桃花江汇流处，因山形酷似一头巨象临江饮水而得名，是桂林城徽，讲解时应突出其形象特征与传说故事。",
    },
    {
        "id": "gx_culture_zhuang",
        "category": "民俗",
        "source": "广西/民俗/壮族三月三",
        "content": "壮族'三月三'是广西重要传统节日，以对歌、抛绣球、五色糯米饭等民俗活动闻名，2014年列入国家级非物质文化遗产，是讲解民俗风情的重要素材。",
    },
    {
        "id": "gx_heritage_dage",
        "category": "非遗",
        "source": "广西/非遗/刘三姐歌谣",
        "content": "刘三姐歌谣是广西壮族民歌文化的代表，2006年列入国家级非遗，'印象·刘三姐'实景演出是文旅融合典范。",
    },
    {
        "id": "gx_red_xiangjiang",
        "category": "红色文化",
        "source": "广西/红色文化/湘江战役",
        "content": "湘江战役是红军长征中最壮烈的战役之一，主战场位于广西桂林全州、兴安、灌阳一带，红军长征突破湘江纪念馆是重要的红色教育基地。",
    },
    {
        "id": "gx_history_lingqu",
        "category": "历史",
        "source": "广西/历史/灵渠",
        "content": "灵渠位于桂林兴安县，秦始皇时期开凿，是世界上最古老的运河之一，沟通湘江与漓江，连接长江与珠江两大水系，2018年入选世界灌溉工程遗产。",
    },
    {
        "id": "gx_geo",
        "category": "地理",
        "source": "广西/地理/概况",
        "content": "广西壮族自治区位于中国南部，北回归线横贯中部，地形以喀斯特地貌为主，沿海、沿江、沿边，是中国唯一沿海的少数民族自治区。",
    },
    {
        "id": "svc_process",
        "category": "导游服务规范",
        "source": "规范/导游服务流程",
        "content": "标准导游服务流程包括：接团准备、首站接待、行程讲解、餐饮住宿安排、安全提示、突发处理、送团总结。全程应主动告知、规范礼仪、保障游客安全。",
    },
    {
        "id": "svc_regulation",
        "category": "导游管理条例",
        "source": "规范/导游人员管理条例",
        "content": "依据《导游人员管理条例》，导游须持证上岗，不得擅自改变行程、不得诱导或强迫购物、不得索取小费，应维护游客合法权益与人身财产安全。",
    },
    {
        "id": "svc_emergency",
        "category": "导游服务规范",
        "source": "规范/应急处置",
        "content": "遇游客突发疾病或意外，应立即停止行程、拨打120/110、保护现场、安抚其他游客并及时上报旅行社；遇自然灾害应按预案有序疏散，确保人身安全优先。",
    },
]


def _tokenize(text: str) -> List[str]:
    # 中文按字 + 英文按词的混合切分，简单但够用
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    tokens += list(re.sub(r"[^\u4e00-\u9fff]", "", text))
    return tokens


class KnowledgeBase:
    def __init__(self, docs: List[Dict[str, str]] | None = None):
        self.docs = docs or KB_DOCS

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not query.strip():
            return []
        q_tokens = set(_tokenize(query))
        scored = []
        for doc in self.docs:
            d_tokens = _tokenize(doc["content"] + " " + doc["source"])
            overlap = sum(1 for t in d_tokens if t in q_tokens)
            if overlap:
                scored.append((overlap, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, doc in scored[:top_k]:
            results.append(
                {
                    "id": doc["id"],
                    "category": doc["category"],
                    "source": doc["source"],
                    "content": doc["content"],
                    "score": score,
                }
            )
        return results

    def categories(self) -> List[str]:
        return sorted({d["category"] for d in self.docs})
