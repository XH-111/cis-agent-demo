# Phase 6 Evidence 质量增强说明

## 背景

Phase 5 已接入最小 Web Collector，并优先支持 Tavily Search API。Web Collector 可以把公开搜索结果转换为 Evidence，但初版存在几个演示和工程风险：

- 搜索结果可能重复，同一 URL 可能以不同 tracking 参数出现。
- Evidence 缺少来源域名，不利于快速判断来源可信度。
- Evidence 只有单一 confidence 数值，缺少可解释的来源质量标签。
- QA 只检查 evidence 是否存在，缺少对低可信证据的软提醒。
- 前端 Evidence Panel 只展示 snippet、URL 和 confidence，可读性不足。

本阶段目标是在不接 RAG、不接向量数据库、不做复杂爬虫、不重构 Agent 架构的前提下，增强 Evidence 的可信度、可读性和可追溯性。

## 已完成改动

### 1. Evidence Schema 扩展

`Evidence` 新增两个兼容字段：

- `source_domain: str | None`
- `source_quality: official | documentation | media | review | unknown | low_quality`

示例：

```json
{
  "source_type": "public_web",
  "url": "https://www.feishu.cn/pricing",
  "source_domain": "feishu.cn",
  "source_quality": "official",
  "confidence": 0.9
}
```

### 2. URL normalize 与去重

Web Collector 会在去重前 normalize URL：

- 去掉末尾 `/`
- 去掉常见 tracking 参数：
  - `utm_source`
  - `utm_medium`
  - `utm_campaign`
  - `utm_term`
  - `utm_content`
  - `spm`
  - `fbclid`

同一个 normalized URL 只保留一次。

Trace 中新增：

- `raw_evidence_count`
- `deduplicated_evidence_count`
- `duplicate_removed_count`

### 3. source_domain 提取

Web Collector 会从 URL 中提取来源域名：

```text
https://www.feishu.cn/pricing -> feishu.cn
https://open.dingtalk.com/document -> dingtalk.com
```

Mock Evidence 也补充了 `source_domain`，保证前后端展示一致。

### 4. source_quality 判断

当前使用轻量规则判断来源质量：

- `official`
  - URL path 包含 `official`、`pricing`、`product`、`features`
  - 或域名与竞品名称存在明显关联
- `documentation`
  - domain 或 path 包含 `docs`、`document`、`developer`、`help`、`support`
- `media`
  - 常见媒体、行业网站，如 `techcrunch`、`theverge`、`36kr`、`infoq`、`gartner`、`forrester`
- `review`
  - title、URL 或 snippet 包含 `review`、`compare`、`alternative`
- `low_quality`
  - snippet 太短
  - 域名可疑
- `unknown`
  - 不符合以上规则

### 5. confidence 计算优化

基础 confidence 来自 `source_quality`：

| source_quality | confidence |
|---|---:|
| official | 0.9 |
| documentation | 0.85 |
| media | 0.75 |
| review | 0.65 |
| unknown | 0.6 |
| low_quality | 0.4 |

如果搜索 API 返回 score，会与基础 confidence 做轻量加权，但不会引入复杂可信度模型。

### 6. QA Evidence 质量软检查

QaAgent 增加 soft check：

1. Claim 有 evidence_ids，但关联 Evidence 全部 confidence `< 0.5`
   - soft suggestion：
     `该结论引用的证据可信度较低，建议补充官方或高质量来源。`
2. Evidence 缺少 `source_domain`
   - soft suggestion：
     `部分 Evidence 缺少 source_domain，建议检查来源解析逻辑。`
3. Evidence 数量少于 3
   - soft suggestion：
     `Web Collector 返回 Evidence 数量少于 3，建议补充更多公开来源。`

注意：

- 低 confidence 不会 hard fail。
- Evidence 为空仍然是 hard error。
- Claim 缺少 evidence_ids 仍然 hard fail。

QaAgent Trace diagnostics 新增：

- `evidence_quality_checked`
- `low_confidence_claim_count`
- `soft_suggestion_count`

### 7. Collector Trace 增强

CollectorAgent Trace diagnostics 新增：

- `raw_evidence_count`
- `deduplicated_evidence_count`
- `duplicate_removed_count`
- `source_quality_summary`
- `low_confidence_count`

示例：

```json
{
  "collector_mode_requested": "web",
  "collector_mode_used": "web",
  "raw_evidence_count": 5,
  "deduplicated_evidence_count": 4,
  "duplicate_removed_count": 1,
  "source_quality_summary": {
    "official": 2,
    "media": 1,
    "unknown": 1
  },
  "low_confidence_count": 0
}
```

### 8. 前端 Evidence Panel 优化

Evidence Panel 现在展示：

- `source_domain`
- `source_quality`
- `confidence`
- 可信度标签：
  - `>= 0.8`：高可信
  - `0.5 <= confidence < 0.8`：中可信
  - `< 0.5`：低可信

点击 Claim 后，关联 Evidence 会按 confidence 从高到低排序。低可信 Evidence 使用轻微警告样式，不做夸张提示。

## 测试覆盖

新增或补充 pytest 覆盖：

1. 相同 URL 会被去重。
2. URL tracking 参数会被忽略。
3. `source_domain` 能正确提取。
4. official 来源 confidence 高于 unknown。
5. low_quality 来源 confidence 低于 0.5。
6. Claim 只绑定低可信 Evidence 时，QA 产生 soft suggestion。
7. Evidence 为空仍然是 hard error。
8. `collector_mode=mock` 和 `collector_mode=web` 均不受影响。

## 验证结果

后端：

```bash
cd backend
pytest
```

结果：

```text
36 passed
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

1. source_quality 仍是规则判断，不是完整来源信誉模型。
2. 官方域名识别依赖 URL/path 和竞品名称，可能误判。
3. confidence 没有做跨来源一致性校验。
4. 没有抓取网页正文，也不会读取 raw_content。
5. 没有接 RAG 或向量数据库。

## 后续建议

1. 增加可维护的 source domain whitelist / blacklist。
2. 将 source_quality 规则抽成独立 service，方便测试和复用。
3. 引入 claim-level evidence quality summary。
4. 后续接入真实 AnalystAgent 时，让 Analyst 使用 source_quality 和 confidence 参与结构化抽取。
5. 如果接 RAG，应保留当前 Evidence 元数据作为 chunk metadata。
