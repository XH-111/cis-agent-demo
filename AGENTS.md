# AGENTS.zh-CN.md

## 项目目标

构建一个用于 CIS AI 挑战赛的多 Agent 竞品分析系统。

系统必须实现端到端工作流：

```text
Planner -> Collector -> Analyst -> Report Writer -> QA -> Final Report
```

QA 可以把未通过质检的任务打回 Collector、Analyst 或 Report Writer。

## 工程原则

- Agent 职责必须清晰且相互隔离。
- 每个 Agent 的输入和输出都必须使用结构化 Schema。
- 最终报告中的任何结论都必须包含 `evidence_ids`。
- 每个任务必须携带全局 `trace_id`。
- 每次 Agent 执行都必须通过 Trace 记录可观测。
- 优先沿用项目已有模式，避免随意新增抽象。
- 改动范围要小，并且可以测试。

## Agent 定义

在本项目中，Agent 不只是 DAG 节点。

一个 Agent 由以下部分组成：

- 角色和职责
- Prompt 模板
- 工具权限
- 输入 Schema
- 输出 Schema
- Trace 日志
- 重试和错误处理策略

在 LangGraph 中，一个 Agent 可以实现为一个节点，也可以实现为一个子图。

## 必需 Agent

### PlannerAgent

- 解析用户意图。
- 选择产品类型和行业 Schema。
- 生成任务计划和 DAG 配置。

### CollectorAgent

- 采集公开网页、文档、定价、评价、问卷或访谈证据。
- 保存原始来源材料。
- 生成 `Evidence` 记录。
- 不允许输出没有证据支撑的结论。

### AnalystAgent

- 将 Evidence 转换为结构化竞品知识。
- 所有抽取字段都必须绑定 `evidence_ids`。
- 归一化同义词和功能粒度。

### ReportWriterAgent

- 生成 Markdown 报告和前端可渲染 JSON 报告。
- 每条关键结论都必须包含 `claim_id` 和 `evidence_ids`。

### QaAgent

- 校验 Schema、证据覆盖率、事实支撑、冲突和报告格式。
- 区分硬错误和软建议。
- 生成结构化打回指令。
- 最多打回 3 次，超过后标记为人工复核。

## Schema 规则

核心 Schema 必须包括：

- ProductProfile
- FeatureTree
- PricingModel
- UserPersona
- Evidence
- Claim
- AgentMessage
- QaResult
- TraceRecord

校验规则：

- `Claim.evidence_ids` 必填且不能为空。
- Evidence 必须包含来源类型、URL 或本地引用、采集时间、片段和可信度。
- Agent 消息必须包含 `trace_id`、`task_id`、`from_agent`、`to_agent`、`message_type` 和 Schema 名称。
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
- Token 消耗，如果可获取
- 执行耗时
- 重试次数
- 失败时的错误信息

## QA 与反馈闭环

- QA 通过 -> 进入最终报告。
- 缺少证据 -> 打回 CollectorAgent。
- 抽取错误或结论冲突 -> 打回 AnalystAgent。
- 报告格式错误 -> 打回 ReportWriterAgent。
- 最大打回次数：3 次。
- 打回指令必须包含具体结论、错误类型、原因和建议动作。

## 产品要求

前端应包含：

- 任务创建页
- DAG 执行页
- 竞品知识页
- 报告页
- 证据/来源面板
- QA 结果面板
- Trace 查看器

报告页必须支持点击结论查看对应证据。

## 亮点功能

MVP 完成后实现以下功能：

1. 证据图谱：
   - 展示 Claim、Evidence、Competitor、Feature 之间的关系。
   - 支持结论级 Trace 回放。

2. 自适应 Schema Router：
   - 根据产品类型和行业选择 Schema。
   - 将未知但有价值的分析维度写入 `custom_dimensions`。

## 合规要求

- 在适用场景下遵守 robots.txt 和网站服务条款。
- 不采集私人或敏感个人数据。
- 对访谈和问卷内容做脱敏处理。
- 保留公开来源引用。
- 避免在最终报告中复制长篇受版权保护文本。

## 测试要求

需要补充聚焦测试：

- Schema 校验
- Claim 必须包含证据
- Agent 消息协议
- QA 路由逻辑
- 最大打回次数限制
- Trace 记录创建

在完成有意义的代码改动前，应运行相关测试并报告结果。
