# Phase 9 Evidence Relevance Gate

## 背景问题

系统已经能检查 Schema、`evidence_ids`、竞品覆盖、Trace 和 QA 闭环，但之前没有严格检查 Evidence 是否真的与 competitor 实体相关。

因此当用户输入随机竞品名，例如 `jskad / sda / dsja` 时，搜索 API 仍可能返回 TaxJar、行业媒体或其他无关网页；如果只检查 URL 和 evidence_ids，系统就可能生成看似正式但事实基础错误的报告。

## 本阶段目标

Phase 9 增加 Evidence 与 competitor 的实体相关性校验，防止无关网页被当成竞品证据使用。

本阶段不接 RAG、不接向量数据库、不重构 Agent 架构，只在现有 Web Collector、Analyst、ReportWriter、QA 和前端展示中增加 relevance gate。

## 新增 Schema 字段

`Evidence` 新增：

- `relevance_score`: 0.0 到 1.0
- `relevance_level`: `high / medium / low / unrelated`
- `relevance_reason`
- `entity_match_signals`

`entity_match_signals` 包含：

- `competitor_in_title`
- `competitor_in_snippet`
- `competitor_in_url`
- `competitor_in_domain`
- `competitor_alias_matched`
- `domain_similarity_score`

## Relevance 评分规则

当前使用轻量规则：

- competitor 或 alias 出现在 title：+0.35
- competitor 或 alias 出现在 snippet：+0.35
- competitor 或 alias 出现在 url：+0.20
- competitor 或 alias 出现在 domain：+0.20
- source_domain 与 competitor name 字符串相似：+0.10
- 如果完全没有命中 competitor / alias，最高分不超过 0.35

等级划分：

- `score >= 0.75`: high
- `0.45 <= score < 0.75`: medium
- `0.25 <= score < 0.45`: low
- `score < 0.25`: unrelated

## Collector 行为

Web Collector 对每条搜索结果生成 Evidence 后会计算 relevance。

- `high / medium / low` 可以保留展示。
- `unrelated` 默认不进入有效 Evidence 列表。
- 如果搜索成功但结果都 unrelated，不 fallback 到 Mock，避免随机竞品被 Mock 证据“洗白”。
- 只有搜索未配置、401、超时、空结果等采集失败才 fallback 到 Mock。

Collector Trace 新增：

- `raw_search_result_count_by_competitor`
- `relevant_evidence_count_by_competitor`
- `unrelated_evidence_count_by_competitor`
- `filtered_unrelated_count`
- `missing_relevant_evidence_competitors`

## Analyst 行为

Evidence-based Analyst 只使用 `high / medium` Evidence 抽取结构化知识。

- `low` Evidence 只作为弱参考。
- `unrelated` Evidence 禁止用于 ProductProfile、FeatureTree、PricingModel、UserPersona。
- 如果某个 competitor 没有 relevant Evidence，则输出 insufficient evidence，不编造功能、定价或用户画像。

## ReportWriter 行为

ReportWriter 只允许 concrete claim 引用 `high / medium` Evidence。

- 如果 competitor 缺少 relevant Evidence，只能写“当前公开证据不足，暂不做强结论。”
- 不允许因为 Evidence 有 URL 就默认可信。
- LLM prompt 明确要求不能使用 unrelated Evidence。

## QA 行为

QaAgent 增加 relevance hard check：

- 每个 competitor 必须有 high / medium relevant Evidence，否则 route_to CollectorAgent。
- Claim 不能引用 unrelated Evidence，否则 route_to ReportWriterAgent。
- low relevance Evidence 会进入 soft suggestion。

QA diagnostics 新增：

- `relevance_checked`
- `missing_relevant_evidence_competitors`
- `unrelated_evidence_claims`
- `low_relevance_claims`

## 前端展示

Evidence Panel 新增展示：

- `relevance_score`
- `relevance_level`
- `relevance_reason`
- 可折叠 `entity_match_signals`

竞品覆盖区域新增：

- Evidence 数量
- Relevant Evidence 数量
- Unrelated Evidence 数量
- Claim 数量

## 随机竞品保护

当输入 `jskad, sda, dsja` 这类随机竞品时：

1. Web Collector 可以发起搜索。
2. 如果搜索结果未命中 competitor / alias，则被标记为 unrelated 并过滤。
3. Analyst 输出 evidence insufficient。
4. ReportWriter 不应输出强结论。
5. QA 会提示缺少相关公开证据。

## 测试覆盖

新增测试覆盖：

- competitor 出现在 title / snippet 时 relevance 高。
- competitor 完全不出现时 relevance 低。
- TaxJar 不能作为 jskad 的 high relevance Evidence。
- Collector 能过滤 unrelated Evidence。
- missing relevant competitors 会进入 diagnostics。
- Analyst 不使用 unrelated Evidence 抽取。
- ReportWriter 不引用 unrelated Evidence。
- QA 能发现 Claim 引用 unrelated Evidence。
- 随机 competitor 不生成强结论。
- 飞书等常见竞品 alias 仍能正常匹配。

