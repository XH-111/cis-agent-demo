# Phase 10: Run ID / Report Versioning

## 目标

Phase 10 将 Phase 9.1 的 cleanup 过渡策略升级为产品级 `run_id` 隔离。每次 workflow 执行都会创建独立 `TaskRun`，Evidence、Report、QA、Trace 和 WorkflowEngine summary 都绑定到该 run，支持历史运行查看、报告版本回放和 Trace 回放。

## Task 与 TaskRun

- `Task`：用户创建的分析任务，例如“企业协作工具竞品分析”。
- `TaskRun`：该任务的一次具体 workflow 执行。

同一个 Task 可以有多个 TaskRun。前端默认展示 latest run，也可以通过 Run History 切换历史 run。

## 数据隔离

新增数据绑定规则：

- `Evidence.run_id`
- `Report.run_id`
- `QaResult.run_id`
- `TraceRecord.run_id`
- `WorkflowEngine Trace.output_summary.run_id`

旧数据没有 `run_id` 时仍作为 legacy 数据兼容；新 run 不再删除旧 Evidence / Report / QA，而是通过 run_id 隔离。

## API

新增接口：

- `GET /api/tasks/{task_id}/runs`
- `GET /api/tasks/{task_id}/runs/latest`
- `GET /api/tasks/{task_id}/runs/{run_id}`
- `GET /api/tasks/{task_id}/runs/{run_id}/evidence`
- `GET /api/tasks/{task_id}/runs/{run_id}/report`
- `GET /api/tasks/{task_id}/runs/{run_id}/qa`
- `GET /api/tasks/{task_id}/runs/{run_id}/traces`

旧接口仍保留，并默认返回 latest run：

- `GET /api/tasks/{task_id}/evidence`
- `GET /api/tasks/{task_id}/report`
- `GET /api/tasks/{task_id}/qa`
- `GET /api/tasks/{task_id}/traces`

## LangGraph 集成

`WorkflowState` 增加：

- `run_id`
- `task_run`
- `run_status`

LangGraph Runner 在运行开始时创建 `TaskRun`，并通过 `TraceService` 的 run context 自动给各 Agent Trace 补齐 `run_id`。各节点保存 Evidence、QA、Report 时也传入当前 `run_id`。

## 前端

前端增加 Run History 区域，展示：

- run_id 短 ID
- started_at
- workflow_engine
- collector_mode
- analyst_mode
- writer_mode
- final_status
- elapsed_time_ms

用户点击历史 run 后，Evidence、Report、QA、Trace 和 workflow summary 都切换到对应 run。

## 测试覆盖

新增或更新测试覆盖：

- 每次运行都会创建新的 TaskRun。
- 同一个 Task 多次运行产生不同 run_id。
- Evidence / Report / QA / Trace 绑定 run_id。
- latest report 返回最新 run。
- 指定 run_id 查询返回对应 run 的数据。
- 不同 run 的 Evidence 不混用。
- `workflow_engine=langgraph` 下 run_id 贯穿 WorkflowState。
- `workflow_engine=custom` 旧主链路仍可运行。
