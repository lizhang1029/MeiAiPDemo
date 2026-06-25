"""语音/视频转写（ASR）：接入阿里百炼 Paraformer 语音识别。

设计目标：
- 有 DASHSCOPE_API_KEY 且安装 dashscope SDK 时，调用百炼 Paraformer 对上传的
  音/视频做真实语音识别。
- 视频文件先用 ffmpeg 抽取音轨并重采样为 16k 单声道 wav，再送入识别。
- 无 Key / 缺少依赖 / 识别失败时，自动降级为 mock 转写，保证 demo 可离线跑通。

转写结果仅为「原始转写文本」，其中可能包含考官读题；剔除考官读题、仅保留考生
回答的逻辑由 `transcript.clean_transcript` 在评分阶段完成。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Dict, Any, List, Optional

# Paraformer 实时识别模型（支持本地文件同步识别）
ASR_MODEL = os.getenv("DASHSCOPE_ASR_MODEL", "paraformer-realtime-v2")

# 常见音/视频扩展名
_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".amr"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".webm", ".wmv", ".m4v", ".ts"}


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _extract_wav(src_path: str, dst_path: str) -> None:
    """用 ffmpeg 把任意音/视频转成 16k 单声道 wav（Paraformer 推荐格式）。"""
    cmd = [
        "ffmpeg", "-y", "-i", src_path,
        "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", dst_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _language_hints(language: str) -> List[str]:
    lang = (language or "zh").lower()
    if lang.startswith("vi"):
        return ["vi", "zh"]
    if lang.startswith("en"):
        return ["en", "zh"]
    return ["zh", "en"]


class ASRClient:
    """封装百炼 Paraformer 语音识别；自动检测 mock / 真实模式。"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = (api_key or os.getenv("DASHSCOPE_API_KEY", "")).strip()
        self.model = model or ASR_MODEL
        self.mock = not bool(self.api_key)
        self._dashscope = None
        if not self.mock:
            try:
                import dashscope  # type: ignore

                dashscope.api_key = self.api_key
                self._dashscope = dashscope
            except Exception as exc:  # pragma: no cover - 依赖缺失降级
                print(f"[ASRClient] 加载 dashscope 失败，降级 mock: {exc}")
                self.mock = True

    @property
    def mode(self) -> str:
        return "mock" if self.mock else "bailian-asr"

    def transcribe(self, data: bytes, filename: str, language: str = "zh") -> Dict[str, Any]:
        """转写上传的音/视频字节流。

        返回:
            {"text": "转写文本", "engine": "mock|bailian-asr",
             "is_video": bool, "note": "可选说明"}
        """
        ext = os.path.splitext(filename or "")[1].lower()
        is_video = ext in _VIDEO_EXTS

        if self.mock:
            return {
                "text": _mock_transcript(language, is_video),
                "engine": "mock",
                "is_video": is_video,
                "note": "未配置 DASHSCOPE_API_KEY 或缺少 dashscope 依赖，返回示例转写。",
            }

        tmpdir = tempfile.mkdtemp(prefix="asr_")
        try:
            src_path = os.path.join(tmpdir, "input" + (ext or ".bin"))
            with open(src_path, "wb") as f:
                f.write(data)

            # 统一转 16k 单声道 wav；音频亦重采样以保证格式正确
            audio_path = os.path.join(tmpdir, "audio.wav")
            if _has_ffmpeg():
                _extract_wav(src_path, audio_path)
            elif ext == ".wav":
                audio_path = src_path
            else:
                return {
                    "text": _mock_transcript(language, is_video),
                    "engine": "mock",
                    "is_video": is_video,
                    "note": "服务器缺少 ffmpeg，无法抽取音轨，返回示例转写。",
                }

            text = self._recognize(audio_path, language)
            return {"text": text, "engine": "bailian-asr", "is_video": is_video, "note": ""}
        except Exception as exc:  # pragma: no cover - 网络/识别失败降级
            return {
                "text": _mock_transcript(language, is_video),
                "engine": "mock",
                "is_video": is_video,
                "note": f"语音识别失败，已降级示例转写：{exc}",
            }
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _recognize(self, audio_path: str, language: str) -> str:
        """调用 Paraformer 对本地 wav 做同步识别，拼接为整段文本。"""
        from dashscope.audio.asr import Recognition  # type: ignore

        recognition = Recognition(
            model=self.model,
            format="wav",
            sample_rate=16000,
            language_hints=_language_hints(language),
            callback=None,
        )
        result = recognition.call(audio_path)
        sentences = result.get_sentence() if hasattr(result, "get_sentence") else None
        if not sentences:
            return ""
        return "".join(s.get("text", "") for s in sentences).strip()


# --------------------------------------------------------------------------- #
# Mock 转写：用于无 Key / 离线演示。故意包含「考官：」读题行，便于演示自动剔除。
# --------------------------------------------------------------------------- #

_MOCK_BY_LANG = {
    "zh": (
        "考官：请结合题目进行讲解。\n"
        "考生：各位游客大家好，我是本次的讲解员。下面我将围绕题目要点展开："
        "首先介绍整体概况，其次讲解特色与文化内涵，最后总结注意事项，"
        "希望大家在游览中既能欣赏美景，也能了解背后的历史文化。"
    ),
    "vi": (
        "考官：请用越南语完成本题作答。\n"
        "考生：Xin chào quý khách, tôi là hướng dẫn viên của đoàn. "
        "Trong phần này tôi sẽ giới thiệu tổng quan, đặc điểm nổi bật và "
        "giá trị văn hóa, chúc quý khách có chuyến tham quan vui vẻ."
    ),
    "en": (
        "考官：Please answer the question in English.\n"
        "考生：Good morning everyone, I am your tour guide. "
        "First I will give an overview, then explain the cultural highlights, "
        "and finally share some tips so you can enjoy the visit safely."
    ),
}


def _mock_transcript(language: str, is_video: bool) -> str:
    lang = (language or "zh").lower()
    key = "vi" if lang.startswith("vi") else "en" if lang.startswith("en") else "zh"
    return _MOCK_BY_LANG[key]
