# AI 辅助导游面试评分系统 · Demo

基于 Python + 阿里百炼（DashScope / 通义千问 Qwen）的 **AI 辅助判分** 演示。
覆盖导游资格面试的 7 大评分维度，输出 **总分 / 分项分 / 扣分项 / 扣分原因 / 评分依据 / 引用证据 / AI 置信度** 的结构化、可解释评分结果。

> AI 仅提供评分建议，最终分数由评委确认。

## 特性

- **7 维度评分体系**（总分 100）：形象礼仪、语言表达、专题线路讲解、旅游景区讲解、服务规范问答、应变能力问答、综合知识问答。
- **接入阿里百炼**：OpenAI 兼容模式调用 Qwen，结构化 JSON 输出。
- **无 Key 自动降级**：未配置 `DASHSCOPE_API_KEY` 时走启发式 mock 引擎，demo 开箱即跑。
- **RAG 知识库**：内置广西旅游文化 + 导游服务规范知识，问答/讲解类维度自动检索证据。
- **评分校准**：分值区间约束、分项之和校验，降低评分漂移。
- **可解释证据链**：每个分数可回溯到 扣分原因 → 引用证据 → 转写片段 / 多模态指标。
- **REST API + Web UI**：一键演示。

## 快速开始

```bash
pip install -r requirements.txt

# 1) 命令行 demo（mock 模式）
python -m examples.run_cli

# 2) 启动 Web 服务 + UI
uvicorn app.main:app --reload --port 8000
# 浏览器打开 http://localhost:8000 ，点击「填充示例数据」→「开始 AI 评分」
```

### 接入真实百炼大模型

```bash
export DASHSCOPE_API_KEY=sk-xxxx          # 阿里云百炼控制台获取
export DASHSCOPE_MODEL=qwen-plus          # 可选，默认 qwen-plus
uvicorn app.main:app --port 8000
```

## REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/rubric` | 查看评分体系 |
| GET | `/kb/search?q=` | RAG 知识库检索 |
| POST | `/interviews` | 创建面试并评分 |
| GET | `/interviews/{id}` | 获取评分结果 |
| GET | `/interviews/{id}/evidence` | 获取证据链 |
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
    scoring_engine.py   评分引擎编排
    schemas.py          API 数据结构
  web/index.html        演示前端
  main.py               FastAPI 入口
examples/run_cli.py     命令行 demo
docs/                   落地方案与设计文档
```

## 落地文档

- `docs/快速实现方案.md` — 快速实现方案（MVP 范围、里程碑、技术选型）
- `docs/AI辅助导游面试评分系统设计文档.md` — 完整 PRD + 技术方案（含 Mermaid 图、JSON 示例、数据库/API/验收标准）
