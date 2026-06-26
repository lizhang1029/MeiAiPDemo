# AI 辅助导游面试评分系统 · Demo

基于 Python + 阿里百炼（DashScope / 通义千问 Qwen）的 **AI 辅助判分** 演示。
覆盖导游资格面试的 7 大评分维度，输出 **总分 / 分项分 / 扣分项 / 扣分原因 / 评分依据 / 引用证据 / AI 置信度** 的结构化、可解释评分结果。

> AI 仅提供评分建议，最终分数由评委确认。

## 特性

- **7 维度评分体系**（总分 100）：形象礼仪、语言表达、专题线路讲解、旅游景区讲解、服务规范问答、应变能力问答、综合知识问答。
- **岗位 + 题目入口**：内置多岗位题库（中文导游 / 英语导游 / 景区讲解员），**每位考生题目可不同**；选岗位自动带出题目，也可手动改题。
- **试题导入（接口对接）**：支持考务平台（ezinterview 格式）下发的试题 JSON（`sections → groups → items`），自动按 group 名映射评分维度、按 `selection` 抽题规则取题（含复合题 `mq-lr` 抽取小题）、抽取题干文本与图片，并以实际作答题目分值作为该维度满分。中文/外语题型不同（外语含**中译外/外译中**），维度与满分**随试题动态变化**。
- **分数全部为整数**：总分、分项分、扣分值均为整数，不出现小数点。
- **整段面试评分（新）**：上传一名考生整场面试的**一个**音/视频文件，接入阿里百炼 **Paraformer** 转写后，按「每题作答前的明显停顿」自动**切分为多段**，按题目顺序对应各题回答；再逐题按**手动录入的评分表**（维度名 / 满分 / 评分标准）打分，**总分以评分表合计为准**；导入试题 JSON 只提供题干。无 Key 或缺依赖时降级为示例整段转写，demo 仍可离线跑。
- **音/视频转写（ASR）**：接入阿里百炼 **Paraformer** 语音识别自动转写为文本（视频先用 ffmpeg 抽取音轨）；无 Key 或缺依赖时降级为示例转写。
- **自动剔除与答题无关内容**：转写中考官读题（「考官：…」标注行或与题目高度相似的行）与考务口令（「可以开始作答 / 时间到 / 下一题」等）会被自动剔除，仅对考生回答评分，并在结果中展示被剔除的内容。
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
python -m venv .ai_venv/
source .ai_venv/bin/activate          # Windows: .venv\Scripts\activate
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

打开 `http://localhost:8000`，页面为**整段面试 · 分步评分向导**，按 4 步操作：

**① 上传整段面试录音并按题分段**
- 选语言 → 选择一名考生整场面试的**一个**音频/视频文件 →（可调「题前停顿阈值」，默认 2000ms）→ 点「🎙 转写并分段」。
- 系统转写后按「题前明显停顿」自动切分为多段，下方列出各段（含起止时间）。无 Key 时返回示例整段转写（普通话 5 题）。处理视频需本机装好 `ffmpeg`。

**② 导入试题 JSON（仅取题干）**
- 点「载入普通话样例 / 载入越南语样例」或粘贴考务接口 JSON → 点「解析题干」。
- 仅提取各题题干，按顺序与各段回答、各维度对齐；维度/满分/评分标准以第 ③ 步手动录入为准。

**③ 录入各维度评分标准与满分**
- 点「按题目数生成评分表」→ 每行一题：题干只读、该题考生回答自动回填（可改）；**维度名 / 满分 / 评分标准**手动录入。可点「填充示例评分标准」快速演示。**总分以评分表满分合计为准。**

**④ 开始评分**
- 点「开始 AI 评分」。右侧查看：总分为整数；每维度有得分/等级/扣分原因/引用证据/置信度；橙色「✂ 已剔除…」即被自动剔除（考官读题 / 无关提示）、未参与评分的内容。点「查看报告」可看 Markdown 评分报告。

**第 5 步（可选）：接入真实阿里百炼大模型**

```bash
export DASHSCOPE_API_KEY=sk-xxxxxxxx          # 阿里云百炼控制台获取，请勿提交到代码库
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
| POST | `/transcribe` | 上传音/视频文件 → 百炼 Paraformer 转写为文本（无 Key 降级 mock）；表单字段 `file`、`language=zh\|vi\|en` |
| POST | `/transcribe_full` | 上传整段面试录音 → 转写并按题前停顿切分为多段回答；表单字段 `file`、`language`、`pause_ms` |
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
    asr.py              音/视频转写（百炼 Paraformer + ffmpeg 抽音轨，无 Key 降级 mock）
    asr.py              音/视频转写 + 整段面试按停顿分段（Paraformer + ffmpeg，无 Key 降级 mock）
    transcript.py       转写清洗（剔除考官读题 + 「可以开始作答/时间到」等考务口令）
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
