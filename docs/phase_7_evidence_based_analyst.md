# Phase 7 Evidence-based AnalystAgent

## 背景

Phase 5 已完成 Tavily Web Collector，Phase 6 已增强 Evidence 质量评分。但此前 `AnalystAgent` 仍主要依赖 Mock 模板，导致真实 Web Evidence 进入系统后，结构化竞品知识仍可能被 Mock 内容带偏。

本阶段目标是让 `AnalystAgent` 能基于 Evidence snippet 做轻量规则抽取，生成更贴近真实来源的结构化竞品知识。

## 目标

1. 保留 Mock Analyst 作为稳定演示模式。
2. 新增 Evidence-based Analyst，默认启用。
3. 支持 `analyst_mode=mock/evidence/llm` 参数。
4. 当前阶段不实现真实 LLM Analyst；选择 `llm` 时 fallback 到 evidence 模式并记录原因。
5. 所有结构化分析对象尽量绑定 `evidence_ids`。
6. Evidence 不足时输出保守结论，不编造事实。

## 新增运行参数

后端 `/api/tasks/{task_id}/run` 新增：

```text
analyst_mode=mock
analyst_mode=evidence
analyst_mode=llm
```

默认值：

```text
analyst_mode=evidence
```

可组合：

```text
POST /api/tasks/{task_id}/run?collector_mode=web&analyst_mode=evidence&writer_mode=llm
```

## Analyst 模式说明

### mock

保留原有 Mock 逻辑，用于稳定演示和 fallback。

### evidence

基于 Evidence snippet 的规则抽取，不调用 LLM。

抽取对象：

- `ProductProfile`
- `FeatureTree`
- `PricingModel`
- `UserPersona`

### llm

当前阶段暂不接真实 LLM Analyst。

如果用户选择：

```text
analyst_mode=llm
```

系统会 fallback 到 evidence 模式，并在 Trace 中记录：

```json
{
  "analyst_mode_requested": "llm",
  "analyst_mode_used": "evidence",
  "fallback_used": true,
  "fallback_reason": "analyst_mode=llm is not implemented in this phase; fallback to evidence mode."
}
```

## Evidence-based 抽取规则

### ProductProfile

基于高 confidence Evidence 生成：

- `product_name`
- `positioning`
- `target_segments`
- `strengths`
- `weaknesses`
- `evidence_ids`

如果 Evidence 不足，会输出：

```text
Evidence is insufficient for a confident conclusion.
```

并绑定已有 `evidence_ids`。

### FeatureTree

根据关键词抽取功能类别：

英文关键词：

- AI
- automation
- collaboration
- pricing
- integration
- analytics
- security
- mobile
- API
- workflow

中文关键词：

- 智能
- 自动化
- 协作
- 定价
- 集成
- 分析
- 安全
- 移动端
- 接口
- 流程

每个抽取出的功能类别会绑定对应 Evidence。

### PricingModel

根据定价关键词抽取：

- free
- trial
- pricing
- subscription
- enterprise
- plan
- quote
- 免费
- 试用
- 订阅
- 企业版
- 套餐
- 定价

如果没有足够定价证据，会输出保守说明：

```text
Evidence is insufficient for a confident pricing conclusion.
```

### UserPersona

根据用户画像关键词抽取：

- enterprise / 企业
- team / 团队
- developer / 开发者
- marketer / 市场
- product team / product manager / 产品经理
- student / 学生

抽取结果会绑定对应 Evidence。

## Evidence 不足处理

当满足以下条件之一时，Analyst 会进入保守输出：

1. Evidence 数量少于 3。
2. 可抽取 feature、pricing、persona 信息过少。

处理策略：

- 不编造具体事实。
- 输出 `Evidence is insufficient for a confident conclusion.`
- 绑定已有 `evidence_ids`。
- Trace 中记录 `insufficient_evidence=true`。
- QA 产生 soft suggestion：

```text
结构化分析证据不足，建议补充更多来源。
```

## Trace 诊断字段

AnalystAgent Trace `output_summary` 新增：

- `analyst_mode_requested`
- `analyst_mode_used`
- `evidence_count`
- `evidence_used_count`
- `extracted_profile_count`
- `extracted_feature_count`
- `extracted_pricing_count`
- `extracted_persona_count`
- `insufficient_evidence`
- `fallback_used`
- `fallback_reason`

示例：

```json
{
  "analyst_mode_requested": "evidence",
  "analyst_mode_used": "evidence",
  "evidence_count": 5,
  "evidence_used_count": 5,
  "extracted_profile_count": 1,
  "extracted_feature_count": 4,
  "extracted_pricing_count": 2,
  "extracted_persona_count": 1,
  "insufficient_evidence": false,
  "fallback_used": false,
  "fallback_reason": null
}
```

## 前端变化

运行区新增 Analyst 模式下拉：

- `Mock Analyst`
- `Evidence-based Analyst`
- `LLM Analyst`

默认选择：

```text
Evidence-based Analyst
```

竞品知识页面增强：

1. 展示结构化知识 JSON。
2. 自动识别并展示 `evidence_ids`。
3. 点击 `evidence_id` 后，右侧 Evidence Panel 会切换到对应 Evidence。
4. 如果字段包含 `Evidence is insufficient`，会显示轻量提示。

## QA 增强

QaAgent 增加 Analyst 输出检查：

1. 结构化对象缺少 `evidence_ids` -> soft suggestion。
2. 分析字段过空 -> soft suggestion。
3. 出现明显 `unsupported conclusion` -> route_to `AnalystAgent`。
4. Evidence 不足分析 -> soft suggestion。

低置信度 Evidence 和 Evidence 质量检查仍沿用 Phase 6 的 soft check。

## 测试覆盖

新增或补充 pytest：

1. `analyst_mode=mock` 仍然可用。
2. `analyst_mode=evidence` 能从 Evidence 中抽取 feature。
3. pricing 关键词能生成 `PricingModel`。
4. persona 关键词能生成 `UserPersona`。
5. 抽取结果包含 `evidence_ids`。
6. Evidence 不足时不编造事实，并产生 soft suggestion。
7. `collector_mode=web&analyst_mode=evidence&writer_mode=llm` 参数链路可传递。
8. AnalystAgent Trace 包含 analyst_mode 和 extracted counts。

## 验证结果

后端：

```bash
cd backend
pytest
```

结果：

```text
41 passed
```

前端：

```bash
cd frontend
npm run build
```

结果：

```text
build passed
```

## 当前限制

1. Evidence-based Analyst 仍是轻量规则，不是完整 NLP 抽取。
2. 当前 `analyst_mode=llm` 只是模式占位，会 fallback 到 evidence。
3. Feature 与 pricing 抽取基于关键词，可能漏掉隐含表达。
4. UserPersona 规则较粗，只用于演示结构化知识从 Evidence 生成的闭环。
5. 如果 Web Collector 搜索结果本身偏题，Analyst 也会受到影响。

## 后续建议

1. 给 Evidence-based Analyst 增加更细的中文关键词和行业词表。
2. 将 Analyst 规则抽成独立 service，便于维护和单元测试。
3. 后续实现 `analyst_mode=llm`，要求 LLM 只基于 Evidence 输出结构化 JSON。
4. ReportWriter Prompt 中增加约束：Evidence 与 Knowledge 冲突时优先 Evidence。
5. 后续接 RAG 时，Analyst 可基于检索结果和 Evidence metadata 进行结构化抽取。
