# Phase 1 高优先级工程补强验收报告

## 验收范围

本次验收只检查第一轮高优先级工程补强是否真实落地，不继续开发新功能。

验收项包括：

- FinalReportAgent
- Agent Input / Output Schema
- QA 三类打回 Demo
- 测试与前端构建
- README 与编码风险处理

## 已完成项

### 1. FinalReportAgent

已完成。

检查结果：

- `backend/app/agents/final_report.py` 已存在。
- `FinalReportAgent` 已定义独立 `run()` 方法。
- `run()` 输入为 `FinalReportInput`。
- `run()` 输出为 `FinalReportOutput`。
- `FinalReportAgent` 内部通过 `run_with_trace()` 执行，因此会生成 `TraceRecord`。
- `backend/app/agents/runner.py` 已实例化并调用 `FinalReportAgent`。
- 正常 workflow 中，`QaAgent` 通过后会执行：

```text
FinalReportAgent.run(FinalReportInput(...))
```

- `FinalReportAgent` 会整合：
  - ReportWriter 输出的 `Report`
  - QA 结果
  - Evidence summary
- 最终报告仍通过原有 `ReportService.save_report()` 保存，不破坏 `/api/tasks/{task_id}/report`。

结论：

```text
PlannerAgent -> CollectorAgent -> AnalystAgent -> ReportWriterAgent -> QaAgent -> FinalReportAgent
```

这条链路已经真实存在。

### 2. Agent Input / Output Schema

已完成。

`backend/app/schemas/agent_io.py` 中已存在：

- `PlannerInput`
- `PlannerOutput`
- `CollectorInput`
- `CollectorOutput`
- `AnalystInput`
- `AnalystOutput`
- `ReportWriterInput`
- `ReportWriterOutput`
- `QaInput`
- `QaOutput`
- `FinalReportInput`
- `FinalReportOutput`
- `DemoMode`

每个 Agent 的 `run()` 方法已改为使用对应 Schema：

- `PlannerAgent.run(input_data: PlannerInput) -> PlannerOutput`
- `CollectorAgent.run(input_data: CollectorInput) -> CollectorOutput`
- `AnalystAgent.run(input_data: AnalystInput) -> AnalystOutput`
- `ReportWriterAgent.run(input_data: ReportWriterInput) -> ReportWriterOutput`
- `QaAgent.run(input_data: QaInput) -> QaOutput`
- `FinalReportAgent.run(input_data: FinalReportInput) -> FinalReportOutput`

测试中也直接覆盖了这些 Schema 类型。

### 3. QA 三类打回

已完成。

后端接口已支持：

```text
POST /api/tasks/{task_id}/run?demo_mode=normal
POST /api/tasks/{task_id}/run?demo_mode=qa_missing_evidence
POST /api/tasks/{task_id}/run?demo_mode=qa_invalid_extraction
POST /api/tasks/{task_id}/run?demo_mode=qa_bad_report
```

三类打回真实逻辑如下：

#### Missing evidence -> CollectorAgent

触发方式：

```text
demo_mode=qa_missing_evidence
```

验收结果：

- QA 会检测到 Evidence 为空。
- `route_to = CollectorAgent`
- `error_type = missing_evidence`
- `failed_schema = Evidence`

#### Invalid extraction / contradiction -> AnalystAgent

触发方式：

```text
demo_mode=qa_invalid_extraction
```

验收结果：

- Analyst 输出中会模拟 `ProductProfile` 关键字段为空。
- QA 会识别为抽取错误或结构化结果冲突。
- `route_to = AnalystAgent`
- `error_type = invalid_extraction`
- `failed_schema = ProductProfile`

#### Bad report format / claim missing evidence_ids -> ReportWriterAgent

触发方式：

```text
demo_mode=qa_bad_report
```

验收结果：

- ReportWriter 会模拟 Markdown 报告缺少一级标题。
- QA 会识别报告格式错误。
- `route_to = ReportWriterAgent`
- `error_type = bad_report_format`
- `failed_schema = Report.markdown`

另外，`ReportWriterOutput.draft_report` 中 Claim 缺少 `evidence_ids` 的场景也仍然会被 QA 路由到 `ReportWriterAgent`。

### 4. 前端 demo_mode 选择与 QA 展示

已完成。

前端已支持在“运行 Demo 工作流”旁选择：

- 正常流程
- QA 失败：缺少证据
- QA 失败：抽取冲突
- QA 失败：报告格式错误

前端 API client 已把选择值传给：

```text
/api/tasks/{task_id}/run?demo_mode=...
```

QA Panel 已展示：

- `error_type`
- `failed_claim`
- `failed_schema`
- `reason`
- `route_to`
- `suggested_action`
- `rework_count`
- `final_status`

同时，Trace 表头已明确为 `Schema 校验`，QA 区域已明确为 `业务质检结果`，避免用户误解“Trace 通过但 QA 失败”的含义。

### 5. 测试覆盖

已完成。

`backend/tests/test_schema_and_workflow.py` 已覆盖：

- Claim 缺少 `evidence_ids` 校验失败
- Evidence 缺少 `url/local_ref` 校验失败
- AgentMessage 缺少 `trace_id/task_id` 校验失败
- 每个 Agent 使用对应 Input / Output Schema
- Missing evidence 路由到 `CollectorAgent`
- Invalid extraction 路由到 `AnalystAgent`
- Bad report format 路由到 `ReportWriterAgent`
- `max_rework >= 3` 后进入 `manual_review`
- `FinalReportAgent` 执行后生成 TraceRecord
- 正常 workflow 仍能通过，并产生完整 Agent Trace

### 6. 文档和编码

已完成基础处理。

检查结果：

- README 已更新为 Phase 1 后的架构和运行说明。
- README 已包含 `demo_mode` API 说明。
- README 已包含 Windows PowerShell 中文乱码说明。
- `.gitattributes` 已存在，内容包括：

```text
*.md text eol=lf
*.py text eol=lf
*.ts text eol=lf
*.tsx text eol=lf
*.json text eol=lf
```

未使用 `working-tree-encoding`，符合要求。

## 未完成项

### 1. DAG 状态仍不是实时逐节点执行态

虽然 FinalReportAgent 已真实执行并记录 Trace，但前端 DAG 仍是任务结果态展示，不是运行过程中的实时节点流转。

这不影响 Phase 1 要求，但如果用于更强现场演示，后续可以通过轮询或事件流展示逐节点 running/completed 状态。

### 2. QA 打回后没有自动多轮修复 Collector / Analyst 场景

当前三类打回 Demo 已能 route 到对应 Agent，但 `qa_missing_evidence` 和 `qa_invalid_extraction` 模式不会继续自动返工并修复通过。

这符合本轮“补齐三类 QA 路由”的要求，但还不是完整多轮自愈流程。

### 3. 前端组件仍集中在 `App.tsx`

本轮没有做前端组件拆分。功能可用，但后续维护性一般。

## 有风险项

### 1. PowerShell 读取部分中文源码字符串仍可能显示乱码

验收时通过 `Get-Content` 查看部分 Python 文件，中文字符串在 PowerShell 输出中出现 mojibake。当前代码可以通过 pytest，说明语法和运行不受影响，但在 Windows 控制台直接查看源码时仍可能影响观感。

当前缓解措施：

- README 已增加 Windows PowerShell 中文乱码说明。
- `.gitattributes` 已统一文本文件 LF 换行。
- GitHub 页面和 VS Code 通常能正确显示 UTF-8 文件。

建议后续使用 VS Code 或脚本统一确认所有中文源码与 Markdown 均为 UTF-8。

### 2. `FinalReportAgent.name = "FinalReport"` 而不是 `"FinalReportAgent"`

当前 Trace 中 agent name 使用 `FinalReport`，这是为了匹配已有 DAG 节点和 `AgentName` 枚举中的终态节点语义。

风险：

- 从代码类名看叫 `FinalReportAgent`
- 从 Trace 和 DAG 看叫 `FinalReport`

这不影响功能，但命名上有轻微认知成本。后续可统一为 `FinalReportAgent`，同时更新 DAG 节点和前端显示。

### 3. Pydantic datetime 与 protected namespace warnings

pytest 通过，但存在 warnings：

- `datetime.utcnow()` deprecation warning
- `model_name` 与 Pydantic protected namespace 警告

当前不影响 Demo 运行，但后续可清理。

## 建议下一阶段修改项

### 高优先级

1. 统一源码和文档 UTF-8 显示

确保 README、docs、Python 中的中文在 VS Code、GitHub、PowerShell UTF-8 模式下都能稳定显示。

2. 统一 FinalReport 命名

考虑将 DAG 节点、AgentName、Trace 中的 `FinalReport` 统一为 `FinalReportAgent`，或在前端显示层明确映射。

3. 增加 QA 打回后的可选自动返工流程

当前三类路由已存在，下一步可以让：

- Missing evidence -> CollectorAgent -> QA retry
- Invalid extraction -> AnalystAgent -> QA retry
- Bad report format -> ReportWriterAgent -> QA retry

形成更完整闭环。

### 中优先级

1. 拆分前端组件

把 `App.tsx` 拆为：

- `TaskForm`
- `DemoGuide`
- `DagView`
- `KnowledgeView`
- `ReportView`
- `EvidencePanel`
- `QaPanel`
- `TraceViewer`

2. 增加任务列表与任务切换

让多个任务的 Task、DAG、Report、Evidence、Trace 对应关系更清楚。

3. 增强 Trace 查看器

增加输入/输出 JSON 展开、错误 Trace 高亮、Claim/Evidence 关联跳转。

### 低优先级

1. 增加前端 lint / format

当前只有 `npm run build`，后续可增加 ESLint 和 Prettier。

2. 增加前端 E2E 冒烟测试

建议用 Playwright 覆盖：

- 页面打开
- 使用示例任务
- 创建任务
- 运行正常 workflow
- 运行三类 QA demo mode

3. 清理 pytest warnings

替换 `datetime.utcnow()`，并处理 `model_name` protected namespace warning。

## 测试结果

### 后端 pytest

命令：

```bash
cd backend
pytest
```

结果：

```text
10 passed
```

说明：

- FinalReportAgent 测试通过。
- Agent I/O Schema 测试通过。
- QA 三类路由测试通过。
- 正常 workflow 测试通过。

### 前端构建

命令：

```bash
cd frontend
npm.cmd run build
```

结果：

```text
✓ built in 1.39s
```

说明：

- TypeScript 编译通过。
- Vite 生产构建通过。

## 总体验收结论

Phase 1 高优先级工程补强已经真实完成，不只是文档描述。

验收结论：

- FinalReportAgent 已真实存在并接入 workflow。
- Agent Input / Output Schema 已真实存在，并被 Agent `run()` 使用。
- QA 三类打回已真实可演示。
- 前端已支持选择不同 `demo_mode`。
- QA Panel 已展示关键返工字段。
- pytest 和前端构建均通过。
- README 和 `.gitattributes` 已完成基础编码风险处理。

当前剩余问题主要是演示细节和工程打磨，不影响 Phase 1 验收通过。
