# Phase 8 LangGraph Workflow Engine

## 目标

本阶段引入 LangGraph 作为新的 workflow engine，用 `StateGraph` 显式表达 Agent DAG、QA conditional routing 和 `auto_rework` 返工循环。

本阶段只改编排层，不重写 Agent 业务逻辑。现有 `PlannerAgent`、`CollectorAgent`、`AnalystAgent`、`ReportWriterAgent`、`QaAgent`、`FinalReportAgent` 的 `run()` 方法仍然是唯一业务实现。

## 新增文件

- `backend/app/schemas/workflow_state.py`
- `backend/app/agents/langgraph_runner.py`
- `backend/app/agents/runner_factory.py`

## WorkflowState

`WorkflowState` 使用 `TypedDict` 定义，保存 workflow 上下文和各 Agent 输出，包括：

- `task_id`
- `task`
- `workflow_engine_requested`
- `workflow_engine_used`
- `demo_mode`
- `collector_mode`
- `analyst_mode`
- `writer_mode`
- `content_mode`
- `auto_rework`
- `rework_count`
- `max_rework`
- `planner_output`
- `collector_output`
- `analyst_output`
- `report_writer_output`
- `qa_output`
- `final_report_output`
- `evidence`
- `report`
- `qa_result`
- `route_to`
- `final_status`
- `node_sequence`
- `conditional_routes_taken`

## LangGraph DAG

当前 LangGraph 主链路：

```text
planner -> collector -> analyst -> report_writer -> qa -> final_report
```

每个 node 只做四件事：

1. 从 `WorkflowState` 读取输入。
2. 构造现有 Agent Input Schema。
3. 调用现有 `Agent.run()`。
4. 将 Agent Output 写回 `WorkflowState`。

## QA Conditional Routing

`qa` 节点后使用 conditional edge：

```text
QA passed -> final_report
route_to = CollectorAgent -> collector
route_to = AnalystAgent -> analyst
route_to = ReportWriterAgent -> report_writer
manual_review / unknown route -> final_report
```

当 `auto_rework=false` 时，QA failed 不自动返工，直接进入最终状态处理。

当 `auto_rework=true` 时，LangGraph 根据 `QaResult.route_to` 回到对应节点，并保证后续路径完整：

- `qa -> collector -> analyst -> report_writer -> qa`
- `qa -> analyst -> report_writer -> qa`
- `qa -> report_writer -> qa`

## 防止死循环

系统沿用 `max_rework=3`。

当 QA 返回 `manual_review`，或 `rework_count >= max_rework` 时，LangGraph 不再继续返工，而是进入最终状态处理，避免无限循环。

## Runner 维护边界

- `Custom Runner` 保留为 legacy stable fallback，默认仍可通过 `workflow_engine=custom` 使用。
- `LangGraph Runner` 是后续扩展主线。
- 后续新增节点，例如 PageFetcher、Chunker、Indexer、Retriever、SWOTAgent、QuestionnaireAgent，只接入 LangGraph Runner。
- 不再把未来复杂节点同步维护到 Custom Runner，避免双状态机长期分叉。

从 Phase 9 开始，新增能力必须优先开发在 LangGraph workflow path 上。除非明确用于紧急 fallback，否则不要扩展 `CustomWorkflowRunner`。

## API 切换方式

```text
POST /api/tasks/{task_id}/run?workflow_engine=custom
POST /api/tasks/{task_id}/run?workflow_engine=langgraph
```

也支持环境变量：

```text
WORKFLOW_ENGINE=custom
WORKFLOW_ENGINE=langgraph
```

优先级：

```text
API query 参数 > WORKFLOW_ENGINE 环境变量 > 默认 custom
```

## 前端变化

运行设置区域新增：

- `Custom Runner`
- `LangGraph Runner`

运行后轻量展示：

- `workflow_engine_requested`
- `workflow_engine_used`
- `rework_count`
- `final_status`
- `conditional_routes_taken`

## 测试覆盖

新增测试覆盖：

- custom runner 正常流程不受影响
- LangGraph 正常流程通过
- QA passed 进入 FinalReportAgent
- missing evidence 路由到 CollectorAgent
- invalid extraction 路由到 AnalystAgent
- bad report format 路由到 ReportWriterAgent
- max_rework 后进入 manual_review，不死循环
- LangGraph 每个 Agent node 仍生成 TraceRecord
- LangGraph 不破坏 collector_mode、analyst_mode、writer_mode、demo_mode、auto_rework
- 竞品覆盖检查在 LangGraph 模式下仍然生效
- workflow_engine 参数优先级正确

## 验证结果

- 后端：`pytest` 通过，56 passed
- 前端：`npm run build` 通过
