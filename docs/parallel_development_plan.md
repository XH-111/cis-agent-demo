# Planner / Survey / RAG 并行开发架构解耦审计

## 1. 总体结论

当前项目结论：**基本解耦，但需先补公共接口**。

项目已经具备三条线并行开发的基础：

- Agent 职责总体清晰，业务逻辑主要集中在各自 `Agent.run()` 及 Agent 内部私有方法。
- Agent 间通信已经通过 Pydantic Schema 承载，核心对象包括 `Task`、`Evidence`、`Claim`、`Report`、`QaResult`、`TraceRecord`、`WorkflowState`。
- `LangGraphWorkflowRunner` 已成为新能力主线，`CustomWorkflowRunner` 保持 legacy fallback。
- `run_id` 已贯穿 `TaskRun`、`Evidence`、`Report`、`QA`、`Trace` 查询链路。
- `EvidenceGate` 已位于 `CollectorAgent` 后、`PageFetcher` 前，能阻断明显无关 Evidence 进入分析与报告。
- 前端已经能展示任务、run history、DAG、Evidence、Report、QA、Trace 和 workflow summary，具备承载新增节点状态的基础。

但不建议三条线立即在同一批核心文件上自由开发。需要先冻结或补充以下公共接口：

- `AnalysisDimension`、`AnalysisDimensionPlan`、`DimensionResult`
- `Chunk`、`RetrievalResult`
- `SurveyPlan`、`SurveyQuestion`、`SurveyResponse`、`SurveyEvidence`
- `ReworkContext` / `RouteInstruction`
- `WorkflowState` 中面向 planner、survey、retrieval 的预留字段

建议先做一个很小的公共接口补丁，再开始三条功能分支并行开发。

## 2. 当前架构解耦检查

### 2.1 Agent 职责

当前职责边界基本清晰：

- `PlannerAgent`：生成任务计划和 DAG，目前偏固定计划，尚未承担行业维度拆解和动态采集策略。
- `CollectorAgent`：负责 mock/web evidence 采集，web 模式通过 Tavily 搜索公开网页结果，并做 source quality、dedupe、relevance 标注。
- `EvidenceGate`：在 LangGraph runner 中承担相关证据门禁，阻止缺少 high/medium relevance evidence 的任务继续进入正文抓取和分析。
- `PageFetcher`：本地轻量 HTML 摘要抓取，只处理通过门禁的相关 Evidence，不保存完整网页正文。
- `AnalystAgent`：基于 Evidence 抽取 `ProductProfile`、`FeatureTree`、`PricingModel`、`UserPersona`，已按 competitor 分组，优先使用 `content_excerpt`，否则使用 `snippet`。
- `ReportWriterAgent`：生成 Markdown / JSON Report 和 Claims，支持 mock/llm，Claim 必须绑定 `evidence_ids`。
- `QaAgent`：校验 Schema、Evidence 覆盖、competitor 覆盖、relevance、Claim 绑定和格式，并路由返工。
- `FinalReportAgent`：整合最终报告、QA 结果和 Evidence summary。

风险：`EvidenceGate` 当前是 workflow runner 内部逻辑，不是独立 Agent 类；`PageFetcher` 当前是 service，不是 Agent。短期可接受，但 RAG 继续扩展时建议把 Chunker / Indexer / Retriever 都按“service + LangGraph adapter”或“Agent.run + node adapter”统一约定清楚。

### 2.2 Agent 输入输出 Schema

已有：

- `PlannerInput` / `PlannerOutput`
- `CollectorInput` / `CollectorOutput`
- `AnalystInput` / `AnalystOutput`
- `ReportWriterInput` / `ReportWriterOutput`
- `QaInput` / `QaOutput`
- `FinalReportInput` / `FinalReportOutput`

不足：

- `PlannerOutput` 目前只有 `dag` 和 `plan`，不能稳定承载 `selected_dimensions`、`analysis_dimension_plan`、`research_goals`。
- `AnalystInput` 目前只接收 `evidence`，没有接收 `retrieval_results` 或 `analysis_dimension_plan` 的正式字段。
- `QaInput` 目前只接收 `evidence`、`analysis`、`report_output`，没有接收 retrieval support verification 结果的正式字段。
- Survey 相关输入输出 Schema 尚不存在。

### 2.3 LangGraphWorkflowRunner

当前 `LangGraphWorkflowRunner` 基本承担编排层职责：创建 run、调用 Agent / service、更新 state、记录 node sequence 和 conditional routes。它已经接入 `EvidenceGate` 和 `PageFetcher`。

需要注意：

- LangGraph node 可以保留 routing / state adapter 逻辑，但不能继续堆 Agent 业务逻辑。
- RAG 线新增 `Chunker`、`Indexer`、`Retriever` 时，应避免把 chunking、embedding、retrieval scoring 写进 runner。
- Survey 线不应直接在 runner 中实现问卷设计或 CSV 解析，只能调用 `SurveyAgent.run()` 或 service。

### 2.4 WorkflowState

`WorkflowState` 已经是统一状态承载层，但字段仍围绕当前主线：task、plan、evidence、analysis、report、qa、routing、workflow summary。

并行开发前建议预留：

- `selected_dimensions`
- `analysis_dimension_plan`
- `survey_plan`
- `survey_evidence`
- `chunks`
- `retrieval_results`
- `claim_support_results`
- `rework_context`

### 2.5 run_id

`run_id` 已贯穿：

- `TaskRun`
- `Evidence`
- `Report`
- `QaResult`
- `TraceRecord`
- latest run 和 `/runs/{run_id}/...` 查询接口

RAG / Survey 新表或新对象必须继承该约束。尤其是 `Chunk`、`RetrievalResult`、`SurveyEvidence` 必须包含 `run_id`，否则会出现跨 run 混用。

### 2.6 EvidenceGate 位置

当前位置正确：

```text
CollectorAgent -> EvidenceGate -> PageFetcher -> AnalystAgent
```

未来 RAG 主线应保持：

```text
CollectorAgent -> EvidenceGate -> PageFetcher -> Chunker -> Indexer -> Retriever -> AnalystAgent
```

Survey 证据如果已经转成 `Evidence(source_type="survey")`，可以在 Analyst 前合并，但不应绕过基本 Evidence schema 校验和 run isolation。

### 2.7 新节点接入策略

新增节点可以只接入 `LangGraphWorkflowRunner`，不需要扩展 `CustomWorkflowRunner`。`CustomWorkflowRunner` 只保持旧主链路稳定。

### 2.8 前端承载能力

前端已有：

- run history
- DAG 展示
- Evidence panel
- Knowledge view
- Report view
- QA panel
- Trace viewer
- workflow summary / route history

新增节点状态可以先通过 Trace 和 workflow summary 展示。后续再增加 RAG / Survey tab。高风险文件是 `frontend/src/App.tsx`、`frontend/src/api/types.ts`、`frontend/src/components/DagView.tsx`、`frontend/src/components/EvidencePanel.tsx`。

## 3. 三条并行开发线边界

### 3.1 Planner 增强线

负责范围：

- `AnalysisDimension`
- `AnalysisDimensionPlan`
- `selected_dimensions`
- industry-specific planning
- task decomposition
- collection query planning
- planner diagnostics

允许修改：

- `backend/app/agents/planner.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/models.py` 中 Planner 公共 Schema
- `backend/app/schemas/workflow_state.py` 中 planner 字段
- Planner 相关测试
- 文档中 Planner 协议

不得修改：

- Retriever 内部逻辑
- VectorStore / Chunker
- Survey response ingestion
- `CustomWorkflowRunner`

边界要求：

- Planner 可以输出 `analysis_dimension_plan`，但不负责执行 RAG 检索。
- Planner 可以输出每个 competitor / dimension 的 research goals 和 query hints，但 Collector / Retriever 自己决定具体工具调用。
- Planner 不应直接操作 Evidence、Chunk 或 SurveyResponse。

### 3.2 Survey / Questionnaire 线

负责范围：

- `SurveyAgent` / `QuestionnaireAgent`
- `SurveyPlan`
- `SurveyQuestion`
- `SurveyResponse`
- `SurveyEvidence`
- CSV import / mock response
- survey evidence 转标准 `Evidence`
- survey privacy / mock 标记

允许修改：

- 新增 `backend/app/agents/survey.py` 或 `questionnaire.py`
- 新增 survey service，例如 `backend/app/services/survey_service.py`
- `backend/app/schemas/models.py` 中 Survey 公共 Schema
- `backend/app/schemas/agent_io.py` 中 Survey I/O
- `backend/app/schemas/workflow_state.py` 中 survey 字段
- Survey 相关 API，若做独立模块
- Survey 相关前端组件，建议独立文件

不得修改：

- Retriever 内部逻辑
- Planner 核心计划生成之外的 workflow 结构
- `CustomWorkflowRunner`

边界要求：

- Survey 输出必须最终转为标准 `Evidence`，不能让 Analyst 直接消费自由格式问卷结果。
- mock survey 必须显式标记 `is_mock=true`。
- CSV import 必须避免敏感个人数据，至少做字段白名单和摘要化。

### 3.3 RAG 线

负责范围：

- `PageFetcher`
- `Chunker`
- `Indexer`
- `RetrieverService`
- `RetrievalResult`
- chunk metadata
- `AnalystAgent` 使用 Retriever
- `QaAgent` claim support verification

允许修改：

- 新增 `backend/app/services/chunker.py`
- 新增 `backend/app/services/indexer.py`
- 新增 `backend/app/services/retriever.py`
- 新增可替换 VectorStore adapter
- `backend/app/agents/analyst.py`
- `backend/app/agents/qa.py`
- `backend/app/agents/langgraph_runner.py`
- `backend/app/schemas/models.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/workflow_state.py`
- RAG 相关测试和文档

不得修改：

- Survey question design
- Planner dimension recommendation 规则，除非只是读取 `AnalysisDimensionPlan`
- `CustomWorkflowRunner`

边界要求：

- RAG 只能消费通过 EvidenceGate 的 relevant Evidence / chunks。
- Chunk 必须继承 `run_id`、`evidence_id`、`competitor`、source metadata。
- Retriever 返回必须保留 citation metadata。
- QA claim support verification 不应替代 Claim evidence_ids 校验，而是增强其可信度检查。

## 4. 需要冻结的公共 Schema

### 4.1 已存在 Schema

- `Task`
- `TaskRun`
- `WorkflowState`
- `Evidence`
- `Claim`
- `QaResult`
- `ReworkInstruction`
- `TraceRecord`
- `Report`
- Agent I/O Schema

### 4.2 需要新增 Schema

建议新增：

- `AnalysisDimension`
- `AnalysisDimensionPlan`
- `DimensionResult`
- `SurveyPlan`
- `SurveyQuestion`
- `SurveyResponse`
- `SurveyEvidence`
- `Chunk`
- `RetrievalResult`
- `ClaimSupportResult`
- `ReworkContext`
- `RouteInstruction`

### 4.3 共享字段，不能随意改名

以下字段是三条线共享字段，应冻结命名：

- `task_id`
- `run_id`
- `competitor`
- `evidence_id`
- `claim_id`
- `source_type`
- `url`
- `local_ref`
- `source_domain`
- `source_quality`
- `confidence`
- `relevance_score`
- `relevance_level`
- `relevance_reason`
- `entity_match_signals`
- `content_excerpt`
- `selected_dimensions`
- `dimension_id`
- `chunk_id`
- `retrieval_score`
- `citation_metadata`
- `question_ids`
- `sample_size`
- `is_mock`

### 4.4 可扩展 metadata 字段

建议允许各线扩展：

- `Evidence.entity_match_signals`
- `Evidence.metadata`，建议新增
- `AnalysisDimensionPlan.metadata`
- `SurveyEvidence.metadata`
- `Chunk.metadata`
- `RetrievalResult.citation_metadata`
- `ClaimSupportResult.metadata`
- `WorkflowState.workflow_summary`

## 5. 公共接口契约

### 5.1 Planner -> Collector / Analyst / RAG

Planner 输出建议包含：

```json
{
  "selected_dimensions": ["positioning", "feature", "pricing", "persona"],
  "analysis_dimension_plan": [
    {
      "dimension_id": "pricing",
      "label": "定价与商业模式",
      "priority": 1,
      "competitors": ["A", "B"],
      "research_goals": ["识别套餐、免费试用、企业版信号"],
      "query_hints": ["{competitor} pricing official", "{competitor} enterprise plan"],
      "required_source_types": ["official", "pricing_page"],
      "min_relevant_evidence": 1,
      "metadata": {}
    }
  ],
  "competitors": ["A", "B"],
  "industry": "B2B SaaS",
  "region": "China",
  "research_goals": ["竞品功能、定价、目标用户、风险缺口"]
}
```

约束：

- Planner 只输出计划，不执行采集、问卷、检索。
- Collector 可以读取 `query_hints`，但保留 fallback query。
- Analyst 可以读取 `selected_dimensions` 决定输出重点。
- RAG 可以读取 dimension plan 构造 retrieval query。

### 5.2 Survey -> Evidence

Survey 模块输出必须转成 Evidence，最低字段：

```json
{
  "evidence_id": "ev_xxx",
  "run_id": "run_xxx",
  "source_type": "survey",
  "competitor": "A",
  "local_ref": "survey://run_xxx/question_1",
  "snippet": "Survey summary only, no raw private respondent data.",
  "confidence": 0.65,
  "relevance_level": "medium",
  "question_ids": ["q_1", "q_2"],
  "sample_size": 12,
  "is_mock": true
}
```

建议：

- 先通过 `Evidence.metadata` 或 `SurveyEvidence` 承载 `question_ids`、`sample_size`、`is_mock`。
- 不保存私人身份信息。
- CSV import 只保存聚合摘要和可审计 local_ref。

### 5.3 RAG -> Analyst / QA

Retriever 输出必须包含：

```json
{
  "chunk_id": "chunk_xxx",
  "evidence_id": "ev_xxx",
  "run_id": "run_xxx",
  "competitor": "A",
  "source_url": "https://example.com",
  "source_domain": "example.com",
  "text": "truncated chunk text",
  "score": 0.82,
  "citation_metadata": {
    "source_quality": "official",
    "relevance_level": "high",
    "page_title": "Pricing",
    "content_mode": "page"
  }
}
```

约束：

- `RetrievalResult` 不能丢失 `evidence_id`。
- `ClaimSupportResult` 应记录 claim 与 retrieved chunks 的匹配结果。
- QA 使用 Retriever 做支持性验证时，只能增强校验，不能允许无 `evidence_ids` 的 Claim 通过。

## 6. LangGraph 合并策略

### 6.1 推荐主线

RAG 完整主线建议：

```text
PlannerAgent
-> CollectorAgent
-> EvidenceGate
-> PageFetcher
-> Chunker
-> Indexer
-> Retriever
-> AnalystAgent
-> ReportWriterAgent
-> QaAgent
-> FinalReportAgent
```

其中：

- `Chunker` 只消费 relevant Evidence 的 `content_excerpt` 或 snippet fallback。
- `Indexer` 只索引 relevant chunks。
- `Retriever` 输出 `RetrievalResult`，写入 `WorkflowState`，供 Analyst / QA 使用。

### 6.2 SurveyAgent 推荐接入方式

推荐方案：**先采用 4. 独立模块，输出 Evidence 后再接入；第二阶段作为 Planner 后的可选并行分支**。

理由：

- Survey / Questionnaire 涉及问卷设计、mock response、CSV import、隐私脱敏，和 Web/RAG 的技术路径不同。
- 当前 Evidence 是系统统一可信载体，Survey 先转 Evidence 可以最大限度降低对 Analyst / ReportWriter / QA 的冲击。
- 如果一开始就把 SurveyAgent 放进主 DAG，会和 Planner、WorkflowState、前端 DAG、API response shape 同时冲突。
- 独立模块成熟后，可以接成：

```text
PlannerAgent -> SurveyAgent -> SurveyEvidence -> Evidence merge -> AnalystAgent
```

中期目标：

```text
PlannerAgent
  -> CollectorAgent -> EvidenceGate -> PageFetcher -> RAG
  -> SurveyAgent -> SurveyEvidence
Evidence merge -> AnalystAgent
```

Survey 本质是 Analyst 前的可选 Evidence source，不应绕过 Evidence schema。

## 7. Git / 分支建议

建议分支：

- `feature/rag-pipeline`
- `feature/planner-dimensions`
- `feature/survey-agent`

### 7.1 feature/rag-pipeline

允许修改：

- `backend/app/services/page_fetcher.py`
- `backend/app/services/chunker.py`
- `backend/app/services/indexer.py`
- `backend/app/services/retriever.py`
- `backend/app/agents/analyst.py`
- `backend/app/agents/qa.py`
- `backend/app/agents/langgraph_runner.py`
- `backend/app/schemas/models.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/workflow_state.py`
- RAG tests
- RAG docs

避免修改：

- `backend/app/agents/planner.py` 的推荐规则
- survey agent / survey service
- `CustomWorkflowRunner`

### 7.2 feature/planner-dimensions

允许修改：

- `backend/app/agents/planner.py`
- `backend/app/schemas/models.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/workflow_state.py`
- Planner tests
- Planner docs

避免修改：

- `backend/app/services/retriever.py`
- `backend/app/services/chunker.py`
- Survey ingestion
- `CustomWorkflowRunner`

### 7.3 feature/survey-agent

允许修改：

- `backend/app/agents/survey.py`
- `backend/app/agents/questionnaire.py`
- `backend/app/services/survey_service.py`
- `backend/app/schemas/models.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/workflow_state.py`
- Survey API / frontend isolated components
- Survey tests
- Survey docs

避免修改：

- Retriever internals
- Planner dimension recommendation rules
- `CustomWorkflowRunner`

### 7.4 高风险公共文件

- `backend/app/schemas/models.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/workflow_state.py`
- `backend/app/agents/langgraph_runner.py`
- `backend/app/api/routes.py`
- `frontend/src/App.tsx`
- `frontend/src/api/types.ts`
- `frontend/src/components/DagView.tsx`
- `frontend/src/components/EvidencePanel.tsx`
- `backend/tests/test_schema_and_workflow.py`
- `AGENTS.md`

### 7.5 修改公共接口的同步规则

任何分支修改以下内容前，先在 main 合入公共接口补丁：

- `WorkflowState`
- `Evidence`
- `TaskRun`
- `AgentName`
- API response shape
- LangGraph edge
- run_id 查询逻辑

### 7.6 合并顺序

推荐：

1. `chore/public-contracts-parallel-dev`：只补公共 Schema、WorkflowState 预留字段和文档。
2. `feature/planner-dimensions`：先合，因为它影响 Collector / RAG 的输入计划。
3. `feature/rag-pipeline`：再合，因为它影响主 DAG 和 Analyst / QA。
4. `feature/survey-agent`：先独立模块合入，再接入 DAG。

如果 Survey 先做独立 API 和 Evidence 转换，也可以与 RAG 并行合并，但不要同时改 LangGraph 主线。

## 8. 冲突风险清单与规避方案

### 8.1 WorkflowState 字段冲突

风险：三条线都会想往 state 加字段。

规避：

- 先统一预留字段。
- 字段名只增不改。
- 使用 `metadata` 承载实验性字段。

### 8.2 Evidence Schema 字段冲突

风险：Survey 想加 question fields，RAG 想加 chunk fields，Planner 想加 dimension fields。

规避：

- Evidence 保持统一最小可信载体。
- Survey-specific 字段先放 `SurveyEvidence` 或 `Evidence.metadata`。
- Chunk 不要塞进 Evidence，单独 `Chunk` Schema。

### 8.3 LangGraph edges 冲突

风险：RAG 和 Survey 都改主 DAG。

规避：

- RAG 先改主线。
- Survey 第一阶段不进主 DAG，只输出 Evidence。
- 新 edge 必须记录 `conditional_routes_taken` 和 Trace。

### 8.4 Frontend task detail page 冲突

风险：都改 `App.tsx`。

规避：

- 新增独立组件：`RagPanel.tsx`、`SurveyPanel.tsx`、`PlannerPanel.tsx`。
- `App.tsx` 只做最小挂载。
- 类型集中在 `frontend/src/api/types.ts`，字段先可选。

### 8.5 API response shape 冲突

风险：run result 和 workflow summary 被多条线同时扩展。

规避：

- `workflow_summary` 允许新增 optional 字段。
- 不改已有字段含义。
- 新接口优先用 `/runs/{run_id}/...` 路径。

### 8.6 run_id 查询逻辑冲突

风险：Chunk / SurveyResponse 如果不绑定 run，会污染历史运行。

规避：

- 所有新存储对象必须包含 `run_id`。
- latest run 默认行为保持不变。
- 历史查询必须支持 run-specific endpoint 或能从 Trace/Report 追溯。

### 8.7 AGENTS.md 规则冲突

风险：组员为各自功能修改项目规则，产生冲突。

规避：

- AGENTS.md 暂时冻结。
- 各分支写独立 docs。
- 最后由维护者统一更新 AGENTS.md。

## 9. 需要先做的小补丁

### 9.1 必须先做

1. 新增公共 Schema：
   - `AnalysisDimension`
   - `AnalysisDimensionPlan`
   - `DimensionResult`
   - `Chunk`
   - `RetrievalResult`
   - `ClaimSupportResult`
   - `SurveyEvidence`
   - `ReworkContext`
   - `RouteInstruction`

2. `WorkflowState` 预留字段：
   - `selected_dimensions`
   - `analysis_dimension_plan`
   - `survey_evidence`
   - `chunks`
   - `retrieval_results`
   - `claim_support_results`
   - `rework_context`

3. 文档冻结接口契约：
   - Planner -> Collector / Analyst / RAG
   - Survey -> Evidence
   - RAG -> Analyst / QA

4. `AgentName` 预留：
   - `SurveyAgent`
   - `QuestionnaireAgent`
   - `Chunker`
   - `Indexer`
   - `Retriever`

### 9.2 可以边开发边做

- 前端新增 `RagPanel`、`SurveyPanel`、`PlannerPlanPanel`
- Survey 独立 API
- Chunk / Retrieval persistence 表
- workflow summary 中新增 RAG / Survey metrics
- docs 中新增各线详细设计

### 9.3 暂时不做

- 不扩展 `CustomWorkflowRunner`
- 不做完整生产级 Vector DB 抽象，先可用内存或 SQLite mock index
- 不把 SurveyAgent 强行接入主 DAG
- 不让 Planner 直接调用 Retriever
- 不让 QA 完全依赖 LLM 判断 claim support

## 10. 测试策略

### 10.1 Planner 线

- `selected_dimensions` 默认值正确。
- `AnalysisDimensionPlan` 输出符合 Schema。
- 不同行业能生成不同 dimension priority / query hints。
- query planning 不破坏旧任务。
- Planner Trace 记录 selected dimensions 和 plan summary。

### 10.2 Survey 线

- `SurveyPlan` 生成。
- `SurveyQuestion` Schema 校验。
- mock response 转 `SurveyEvidence`。
- CSV import 转 Evidence。
- survey evidence 不含敏感个人数据。
- mock survey 必须标记 `is_mock=true`。
- SurveyEvidence 必须绑定 `run_id`。

### 10.3 RAG 线

- PageFetcher 只处理 relevant Evidence。
- Chunk 绑定 `run_id` / `evidence_id` / `competitor`。
- Indexer 不索引 unrelated Evidence。
- Retriever 返回 citation metadata。
- Analyst 使用 retrieved chunks，且保留 fallback 到 Evidence。
- QA 能反查 claim support。
- Claim 即使通过 retrieval support，也仍必须有 `evidence_ids`。

### 10.4 集成测试

- LangGraph 主流程正常通过。
- Survey + Web Evidence 同时存在时 Analyst 正常消费。
- RAG + EvidenceGate 正常，unrelated Evidence 不进入 index。
- QA conditional routing 不死循环。
- max_rework 限制仍生效。
- Custom Runner 旧主链路不被破坏。

## 11. 推荐开发顺序

1. 先合入公共接口补丁。
2. Planner 线实现 `selected_dimensions` 和 `AnalysisDimensionPlan`。
3. RAG 线接入 Chunker / Indexer / Retriever，并让 Analyst 读取 retrieval results。
4. RAG 线增强 QA claim support verification。
5. Survey 线先实现独立模块和 Evidence 转换。
6. Survey 线再作为 Planner 后可选分支接入 LangGraph。
7. 前端最后统一展示 Planner plan、RAG retrieval、Survey evidence，避免三条线同时大改 `App.tsx`。

## 12. 是否建议现在开始并行开发

建议：**可以开始准备分支，但正式并行编码前应先做公共接口补丁**。

如果不先补公共接口，三条线会在 `models.py`、`agent_io.py`、`workflow_state.py`、`langgraph_runner.py` 和 `App.tsx` 上高概率冲突。补完最小公共契约后，可以并行：

- Planner 线围绕计划生成和 selected dimensions。
- Survey 线先做独立模块并输出 Evidence。
- RAG 线围绕 PageFetcher 后的 Chunk / Index / Retrieve / Analyst / QA。

最终判断：项目当前架构已经具备并行开发基础，但还需要一次小型 schema contract freeze，之后再进入三线并行最稳。
