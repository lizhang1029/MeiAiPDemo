"""图片加载与多格式试题解析工具。

用于口译「外译中」场景：题目是一段小语种（外语）文字的图片，考生用中文口译。
按需求不做 OCR，而是把「题目图片 + 考生中文回答」一起交给多模态模型（qwen-vl-max）
直接对照图片原意判分。本模块负责把各种来源的图片统一成模型可用的 data URL，
并支持从 JSON / PDF / 图片文件三种格式录入试题。
"""
from __future__ import annotations

import base64
import mimetypes
import os
from typing import Any, Dict, List, Optional

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif"}


def is_image_filename(name: str) -> bool:
    return os.path.splitext(name or "")[1].lower() in _IMAGE_EXTS


def bytes_to_data_url(data: bytes, filename: str = "image.png") -> str:
    """把图片二进制转为 data URL（base64），供多模态模型直接读取。"""
    mime = mimetypes.guess_type(filename)[0] or "image/png"
    if not mime.startswith("image/"):
        mime = "image/png"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def to_model_image_url(src: str, timeout: float = 15.0) -> Optional[str]:
    """把图片来源规整为模型可用的 URL。

    - 已是 data URL：原样返回。
    - http(s) URL：尝试下载并转 base64 data URL（内网/需鉴权的图模型无法直接取，
      故由后端代理下载）；下载失败则回退为原始 URL（交由模型侧尝试）。
    - 本地文件路径：读取并转 data URL。
    - 裸 base64 字符串：包成 data URL。
    """
    if not src:
        return None
    s = src.strip()
    if s.startswith("data:image/"):
        return s
    if s.startswith("http://") or s.startswith("https://"):
        try:
            import requests

            resp = requests.get(s, timeout=timeout)
            resp.raise_for_status()
            return bytes_to_data_url(resp.content, s.split("?")[0])
        except Exception:
            return s
    if os.path.isfile(s):
        with open(s, "rb") as f:
            return bytes_to_data_url(f.read(), s)
    # 裸 base64
    try:
        base64.b64decode(s, validate=True)
        return f"data:image/png;base64,{s}"
    except Exception:
        return None


def normalize_images(images: List[str]) -> List[str]:
    """批量把图片来源规整为模型可用 URL，剔除无法解析的。"""
    out: List[str] = []
    for img in images or []:
        url = to_model_image_url(img)
        if url:
            out.append(url)
    return out


# --------------------------------------------------------------------------- #
# 多格式试题录入：PDF / 图片 → 与 parse_exam_paper 一致的 dimensions 结构
# --------------------------------------------------------------------------- #
def _guess_modality(text: str, has_image: bool) -> str:
    if any(k in text for k in ("外译中", "译中", "翻译成中文", "译为中文")):
        return "translation"
    if any(k in text for k in ("中译外", "译外", "翻译成", "口译")):
        return "translation"
    if "讲解" in text:
        return "content"
    if has_image and not text.strip():
        return "translation"  # 纯图片题：默认按外译中处理
    return "qa"


def parse_pdf_paper(data: bytes, filename: str = "paper.pdf", render_dpi: int = 150) -> Dict[str, Any]:
    """解析 PDF 试题：逐页抽取文字题干，并把每页渲染为图片附上。

    文字版 PDF 可抽到题干文本；扫描/图片版 PDF 抽不到文字，则仅保留页面图片，
    交由多模态模型直读。每页作为一道题目条目返回。
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    dims: List[Dict[str, Any]] = []
    for i, page in enumerate(doc):
        text = (page.get_text() or "").strip()
        pix = page.get_pixmap(dpi=render_dpi)
        img_url = bytes_to_data_url(pix.tobytes("png"), f"page_{i + 1}.png")
        dims.append(
            {
                "dimension_key": f"pdf_{i + 1}",
                "dimension_name": f"第 {i + 1} 页题目",
                "modality": _guess_modality(text, True),
                "max_score": 0,
                "question": text,
                "images": [img_url],
                "item_id": f"pdf-p{i + 1}",
            }
        )
    doc.close()
    return {
        "paper_name": os.path.splitext(filename)[0],
        "language": "foreign",
        "total_max": 0,
        "dimensions": dims,
        "source_format": "pdf",
    }


def parse_image_paper(data: bytes, filename: str = "paper.jpg") -> Dict[str, Any]:
    """解析图片试题：整张图片作为一道（外译中）题目，交由多模态模型直读。"""
    img_url = bytes_to_data_url(data, filename)
    return {
        "paper_name": os.path.splitext(filename)[0],
        "language": "foreign",
        "total_max": 0,
        "dimensions": [
            {
                "dimension_key": "img_1",
                "dimension_name": "外译中（图片题）",
                "modality": "translation",
                "max_score": 0,
                "question": "",
                "images": [img_url],
                "item_id": "img-1",
            }
        ],
        "source_format": "image",
    }
