# Demo 启动方式、已完成功能与后续计划

## 启动方式

### 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

后端健康检查：

```bash
curl http://127.0.0.1:8000/health
```

正常返回：

```json
{"status":"ok"}
```

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问地址：

```text
http://127.0.0.1:5173
```

### 运行测试

```bash
cd backend
pytest
```

### 前端构建检查

```bash
cd frontend
npm run build
```

## 当前已完成功能

### 工程骨架

- 已创建后端、前端、文档和测试目录。
- 后端采用 FastAPI、Pydantic、SQLAlchemy、SQLite、pytest。
- 前端采用 React、Vite、TypeScript、TailwindCSS。
- 已提供 README 和需求摘要文档。

### 后端能力

- 已实现 FastAPI 入口、CORS 和 `/health` 健康检查。
- 已实现 SQLite 持久化。
- 已实现 Task、Trace、Evidence、Report、QA 相关服务。
- 已实现完整 REST API：
  - `POST /api/tasks`
  - `GET /api/tasks`
  - `GET /api/tasks/{task_id}`
  - `POST /api/tasks/{task_id}/run`
  - `GET /api/tasks/{task_id}/dag`
  - `GET /api/tasks/{task_id}/traces`
  - `GET /api/tasks/{task_id}/evidence`
  - `GET /api/tasks/{task_id}/qa`
  - `GET /api/tasks/{task_id}/report`
  - `GET /api/reports/{report_id}`

### Schema 与校验

- 已实现以下 Pydantic Schema：
  - `ProductProfile`
  - `FeatureTree`
  - `PricingModel`
  - `UserPersona`
  - `Evidence`
  - `Claim`
  - `AgentMessage`
  - `QaResult`
  - `TraceRecord`
  - `Task`
  - `Report`
- `Claim.evidence_ids` 必须非空。
- `Evidence` 必须包含 `url` 或 `local_ref`。
- `AgentMessage` 必须包含 `trace_id` 和 `task_id`。
- 无效输出会被 Pydantic 或 QA 拦截，不会静默通过。

### Mock Agent 工作流

已实现完整 Mock 流程：

```text
PlannerAgent -> CollectorAgent -> AnalystAgent -> ReportWriterAgent -> QaAgent -> FinalReport
```

当前工作流行为：

- `PlannerAgent` 生成 DAG 和任务计划。
- `CollectorAgent` 生成 3-5 条 Mock Evidence。
- `AnalystAgent` 生成结构化竞品知识。
- `ReportWriterAgent` 生成 Markdown 和 JSON 报告。
- `QaAgent` 校验 Schema、证据绑定和报告格式。
- 工作流会故意先生成一次缺少 `evidence_ids` 的坏草稿，触发 QA 打回。
- QA 打回 `ReportWriterAgent` 后重新生成报告。
- 最终报告通过 QA，任务状态变为 `completed`。

### QA 反馈闭环

- 已支持 QA `passed`、`failed`、`manual_review` 状态。
- 已支持缺少证据时生成返工指令。
- 已支持返工路由到 `CollectorAgent` 或 `ReportWriterAgent`。
- 已支持 `max_rework = 3`，超过后进入 `manual_review`。

### Trace 可观测性

每次 Agent 执行都会生成 `TraceRecord`，包含：

- `trace_id`
- `task_id`
- Agent 名称
- 输入摘要
- 输出摘要
- Schema 校验结果
- Mock 模型名称
- 执行耗时
- 重试次数
- 错误信息

### 前端页面

已实现单页 Demo 工作台：

- 任务创建区域
- `Run Demo Workflow` 按钮
- DAG 执行状态展示
- 竞品知识展示
- Markdown 报告展示
- Claim 列表
- 点击 Claim 查看对应 Evidence
- Evidence / Source Panel
- QA Result Panel
- Trace Viewer
- Trace 按 Agent 过滤

### 测试

已添加 pytest 测试，覆盖：

- Claim 缺少 `evidence_ids` 时校验失败。
- Evidence 缺少 `url` 和 `local_ref` 时校验失败。
- AgentMessage 缺少 `trace_id` 和 `task_id` 时校验失败。
- QA 能把 missing evidence 路由到返工 Agent。
- `max_rework` 超过 3 后变为 `manual_review`。
- 每个 Agent 执行后都会生成 TraceRecord。

当前验证结果：

- 后端 `pytest`：7 个测试通过。
- 前端 `npm run build`：构建通过。
- 后端 `/health`：返回 `ok`。
- 前端本地页面：HTTP 200。

## 后续要完成的功能

### 接入真实 Agent 编排

- 将 `backend/app/agents/runner.py` 替换为 LangGraph 工作流。
- 将每个 Mock Agent 改为 LangGraph 节点或子图。
- 保留现有 Pydantic Schema 作为 Agent 间通信协议。
- 为每个节点补充真实 Prompt、工具权限、失败重试和超时控制。

### 接入真实 LLM

- 为 Planner、Analyst、ReportWriter、QA 接入真实 LLM。
- 使用结构化输出或 function calling，保证输出符合 Schema。
- 对 LLM 输出增加更严格的解析失败处理和自动修复策略。
- 增加 token usage、模型名称、调用耗时等真实 Trace 字段。

### 接入真实 Web Collector

- 替换 `CollectorAgent` 的 Mock 数据。
- 支持公开网页、定价页、文档、评论、访谈或问卷来源。
- 遵守 robots.txt 和网站服务条款。
- 保存原始来源、采集时间、URL、snippet、置信度和来源类型。
- 增加网页去重、正文抽取、来源可信度评分。

### 接入 RAG 与向量数据库

- 在 `EvidenceService` 后增加向量化和检索能力。
- 可选技术：Qdrant、Milvus、pgvector 或其他向量数据库。
- 支持按任务、竞品、功能、价格、用户画像等维度检索证据。
- 支持 Claim 到 Evidence 的可追溯查询。

### 增强 QA 能力

- 增加证据覆盖率评分。
- 增加 Claim 与 Evidence 语义一致性检查。
- 增加冲突检测。
- 增加报告格式规范检查。
- 增加人工审核入口和人工修正记录。
- 支持 QA 打回 `CollectorAgent`、`AnalystAgent`、`ReportWriterAgent` 后多轮返工。

### 增强前端体验

- 增加任务列表和任务切换。
- 增加 DAG 节点运行中的动态状态刷新。
- 增加 Claim-Evidence-Trace 关系图。
- 增加 Agent 执行回放。
- 增加人工审核和修正页面。
- 增加报告导出能力。

### 生产化能力

- 增加鉴权和用户隔离。
- 增加任务队列和异步执行。
- 增加日志、指标和错误告警。
- 增加数据库迁移工具。
- 增加 Docker 和部署配置。
- 增加 CI 流水线。
- 增加更完整的单元测试、集成测试和端到端测试。
