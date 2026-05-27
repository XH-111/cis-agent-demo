# Phase 9.1 Run Isolation + EvidenceGate

## 目标

Phase 9.1 解决两个问题：

1. 同一个 task 多次运行时，旧 Evidence / Report / QA 结果会污染新运行。
2. 明显缺少相关 Evidence 的任务仍会进入 Analyst / ReportWriter，造成无效分析和无效 LLM 调用。

本阶段不接 RAG、不接向量数据库、不新增复杂 Agent，只在 LangGraph 主线上增加 run cleanup 和 EvidenceGate。

## Run Isolation

当前 Demo 没有引入 `run_id` 表结构，因此采用简单稳定的 cleanup 策略：

- 每次 LangGraph run 开始前清理当前 task 的旧 Evidence。
- 每次 LangGraph run 开始前清理当前 task 的旧 Report。
- 每次 LangGraph run 开始前清理当前 task 的旧 QA。
- Trace 保留，用于历史可观测。

WorkflowEngine Trace 会记录：

- `run_isolation_strategy=cleanup`
- `run_cleanup_summary`

这样 `/api/tasks/{task_id}/evidence`、`/api/tasks/{task_id}/report`、`/api/tasks/{task_id}/qa` 展示的就是最新运行结果，不再混入旧数据。

## EvidenceGate

LangGraph 主链路变为：

```text
PlannerAgent
-> CollectorAgent
-> EvidenceGate
-> AnalystAgent
-> ReportWriterAgent
-> QaAgent
-> FinalReportAgent
```

EvidenceGate 检查：

- 每个 competitor 是否有 high / medium relevance Evidence。
- 每个 competitor 的 relevant evidence 数量。
- 每个 competitor 的 unrelated evidence 数量。
- 缺少相关 Evidence 的 competitor 列表。

EvidenceGate 输出：

- `evidence_gate_passed`
- `missing_relevant_evidence_competitors`
- `relevant_evidence_count_by_competitor`
- `unrelated_evidence_count_by_competitor`
- `suggested_route`
- `suggested_action`

## LangGraph 路由

EvidenceGate 后使用 conditional routing：

- passed -> AnalystAgent
- failed + auto_rework=true -> CollectorAgent
- failed + auto_rework=false -> FinalReportAgent / insufficient_evidence
- max_rework reached -> manual_review

`conditional_routes_taken` 会记录 EvidenceGate 的跳转。

## 随机竞品表现

对于 `xqzvra / lmptuo` 这类随机竞品：

- Web Collector 可以搜索。
- Evidence relevance 会被判定为 low / unrelated。
- EvidenceGate failed。
- AnalystAgent / ReportWriterAgent 不执行。
- `/report` 不返回最终报告。
- QA 显示 missing_relevant_evidence。

## 后续方向

后续如果接 RAG，应只索引 high / medium relevance Evidence 或 chunks。

长期更完整的 run isolation 应引入 `run_id`，让 Evidence、Report、QA、Trace 全部按 run 查询。

