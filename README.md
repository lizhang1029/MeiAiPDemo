# AI 辅助导游面试评分系统 · Demo

基于 Python + 阿里百炼（DashScope / 通义千问 Qwen）的 **AI 辅助判分** 演示。
覆盖导游资格面试的 7 大评分维度，输出 **总分 / 分项分 / 扣分项 / 扣分原因 / 评分依据 / 引用证据 / AI 置信度** 的结构化、可解释评分结果。

> AI 仅提供评分建议，最终分数由评委确认。

## 特性

- **7 维度评分体系**（总分 100）：形象礼仪、语言表达、专题线路讲解、旅游景区讲解、服务规范问答、应变能力问答、综合知识问答。
- **岗位 + 题目入口**：内置多岗位题库（中文导游 / 英语导游 / 景区讲解员），**每位考生题目可不同**；选岗位自动带出题目，也可手动改题。
- **试题导入（接口对接）**：支持考务平台（ezinterview 格式）下发的试题 JSON（`sections → groups → items`），自动按 group 名映射评分维度、按 `selection` 抽题规则取题（含复合题 `mq-lr` 抽取小题）、抽取题干文本与图片，并以实际作答题目分值作为该维度满分。中文/外语题型不同（外语含**中译外/外译中**），维度与满分**随试题动态变化**。
- **分数全部为整数**：总分、分项分、扣分值均为整数，不出现小数点。
- **自动剔除考官读题**：ASR 转写中考官朗读题目的内容（「考官：…」标注行或与题目高度相似的行）会被自动剔除，仅对考生回答评分，并在结果中展示被剔除的内容。
- **接入阿里百炼**：OpenAI 兼容模式调用 Qwen，结构化 JSON 输出。
- **无 Key 自动降级**：未配置 `DASHSCOPE_API_KEY` 时走启发式 mock 引擎，demo 开箱即跑。
- **RAG 知识库**：内置广西旅游文化 + 导游服务规范知识，问答/讲解类维度自动检索证据。
- **评分校准**：分值区间约束、分项之和校验，降低评分漂移。
- **可解释证据链**：每个分数可回溯到 扣分原因 → 引用证据 → 转写片段 / 多模态指标。
- **REST API + Web UI**：一键演示。

## 本地运行步骤（查看效果）

> 需要 Python 3.10+。以下命令在项目根目录执行。

**第 1 步：创建虚拟环境并安装依赖**

```bash
cd ai-guide-scoring
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**第 2 步（可选）：跑命令行 demo，快速看结构化评分结果**

```bash
python -m examples.run_cli
```

输出为完整 JSON：总分（整数）、各维度分项分、扣分原因、引用证据、AI 置信度，以及被剔除的考官读题（`removed_segments`）。

> 演示「接口下发试题」导入评分：`python -m examples.run_cli --import-paper`（读取 `examples/sample_paper_vi.json`，按试题动态生成维度并评分）。

**第 3 步：启动 Web 服务**

```bash
uvicorn app.main:app --reload --port 8000
```

**第 4 步：浏览器查看效果**

打开 `http://localhost:8000`，有两种试题来源：

**方式 A · 岗位题库**
1. 「试题来源」选「岗位题库」，在「报考岗位」下拉选择岗位 → 题目自动载入（切换岗位题目会变，体现"每位考生题目不同"）。
2. 点击「**填充示例数据（含考官读题）**」——示例回答里特意含「考官：…」读题行。
3. 点击「**开始 AI 评分**」。
4. 右侧查看：总分为整数；每个维度有得分/等级/扣分原因/引用证据/置信度；橙色「✂ 已剔除考官读题」即被自动剔除、未参与评分的内容。
5. 点「查看报告」可看 Markdown 评分报告。

**方式 B · 导入试题 JSON（接口）**
1. 「试题来源」选「导入试题 JSON（接口）」。
2. 点「**载入普通话样例**」或「**载入越南语样例**」（也可直接粘贴你自己的接口 JSON）。
3. 点「**解析试题**」→ 维度、题目、满分、图片自动生成（中文合计 100；越南语含中译外/外译中，合计 100）。
4. 点「填充示例数据」「开始 AI 评分」，结果同样为整数、自动剔除考官读题。

**第 5 步（可选）：接入真实阿里百炼大模型**

```bash
export DASHSCOPE_API_KEY=sk-xxxx          # 阿里云百炼控制台获取
export DASHSCOPE_MODEL=qwen-plus          # 可选，默认 qwen-plus
uvicorn app.main:app --reload --port 8000
```

设置 Key 后引擎自动切换为真实百炼推理（`/health` 返回 `engine_mode: bailian`），无需改代码。

**用 curl 快速验证接口（可选）**

```bash
curl http://localhost:8000/positions
curl "http://localhost:8000/positions/guide_zh/paper"
curl -X POST http://localhost:8000/interviews -H "Content-Type: application/json" \
  -d '{"candidate":{"name":"张三","position":"guide_zh"},
       "items":[{"dimension_key":"knowledge_qa","question":"介绍广西世界遗产",
       "answer_transcript":"考官：介绍广西世界遗产。\n考生：灵渠是世界灌溉工程遗产，壮族三月三是国家级非遗。"}]}'

# 接口下发试题 JSON → 解析为动态试卷
curl -X POST http://localhost:8000/papers/import -H "Content-Type: application/json" \
  --data @examples/sample_paper_vi.json
```

## REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/rubric` | 查看评分体系 |
| GET | `/positions` | 岗位列表 |
| GET | `/positions/{id}/paper` | 按岗位生成试卷（每位考生题目可不同，`?variant=` 抽不同套题） |
| GET | `/papers/samples` | 内置试题样例（普通话 / 越南语，接口格式） |
| POST | `/papers/import` | 解析考务接口下发的试题 JSON → 动态试卷（维度/题目/满分/图片）；`?pick=first\|random` |
| POST | `/interviews/custom` | 基于导入试卷评分（维度与满分随试题动态变化） |
| GET | `/kb/search?q=` | RAG 知识库检索 |
| POST | `/interviews` | 创建面试并评分 |
| GET | `/interviews/{id}` | 获取评分结果 |
| GET | `/interviews/{id}/evidence` | 获取证据链（含被剔除的考官读题） |
| GET | `/interviews/{id}/report` | 生成 Markdown 报告 |
| GET | `/health` | 健康检查（含引擎模式） |

请求示例见 `examples/run_cli.py`。

## 目录结构

```
app/
  core/
    rubric.py           评分体系定义
    prompts.py          Prompt 工程（System/Scoring/Review）
    bailian_client.py   百炼客户端 + mock 降级
    knowledge_base.py   RAG 知识库
    question_bank.py    岗位与题库（每位考生题目可不同）
    paper_import.py     试题导入：解析考务接口试题 JSON → 动态试卷
    transcript.py       转写清洗（剔除考官读题）
    scoring_engine.py   评分引擎编排（整数评分 + 校准）
    schemas.py          API 数据结构
  web/index.html        演示前端
  main.py               FastAPI 入口
examples/run_cli.py     命令行 demo（--import-paper 演示导入评分）
examples/sample_paper_zh.json / sample_paper_vi.json  接口试题样例
docs/                   落地方案与设计文档
```

## 落地文档

- `docs/快速实现方案.md` — 快速实现方案（MVP 范围、里程碑、技术选型）
- `docs/AI辅助导游面试评分系统设计文档.md` — 完整 PRD + 技术方案（含 Mermaid 图、JSON 示例、数据库/API/验收标准）
