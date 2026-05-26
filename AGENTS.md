# AGENTS.md

## 项目目标

构建一个用于 CIS AI 挑战赛的多 Agent 竞品分析系统。

系统必须实现端到端工作流：

```text
PlannerAgent -> CollectorAgent -> AnalystAgent -> ReportWriterAgent -> QaAgent -> FinalReportAgent
```

QA 可以把未通过质检的任务打回 CollectorAgent、AnalystAgent 或 ReportWriterAgent，并通过 Trace 展示完整执行过程。

## 工程原则

- Agent 职责必须清晰且相互隔离。
- 每个 Agent 的输入和输出都必须使用结构化 Schema。
- 最终报告中的任何关键结论都必须包含 `evidence_ids`。
- 每次 Agent 执行都必须通过 Trace 记录可观测信息。
- 优先沿用项目已有模式，避免随意新增抽象。
- 改动范围要小，并且必须可测试。
- 不要把 API Key、真实密钥或 `.env` 提交到仓库。

## Agent 定义

在本项目中，Agent 不只是 DAG 节点。

一个 Agent 由以下部分组成：

- 角色和职责
- 输入 Schema
- 输出 Schema
- `run()` 方法
- Trace 日志
- 重试和错误处理策略
- 可选的外部能力，例如 LLM、Web Search

在 LangGraph 中，一个 Agent 可以实现为一个 node，但 node 只能包装现有 `Agent.run()`，不能复制 Agent 业务逻辑。

## 必需 Agent

### PlannerAgent

- 解析用户任务。
- 生成任务计划和 DAG。
- 输出结构化 `PlannerOutput`。

### CollectorAgent

- 支持 `collector_mode=mock/web`。
- Web 模式通过 Tavily Search API 搜索公开网页结果。
- 生成结构化 `Evidence`。
- 每条 Evidence 必须可追溯，包含来源、snippet、confidence、source_domain、source_quality、competitor。
- 多竞品任务必须按 competitor 分组采集，避免单一竞品信息带偏。

### AnalystAgent

- 支持 `analyst_mode=mock/evidence/llm`。
- 当前主线是 evidence-based analyst。
- 从 Evidence 中抽取 `ProductProfile`、`FeatureTree`、`PricingModel`、`UserPersona`。
- 多竞品任务必须按 `Evidence.competitor` 分组分析。
- 不允许用一个竞品的证据支撑另一个竞品的结构化结论。

### ReportWriterAgent

- 支持 `writer_mode=mock/llm`。
- LLM 模式没有 API Key 或调用失败时必须 fallback 到 mock。
- 生成 Markdown 报告和前端可渲染 JSON 报告。
- 每条 Claim 必须包含 `claim_id`、`competitor`、`category`、`text`、`evidence_ids`、`confidence`。
- 不允许用一个竞品的 Evidence 支撑另一个竞品的 Claim。

### QaAgent

- 校验 Schema、证据覆盖、竞品覆盖、报告格式、Claim evidence 绑定和 Evidence 质量。
- 区分 hard error 和 soft suggestion。
- 支持以下路由：
  - 缺少 Evidence -> CollectorAgent
  - 抽取错误 / 结构化冲突 -> AnalystAgent
  - 报告格式错误 / Claim 问题 -> ReportWriterAgent
- 最大返工次数默认 3，超过后进入 `manual_review`。

### FinalReportAgent

- 负责整合最终报告、QA 结果和 Evidence summary。
- 是真实执行节点，不只是 DAG 终态标签。

## Schema 规则

核心 Schema 包括：

- ProductProfile
- FeatureTree
- PricingModel
- UserPersona
- Evidence
- Claim
- AgentMessage
- QaResult
- TraceRecord
- Task
- Report

强制规则：

- `Claim.evidence_ids` 必填且不能为空。
- `Claim.competitor` 在多竞品报告中应标识对应竞品。
- Evidence 必须包含 `source_type`、`url` 或 `local_ref`、`collected_at`、`snippet`、`confidence`。
- Web Evidence 应包含 `source_domain`、`source_quality`、`competitor`。
- AgentMessage 必须包含 `trace_id`、`task_id`、`from_agent`、`to_agent`、`message_type` 和 `schema_name`。
- 模型输出不合法时不能静默通过。

## Trace 规则

每次 Agent 执行都必须记录：

- `trace_id`
- `task_id`
- Agent 名称
- 输入摘要
- 输出摘要
- Schema 校验结果
- 模型名称
- token usage，如果可获得
- 执行耗时
- retry count
- 失败时的 error message

Workflow 级别也应记录：

- `workflow_engine_requested`
- `workflow_engine_used`
- `node_sequence`
- `conditional_routes_taken`
- `rework_count`
- `final_status`
- `elapsed_time_ms`

## QA 与反馈闭环

- QA passed -> FinalReportAgent
- 缺少证据 -> CollectorAgent
- 抽取错误或结论冲突 -> AnalystAgent
- 报告格式错误或 Claim 问题 -> ReportWriterAgent
- 最大返工次数：3
- 超过最大返工次数 -> `manual_review`
- 打回指令必须包含错误类型、原因、建议动作和目标 Agent。

## Evidence Relevance Policy

Evidence 不只需要存在，还必须与对应 competitor 实体相关。

- `evidence_ids` 只表示报告结论绑定了证据，不代表事实自动可信。
- Web Evidence 必须记录 `relevance_score`、`relevance_level`、`relevance_reason` 和 `entity_match_signals`。
- `entity_match_signals` 至少应包含 competitor 是否出现在 title、snippet、url、domain、alias 中，以及 domain similarity。
- Claim 不能引用 `relevance_level=unrelated` 的 Evidence。
- 具体功能、定价、定位、用户画像等强结论只能由 `high` 或 `medium` relevance Evidence 支撑。
- `low` relevance Evidence 只能作为弱提示或 soft suggestion，不应支撑强结论。
- 随机或不存在的竞品名称不得生成看似正式的强结论；应输出“未找到与该竞品明确相关的公开证据，暂不生成强结论”。
- CollectorAgent 需要过滤或降级 unrelated Evidence，并在 Trace 中记录 missing relevant evidence 的竞品。
- AnalystAgent 在 evidence 模式下不得用 unrelated Evidence 抽取结构化知识。
- ReportWriterAgent 不得因为 Evidence 有 URL 就默认可信。
- QaAgent 必须检查 Evidence relevance，并在缺少相关证据或 Claim 引用 unrelated Evidence 时打回。

## Current Workflow Engine Status

当前系统有两个 workflow engine：

### 1. CustomWorkflowRunner / MockWorkflowRunner

- 用途：legacy stable fallback。
- 负责当前稳定主链路：

```text
PlannerAgent -> CollectorAgent -> AnalystAgent -> ReportWriterAgent -> QaAgent -> FinalReportAgent
```

- 不再作为未来功能扩展主线。
- 不要求支持未来新增的 RAG / Retriever / SWOT / Questionnaire / Interview 节点。

### 2. LangGraphWorkflowRunner

- 用途：main workflow engine for future development。
- 使用 `StateGraph` 显式表达 Agent DAG、`WorkflowState`、QA conditional routing 和 `auto_rework`。
- 后续新增 workflow 节点只接入 `LangGraphWorkflowRunner`。

## Workflow Engine Policy

1. Agent business logic must remain single-source.

   `PlannerAgent`、`CollectorAgent`、`AnalystAgent`、`ReportWriterAgent`、`QaAgent`、`FinalReportAgent` 的业务逻辑只能写在各自 `Agent.run()` 中。

2. LangGraph nodes are adapters only.

   LangGraph node 只负责：

   - 从 `WorkflowState` 读取输入
   - 构造 Agent Input Schema
   - 调用 `Agent.run()`
   - 将 Agent Output 写回 `WorkflowState`

   不允许把 Agent 业务逻辑复制到 LangGraph node 里。

3. Future workflow nodes must target LangGraph only.

   后续新增节点只接入 `LangGraphWorkflowRunner`，包括但不限于：

   - PageFetcher
   - Chunker
   - Indexer
   - Retriever
   - RAG-related nodes
   - SWOTAgent
   - QuestionnaireAgent
   - InterviewAgent

   不再同步改 `CustomWorkflowRunner`。

4. Custom Runner is frozen as legacy fallback.

   Custom Runner 只保证当前稳定流程可运行，不再跟随新功能演进。

5. `workflow_engine` selection:

   - `workflow_engine=custom` 表示 legacy fallback
   - `workflow_engine=langgraph` 表示推荐主流程
   - 参数优先级：query 参数 > `WORKFLOW_ENGINE` 环境变量 > 默认 `custom`

6. QA routing policy:

   LangGraph 中 `QaAgent` 后必须使用 conditional edge：

   - passed -> `FinalReportAgent`
   - `route_to=CollectorAgent` -> `CollectorAgent`
   - `route_to=AnalystAgent` -> `AnalystAgent`
   - `route_to=ReportWriterAgent` -> `ReportWriterAgent`
   - max_rework reached -> `manual_review` / `FinalReportAgent`

7. Rework loop policy:

   - `max_rework` 默认 3
   - 每次 QA failed 且需要返工时 `rework_count + 1`
   - 不允许死循环
   - `conditional_routes_taken` 必须记录每次跳转

## Future Development Rule

From Phase 9 onward, new capabilities must be developed on the LangGraph workflow path first. `CustomWorkflowRunner` should not be expanded unless explicitly required for emergency fallback.

## Current Completed Phases

- Phase 1: FastAPI + React + Schema + Mock Agents + Trace + QA
- Phase 2: Frontend demo experience
- Phase 3: auto_rework
- Phase 4: LLM ReportWriter
- Phase 5: Web Collector with Tavily
- Phase 6: Evidence quality scoring
- Phase 7: Evidence-based AnalystAgent
- Phase 7.1: Competitor Coverage Fix
- Phase 8: LangGraph Workflow Engine

## Product Requirements

前端应包含：

- 任务创建页
- DAG 执行页
- 竞品知识页
- 报告页
- Evidence / Source Panel
- QA Result Panel
- Trace Viewer
- Workflow Engine 选择和运行摘要

报告页必须支持点击 Claim 查看对应 Evidence。

## Compliance Requirements

- 遵守 robots.txt 和网站服务条款。
- 不采集私人或敏感个人数据。
- 不复制长篇受版权保护文本。
- 只展示公开来源摘要、URL、snippet 和可追溯元数据。
- 不把真实 API Key 提交到仓库。

## Testing Requirements

常规改动至少覆盖：

- Schema 校验
- Claim 必须包含 evidence_ids
- Evidence 必须可追溯
- Agent Input / Output Schema
- QA 路由逻辑
- max_rework 限制
- Trace 记录创建
- Custom Runner 旧主链路不被破坏

## Testing Requirements Update

任何后续新增节点时，必须至少测试：

1. LangGraph workflow 正常通过。
2. QA conditional routing 不死循环。
3. 每个新节点产生 Trace 或可观测记录。
4. Custom Runner 旧主链路仍然不被破坏。
5. `workflow_engine=langgraph` 不破坏已有 mode 参数：
   - `collector_mode`
   - `analyst_mode`
   - `writer_mode`
   - `content_mode`
   - `demo_mode`
   - `auto_rework`

在完成有意义的代码改动后，应运行相关测试并报告结果。
