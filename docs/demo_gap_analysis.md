# CIS 多 Agent 竞品分析系统 Demo 工程自检报告

## 已满足项

### 1. 多 Agent 协作与输出可信度

- 已实现核心 Agent 文件和职责拆分：
  - `PlannerAgent`
  - `CollectorAgent`
  - `AnalystAgent`
  - `ReportWriterAgent`
  - `QaAgent`
  - `FinalReport` 作为 DAG 终态节点存在于 DAG 配置中
- 已实现完整 Mock 工作流：

```text
PlannerAgent -> CollectorAgent -> AnalystAgent -> ReportWriterAgent -> QaAgent -> FinalReport
```

- 每个 Agent 都有独立文件、`run()` 方法和清晰职责边界。
- Agent 输出使用 Pydantic Schema 或结构化字典承载，不是纯自然语言对话。
- DAG 节点和边可通过 `GET /api/tasks/{task_id}/dag` 查询，前端也能展示 DAG 状态。
- QA 支持打回逻辑：
  - 缺少证据可路由到 `ReportWriterAgent`
  - 测试中覆盖了缺少采集证据时路由到 `CollectorAgent`
  - `max_rework = 3` 后进入 `manual_review`
- `Claim.evidence_ids` 已通过 Pydantic `Field(min_length=1)` 强制非空。
- `Evidence` 已强制包含 `source_type`、`collected_at`、`snippet`、`confidence`，并要求 `url` 或 `local_ref` 至少存在一个。
- 报告中的 Claim 可以点击查看对应 Evidence，具备基础溯源能力。

### 2. 技术深度与工程完整度

- 后端接口基本完整，已覆盖：
  - 创建任务
  - 查询任务列表
  - 查询任务详情
  - 运行 Mock workflow
  - 查询 DAG
  - 查询 Trace
  - 查询 Evidence
  - 查询 QA
  - 查询任务报告
  - 按报告 ID 查询报告
- 后端使用 FastAPI、Pydantic、SQLAlchemy、SQLite、pytest，工程栈符合 Demo 要求。
- 前端已展示：
  - 任务创建
  - 示例任务
  - 当前任务 ID 和状态
  - DAG
  - 竞品知识
  - Markdown 报告
  - Claim 列表
  - Evidence / Source Panel
  - QA Result Panel
  - Trace Viewer
- TraceRecord 已包含要求字段：
  - `trace_id`
  - `task_id`
  - `agent_name`
  - `input_summary`
  - `output_summary`
  - `schema_validation_result`
  - `elapsed_time_ms`
  - `retry_count`
  - `error_message`
  - 另有 `model_name`、`token_usage`、`created_at`
- 已有基础错误处理：
  - Agent 输出校验失败会记录失败 Trace
  - API 查询不存在的 Task、Report、QA 时返回 404
  - QA 失败后会更新任务状态
- 已有重试/返工字段：
  - `retry_count`
  - `rework_count`
  - `MAX_REWORK = 3`

### 3. 业务价值与产品体验

- 任务创建区域已优化为带标签、placeholder、helper text 和错误提示的表单卡片。
- 用户能明确看到这是在创建“分析任务”。
- 已提供 3 个示例任务：
  - AI 编程工具
  - 企业协作工具
  - 美妆电商平台
- 表单提交前已有前端校验：
  - 分析任务名称不能为空
  - 竞品至少 2 个
  - 分析区域不能为空
  - 行业或产品类型不能为空
- 页面有“本 Demo 会做什么”说明卡片，能解释 Planner、Collector、Analyst、ReportWriter、QA、FinalReport 的作用。
- 报告支持点击 Claim 查看 Evidence，适合演示证据绑定与溯源。
- 当前页面能支撑现场演示一条完整 Mock 流程。

### 4. 代码质量与文档

- 项目目录清晰：

```text
backend/app/api
backend/app/agents
backend/app/schemas
backend/app/services
backend/tests
frontend/src
docs
```

- 后端 Schema、Agent、Service、API 分层清楚。
- 前端有 API client、类型定义和主页面组件。
- README 包含本地启动、测试、API、功能说明和后续接入真实 Agent 的说明。
- 已有 pytest 测试，覆盖：
  - Claim evidence 校验
  - Evidence 来源校验
  - AgentMessage 必填字段校验
  - QA 路由
  - max_rework
  - TraceRecord 创建
- 文档中已说明后续接入 LangGraph、LLM、Web Collector、RAG / Vector DB 的位置。

## 缺失项

### 1. FinalReport 还不是独立 Agent

当前 `FinalReport` 是 DAG 终态节点，不是一个独立的 `FinalReportAgent` 文件或执行步骤。严格按“每个 Agent 单独实现”的标准看，FinalReport 仍偏弱。

### 2. Agent 输入 Schema 还不够显式

当前输出 Schema 比较明确，但每个 Agent 的输入 Schema 主要通过函数参数体现，例如 `Task`、`list[Evidence]`、`knowledge: dict`。还没有为每个 Agent 定义专门的 `PlannerInput`、`CollectorInput`、`AnalystInput`、`ReportWriterInput`、`QaInput`。

### 3. QA 打回能力仍是 Demo 级

当前真实工作流只演示了“ReportWriter 缺少 evidence_ids -> QA 打回 -> 修复”的路径。

尚未完整演示：

- 缺少采集证据后自动回到 `CollectorAgent` 并重新采集
- 抽取错误或结论冲突后自动回到 `AnalystAgent`
- 多轮返工过程中的差异化改进

### 4. DAG 执行状态是结果态，不是实时态

当前前端展示 DAG 状态，但不是实时流式刷新。运行过程中没有逐节点 running/completed 的动态更新。

### 5. 竞品知识维度目前固定

当前竞品知识固定为：

- ProductProfile
- FeatureTree
- PricingModel
- UserPersona

这满足 Demo 的核心 Schema 要求，但还没有按行业、任务目标或 Planner 输出动态选择 Schema。

### 6. Evidence 仍是 Mock 数据

当前证据为固定模板生成。虽然满足 Demo 阶段“不做真实爬虫”的要求，但从评分角度看，证据可信度仍主要用于演示结构，不代表真实信息源质量。

### 7. README 在 Windows 控制台读取时可能出现编码显示问题

README 内容是中文，但当前 PowerShell `Get-Content` 输出出现乱码。浏览器或支持 UTF-8 的编辑器通常可正常显示，但为了提交材料稳定性，建议后续统一确认所有 Markdown 文件为 UTF-8。

### 8. 前端组件仍集中在单个 `App.tsx`

当前前端可以跑 Demo，但组件拆分还不够细。任务表单、Demo 说明、DAG、报告、证据、QA、Trace 都在一个文件里，后续维护成本会升高。

### 9. 缺少前端测试和 lint

当前只有 `npm run build`，没有配置：

- ESLint
- Prettier
- 前端单元测试
- E2E 测试

## 高优先级修改项

1. 增加 `FinalReportAgent` 或显式 FinalReport 生成步骤

让 `FinalReport` 不只是 DAG 节点，而是一次可追踪的执行记录。建议新增：

```text
backend/app/agents/final_report.py
```

并为其生成 TraceRecord。

2. 为每个 Agent 增加显式 Input / Output Schema

建议新增：

```text
PlannerInput / PlannerOutput
CollectorInput / CollectorOutput
AnalystInput / AnalystOutput
ReportWriterInput / ReportWriterOutput
QaInput / QaOutput
FinalReportInput / FinalReportOutput
```

这样更符合“所有 Agent 输入输出必须结构化”的评分点。

3. 完整演示 QA 三类打回路径

当前主流程只演示 ReportWriter 打回。建议增加 Demo 模式或测试入口，覆盖：

- Missing evidence -> CollectorAgent
- Invalid extraction / contradiction -> AnalystAgent
- Bad report format -> ReportWriterAgent

4. 修复 Markdown 中文编码显示风险

确保 README 和 docs 下文档均保存为 UTF-8。必要时增加 `.gitattributes`：

```text
*.md text working-tree-encoding=UTF-8
*.py text eol=lf
*.ts text eol=lf
*.tsx text eol=lf
```

或至少统一编辑器编码，避免答辩材料打开乱码。

## 中优先级修改项

1. 前端组件拆分

建议拆分：

```text
frontend/src/components/TaskForm.tsx
frontend/src/components/DemoGuide.tsx
frontend/src/components/DagView.tsx
frontend/src/components/KnowledgeView.tsx
frontend/src/components/ReportView.tsx
frontend/src/components/EvidencePanel.tsx
frontend/src/components/QaPanel.tsx
frontend/src/components/TraceViewer.tsx
```

2. 增加任务列表和任务切换

当前会自动加载最新任务，但没有清晰的任务列表入口。建议增加左侧或顶部任务列表，使多个任务的 DAG、报告、证据、Trace 对应关系更直观。

3. 增加 DAG 运行中的动态状态

可以先用轮询实现：

- 创建任务后 DAG 全部 pending
- 运行中逐步显示 running / completed
- QA failed 时显示返工边

4. 增强 Trace 可读性

当前 Trace 有必要字段，但 payload 级别的输入输出细节未完整展示。建议增加：

- Agent 输入 JSON 摘要展开
- Agent 输出 JSON 摘要展开
- 错误 Trace 高亮
- 与 Claim / Evidence 的关联跳转

5. 增强 Report JSON 展示

当前竞品知识以 JSON 字符串展示，能用但不够产品化。建议把 ProductProfile、FeatureTree、PricingModel、UserPersona 拆成结构化 UI。

## 低优先级修改项

1. 增加前端 lint / format

可加入 ESLint、Prettier，提升提交质量。

2. 增加前端单元测试或 E2E 测试

建议先加 Playwright 冒烟测试：

- 页面可打开
- 示例任务可填充
- 创建任务成功
- 运行工作流后出现报告和 Trace

3. 增加数据库迁移工具

当前 SQLite 表通过 `Base.metadata.create_all` 创建，Demo 足够。后续生产化可接入 Alembic。

4. 增加异步任务队列

当前 `/api/tasks/{task_id}/run` 是同步执行。后续真实 Agent / 爬虫 / RAG 接入后，应改为后台任务或队列。

5. 增加合规策略文档

当前 README 有合规说明。后续可单独新增：

```text
docs/compliance.md
```

覆盖 robots.txt、版权、隐私、访谈脱敏和公开来源引用。

## 建议下一步开发顺序

1. 修复文档编码显示风险

这是低成本、高收益项。答辩或 GitHub 页面中文乱码会直接影响观感。

2. 增加 `FinalReportAgent`

补齐 Agent 链路闭环，让 FinalReport 也有 Trace。

3. 为 Agent 增加显式 Input / Output Schema

这是最贴近评分细则“结构化 Agent 消息传递”的改动，且不会大改业务流程。

4. 完整补齐 QA 三类打回 Demo

可以先通过测试和可选 demo 参数实现，不必立即做复杂真实分析。

5. 拆分前端组件

在功能稳定后拆分 `App.tsx`，提升代码可维护性。

6. 增加任务列表和任务切换

让多个任务的 DAG、报告、证据、Trace 对应关系更清晰。

7. 接入真实 LangGraph / LLM / Web Collector / RAG

等 Demo 骨架和评分项补齐后，再进入真实 Agent 能力建设，避免在基础闭环尚未完全稳固时引入过多复杂性。

## 总体判断

当前 Demo 已经满足“可跑、可演示、可解释”的初步要求，覆盖了评分细则中多 Agent 协作、Schema 校验、证据绑定、QA 反馈闭环、Trace 可观测和端到端页面展示等关键点。

主要短板不在能否跑通，而在“严格工程化程度”和“评分项展示完整度”：

- FinalReport 还不是独立可追踪执行单元。
- Agent 输入 Schema 不够显式。
- QA 打回路径还没有在主流程中完整展示。
- 前端组件拆分和任务管理还可以加强。
- 文档中文编码需要确认。

建议下一阶段先做小范围工程补强，不急于接入真实 LLM 和爬虫。
