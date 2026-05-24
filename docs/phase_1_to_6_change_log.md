# Phase 1-6 改动总览

本文档汇总 CIS 多 Agent 竞品分析系统 Demo 从 Phase 1 到 Phase 6 的主要工程改动、验证结果和后续风险。

## Phase 1：高优先级工程补强

### 目标

补齐多 Agent 工作流的结构化边界，让 FinalReport 从 DAG 终态变成真实 Agent 执行步骤，并补齐 QA 三类打回能力。

### 主要改动

1. 新增 `FinalReportAgent`
   - 文件：`backend/app/agents/final_report.py`
   - 有独立 `run()` 方法。
   - 输入 `FinalReportInput`。
   - 输出 `FinalReportOutput`。
   - 执行时生成 `TraceRecord`。
   - Runner 中流程变为：

```text
PlannerAgent
-> CollectorAgent
-> AnalystAgent
-> ReportWriterAgent
-> QaAgent
-> FinalReportAgent
```

2. 增加 Agent I/O Schema
   - 文件：`backend/app/schemas/agent_io.py`
   - 新增：
     - `PlannerInput / PlannerOutput`
     - `CollectorInput / CollectorOutput`
     - `AnalystInput / AnalystOutput`
     - `ReportWriterInput / ReportWriterOutput`
     - `QaInput / QaOutput`
     - `FinalReportInput / FinalReportOutput`

3. 补齐 QA 三类打回
   - Missing evidence -> `CollectorAgent`
   - Invalid extraction / contradiction -> `AnalystAgent`
   - Bad report format / claim missing evidence_ids -> `ReportWriterAgent`

4. 增加 demo_mode
   - `normal`
   - `qa_missing_evidence`
   - `qa_invalid_extraction`
   - `qa_bad_report`

5. 文档和编码
   - 增加 `.gitattributes`
   - README 增加 Windows 中文乱码说明
   - `.env.example` 开始用于本地配置模板

### 验证

- `pytest` 通过。
- `npm run build` 通过。
- 已生成 `docs/phase_1_acceptance_report.md`。

## Phase 2：答辩演示体验优化

### 目标

让前端更适合现场演示和评分，降低 App.tsx 集中度，并让任务、DAG、报告、证据、QA、Trace 之间可以清晰切换和联动。

### 主要改动

1. 前端组件拆分
   - `TaskForm.tsx`
   - `TaskList.tsx`
   - `DemoGuide.tsx`
   - `DagView.tsx`
   - `KnowledgeView.tsx`
   - `ReportView.tsx`
   - `EvidencePanel.tsx`
   - `QaPanel.tsx`
   - `TraceViewer.tsx`

2. 增加任务列表和任务切换
   - 展示：
     - `task_id`
     - 任务名称
     - competitors
     - region
     - industry
     - status
     - created_at
   - 点击任务后加载对应 DAG、Report、Evidence、QA、Trace。
   - 创建新任务后自动选中新任务。

3. 优化 DAG 展示
   - 展示 Agent 名称、状态、输入 Schema、输出 Schema、Trace 数量、耗时。
   - QA 失败时展示打回边。

4. 优化 Trace Viewer
   - 支持按 Agent 筛选。
   - 支持按 schema validation result 筛选。
   - 错误 Trace 高亮。
   - 点击 Trace 展开 input/output summary。

5. 优化 Report + Evidence 联动
   - 左侧展示 Markdown 报告。
   - JSON 报告可折叠。
   - 右侧展示 Claim 列表。
   - 点击 Claim 后 Evidence Panel 展示对应 Evidence。

6. 增加答辩演示指南
   - 推荐演示路径：
     - 创建示例任务
     - 运行 workflow
     - 查看 DAG
     - 查看竞品知识
     - 点击 Claim 查看 Evidence
     - 查看 Trace
     - 切换 QA 失败模式

### 验证

- `npm run build` 通过。
- 后端接口未破坏。

## Phase 3：auto_rework 自动返工流程

### 目标

让 QA 失败后可以选择自动返工，展示多 Agent 闭环能力。

### 主要改动

1. 增加 `auto_rework=true`
   - 支持：

```text
POST /api/tasks/{task_id}/run?demo_mode=qa_missing_evidence&auto_rework=true
POST /api/tasks/{task_id}/run?demo_mode=qa_invalid_extraction&auto_rework=true
POST /api/tasks/{task_id}/run?demo_mode=qa_bad_report&auto_rework=true
```

2. 三类自动返工路径
   - Missing evidence：
     - 第一次 QA route_to `CollectorAgent`
     - Collector 重新生成 Evidence
     - 再进入 Analyst / ReportWriter / QA
   - Invalid extraction：
     - 第一次 QA route_to `AnalystAgent`
     - Analyst 重新生成合法结构化知识
     - 再进入 ReportWriter / QA
   - Bad report format：
     - 第一次 QA route_to `ReportWriterAgent`
     - ReportWriter 重新生成合法报告
     - 再进入 QA

3. 增加 rework history
   - QA Panel 展示：
     - error_type
     - route_to
     - suggested_action
     - rework_count
     - final_status
     - rework_history

4. max_rework 控制
   - 最大返工次数 `max_rework=3`
   - 超过后进入 `manual_review`

### 验证

- `pytest` 通过。
- `npm run build` 通过。
- 每一轮返工都会生成 TraceRecord。

## Phase 4：最小真实 LLM ReportWriter

### 目标

只增强 `ReportWriterAgent`，让它支持 `mock / llm` 两种模式；没有 API Key 或 LLM 调用失败时必须 fallback 到 Mock。

### 主要改动

1. 新增 `LlmClient`
   - 文件：`backend/app/services/llm_client.py`
   - 支持环境变量：
     - `LLM_PROVIDER`
     - `LLM_API_KEY`
     - `LLM_BASE_URL`
     - `LLM_MODEL`
   - 使用 OpenAI-compatible Chat Completions。
   - 不把 API Key 写死到代码。
   - 所有异常捕获并写入 Trace / diagnostics。

2. ReportWriter 支持模式切换
   - 默认：

```text
writer_mode=mock
```

   - 可选：

```text
writer_mode=llm
```

3. fallback 行为
   - 没有 `LLM_API_KEY` -> fallback mock。
   - LLM 调用失败 -> fallback mock。
   - LLM 返回非法 JSON -> 记录失败 Trace，再 fallback mock。
   - LLM 返回 Claim 缺少 evidence_ids -> 不静默修复，交给 QA failed。

4. LLM 诊断增强
   - Trace / writer_diagnostics 记录：
     - `writer_mode_requested`
     - `writer_mode_used`
     - `llm_enabled`
     - `llm_provider`
     - `llm_model`
     - `llm_call_attempted`
     - `llm_call_success`
     - `llm_elapsed_time_ms`
     - `llm_error_type`
     - `llm_error_message`
     - `llm_response_preview`
     - `fallback_used`
     - `llm_fallback_reason`
     - `llm_schema_validation_success`
     - `llm_schema_validation_errors`
     - `llm_category_normalization_count`

5. LLM 状态接口
   - `GET /api/llm/status`
   - `POST /api/llm/test`

6. 前端展示
   - LLM 状态：
     - 未配置 API Key
     - 已配置，未测试
     - 测试成功
     - 测试失败
   - 运行后展示：
     - requested
     - used
     - fallback
     - llm_call
     - fallback 原因或成功耗时

7. Prompt 收紧
   - 要求每个 Claim 必须绑定 evidence_ids。
   - 要求输出 JSON。
   - 要求 `category` 只能使用：
     - `positioning`
     - `feature`
     - `pricing`
     - `persona`
     - `risk`
     - `recommendation`
   - 禁止中文 category。

### 验收与文档

- 已生成 `docs/llm_reportwriter_acceptance_report.md`。
- `pytest` 通过。
- `npm run build` 通过。

## Phase 5：最小真实 Web Collector

### 目标

让 `CollectorAgent` 支持 `mock / web` 两种模式。Web 模式只做公开搜索结果采集，不做复杂爬虫。

### 主要改动

1. 增加 `collector_mode`

```text
POST /api/tasks/{task_id}/run?collector_mode=mock
POST /api/tasks/{task_id}/run?collector_mode=web
```

支持与 LLM Writer 组合：

```text
collector_mode=web&writer_mode=llm
collector_mode=mock&writer_mode=llm
```

2. 新增 `WebSearchClient`
   - 文件：`backend/app/services/web_search_client.py`
   - 支持环境变量：
     - `SEARCH_PROVIDER`
     - `SEARCH_API_KEY`
     - `SEARCH_BASE_URL`
     - `SEARCH_TIMEOUT`
     - `SEARCH_MAX_RESULTS`

3. 优先支持 Tavily

```env
SEARCH_PROVIDER=tavily
SEARCH_API_KEY=
SEARCH_BASE_URL=https://api.tavily.com
SEARCH_TIMEOUT=15
SEARCH_MAX_RESULTS=5
```

调用方式：

```text
POST {SEARCH_BASE_URL}/search
```

请求体：

```json
{
  "query": "飞书 B2B SaaS 功能 定价 官网",
  "search_depth": "basic",
  "max_results": 5,
  "include_answer": false,
  "include_raw_content": false
}
```

4. Tavily 结果转 Evidence
   - 使用：
     - `title`
     - `url`
     - `content`
     - `score`
   - 不请求 raw_content。
   - 不复制网页全文。
   - `source_type=public_web`

5. Search 状态接口
   - `GET /api/search/status`
   - 返回：
     - search_provider
     - api_key_configured
     - base_url_configured
     - timeout
     - max_results
     - enabled
   - 不返回 API Key。

6. Search 测试接口
   - `POST /api/search/test`
   - 请求：

```json
{
  "query": "飞书 B2B SaaS 功能 定价 官网"
}
```

   - 返回：
     - success
     - provider
     - query
     - result_count
     - results_preview，最多 3 条
     - error_type
     - error_message

7. fallback 行为
   - 未配置 API Key
   - 401
   - timeout
   - 空结果
   - 搜索 API 异常

都会 fallback 到 Mock Evidence，并在 Trace 中记录 `fallback_reason`。

8. 前端展示
   - 增加 `Mock Collector / Web Collector` 下拉框。
   - 增加搜索状态：
     - 未配置
     - 已配置
     - 测试成功
     - 测试失败
   - 增加按钮：
     - `测试搜索连接`

### 验证

- `pytest` 通过。
- `npm run build` 通过。

## Phase 6：Evidence 质量增强

### 目标

提升 Web Collector 采集结果的可信度、可读性和可追溯性。

### 主要改动

1. Evidence 去重
   - normalize URL 后去重。
   - 去掉末尾 `/`。
   - 去掉 tracking 参数：
     - `utm_source`
     - `utm_medium`
     - `utm_campaign`
     - `utm_term`
     - `utm_content`
     - `spm`
     - `fbclid`

2. Evidence Schema 增加：
   - `source_domain`
   - `source_quality`

3. source_quality
   - `official`
   - `documentation`
   - `media`
   - `review`
   - `unknown`
   - `low_quality`

4. confidence 计算

| source_quality | confidence |
|---|---:|
| official | 0.9 |
| documentation | 0.85 |
| media | 0.75 |
| review | 0.65 |
| unknown | 0.6 |
| low_quality | 0.4 |

5. QA soft check
   - Claim 绑定的 Evidence 全部低于 0.5 -> soft suggestion。
   - Evidence 缺少 source_domain -> soft suggestion。
   - Evidence 数量少于 3 -> soft suggestion。
   - Evidence 为空仍然 hard fail。

6. Trace 增强
   - CollectorAgent：
     - raw_evidence_count
     - deduplicated_evidence_count
     - duplicate_removed_count
     - source_quality_summary
     - low_confidence_count
   - QaAgent：
     - evidence_quality_checked
     - low_confidence_claim_count
     - soft_suggestion_count

7. 前端 Evidence Panel
   - 展示：
     - source_domain
     - source_quality
     - confidence
   - 可信度标签：
     - 高可信
     - 中可信
     - 低可信
   - 点击 Claim 后 Evidence 按 confidence 从高到低排序。

### 验证

- `pytest` 通过。
- `npm run build` 通过。
- 详细文档见：
  - `docs/phase_6_evidence_quality_enhancement.md`

## 当前总体能力

系统目前具备：

- 结构化 Agent I/O Schema。
- Mock 多 Agent 工作流。
- 独立 FinalReportAgent。
- QA 三类打回。
- 可选自动返工。
- 可选 LLM ReportWriter。
- 可选 Tavily Web Collector。
- Evidence 质量元数据。
- Trace 可观测。
- 前端任务、DAG、报告、Evidence、QA、Trace 联动展示。

## 当前总体限制

1. PlannerAgent、AnalystAgent、QaAgent 仍主要是 Mock / 规则逻辑。
2. Web Collector 只采集搜索结果摘要，不抓网页正文。
3. 没有接 RAG。
4. 没有接向量数据库。
5. LLM ReportWriter 会受到 Mock Analyst 输出影响，报告内容可能被 Mock knowledge 带偏。
6. source_quality 和 confidence 仍是轻量规则，不是完整来源信誉模型。

## 后续建议

1. 优先增强 AnalystAgent，让它能基于 Evidence snippet 生成更贴近真实来源的结构化知识。
2. 将 source_quality 规则抽成独立 service，便于维护和扩展。
3. 给 ReportWriter Prompt 增加约束：Web Evidence 与 Mock Knowledge 冲突时优先 Evidence。
4. 后续接 RAG 时，将 Evidence 的 source_domain、source_quality、confidence 作为 metadata。
5. 保留当前 Mock 模式作为现场演示稳定 fallback。
