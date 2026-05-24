# LLM ReportWriter 接入验收报告

## 已完成项

1. **writer_mode=llm 能进入 LLM 分支**
   - 前端 `api.runTask(...)` 会向 `/api/tasks/{task_id}/run` 传递 `writer_mode=llm`。
   - 后端 API route 接收 `writer_mode`，并传入 `MockWorkflowRunner.run(...)`。
   - `runner.py` 将 `writer_mode` 传入 `ReportWriterInput`。
   - `ReportWriterAgent.run()` 根据 `input_data.writer_mode == "llm"` 进入 `_run_llm_with_trace(...)`。

2. **LLM 调用成功时 writer_mode_used 为 llm**
   - LLM 返回合法 JSON，且 `claims` 可通过 `Claim` Schema 时，`ReportWriterAgent` 会生成 `Report`。
   - 报告中的 `json_report.writer_mode` 为 `llm`。
   - `json_report.writer_diagnostics.writer_mode_used` 为 `llm`。

3. **LLM 调用失败时 fallback 到 mock**
   - 未配置 `LLM_API_KEY`、HTTP 调用失败、超时、非法 JSON 等场景不会导致 workflow 崩溃。
   - 可 fallback 的失败会生成 mock report。
   - `writer_diagnostics` 中会记录：
     - `fallback_used=true`
     - `writer_mode_requested=llm`
     - `writer_mode_used=mock`
     - `llm_fallback_reason`

4. **Claim.category 约束已强化**
   - Prompt 已明确要求 `claims[].category` 只能使用：
     - `positioning`
     - `feature`
     - `pricing`
     - `persona`
     - `risk`
     - `recommendation`
   - Prompt 明确禁止中文分类名。
   - Prompt 提供了合法 claim JSON 示例。
   - 后端 Schema 仍保持严格校验，不会静默接受非法 category。

5. **LLM 输出可以通过 ReportWriterOutput / Claim Schema**
   - 当 LLM 输出满足 JSON 结构、Claim 字段和 category 枚举约束时，`Claim(...)` 与 `ReportWriterOutput(...)` 能正常构造。
   - 无效模型输出会进入 Trace failed 分支，符合“无效模型输出不能静默通过”的要求。

6. **每个 claim 强制包含 evidence_ids**
   - `Claim.evidence_ids` 在 Pydantic Schema 中强制非空。
   - LLM 分支在构造 `Claim` 前会检查 `claims_payload`，若任一 claim 缺少 `evidence_ids`，会抛出校验错误并让 QA 路由到 `ReportWriterAgent`。

7. **LLM 报告后 QA 可正常校验**
   - LLM 生成合法报告后，会继续进入 `QaAgent`。
   - QA 仍检查 evidence coverage、report format 和 schema 结果。
   - 原有 QA 打回机制未被 LLM 模式破坏。

8. **Trace 可观测性已覆盖主要 LLM 诊断字段**
   - `ReportWriterAgent` Trace 的 `input_summary` 可看到：
     - `writer_mode_requested`
     - `llm_provider`
     - `llm_model`
     - `has_api_key`
   - `output_summary` 会写入 `writer_diagnostics`，包括：
     - `writer_mode_requested`
     - `writer_mode_used`
     - `llm_call_attempted`
     - `llm_call_success`
     - `llm_elapsed_time_ms`
     - `fallback_used`
     - `llm_fallback_reason`
     - `llm_error_type`
     - `llm_error_message`
     - `llm_response_preview`

9. **前端可显示 LLM 调用状态**
   - 运行区可显示：
     - LLM Provider
     - 模型
     - Base URL 是否配置
     - API Key 是否配置
     - LLM 测试状态
   - workflow 运行后可显示：
     - requested
     - used
     - fallback
     - llm_call
     - LLM 成功耗时或 fallback 原因
   - Trace Viewer 可展开查看 ReportWriterAgent 的 input/output summary、Schema 校验结果和耗时。

10. **测试和构建通过**
   - 后端 `pytest` 已通过。
   - 前端 `npm run build` 已通过。

## 当前风险

1. **`llm_schema_validation_success` 不是独立诊断字段**
   - 当前通过 Trace 的 `schema_validation_result=passed/failed` 表达 Schema 校验结果。
   - `writer_diagnostics` 中尚未单独记录 `llm_schema_validation_success`。
   - 这不影响实际校验，但不完全满足“诊断字段显式存在”的展示诉求。

2. **category 当前主要依赖 Prompt 约束**
   - 系统没有把非法中文 category 自动映射为合法枚举。
   - 这是有意保留的严格策略：非法输出会失败，不会静默修复。
   - 如果演示模型偶发输出中文 category，仍会触发 ReportWriterAgent Schema failed。

3. **缺失 category 时存在默认值**
   - LLM 分支构造 Claim 时使用 `claim.get("category", "recommendation")`。
   - 这属于最小兜底，不会修复非法 category。
   - 严格来说，这是一种“缺失字段默认归一化”，建议后续改为显式诊断或二次修复。

4. **LLM 稳定性依赖外部服务**
   - 仍可能出现超时、401/400、限流、模型响应慢、JSON 不合法等问题。
   - 当前系统能诊断和 fallback，但不能保证外部 LLM 每次成功。

5. **token_usage / model_name 未从真实 LLM 响应写回 Trace 字段**
   - Trace 表格中有 `model_name` 和 `token_usage` 列。
   - 当前 LLM 模型信息主要在 `output_summary.writer_diagnostics.llm_model` 中展示。
   - token usage 尚未解析 OpenAI-compatible usage 字段。

## 仍可能失败的场景

1. LLM 返回非 JSON 文本，触发非法 JSON fallback。
2. LLM 返回 JSON，但缺少 `claims` 数组。
3. LLM 返回 claim 缺少 `evidence_ids`。
4. LLM 返回 claim 的 `category` 不在合法枚举中。
5. LLM 返回空 `markdown_report`，QA 会认为报告为空或格式不合格。
6. LLM 返回的 evidence id 不存在于 Collector 生成的 Evidence 列表中。
7. API Key 失效、Endpoint 无权限、服务侧限流或网络超时。
8. 旧任务已有 `rework_count=3`，再次演示时会直接呈现 manual_review 语义，容易造成误解。

## 建议优化项

1. **补充显式诊断字段**
   - 在 `writer_diagnostics` 中增加：
     - `llm_schema_validation_success`
     - `llm_schema_validation_error`
   - 这样前端无需只依赖 Trace 的 `schema_validation_result`。

2. **增加 LLM 输出二次修复模式**
   - 第一次 LLM 输出不合规时，把 Pydantic 校验错误发回 LLM。
   - 要求它只修 JSON，不重写分析内容。
   - 修复后再次执行 Schema 校验。

3. **更严格处理缺失 category**
   - 将 `claim.get("category", "recommendation")` 改为：
     - 记录缺失 category
     - 或进入二次修复
   - 避免“缺失字段默认值”掩盖模型输出不完整。

4. **解析真实 token usage**
   - 从 OpenAI-compatible 响应中读取 `usage.total_tokens`。
   - 写入 `TraceRecord.token_usage` 或 `writer_diagnostics`。

5. **演示时建议新建任务**
   - 避免复用已失败多次、`rework_count=3` 的旧任务。
   - 新任务能更清楚展示 LLM 成功、QA 通过、Trace 耗时等结果。

## 测试结果

### Backend

命令：

```bash
cd backend
pytest
```

结果：

```text
19 passed
```

### Frontend

命令：

```bash
cd frontend
npm run build
```

结果：

```text
tsc && vite build 成功
```

## 验收结论

当前 LLM ReportWriter 已完成最小真实 LLM 接入验收：

- 能通过 `writer_mode=llm` 进入真实 LLM 分支。
- 能在成功时生成结构化 `ReportWriterOutput`。
- 能在失败时 fallback 到 mock，并保留诊断信息。
- 能将 claim 与 evidence_ids 绑定。
- 能通过 QA 继续进入 FinalReport。
- 前端能展示 LLM 是否成功、是否 fallback 和调用耗时。

当前主要缺口是诊断字段 `llm_schema_validation_success` 尚未显式写入 `writer_diagnostics`，以及缺失 category 时仍有默认值兜底。建议下一轮仅做诊断字段补齐和可选二次 JSON 修复，不建议扩大到真实爬虫、RAG 或多 Agent 大重构。
