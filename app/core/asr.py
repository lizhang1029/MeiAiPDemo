"""语音/视频转写（ASR）：接入阿里百炼 Paraformer 语音识别。

设计目标：
- 有 DASHSCOPE_API_KEY 且安装 dashscope SDK 时，调用百炼 Paraformer 对上传的
  音/视频做真实语音识别。
- 视频文件先用 ffmpeg 抽取音轨并重采样为 16k 单声道 wav，再送入识别。
- 无 Key / 缺少依赖 / 识别失败时，自动降级为 mock 转写，保证 demo 可离线跑通。

转写结果仅为「原始转写文本」，其中可能包含考官读题与考务口令；剔除这些与答题
无关的内容、仅保留考生回答的逻辑由 `transcript.clean_transcript` 在评分阶段完成。

整段面试场景：一名考生的整场面试为一个音/视频文件，按题目顺序作答，每题作答
前通常有明显停顿（等待读题）。`transcribe_segments` 在转写的基础上，依据句子
时间戳之间的停顿把整段切分为多段，按顺序对应到各题的回答。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Dict, Any, List, Optional

from .transcript import split_examiner_candidate

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

    def transcribe_segments(
        self,
        data: bytes,
        filename: str,
        language: str = "zh",
        pause_ms: int = 2000,
    ) -> Dict[str, Any]:
        """转写整段面试音/视频，并按题前停顿切分为多段（对应各题回答顺序）。

        返回:
            {"text": "整段转写", "segments": [{index, begin_ms, end_ms, text}],
             "engine": "mock|bailian-asr", "is_video": bool, "note": "..."}
        """
        ext = os.path.splitext(filename or "")[1].lower()
        is_video = ext in _VIDEO_EXTS

        if self.mock:
            segments = _mock_segments(language)
            return {
                "text": "\n".join(s["text"] for s in segments),
                "segments": segments,
                "engine": "mock",
                "is_video": is_video,
                "note": "未配置 DASHSCOPE_API_KEY 或缺少 dashscope 依赖，返回示例整段面试转写（已按题切分）。",
            }

        tmpdir = tempfile.mkdtemp(prefix="asr_")
        try:
            src_path = os.path.join(tmpdir, "input" + (ext or ".bin"))
            with open(src_path, "wb") as f:
                f.write(data)

            audio_path = os.path.join(tmpdir, "audio.wav")
            if _has_ffmpeg():
                try:
                    _extract_wav(src_path, audio_path)
                except subprocess.CalledProcessError as exc:
                    what = "视频抽取音轨" if is_video else "音频转码"
                    raise RuntimeError(
                        f"{what}失败（ffmpeg 退出码 {exc.returncode}）：文件可能损坏或为不受支持的编码"
                    ) from exc
            elif ext == ".wav":
                audio_path = src_path
            else:
                kind = "视频文件需先抽取音轨" if is_video else "该音频格式需转码"
                segments = _mock_segments(language)
                return {
                    "text": "\n".join(s["text"] for s in segments),
                    "segments": segments,
                    "engine": "mock",
                    "is_video": is_video,
                    "note": f"服务器缺少 ffmpeg（{kind}），无法处理，返回示例整段面试转写。请安装 ffmpeg 后重试。",
                }

            sentences = self._recognize_sentences(audio_path, language)
            segments = _segment_by_pause(sentences, pause_ms)
            if not segments:
                segments = _mock_segments(language)
                return {
                    "text": "\n".join(s["text"] for s in segments),
                    "segments": segments,
                    "engine": "mock",
                    "is_video": is_video,
                    "note": "未识别到有效语音，返回示例整段面试转写。",
                }
            full = "".join(s.get("text", "") for s in sentences).strip()
            return {
                "text": full,
                "segments": segments,
                "engine": "bailian-asr",
                "is_video": is_video,
                "note": f"按≥{pause_ms}ms 停顿切分为 {len(segments)} 段（对应各题回答顺序）。",
            }
        except Exception as exc:  # pragma: no cover - 网络/识别失败降级
            segments = _mock_segments(language)
            return {
                "text": "\n".join(s["text"] for s in segments),
                "segments": segments,
                "engine": "mock",
                "is_video": is_video,
                "note": f"音频处理/语音识别失败，已降级示例整段面试转写：{exc}",
            }
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _recognize(self, audio_path: str, language: str) -> str:
        """调用 Paraformer 对本地 wav 做同步识别，拼接为整段文本。"""
        sentences = self._recognize_sentences(audio_path, language)
        return "".join(s.get("text", "") for s in sentences).strip()

    def _recognize_sentences(self, audio_path: str, language: str) -> List[Dict[str, Any]]:
        """调用 Paraformer 同步识别，返回带时间戳的句子列表。

        识别失败（status_code != 200）时抛出异常并带上百炼返回的具体错误信息，
        以便上层把真实原因透传到前端，而不是静默降级为示例转写。
        """
        from dashscope.audio.asr import Recognition  # type: ignore

        recognition = Recognition(
            model=self.model,
            format="wav",
            sample_rate=16000,
            language_hints=_language_hints(language),
            callback=None,
        )
        result = recognition.call(audio_path)

        status = getattr(result, "status_code", 200)
        if status is not None and status != 200:
            code = getattr(result, "code", "")
            message = getattr(result, "message", "")
            raise RuntimeError(f"百炼识别返回 {status} {code}：{message}".strip())

        sentences = result.get_sentence() if hasattr(result, "get_sentence") else None
        return sentences or []


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


def _segment_by_pause(sentences: List[Dict[str, Any]], pause_ms: int) -> List[Dict[str, Any]]:
    """按句子时间戳之间的停顿切分整段转写。

    相邻句子间隔 ≥ pause_ms 视为一道新题的开始（考生作答前等待读题的停顿）。
    """
    groups: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    last_end: Optional[int] = None
    for s in sentences:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        begin = s.get("begin_time")
        end = s.get("end_time")
        if last_end is not None and begin is not None and (begin - last_end) >= pause_ms and cur:
            groups.append(cur)
            cur = []
        cur.append(s)
        if end is not None:
            last_end = end
    if cur:
        groups.append(cur)

    segments: List[Dict[str, Any]] = []
    for i, g in enumerate(groups):
        text = "".join((x.get("text") or "") for x in g).strip()
        qa = split_examiner_candidate(text)
        segments.append(
            {
                "index": i,
                "begin_ms": g[0].get("begin_time"),
                "end_ms": g[-1].get("end_time"),
                "text": text,
                # 未导入试题时，从录音中分离出的「考官提问」与「考生回答」（参考用，可在前端修改）
                "question": qa["question"],
                "answer": qa["answer"],
            }
        )
    return segments


# 示例整段面试转写（普通话）：5 道题、与内置普通话样例试卷一一对应。
# 每段刻意混入「考务口令 + 考官读题 + 考生回答」，且不带说话人标注（贴近真实 ASR），
# 用于演示「按停顿分段 + 评分阶段剔除与答题无关内容」的完整链路。
_MOCK_INTERVIEW_ZH = [
    "听到提示音后可以开始作答。专题历史广西线路一历史文化名城之旅。"
    "尊敬的各位来宾大家好，这条线路串联起广西多座历史名城："
    "我们先抵达桂林靖江王城，领略明代藩王府第的恢宏；再走进柳州柳侯祠，"
    "追忆柳宗元治理柳州的政绩；最后探访合浦汉代文化博物馆，感受海上丝路起点的繁华，"
    "整条线路让宾客在行走中读懂广西厚重的历史脉络。",
    "下一题旅游景区讲解桂林漓江景区请开始讲解。"
    "漓江是世界自然遗产、国家五A级景区，素有百里画廊的盛誉。"
    "我们乘船顺流而下，依次饱览九马画山的神奇、黄布倒影的灵秀和兴坪佳境的开阔，"
    "沿途青峰倒映、烟雨空蒙，生动诠释了桂林山水甲天下的独特意境。",
    "请看大屏幕服务规范问答地陪导游的准备工作中要准备哪些物品与资料现在开始作答。"
    "出团之前我会把接待计划、宾客名单和详细日程整理齐全，"
    "随身带好导游证、接站牌与团队旗帜，备齐各景点门票和讲解词，"
    "同时携带常用药品和紧急联络表，确保整个接待流程衔接顺畅、万无一失。",
    "下一题应变能力问答旅游者要求外出品尝风味餐时地陪导游应如何处理请作答。"
    "遇到这种情形，我会先耐心询问宾客的口味与预算，"
    "在不打乱既定行程的前提下及时向旅行社报备并取得同意，"
    "为大家甄选卫生达标、口碑良好的特色餐馆，并提醒注意饮食安全与费用自理，"
    "让宾客既尝到地道风味又玩得安心。",
    "最后一题综合知识问答广西有哪几种获得国家地理标志产品的水果请列举三项以上可以开始作答。"
    "广西的国家地理标志水果琳琅满目，例如百色芒果、富川脐橙、容县沙田柚，"
    "此外还有桂林金桔和荔浦的砂糖橘等，它们品质上乘、远近闻名，"
    "是广西亮丽的农业名片。",
]


def _mock_segments(language: str) -> List[Dict[str, Any]]:
    """返回示例整段面试的分段转写（默认普通话；音频优先场景）。"""
    texts = _MOCK_INTERVIEW_ZH
    segments: List[Dict[str, Any]] = []
    cursor = 0
    for i, t in enumerate(texts):
        dur = 8000 + len(t) * 40  # 估算每段时长（仅用于展示时间戳）
        begin = cursor
        end = cursor + dur
        qa = split_examiner_candidate(t)
        segments.append({
            "index": i, "begin_ms": begin, "end_ms": end, "text": t,
            "question": qa["question"], "answer": qa["answer"],
        })
        cursor = end + 4000  # 段间 4s 停顿（模拟题前等待）
    return segments
