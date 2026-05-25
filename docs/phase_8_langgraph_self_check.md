# Phase 8 LangGraph Workflow Engine 自检报告

生成时间：2026-05-26

## 1. 总体验收结论

结论：通过，带少量中低优先级改进项。

当前项目已经真实接入 LangGraph Workflow Engine，不是仅在文档或前端表面增加选项。后端存在独立的 `LangGraphWorkflowRunner`，使用 `StateGraph` 表达 Agent DAG，并在 `QaAgent` 后使用 conditional routing 实现返工流转。现有 Custom Runner 仍保留为 legacy fallback，未被删除，也没有被要求承担未来 RAG / Retriever / SWOT 等新增节点扩展。

从测试结果看，Phase 8 没有破坏已有主流程、QA 打回、auto_rework、竞品覆盖、Evidence 质量评分、LLM ReportWriter 和 Web Collector 的关键能力。

## 2. AGENTS.md 规则符合情况

已符合项：

- `AGENTS.md` 已明确写入当前存在两个 workflow engine：CustomWorkflowRunner / MockWorkflowRunner 和 LangGraphWorkflowRunner。
- Custom Runner 被定义为 legacy stable fallback，只维护当前稳定主链路。
- LangGraph Runner 被定义为后续主 workflow engine。
- 文档已明确未来新增 PageFetcher、Chunker、Indexer、Retriever、RAG-related nodes、SWOTAgent、QuestionnaireAgent、InterviewAgent 等节点只接入 LangGraph。
- 现有 Agent 业务逻辑仍集中在各自 `Agent.run()` 中。
- LangGraph node 主要承担 adapter 职责：读取 `WorkflowState`、构造 Agent Input Schema、调用 `Agent.run()`、写回 State。
- 未发现把 Planner / Collector / Analyst / ReportWriter / QA / FinalReport 的核心业务逻辑复制进 LangGraph node 的严重问题。

需要关注项：

- Custom Runner 仍包含 auto_rework 的旧实现，这是 legacy fallback 所需，不构成违规。但后续新能力不应继续同步扩展 Custom Runner。
- 后续 Phase 9 起需要严格执行“新增节点只接入 LangGraph”规则，避免再次出现双状态机维护。

## 3. LangGraph 接入真实性结论

结论：真实接入。

检查结果：

- 后端存在 `backend/app/agents/langgraph_runner.py`。
- 代码真实导入并使用 `langgraph.graph.StateGraph` 和 `END`。
- 存在独立 `backend/app/schemas/workflow_state.py`，定义了 `WorkflowState`。
- LangGraph DAG 中存在节点：
  - `planner`
  - `collector`
  - `analyst`
  - `report_writer`
  - `qa`
  - `final_report`
- 每个节点调用对应 Agent 的 `run()` 方法。
- 每个节点会把输出写回 `WorkflowState`。
- `node_sequence` 会记录实际执行路径。
- `workflow_engine_requested` / `workflow_engine_used` 会进入 workflow summary。
- API 支持 `workflow_engine=custom` / `workflow_engine=langgraph`。
- 前端运行区支持选择 Custom Runner / LangGraph Runner。

判断：当前不是表面包装，而是用 StateGraph 显式承载主 DAG 和 QA conditional routing。

## 4. Custom Runner 与 LangGraph Runner 维护边界检查

当前边界清晰：

- Custom Runner：保留稳定主链路，作为演示和紧急 fallback。
- LangGraph Runner：作为后续扩展主线。
- Runner 选择逻辑集中在 `backend/app/agents/runner_factory.py`。
- API 层通过 runner factory 创建 runner，选择逻辑没有散落到多个地方。
- README、architecture、Phase 8 文档和 AGENTS.md 都已经明确该维护边界。

风险：

- Custom Runner 仍返回一个简化 workflow summary，`conditional_routes_taken` 在 custom 模式下为空。作为 legacy fallback 可以接受，但不要再把新能力同步补到 Custom Runner。

## 5. QA conditional routing 检查结果

LangGraph 中 `QaAgent` 后存在 conditional edge，覆盖情况如下：

- QA passed -> `final_report`
- `route_to=CollectorAgent` -> `collector`
- `route_to=AnalystAgent` -> `analyst`
- `route_to=ReportWriterAgent` -> `report_writer`
- `rework_count >= max_rework` -> `final_report`
- unknown route -> `final_report`

返工路径检查：

- QA 打回 Collector 后，会重新执行 `collector -> analyst -> report_writer -> qa`。
- QA 打回 Analyst 后，会重新执行 `analyst -> report_writer -> qa`。
- QA 打回 ReportWriter 后，会重新执行 `report_writer -> qa`。
- 未发现跳过必要节点的问题。

`conditional_routes_taken` 会记录每次 conditional jump，包括 from、to、reason、rework_count。

注意：

- unknown route 当前会安全进入 `final_report`，不会死循环。最终状态可能是 failed / qa_failed / manual_review，行为安全，但如需严格统一成 manual_review，可后续小补丁处理。

## 6. auto_rework 检查结果

结论：LangGraph 模式下 auto_rework 已接入且有防死循环机制。

检查结果：

- 每次 QA failed 且 `auto_rework=true` 时，会根据 `route_to` 进入对应返工节点。
- `rework_count` 会递增。
- `max_rework` 默认沿用 3。
- 达到 `max_rework` 后进入 final_report 分支，避免死循环。
- `conditional_routes_taken` 会记录返工路径。
- 测试覆盖 missing evidence、invalid extraction、bad report format 三类返工路由。

风险：

- LangGraph 的返工历史主要体现在 workflow summary 的 `conditional_routes_taken` 中，`QaResult.rework_history` 未必与 Custom Runner 完全一致。前端可以从 workflow summary 看到 LangGraph 路由，但 QA Panel 的 rework_history 展示可能不如 custom 模式直观。

## 7. 竞品覆盖检查结果

LangGraph 模式下竞品覆盖能力仍然保留：

- Web Collector 仍按 competitor 分组采集。
- Evidence Schema 包含 `competitor` 字段。
- AnalystAgent 在 evidence 模式下按 competitor 分组分析。
- ReportWriterAgent 要求输出覆盖所有 competitors。
- Claim 包含 `competitor` 字段。
- QaAgent 会检查：
  - `missing_evidence_competitors`
  - `missing_claim_competitors`
  - `mismatched_evidence_claims`
- 前端 ReportView 中仍展示“竞品覆盖情况”。
- Evidence Panel 中展示 competitor、source_domain、source_quality、confidence 等字段。

结论：Phase 8 没有破坏 Phase 7.1 的 Competitor Coverage Fix。

## 8. Trace / 前端展示检查结果

后端可观测性：

- 每个 Agent 仍通过现有 trace_service 生成 TraceRecord。
- LangGraph 额外生成 workflow-level Trace，agent_name 为 `WorkflowEngine`。
- workflow-level Trace 中记录：
  - `workflow_engine_requested`
  - `workflow_engine_used`
  - `node_sequence`
  - `conditional_routes_taken`
  - `rework_count`
  - `final_status`
  - `elapsed_time_ms`
  - `error_message`
- LLM ReportWriter Trace 仍保留：
  - `llm_call_attempted`
  - `llm_call_success`
  - `llm_schema_validation_success`
  - `llm_elapsed_time_ms`
  - `fallback_used`
  - `llm_fallback_reason`
- Web Collector Trace 仍保留：
  - `web_search_attempted`
  - `web_search_success`
  - `query_count`
  - `evidence_count`
  - fallback 信息

前端展示：

- 前端可以选择 Custom Runner / LangGraph Runner。
- 运行完成后显示 workflow summary，包括 workflow_engine_used、requested、rework_count、final_status、conditional routes。
- DAG 页面继续展示 Agent 节点状态。
- Trace Viewer 可以展示 WorkflowEngine Trace 和各 Agent Trace。
- QA Panel 仍展示 hard errors、soft suggestions、rework instructions。
- Report 页面仍支持点击 Claim 查看 Evidence。
- Evidence Panel 仍展示 competitor、source_domain、source_quality、confidence、snippet、url。

风险：

- workflow summary 目前主要来自本次 run 返回值和 WorkflowEngine Trace。切换任务或刷新页面后，顶部 summary 面板不一定从最新 WorkflowEngine Trace 自动恢复，但 Trace Viewer 仍可查看历史记录。

## 9. 已通过的测试结果

后端：

```text
cd backend
pytest

56 passed, 869 warnings in 5.17s
```

前端：

```text
cd frontend
npm run build

tsc && vite build
build passed
```

当前未发现独立 lint 脚本需要额外执行。

## 10. 发现的问题

高优先级问题：

- 暂未发现阻塞 Phase 8 验收或阻止 LangGraph 作为后续主线的问题。

中优先级问题：

- LangGraph 模式下返工历史主要记录在 `conditional_routes_taken`，而不是完全写入 `QaResult.rework_history`。如果答辩时重点展示 QA Panel 的 rework_history，可能不如 workflow summary 直观。
- workflow summary 没有独立持久化表或专门 API，目前依赖 run response 和 WorkflowEngine Trace。页面刷新后主状态区可能不自动恢复最近一次 summary。
- unknown `route_to` 的 safe end 行为是安全的，但最终状态可能表现为 failed / qa_failed，而不是统一 manual_review。

低优先级问题：

- PowerShell 中读取中文文件时可能出现乱码显示，属于 Windows 控制台编码问题；README 已有中文乱码说明。
- Custom Runner 的 workflow summary 是简化版本，`conditional_routes_taken` 不记录 custom auto_rework 细节。考虑到 Custom Runner 已冻结为 legacy fallback，可以接受。
- `workflow_engine_requested` 在通过环境变量选择时可能显示为 `env/default`，实际执行引擎以 `workflow_engine_used` 为准。
- LangGraph runner 中部分 node 函数略长，但主要是编排适配和状态写回，没有明显业务逻辑复制。

## 11. 高优先级修复建议

暂无必须立即修复的高优先级问题。

建议在进入 Phase 9 前保持当前代码稳定，不要再扩展 Custom Runner。

## 12. 中优先级优化建议

建议后续小范围补强：

- 将 LangGraph 的 `conditional_routes_taken` 同步映射到 QA Panel 的 rework history 展示，减少答辩解释成本。
- 增加一个轻量的“最近一次 workflow summary”查询能力，或者让前端从最新 `WorkflowEngine` Trace 中恢复 summary。
- 统一 unknown `route_to` 的最终状态为 manual_review，便于解释异常闭环。
- 为 `workflow_engine_requested` 在 env 选择场景下记录实际请求来源和解析结果，例如 `requested_source=env`、`workflow_engine_used=langgraph`。

## 13. 低优先级优化建议

- 后续可以把 LangGraph runner 中的 summary 构造、route 记录、状态更新拆成更小的私有方法，降低文件长度。
- 可以增加一个前端小标签，明确当前 Trace 中的 `WorkflowEngine` 是 workflow-level trace，而不是普通业务 Agent。
- 可以在文档中补充一张“Custom fallback 与 LangGraph 主线的差异表”，方便答辩时解释为什么保留两个 runner。

## 14. 是否建议后续正式以 LangGraph 作为主线继续开发

建议：是。

理由：

- 当前 LangGraph 已真实承载主链路和 QA conditional routing。
- Agent 业务逻辑仍保持单一来源，没有被复制到 LangGraph node 中。
- Custom Runner 已保留为 fallback，不影响演示稳定性。
- Phase 9 如果要接 RAG、Retriever、SWOT、Questionnaire 或 Interview 类节点，应该直接接入 LangGraphWorkflowRunner，不再扩展 Custom Runner。

建议 Phase 9 开发顺序：

1. 先补一个轻量 `ReworkContext` / `RouteInstruction`，让 QA 打回时把“缺哪个竞品、缺哪类证据、哪个 claim 有问题”结构化传给对应 Agent。
2. 再基于 LangGraph 增加最小 RAG 链路节点，例如 PageFetcher / Chunker / Indexer / Retriever。
3. 最后让 AnalystAgent 或 ReportWriterAgent 使用 Retriever 输出，而不是直接从全量 Evidence 中抽取。

