"""阿里百炼（DashScope / 通义千问 Qwen）大模型客户端。

设计目标：
- 有 DASHSCOPE_API_KEY 时，调用百炼 OpenAI 兼容接口进行真实推理。
- 无 Key 时自动降级为 mock 模式，基于启发式规则生成结构化评分，保证 demo 可直接跑通。
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, Any, List, Optional


# 百炼 OpenAI 兼容模式 Base URL
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
DEFAULT_MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-plus")
# 多模态视觉模型：用于口译「外译中」图片直读判分（读图 + 中文回答 → 判翻译准确度）
DEFAULT_VL_MODEL = os.getenv("DASHSCOPE_VL_MODEL", "qwen-vl-max")


class BailianClient:
    """封装百炼对话接口；自动检测 mock / 真实模式。"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "").strip()
        self.model = model or DEFAULT_MODEL
        self.mock = not bool(self.api_key)
        self._client = None
        if not self.mock:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key, base_url=DASHSCOPE_BASE_URL)
            except Exception as exc:  # pragma: no cover - 网络/依赖问题降级
                print(f"[BailianClient] 初始化真实客户端失败，降级 mock: {exc}")
                self.mock = True

    @property
    def mode(self) -> str:
        return "mock" if self.mock else "bailian"

    def chat_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """发送对话请求并解析返回的 JSON。"""
        if self.mock:
            return _mock_score(user_prompt)

        resp = self._client.chat.completions.create(  # type: ignore[union-attr]
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        return _safe_json(content)

    def chat_vision_json(
        self, system_prompt: str, user_prompt: str, image_urls: List[str]
    ) -> Dict[str, Any]:
        """多模态判分：把题目图片 + 文本一起交给视觉模型，返回结构化 JSON。

        用于口译「外译中」：图片是外语原文，考生用中文口译；模型直接读图对照原意
        判断中文回答的翻译准确度（无需先 OCR）。无 Key 或无图片时降级 mock。
        """
        if self.mock or not image_urls:
            return _mock_vision_score(user_prompt, image_urls)

        content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
        try:
            resp = self._client.chat.completions.create(  # type: ignore[union-attr]
                model=DEFAULT_VL_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                temperature=0.2,
            )
            raw = resp.choices[0].message.content or "{}"
            return _safe_json(raw)
        except Exception as exc:  # pragma: no cover - 网络/模型问题降级
            print(f"[BailianClient] 视觉判分失败，降级 mock: {exc}")
            return _mock_vision_score(user_prompt, image_urls)


def _safe_json(text: str) -> Dict[str, Any]:
    """从模型输出中稳健提取 JSON。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {"_parse_error": True, "raw": text}


# --------------------------------------------------------------------------- #
# Mock 评分逻辑：基于回答文本与多模态特征的启发式打分，用于无 Key 演示。
# --------------------------------------------------------------------------- #

def _extract_block(prompt: str, header: str, until_headers: List[str]) -> str:
    start = prompt.find(header)
    if start == -1:
        return ""
    start += len(header)
    end = len(prompt)
    for h in until_headers:
        idx = prompt.find(h, start)
        if idx != -1:
            end = min(end, idx)
    return prompt[start:end].strip()


def _mock_score(user_prompt: str) -> Dict[str, Any]:
    """根据 Prompt 内嵌的维度信息与回答长度/关键词，生成结构化评分。"""
    # 解析维度元信息
    dim_key = _search(r"key=([a-z_]+),\s*满分", user_prompt) or "unknown"
    max_score = float(_search(r"满分=([0-9.]+),\s*模态", user_prompt) or 10)

    # 提取回答块（标题以「# 候选人回答」开头，剩余括号说明可能变化）
    a_start = user_prompt.find("# 候选人回答")
    if a_start != -1:
        a_start = user_prompt.find("\n", a_start) + 1
        a_end = user_prompt.find("\n#", a_start)
        answer = user_prompt[a_start:(a_end if a_end != -1 else len(user_prompt))].strip()
    else:
        answer = ""

    # 启发式：依据回答长度、结构词、专业词密度估计质量比例 (0.4~0.95)
    length = len(answer)
    structure_hits = len(re.findall(r"(首先|其次|然后|最后|第一|第二|总之|另外|因此)", answer))
    domain_hits = len(re.findall(r"(广西|漓江|象鼻山|壮族|非遗|导游|讲解|文化|历史|安全|游客|景区)", answer))

    if length == 0:
        ratio = 0.0
    else:
        ratio = 0.45 + min(length, 400) / 400 * 0.25 + min(structure_hits, 4) * 0.04 + min(domain_hits, 6) * 0.03
        ratio = max(0.2, min(0.95, ratio))

    # 分数取整数（不出现小数点）
    score = int(round(max_score * ratio))
    score = max(0, min(int(max_score), score))

    # 等级
    level = _mock_level(score, max_score)

    deductions = []
    if length > 0:
        gap = int(max_score) - score
        if gap > 0:
            reasons = []
            if structure_hits == 0:
                reasons.append("回答逻辑结构不够清晰，缺少层次衔接")
            if domain_hits < 2:
                reasons.append("专业知识与本地文化要素覆盖不足")
            if length < 80:
                reasons.append("内容展开不充分，信息量偏少")
            if not reasons:
                reasons.append("表达与内容细节仍有提升空间")
            for reason, pts in zip(reasons, _split_int(gap, len(reasons))):
                if pts > 0:
                    deductions.append(
                        {"reason": reason, "points": pts, "evidence": _snippet(answer)}
                    )
    if length == 0:
        deductions.append(
            {"reason": "未检测到有效回答内容", "points": int(max_score), "evidence": "（空）"}
        )

    evidence = [
        {
            "type": "transcript",
            "content": _snippet(answer),
            "ref": "答案转写片段",
        }
    ]
    if domain_hits > 0:
        evidence.append(
            {
                "type": "rag",
                "content": "回答中涉及广西旅游文化相关知识点，已与知识库匹配",
                "ref": "KB:guangxi/*",
            }
        )

    confidence = round(0.7 + min(length, 300) / 300 * 0.2, 2) if length else 0.5

    return {
        "dimension_key": dim_key,
        "max_score": max_score,
        "score": score,
        "level": level,
        "items": [],
        "deductions": deductions,
        "rationale": _mock_rationale(level, structure_hits, domain_hits, length),
        "evidence": evidence,
        "confidence": confidence,
        "_mock": True,
    }


def _mock_vision_score(user_prompt: str, image_urls: List[str]) -> Dict[str, Any]:
    """外译中图片直读判分的 mock：无 Key/无视觉模型时，基于回答文本长度启发式给分。

    真实模式下由 qwen-vl 读图对照外语原文判分；mock 无法真正读图，故仅依据中文
    回答是否非空/篇幅给出占位分，并在依据中说明为占位结果。
    """
    base = _mock_score(user_prompt)
    n_img = len(image_urls or [])
    if not image_urls:
        base["rationale"] = "未提供题目图片，无法进行外译中图片直读判分。" + base.get("rationale", "")
        base["confidence"] = 0.4
    else:
        base["rationale"] = (
            f"[占位] 已接收 {n_img} 张外语题目图片，但当前为 mock 模式无法真正读图；"
            "以下依据中文回答篇幅估算。真实判分需配置 DASHSCOPE_API_KEY 并使用 qwen-vl。"
            + base.get("rationale", "")
        )
        base["confidence"] = 0.5
    base["evidence"] = (base.get("evidence") or []) + [
        {"type": "image", "content": f"外语题目图片 ×{n_img}（图片直读判分输入）", "ref": "试题图片"}
    ]
    base["_mock_vision"] = True
    return base


def _mock_level(score: float, max_score: float) -> str:
    r = score / max_score if max_score else 0
    if r >= 0.85:
        return "优秀"
    if r >= 0.6:
        return "良好"
    if r >= 0.4:
        return "合格"
    return "不合格"


def _mock_rationale(level: str, structure: int, domain: int, length: int) -> str:
    if length == 0:
        return "未检测到有效回答，无法给分。"
    bits = [f"整体评定为「{level}」。"]
    bits.append("逻辑结构较清晰。" if structure >= 2 else "逻辑层次有待加强。")
    bits.append("专业与文化知识覆盖较好。" if domain >= 3 else "专业知识覆盖一般。")
    bits.append("内容展开充分。" if length >= 150 else "内容可进一步充实。")
    return "".join(bits)


def _snippet(text: str, n: int = 60) -> str:
    text = text.strip().replace("\n", " ")
    return (text[:n] + "…") if len(text) > n else text


def _search(pattern: str, text: str) -> Optional[str]:
    m = re.search(pattern, text)
    return m.group(1) if m else None


def _split_int(total: int, parts: int) -> List[int]:
    """把整数 total 尽量平均地拆成 parts 份整数，和恰为 total。"""
    if parts <= 0:
        return []
    base, rem = divmod(total, parts)
    return [base + (1 if i < rem else 0) for i in range(parts)]
