---
name: testing-scoring-demo
description: Test the AI guide-interview scoring demo end-to-end (positions/questions, integer scoring, examiner-reading exclusion). Use when verifying Web UI or scoring changes.
---

# Testing the AI Guide Scoring Demo

## Run locally (mock mode, no API key needed)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pkill -f uvicorn 2>/dev/null   # kill stale server first; port 8000 reuse causes 'Not Found'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
- Health check: `curl -s localhost:8000/health` → `{"status":"ok","engine_mode":"mock"}`.
- Without `DASHSCOPE_API_KEY`, engine is `mock` (deterministic heuristic). Set the env var to use the real Bailian model. Mock is fine for verifying UI/structure/integer/exclusion logic.

## Web UI test flow (`http://localhost:8000`)
1. **Positions → questions change**: 报考岗位 dropdown has 中文导游/英语导游/景区讲解员. Switching reloads all dimension 题目 inputs via `GET /positions/{id}/paper`. Adversarial check: same dimension (e.g. 综合知识问答) should be Chinese under 中文导游 and English under 英语导游 — if identical, the per-position question loading is broken.
2. **Integer scoring**: click 「填充示例数据（含考官读题）」 then 「开始 AI 评分」. Verify total and every dimension score and deduction are integers (no `.x`). Old/broken behavior showed decimals like `64.6`.
3. **Examiner-reading exclusion**: the demo data prepends a `考官：<question>` line and a `考生：<answer>` line to each answer. After scoring, each affected dimension must show an orange `✂ 已剔除考官读题: <question>` line, and its `[transcript]`/证据 must start with the candidate answer (not `考官：`). If no ✂ line appears or evidence contains `考官：`, exclusion is broken.

## Tips
- The native `<select>` dropdown: click to open, then click the option; verify via DOM `selectedindex` — a click that misses leaves the old value selected. Re-open and reselect if it didn't change.
- Results render in the right panel; scroll the right column to see total score (top) and all 7 dimensions.
- API-only smoke test: `GET /positions`, `GET /positions/guide_zh/paper`, `POST /interviews`.

## Devin Secrets Needed
- None for mock-mode testing. `DASHSCOPE_API_KEY` only required to exercise the real Bailian model.
