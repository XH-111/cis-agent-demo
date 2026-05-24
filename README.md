# CIS 多 Agent 竞品分析系统 Demo

这是一个面向 CIS AI 挑战赛的“多 Agent 竞品分析系统”初步 Demo。

当前版本使用确定性的 Mock Agent，不包含真实 LLM、真实爬虫、真实 RAG、向量数据库或复杂分析。它的目标是先把可演示、可替换、可扩展的工程骨架搭好：Schema、API、持久化、Mock 工作流、QA 打回闭环、证据绑定、Trace 可观测、前端页面和测试。

## 架构概览

```text
React + Vite 前端
       |
FastAPI REST API
       |
SQLite + SQLAlchemy
       |
MockWorkflowRunner
       |
PlannerAgent -> CollectorAgent -> AnalystAgent -> ReportWriterAgent -> QaAgent -> FinalReport
```

QA 支持以下打回路径：

- 缺少证据 -> `CollectorAgent` 或 `ReportWriterAgent`
- 抽取错误或结论冲突 -> `AnalystAgent`
- 报告格式错误 -> `ReportWriterAgent`
- 返工次数超过 3 次 -> `manual_review`

Demo 工作流会故意先生成一版缺少 `evidence_ids` 的坏草稿，触发 QA 失败并打回 `ReportWriterAgent`，随后重新生成带证据绑定的最终报告并通过 QA。

## 项目结构

```text
backend/
  app/
    api/                 FastAPI 路由
    agents/              Mock Agent 和工作流 Runner
    schemas/             Pydantic Schema 与校验规则
    services/            Task、Trace、Evidence、Report 服务
    database.py          SQLite 初始化
    db_models.py         SQLAlchemy 数据表模型
    main.py              FastAPI 入口
  tests/                 pytest 测试
  requirements.txt
frontend/
  src/
    api/                 API Client 与 TypeScript 类型
    App.tsx              Demo 工作台页面
  package.json
docs/
  requirements_summary.md
```

## 后端启动

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

成功时返回：

```json
{"status":"ok"}
```

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

## 运行测试

```bash
cd backend
pytest
```

当前测试覆盖：

- `Claim.evidence_ids` 必须非空
- `Evidence` 必须包含 `url` 或 `local_ref`
- `AgentMessage` 必须包含 `trace_id` 和 `task_id`
- QA 能把缺少证据的问题路由到返工 Agent
- 返工次数超过 3 次后进入 `manual_review`
- 每个 Agent 执行后都会生成 `TraceRecord`

## REST API

- `POST /api/tasks`：创建竞品分析任务
- `GET /api/tasks`：查询任务列表
- `GET /api/tasks/{task_id}`：查询任务详情
- `POST /api/tasks/{task_id}/run`：启动 Mock Agent 工作流
- `GET /api/tasks/{task_id}/dag`：查询 DAG 节点和边
- `GET /api/tasks/{task_id}/traces`：查询 Trace 记录
- `GET /api/tasks/{task_id}/evidence`：查询 Evidence 列表
- `GET /api/tasks/{task_id}/qa`：查询 QA 结果
- `GET /api/tasks/{task_id}/report`：查询任务报告
- `GET /api/reports/{report_id}`：按报告 ID 查询报告

## 前端功能

前端是一个单页 Demo 工作台，包含：

- 任务创建
- 一键运行 Mock Workflow
- DAG 执行状态展示
- 竞品知识展示：`ProductProfile`、`FeatureTree`、`PricingModel`、`UserPersona`
- Markdown 报告和 JSON 报告数据
- 点击 Claim 后查看对应 Evidence
- QA 结果面板：passed、failed、manual_review、hard errors、suggestions、rework instructions
- Trace Viewer：按 Agent 过滤，查看 `trace_id`、输入摘要、输出摘要、Schema 校验结果、耗时、重试次数和错误信息

## 核心 Schema 规则

- `Claim.evidence_ids` 必填且不能为空。
- `Evidence` 必须包含 `source_type`、`collected_at`、`snippet`、`confidence`，并且必须提供 `url` 或 `local_ref`。
- `AgentMessage` 必须包含 `trace_id`、`task_id`、`from_agent`、`to_agent`、`message_type` 和 `schema_name`。
- 所有 Agent 输入输出都保持结构化。
- 无效模型输出不能静默通过，必须被 Pydantic 或 QA 拦截。

## 后续接入真实 Agent 的位置

推荐从 `backend/app/agents/runner.py` 开始接入 LangGraph。

迁移建议：

1. 保留 `backend/app/schemas/models.py` 作为 Agent 间通信契约。
2. 将每个 Mock Agent 替换成 LangGraph 节点或子图。
3. 保持 `run()` 的输入输出形状，避免前端和 API 大改。
4. 替换 `CollectorAgent` 为合规 Web Collector，仍然输出结构化 `Evidence`。
5. 在 `EvidenceService` 后面接入向量数据库或检索服务。
6. 保留 `QaAgent` 的确定性硬校验：Schema 校验、证据覆盖率、引用完整性和人工复核升级不应完全依赖自由文本 LLM 判断。

## 合规说明

当前 Demo 使用 `example.com` 和 `mock://` 的模拟公开来源，不采集真实网站或个人数据。

生产环境接入真实采集时，需要遵守：

- 目标网站 robots.txt 和服务条款
- 数据来源授权或公开声明
- 隐私和敏感信息保护要求
- 访谈、问卷等内容的脱敏要求
- 最终报告中避免复制长篇受版权保护文本
