# Phase 11: Production Web Collection / PageFetcher

## 目标

在 Tavily Search Web Collector 之后增加合规的轻量正文摘要抓取能力，为后续 Chunker / Retriever / RAG 做内容准备，但本阶段不接 RAG、不接向量数据库、不做复杂爬虫。

## 工作流位置

```text
PlannerAgent
-> CollectorAgent
-> EvidenceGate
-> PageFetcher
-> AnalystAgent
-> ReportWriterAgent
-> QaAgent
-> FinalReportAgent
```

PageFetcher 只接入 LangGraph 主线。Custom Runner 继续作为 legacy fallback，不扩展新节点。

## 抓取范围控制

- 只处理 `relevance_level=high/medium` 的 Evidence。
- 跳过 `source_quality=low_quality` 的 Evidence。
- 每个 competitor 最多抓取 `PAGE_FETCH_MAX_PER_COMPETITOR` 条，默认 2。
- 每个 run 最多抓取 `PAGE_FETCH_MAX_PER_RUN` 条，默认 10。
- 最大下载大小由 `PAGE_FETCH_MAX_BYTES` 控制，默认 500000 bytes。
- 只处理 `text/html`，非 HTML 自动 fallback。

## 内容保存策略

PageFetcher 使用 BeautifulSoup 移除 `script/style/nav/footer/header/aside`，只提取 `title/h1/h2/h3/p/li` 文本。

系统只保存：

- `page_title`
- `content_excerpt`
- `content_chars`
- `fetch_status_code`
- `page_fetch_error`
- `fetched_at`

不会保存完整网页正文。`content_excerpt` 默认最多 1000 字符，完整提取文本先受 `PAGE_CONTENT_MAX_CHARS` 截断。

## Fallback 策略

以下情况不会导致 workflow 崩溃：

- timeout
- 403 / 404 / 非 200
- 非 HTML
- 内容超过大小限制
- 文本抽取为空
- 网络异常

失败时 Evidence 保持 `content_mode=snippet`，AnalystAgent 继续使用搜索摘要，并在 Trace 和 Evidence Panel 中展示失败原因。

## Analyst 使用方式

AnalystAgent 在 evidence 模式下优先使用 `content_excerpt`，没有正文摘要时再使用 `snippet`。它仍然不会使用 `relevance_level=unrelated` 的 Evidence。

## 可观测性

PageFetcher 会写入 `PageFetcher` Trace，包含：

- `page_fetch_attempted`
- `page_fetch_success_count`
- `page_fetch_failed_count`
- `page_fetch_skipped_count`
- `page_fetch_fallback_count`
- `page_fetch_error_summary`
- `avg_content_chars`
- `max_content_chars`
- `fetched_evidence_ids`
- `skipped_evidence_ids`
- `run_id`

Workflow summary 中也会包含 `page_fetch_output`，方便前端恢复和答辩说明。
