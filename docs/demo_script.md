# CIS 多 Agent 竞品分析系统现场演示脚本

本文档用于现场答辩演示。建议演示前确认：

- 后端已启动：`http://127.0.0.1:8000`
- 前端已启动：`http://127.0.0.1:5173`
- 默认演示可使用 `Mock Collector + Mock ReportWriter`
- 如需真实能力展示，确认：
  - LLM 状态已配置并测试成功
  - Search 状态已配置并测试成功

## 一、3 分钟演示脚本

### 演示目标

用最短时间说明系统已经具备：

- 多 Agent 协作
- Schema 结构化输出
- Evidence 绑定
- QA 打回
- Trace 可观测
- 可选真实 Web Collector 和 LLM ReportWriter

### 0:00 - 0:30 系统定位

页面操作：

1. 打开前端首页。
2. 指向页面标题和顶部任务创建区。

讲解：

> 这是一个面向 CIS AI 挑战赛的多 Agent 竞品分析 Demo。它不是单次 prompt 生成报告，而是把竞品分析拆成 Planner、Collector、Analyst、ReportWriter、QA 和 FinalReport 多个结构化 Agent。系统重点展示 Schema 校验、Evidence 绑定、QA 打回闭环和 Trace 可观测。

### 0:30 - 1:10 创建任务并运行正常 workflow

页面操作：

1. 在“创建分析任务”卡片点击一个示例任务，例如“企业协作工具”。
2. 点击“创建任务”。
3. 运行区选择：
   - 正常流程
   - Mock Collector
   - Mock ReportWriter
4. 点击“运行 Demo 工作流”。

讲解：

> 我先用稳定的 Mock 模式跑完整链路。Mock 模式用于现场演示兜底，保证系统流程稳定。可以看到任务创建后，系统依次执行 Planner、Collector、Analyst、ReportWriter、QA 和 FinalReport。

### 1:10 - 1:50 展示 DAG、报告和 Evidence

页面操作：

1. 看 “DAG 执行状态”。
2. 滚动到“分析报告”。
3. 点击右侧 Claim 列表中的一个 Claim。
4. 查看 Evidence Panel。

讲解：

> DAG 中每个节点都有执行状态、输入输出 Schema、Trace 数量和耗时。报告里的每个 Claim 都必须绑定 evidence_ids，点击 Claim 后右侧会展示对应 Evidence。Evidence 包含来源、摘要、置信度和采集时间，避免报告结论无法追溯。

### 1:50 - 2:30 展示 Trace 和 QA

页面操作：

1. 滚动到 QA Panel。
2. 滚动到 Trace Viewer。
3. 用 Agent 下拉筛选 `ReportWriterAgent` 或 `CollectorAgent`。
4. 点击 Trace 展开 input_summary / output_summary。

讲解：

> QA 会检查 Schema、Evidence 覆盖和报告格式。Trace Viewer 记录每个 Agent 的输入摘要、输出摘要、Schema 校验结果、耗时、重试次数和错误信息。后续把 Mock Agent 替换成真实 LLM 或 LangGraph 节点时，Trace 仍然能保留可观测性。

### 2:30 - 3:00 展示真实能力入口

页面操作：

1. 指向 Collector 下拉框。
2. 指向 ReportWriter 下拉框。
3. 指向“测试搜索连接”和“测试 LLM 连接”按钮。

讲解：

> 当前系统还支持可选真实能力：Web Collector 可以通过 Tavily 搜公开网页结果，LLM ReportWriter 可以调用 OpenAI-compatible 模型生成报告。即使真实 API 失败，系统也会 fallback 到 Mock，保证演示和业务流程不中断。

## 二、5 分钟演示脚本

### 演示目标

比 3 分钟版本多展示：

- Web Collector + LLM ReportWriter
- QA 失败和自动返工
- Evidence 质量评分
- fallback 机制

### 0:00 - 0:40 系统介绍

页面操作：

1. 打开首页。
2. 指向 DemoGuide。

讲解：

> 这个系统解决的是竞品分析中常见的三个问题：第一，普通 LLM 报告缺少结构化过程；第二，结论缺少证据绑定；第三，生成失败或质量不合格时缺少可追踪的返工闭环。这里把流程拆成多 Agent，并且所有 Agent 输入输出都通过 Pydantic Schema 管理。

### 0:40 - 1:30 正常 workflow

页面操作：

1. 选择示例任务。
2. 创建任务。
3. 选择：
   - 正常流程
   - Mock Collector
   - Mock ReportWriter
4. 点击“运行 Demo 工作流”。

讲解：

> 我先跑稳定的正常 workflow。默认使用 Mock 模式，是为了保证答辩现场不依赖外部网络和模型状态。可以看到 DAG 全部节点完成，QA 通过，FinalReport 生成。

### 1:30 - 2:20 Web Collector + LLM ReportWriter

页面操作：

1. 点击“测试搜索连接”。
2. 点击“测试 LLM 连接”。
3. 运行区选择：
   - 正常流程
   - Web Collector
   - LLM ReportWriter
4. 点击“运行 Demo 工作流”。
5. 查看顶部状态区和 DAG 耗时。

讲解：

> 这里切换到真实 Web Collector 和 LLM ReportWriter。Web Collector 只调用公开搜索 API，不抓网页正文，不请求 raw content，不绕过 robots.txt。LLM ReportWriter 只负责基于结构化知识和 Evidence 写报告。如果外部 API 超时或鉴权失败，系统会自动 fallback 到 Mock。

### 2:20 - 3:10 Evidence 质量评分

页面操作：

1. 在报告右侧点击一个 Claim。
2. 查看 Evidence Panel。
3. 指向 `source_domain`、`source_quality`、`confidence`。

讲解：

> Evidence 现在不仅有 URL 和 snippet，还会记录 source_domain 和 source_quality。系统会根据来源类型给出 confidence，例如官网和文档更高，媒体和评测次之，低质量来源会降低分数。点击 Claim 时，证据会按 confidence 从高到低展示。

### 3:10 - 4:00 QA 失败和自动返工

页面操作：

1. 在任务运行区选择 demo_mode：
   - “QA 失败：缺少证据”或“QA 失败：报告格式错误”
2. 勾选 `auto_rework=true`。
3. 点击“运行 Demo 工作流”。
4. 查看 QA Panel 的 rework history。

讲解：

> 这里展示 QA 打回机制。比如缺少 Evidence 时，QA 会 route_to CollectorAgent；报告格式错误时，会 route_to ReportWriterAgent。勾选 auto_rework 后，系统会自动执行对应 Agent 返工，再次进入 QA。最大返工次数是 3，超过后进入人工复核。

### 4:00 - 4:40 Trace 可观测

页面操作：

1. 滚动到 Trace Viewer。
2. 按 Agent 筛选 `CollectorAgent` 或 `ReportWriterAgent`。
3. 点击展开 Trace。

讲解：

> Trace 是这个系统的可解释层。比如 CollectorAgent Trace 中能看到 collector_mode、是否 fallback、raw_evidence_count、deduplicated_evidence_count、source_quality_summary。ReportWriterAgent Trace 中能看到 writer_mode、LLM 是否调用成功、耗时、fallback 原因和 schema validation 结果。

### 4:40 - 5:00 总结

页面操作：

1. 回到 DAG 或报告区域。

讲解：

> 当前版本已经具备从任务创建、多 Agent 执行、证据采集、报告生成、QA 校验、自动返工到 Trace 回放的完整闭环。后续可以把 Mock Analyst 替换成真实 Evidence-based Analyst，或者接入 LangGraph、RAG 和向量数据库，但核心工程契约已经搭好。

## 三、正常 Workflow 演示步骤

### 页面点击顺序

1. 在“创建分析任务”选择示例任务。
2. 点击“创建任务”。
3. 运行区选择：
   - `正常流程`
   - `Mock Collector`
   - `Mock ReportWriter`
4. 不勾选 `auto_rework=true`。
5. 点击“运行 Demo 工作流”。
6. 查看：
   - DAG 执行状态
   - 竞品知识
   - 分析报告
   - Evidence Panel
   - QA Panel
   - Trace Viewer

### 讲解要点

> 正常 workflow 用于展示完整链路。Mock 模式不是最终目标，而是演示稳定性保障。后续真实 Collector、LLM Writer、真实 Analyst 都可以在保持 Schema 不变的情况下替换。

## 四、Web Collector + LLM ReportWriter 演示步骤

### 页面点击顺序

1. 点击“测试搜索连接”。
2. 点击“测试 LLM 连接”。
3. 运行区选择：
   - `正常流程`
   - `Web Collector`
   - `LLM ReportWriter`
4. 点击“运行 Demo 工作流”。
5. 查看：
   - 顶部搜索状态和 LLM 状态
   - DAG 中 CollectorAgent 和 ReportWriterAgent 耗时
   - Evidence Panel 中 `public_web` 来源
   - Trace Viewer 中 CollectorAgent / ReportWriterAgent 的 output_summary

### 讲解要点

> Web Collector 只采集公开搜索结果摘要，不抓全文。LLM ReportWriter 只负责生成报告，并且输出仍要通过 Claim 和 ReportWriterOutput Schema 校验。真实能力失败时不会影响 workflow，系统会 fallback。

## 五、QA 失败和自动返工演示步骤

### 演示一：缺少证据

页面点击：

1. demo_mode 选择 `QA 失败：缺少证据`。
2. 勾选 `auto_rework=true`。
3. 点击“运行 Demo 工作流”。
4. 查看 QA Panel。

讲解：

> 第一次 QA 会发现没有 Evidence，route_to CollectorAgent。自动返工会重新运行 Collector，再进入 Analyst、ReportWriter 和 QA。

### 演示二：抽取冲突

页面点击：

1. demo_mode 选择 `QA 失败：抽取冲突`。
2. 勾选 `auto_rework=true`。
3. 点击“运行 Demo 工作流”。

讲解：

> QA 发现 Analyst 输出结构化字段异常，会 route_to AnalystAgent。返工后重新生成合法 ProductProfile。

### 演示三：报告格式错误

页面点击：

1. demo_mode 选择 `QA 失败：报告格式错误`。
2. 勾选 `auto_rework=true`。
3. 点击“运行 Demo 工作流”。

讲解：

> QA 发现报告格式不合格，会 route_to ReportWriterAgent。系统重新生成报告，再进入 QA。

## 六、Evidence 质量评分演示步骤

### 页面点击顺序

1. 用 Web Collector 跑一次任务。
2. 在报告右侧 Claim 列表点击一个 Claim。
3. 查看 Evidence Panel。
4. 指向：
   - `source_domain`
   - `source_quality`
   - `confidence`
   - 高可信 / 中可信 / 低可信 标签
5. 滚动到 Trace Viewer，展开 CollectorAgent。

### 讲解要点

> Evidence 不只是引用 URL。系统会对 URL normalize 去重，提取 source_domain，判断 source_quality，并计算 confidence。低可信 Evidence 不会直接 hard fail，但 QA 会给 soft suggestion，提示补充官方或高质量来源。

## 七、Fallback 演示话术

### Web Collector 失败

可能情况：

- Tavily API Key 未配置
- Tavily 401
- 网络超时
- 搜索返回空结果

页面现象：

- 顶部显示搜索测试失败。
- 运行后提示：
  - `Web Collector 调用失败，本次 fallback 到 Mock Evidence。`
- Trace 中：
  - `collector_mode_requested=web`
  - `collector_mode_used=mock`
  - `fallback_used=true`
  - `fallback_reason=...`

讲解：

> 真实搜索工具失败时，系统不会崩溃，而是自动 fallback 到 Mock Evidence。这样现场演示和业务流程都能继续，同时 Trace 会保留失败原因。

### LLM ReportWriter 失败

可能情况：

- API Key 未配置
- 401
- 超时
- 非法 JSON
- Claim 缺 evidence_ids

页面现象：

- 顶部显示 LLM 测试失败或 fallback。
- Trace 中：
  - `writer_mode_requested=llm`
  - `writer_mode_used=mock` 或 schema failed
  - `llm_call_attempted=true`
  - `fallback_used=true`
  - `llm_fallback_reason=...`

讲解：

> LLM 是增强能力，不是系统稳定性的单点依赖。LLM 输出不合法时不会静默通过，要么 fallback，要么进入 QA failed。这保证了报告质量和可追溯性。

## 八、随机竞品保护演示

### 页面点击顺序

1. 在“创建分析任务”中手动输入：
   - 任务名称：随机竞品相关性测试
   - 竞品名称：`jskad, sda, dsja`
   - 分析区域：全球
   - 行业或产品类型：Beauty Retail
2. 点击“创建任务”。
3. 运行区选择：
   - `LangGraph Runner`
   - `Web Collector`
   - `Evidence-based Analyst`
   - `Mock ReportWriter` 或 `LLM ReportWriter`
4. 点击“运行 Demo 工作流”。
5. 查看 Evidence Panel、QA Panel 和 Trace Viewer。

### 讲解要点

> 这个演示用于证明系统不会把任意搜索结果当作竞品证据。随机竞品名可能会触发搜索 API 返回无关网页，但 Collector 会计算 relevance_score，检查竞品名或别名是否出现在 title、snippet、url、domain 中。EvidenceGate 会在 Analyst 和 ReportWriter 之前拦截缺少相关证据的任务，因此系统不会生成强结论。

### 预期页面现象

- Evidence Panel 中相关 Evidence 数量为 0，或 relevance_level 显示为 low / unrelated。
- 竞品覆盖区域显示 Relevant Evidence 不足。
- QA Panel 出现 missing evidence 或 missing relevant evidence。
- DAG 中 EvidenceGate 显示失败，ReportWriter 不应执行。
- Trace Viewer 的 CollectorAgent output_summary 中可以看到：
  - `raw_search_result_count_by_competitor`
  - `relevant_evidence_count_by_competitor`
  - `unrelated_evidence_count_by_competitor`
  - `filtered_unrelated_count`
  - `missing_relevant_evidence_competitors`
- Trace Viewer 的 EvidenceGate output_summary 中可以看到：
  - `evidence_gate_passed=false`
  - `suggested_route=CollectorAgent`
  - `relevant_evidence_count_by_competitor`

讲解话术：

> 过去系统只检查 evidence_ids 是否存在，因此随机竞品也可能被无关网页“支撑”。现在 evidence_ids 只是绑定关系，不能自动代表事实可信。系统增加了实体相关性校验，只有明确命中 competitor 或 alias 的 Evidence 才能支撑强结论。

## 九、每一步页面点哪里

### 创建任务

位置：

- 页面顶部左侧“创建分析任务”卡片。

操作：

- 点击示例任务按钮。
- 点击“创建任务”。

### 运行 workflow

位置：

- 任务列表下方运行区。

操作：

- 选择 demo_mode。
- 选择 ReportWriter 模式。
- 选择 Collector 模式。
- 可选勾选 `auto_rework=true`。
- 点击“运行 Demo 工作流”。

### 测试 LLM

位置：

- 运行区 “测试 LLM 连接”按钮。

操作：

- 点击按钮。
- 查看顶部 LLM 状态区。

### 测试搜索

位置：

- 运行区 “测试搜索连接”按钮。

操作：

- 点击按钮。
- 查看顶部搜索状态区。

### 查看报告和 Evidence

位置：

- “分析报告”区域。

操作：

- 点击右侧 Claim。
- 查看下方 Evidence Panel。

### 查看 QA

位置：

- “业务质检结果”区域。

操作：

- 查看 hard_errors。
- 查看 soft_suggestions。
- 查看 rework_instructions。
- 查看 rework_history。

### 查看 Trace

位置：

- 页面底部 Trace Viewer。

操作：

- 用 Agent 下拉框筛选 Agent。
- 点击某条 Trace 展开详情。

## 十、评委可能追问的问题与回答要点

### Q1：这是不是只是 prompt 包装？

回答要点：

> 不是。系统把竞品分析拆成多个 Agent，每个 Agent 都有结构化 Input / Output Schema。Claim 必须绑定 evidence_ids，Evidence 必须有来源和置信度，QA 会检查输出质量，Trace 会记录每一步执行结果。LLM 只是 ReportWriter 的可选实现，不是整个系统的唯一核心。

### Q2：为什么现在还有 Mock？

回答要点：

> Mock 是为了保证演示稳定，也是为了先定义工程契约。当前 Collector 和 ReportWriter 已经支持真实模式，但保留 Mock 作为 fallback。后续可以在不改 API 和前端的情况下逐步替换 Planner、Analyst、QA。

### Q3：Web Collector 是爬虫吗？

回答要点：

> 不是复杂爬虫。当前只调用 Tavily Search API，使用公开搜索结果的 title、url、content 摘要，不请求 raw_content，不抓网页全文，不绕过 robots.txt。

### Q4：Evidence 可信度怎么来的？

回答要点：

> 当前是轻量规则。系统根据 source_domain、source_quality、搜索 score 计算 confidence。官网和文档更高，媒体和评测次之，低质量来源较低。低 confidence 不会直接 hard fail，但 QA 会给 soft suggestion。

### Q5：如果 LLM 编造内容怎么办？

回答要点：

> ReportWriter Prompt 明确要求只能基于 Evidence 和 Knowledge 输出，每个 Claim 必须绑定 evidence_ids。Schema 会强制 evidence_ids 非空。QA 会检查 evidence coverage。非法 JSON、缺少 evidence_ids 或格式错误不会静默通过。

### Q6：如果外部 API 挂了怎么办？

回答要点：

> Web Collector 和 LLM ReportWriter 都有 fallback。外部 API 失败时，workflow 不崩溃，系统会 fallback 到 Mock，并在 Trace 中记录 fallback_reason。

### Q7：为什么报告有时和 Web Evidence 不完全一致？

回答要点：

> 当前 AnalystAgent 仍是 Mock，这是已知限制。Web Evidence 已经真实接入，但结构化分析还没有完全基于 Evidence 抽取。下一阶段计划做 Evidence-based AnalystAgent，让 Web Evidence 更直接地驱动 ProductProfile、FeatureTree、PricingModel 和 UserPersona。

### Q8：后续怎么接 LangGraph？

回答要点：

> 现在的 Runner 已经把流程和 Schema 边界定义清楚。后续可以把每个 Agent 的 run 方法替换成 LangGraph 节点，保持 Pydantic I/O Schema 不变，Trace 和 API 也能继续复用。

### Q9：有没有 RAG？

回答要点：

> 当前没有接 RAG，这是有意控制范围。现在先做 Web Search -> Evidence -> Report 的闭环。后续如果接 RAG，会把 Evidence 的 source_domain、source_quality、confidence 作为 chunk metadata。

### Q10：这个系统最有价值的地方是什么？

回答要点：

> 价值不在于一次性生成漂亮报告，而在于建立了可信竞品分析的工程闭环：结构化 Agent、证据绑定、质量校验、自动返工、Trace 可观测和 fallback 稳定性。这些能力让后续接真实 LLM、真实采集器和 RAG 时风险更可控。
