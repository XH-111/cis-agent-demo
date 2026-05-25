# Phase 7.1 Competitor Coverage Fix

## 背景

此前 Web Collector 会把多个竞品的搜索结果放进同一个 Evidence 池，AnalystAgent 和 ReportWriterAgent 再基于混合 Evidence 生成分析与报告。实际运行时，如果某个竞品的搜索结果质量更高或返回更多，就容易让最终报告集中在该竞品，例如输入“飞书、钉钉、企业微信”时报告被钉钉信息带偏。

## 已完成改动

1. `Evidence` 增加 `competitor` 字段，每条证据都能标识归属竞品。
2. `Claim` 增加 `competitor` 字段，每条报告结论都能标识对应竞品。
3. Web Collector 改为按 competitor 单独生成 query、单独采集、单独去重，并默认每个竞品最少保留 2 条、最多保留 5 条 Evidence。
4. AnalystAgent 在 evidence 模式下按 competitor 分组抽取结构化知识，不再把所有 Evidence 混合分析；证据不足的竞品会输出保守结论。
5. ReportWriterAgent 的 Mock 与 LLM Prompt 都要求覆盖所有输入 competitors，并要求 claim 绑定同一竞品的 evidence_ids。
6. QaAgent 增加 competitor coverage 检查，包括缺少 Evidence、缺少 Claim、Claim 使用其他竞品 Evidence 三类问题。
7. 前端 ReportView 增加“竞品覆盖情况”，Evidence Panel 和 Claim 列表展示 competitor 字段。
8. Trace 增加按竞品统计字段，如 `query_count_by_competitor`、`evidence_count_by_competitor`、`claim_count_by_competitor`、`competitor_coverage_result`。

## 关键规则

- Collector 去重使用 `competitor + normalized_url`，避免不同竞品因为同一聚合页被误删。
- AnalystAgent 只使用当前 competitor 的 Evidence 抽取该 competitor 的知识。
- ReportWriterAgent 不允许用一个竞品的 Evidence 支撑另一个竞品的 Claim。
- QA 遇到某个竞品没有 Evidence 时路由到 `CollectorAgent`。
- QA 遇到某个竞品有 Evidence 但没有 Claim 时路由到 `ReportWriterAgent`。
- QA 遇到 Claim 与 Evidence 竞品不匹配时路由到 `ReportWriterAgent`。

## 演示价值

这次补强后，多竞品任务不再只是“泛化竞品报告”，而是能体现每个竞品的证据覆盖、结构化知识和结论覆盖。现场演示时可以用飞书、钉钉、企业微信作为输入，重点展示右侧“竞品覆盖情况”和 Evidence Panel 中的 competitor 字段。

## 后续可优化

- 增加每个 competitor 的专属关键词配置，例如官网域名、品牌英文名、产品线别名。
- 在 Web Collector 中引入更细的来源白名单和官方域名识别。
- 在 LLM ReportWriter Prompt 中增加更严格的“每个竞品一个固定小节”JSON 结构。
- 后续接入 RAG 时，可以按 competitor 建立 Evidence partition，避免跨竞品召回污染。
