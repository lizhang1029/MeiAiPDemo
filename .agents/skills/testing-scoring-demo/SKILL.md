---
name: testing-scoring-demo
description: Test the AI guide-interview scoring demo (FastAPI + web UI) end-to-end via the browser. Use when verifying the 4-step whole-interview wizard (upload → pause-based segmentation → exam-paper JSON import for stems only → manual rubric → integer scoring with examiner/prompt exclusion and evidence chain), or audio/video transcription (ASR).
---

# Testing the AI 导游面试评分 Demo

End-to-end UI testing for the scoring demo in this repo. The current page is a **4-step wizard** for scoring **one candidate's entire interview recording**:
- **① 上传整段录音 → 按题前停顿分段**: upload one full-interview audio; ASR returns sentence-level timestamps; gaps ≥ the 题前停顿阈值 (default 2000 ms) mark question boundaries, splitting the recording into ordered segments.
- **② 导入试题 JSON（仅取题干）**: parse a 考务接口 exam-paper JSON (ezinterview format) but take **only the question stems** (维度/满分/评分标准 are entered manually).
- **③ 生成评分表 + 自动回填**: one row per question — readonly 题干, auto-filled 该题考生回答 (from the matching segment), and manually entered 维度名/满分/评分标准. Total = sum of per-row max_scores.
- **④ 评分**: integer scores, removed-segment evidence (examiner prompts + question readings), and an evidence chain.

## Setup
1. Start server: `uvicorn app.main:app --port 8000` (runs in **mock** engine when `DASHSCOPE_API_KEY` is unset — no real LLM needed). Verify `curl -s localhost:8000/health` returns `{"status":"ok","engine_mode":"mock"}`.
2. Prepare test media (ffmpeg): a full-interview audio `ffmpeg -f lavfi -i "sine=frequency=440:duration=30" -ar 16000 -ac 1 /tmp/interview_full.wav` (mock `/transcribe_full` ignores content and returns a fixed 5-question transcript regardless).
3. Maximize browser before recording: `wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz`.
4. Navigate Chrome to `http://localhost:8000`.

## Key UI flow (4-step wizard)
1. **①** Click **Choose File** → GTK dialog → `Ctrl+L`, type `/tmp/interview_full.wav`, Enter. Leave 题前停顿阈值 = `2000`. Click **🎙 转写并分段**.
2. **②** Click **载入普通话样例** to populate the JSON textarea, then **解析题干**.
3. **③** Click **按题目数生成评分表**, then **填充示例评分标准**.
4. **④** Scroll to the bottom of the form and click **开始 AI 评分**; read results in the right/result panel.

## What to assert (4-step flow)
- **① Segmentation**: status reads `✅ 已转写并分段（mock）· 共 5 段`; `#segView` renders exactly **5** `.seg` blocks, each with a `第 N 段 · m:ss–m:ss` timestamp header and visible text (some containing examiner prompts like 「听到提示音」 and question readings). A broken segmenter yields 0/1 segment or no timestamps.
- **② Stems only**: `#paperInfo` reads `已解析：…（普通话样例名）· 取得 5 道题干（维度/满分/评分标准请在下方手动录入）。` (count must be 5; only stems imported, no dims/scores).
- **③ Rubric + auto-fill + total**: `#rubric` shows **5** `.qrow`; each readonly 题干 textarea is non-empty (from JSON); each **该题考生回答** textarea is auto-filled with the matching segment text; `#totalInfo` reads `共 5 题 · 满分合计 100` (5 × default 20). Broken auto-fill → empty answer boxes; broken total calc → wrong sum.
- **④ Integer scoring + exclusion + evidence**: result panel shows integer total `N/100` (no decimal); each of 5 `.dim-score` shows integer `score/max_score`; at least one dimension shows orange `✂ 已剔除无关提示: …` (examiner_prompt) AND `✂ 已剔除考官读题: …` (question_reading); each dimension shows `rationale`/evidence (e.g. `[transcript]` snippet + `[rag]` match). Decimals anywhere, `max_total ≠ 100`, or no removed segments = FAIL (cleaning didn't run / prompts leaked into scoring).

## Tips / gotchas
- The DOM is large; the stripped DOM in computer-tool output is the fastest way to read exact scores/banner text without zooming.
- The pause-based segmenter relies on **sentence-level timestamps** from ASR; mock `/transcribe_full` returns a FIXED 5-question transcript (with built-in pauses, examiner readings, and prompts like 「可以开始作答」「时间到」「下一题」) regardless of the uploaded audio — do NOT assert on speech accuracy in mock mode (mark real Paraformer accuracy as `untested`).
- ③ auto-fill aligns segment *i* to question row *i* in order; if counts differ, extra segments/rows stay unmatched — assert on the 5↔5 case from the 普通话 sample.
- Sample JSON `point` values may exceed 100 in raw form (composite 专题路线讲解 lists a container point); only stems are imported here, so the total comes from the **manual rubric** (5 × 20 = 100), not the JSON.
- After a process/VM restart, the uvicorn server and browser are gone and any active recording is lost — restart server, re-maximize, re-navigate, and start a fresh recording before re-running tests.
- Annotate the recording: one `test_start` per step (①–④) + a consolidated `assertion` (passed/failed) each. Keep assertions < 80 chars.
- Report: post ONE PR comment with `<details>` per test + an animated webp of the recording (convert mp4 with `ffmpeg -i in.mp4 -vf "fps=8,scale=900:-1" -loop 0 demo.webp`; raw mp4 is rejected in PR comments).

## Code map
- `app/web/index.html` — 4-step wizard markup + JS (segment render, auto-fill, total calc, score render).
- `app/core/asr.py` — `transcribe_full` + `_MOCK_INTERVIEW_ZH` (fixed 5-question transcript with timestamps); pause-based segmentation.
- `app/core/transcript.py` — `_PROMPT_PATTERNS` / cleaning (removes 考官读题 + 无关提示).
- `app/main.py` — `/transcribe_full` endpoint + scoring route.

## Devin Secrets Needed
- None for mock-mode UI testing. (`DASHSCOPE_API_KEY` only needed to exercise the real 阿里百炼 scoring engine AND real Paraformer ASR transcription; real ASR also needs the `dashscope` pip package AND `ffmpeg` on PATH — missing any → graceful mock fallback.)
