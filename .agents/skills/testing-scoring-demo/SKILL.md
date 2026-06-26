---
name: testing-scoring-demo
description: Test the AI guide-interview scoring demo (FastAPI + web UI) end-to-end via the browser. Use when verifying scoring, position question-bank, examiner-reading exclusion, the exam-paper JSON import feature, or audio/video transcription (ASR).
---

# Testing the AI 导游面试评分 Demo

End-to-end UI testing for the scoring demo in this repo. Two entry modes share one page:
- **岗位题库 (bank)**: fixed 7-dimension rubric per position.
- **导入试题 JSON (import)**: dynamic dimensions parsed from a 考务接口 exam-paper JSON (ezinterview format).

## Setup
1. Start server: `uvicorn app.main:app --port 8000` (runs in **mock** engine when `DASHSCOPE_API_KEY` is unset — no real LLM needed). Verify `curl -s localhost:8000/health` returns `{"status":"ok","engine_mode":"mock"}`.
2. Maximize browser before recording: `wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz`.
3. Navigate Chrome to `http://localhost:8000`.

## Key UI flow (import mode)
1. Click **导入试题 JSON（接口）** to switch source mode.
2. Click **载入越南语样例** / **载入普通话样例** to populate the JSON textarea, then **解析试题**.
3. Banner should read e.g. `已解析：03.越南语（vi）· 共 7 个维度 · 满分合计 100`.
4. Click **填充示例数据（含考官读题）**, then **开始 AI 评分**.
5. Scroll the LEFT panel to reach the fill/score buttons (they sit at the bottom of a long form); scroll the RIGHT panel up to read results.

## Key UI flow (ASR / audio-video transcription)
Each dimension's answer box has a **Choose File** input + **🎙 转写** button + a status line directly below it (added in the ASR PR).
1. Prepare test media on the box (ffmpeg): audio `ffmpeg -f lavfi -i "sine=frequency=440:duration=2" -ar 16000 /tmp/test_audio.wav`; video `ffmpeg -f lavfi -i testsrc=duration=1:size=320x240 -f lavfi -i sine=frequency=440:duration=1 /tmp/test_vid.mp4`.
2. Click a dimension's **Choose File** → GTK dialog opens → press `Ctrl+L` and type the absolute path (e.g. `/tmp/test_audio.wav`) → Enter. (The file input then shows `C:\fakepath\<name>` in the DOM — that's normal browser behavior.)
3. Click that dimension's **🎙 转写**. Status briefly shows `🔄 转写中…` then `✅ 已转写（mock）…`; the answer `textarea` fills with the mock transcript (starts `考官：…` then `考生：各位游客大家好…`).
4. For video, status reads `✅ 已转写（mock · 视频抽音轨）` (proves `is_video=true` + ffmpeg audio-extract path).
5. Then **开始 AI 评分** to prove the transcribed text flows into scoring + examiner exclusion (the `考官：` line becomes `✂ 已剔除考官读题`).

## What to assert
- **Dynamic parse**: dimension count + names + per-dim max_score match the JSON. 越南语 = 7 dims (incl. 中译外/外译中) total 100; 普通话 = 5 dims (专题/景区 each 35) total 100. Image-only items render `🖼 题目图片` link + placeholder text 「（图片题，题干见附图，需 OCR / 人工录入）」.
- **Integer scoring**: total like `66/100` and every per-dim score is an integer (no decimals).
- **Examiner exclusion**: each dim with a 「考官：」line shows orange `✂ 已剔除考官读题: <题目>`; evidence/transcript snippets start with the candidate answer, never with 「考官：」.
- **Regression**: switch back to 岗位题库, fill + score → still integer total, exclusion still works (7 fixed dims).

## Tips / gotchas
- The DOM is large; the stripped DOM in computer-tool output is the fastest way to read exact scores/banner text without zooming.
- Sample JSON `point` values may exceed 100 (e.g. 170) in raw form because the composite 专题路线讲解 (mq-lr) lists a container point; the parser drills into the selected sub-item so the **displayed** total is normalized to 100. Assert against the parsed banner/dim values, not raw JSON `point`.
- After a process/VM restart, the uvicorn server and browser are gone and any active recording is lost — restart server, re-maximize, re-navigate, and start a fresh recording before re-running tests.
- Annotate the recording: one `test_start` per test + a consolidated `assertion` (passed/failed) each. Keep assertions < 80 chars.
- Report: post ONE PR comment with `<details>` per test + an animated webp of the recording (convert mp4 with `ffmpeg -i in.mp4 -vf "fps=8,scale=900:-1" -loop 0 demo.webp`; raw mp4 is rejected in PR comments).

## What to assert (ASR)
- After 转写: target dimension's empty textarea fills with the mock transcript; status line shows engine `mock`. A broken impl leaves it empty / errors / stuck on `转写中`.
- Video file: status contains `视频抽音轨`.
- Transcribed text is **raw** (keeps `考官：` line); examiner-reading removal happens later in scoring, so only after 评分 does the `✂ 已剔除考官读题` appear — don't expect cleanup at transcribe time.

## Tips / gotchas (ASR)
- mock 模式下 `/transcribe` returns a FIXED sample transcript regardless of the uploaded audio content — do NOT assert on speech accuracy in mock mode (mark real-recognition accuracy as `untested`).
- The `language` form field is auto-inferred client-side (`currentLanguage()`): import mode → paper language; bank mode → `en` only for 英语导游 position, else `zh`. mock returns zh/vi/en sample text accordingly.
- Real ASR path needs both `DASHSCOPE_API_KEY` AND the `dashscope` pip package AND `ffmpeg` on PATH; missing any → graceful mock fallback with a `note` explaining why.

## Devin Secrets Needed
- None for mock-mode UI testing. (`DASHSCOPE_API_KEY` only needed to exercise the real 阿里百炼 scoring engine AND real Paraformer ASR transcription.)
