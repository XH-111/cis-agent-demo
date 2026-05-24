from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.agents.base import run_with_trace
from app.schemas import CollectorInput, CollectorOutput, Evidence
from app.services.trace_service import TraceService
from app.services.web_search_client import WebSearchClient

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "spm", "fbclid"}
QUALITY_CONFIDENCE = {
    "official": 0.9,
    "documentation": 0.85,
    "media": 0.75,
    "review": 0.65,
    "unknown": 0.6,
    "low_quality": 0.4,
}


class CollectorAgent:
    name = "CollectorAgent"

    def __init__(self, trace_service: TraceService, web_search_client: WebSearchClient | None = None):
        self.trace_service = trace_service
        self.web_search_client = web_search_client or WebSearchClient()

    def run(self, input_data: CollectorInput) -> CollectorOutput:
        task = input_data.task

        def produce() -> CollectorOutput:
            diagnostics = self._base_diagnostics(input_data)
            if input_data.collector_mode == "web":
                web_output = self._collect_web(input_data, diagnostics)
                if web_output is not None:
                    return web_output
            return self._mock_output(input_data, diagnostics)

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="AnalystAgent",
            message_type="evidence",
            schema_name="CollectorOutput",
            input_summary=f"collector_mode_requested={input_data.collector_mode}; 为 {task.region} 的 {task.industry} 场景采集证据",
            retry_count=input_data.retry_count,
            fn=produce,
        )

    def _base_diagnostics(self, input_data: CollectorInput) -> dict:
        return {
            "collector_mode_requested": input_data.collector_mode,
            "collector_mode_used": "mock",
            "search_provider": self.web_search_client.provider,
            "search_base_url_configured": bool(self.web_search_client.base_url),
            "has_search_api_key": bool(self.web_search_client.api_key),
            "web_search_attempted": False,
            "web_search_success": False,
            "query_count": 0,
            "evidence_count": 0,
            "raw_evidence_count": 0,
            "deduplicated_evidence_count": 0,
            "duplicate_removed_count": 0,
            "source_quality_summary": {},
            "low_confidence_count": 0,
            "fallback_used": False,
            "fallback_reason": None,
            "elapsed_time_ms": 0,
        }

    def _collect_web(self, input_data: CollectorInput, diagnostics: dict) -> CollectorOutput | None:
        task = input_data.task
        queries = []
        for competitor in task.competitors:
            queries.append(f"{competitor} {task.industry} pricing features official")
            queries.append(f"{competitor} {task.industry} 功能 定价 官网")

        evidence: list[Evidence] = []
        seen_urls: set[str] = set()
        raw_count = 0
        fallback_reason: str | None = None
        total_elapsed = 0
        for query in queries:
            response = self.web_search_client.search(query, limit=3)
            diagnostics["web_search_attempted"] = diagnostics["web_search_attempted"] or response.attempted
            total_elapsed += response.elapsed_time_ms
            if not response.available:
                fallback_reason = response.fallback_reason or response.error_message or "Web search unavailable."
                break
            for result in response.results:
                raw_count += 1
                normalized_url = self.normalize_url(result.url)
                if normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)
                quality = self._source_quality(normalized_url, result.title, result.snippet, task.competitors)
                confidence = self._confidence_for_result(normalized_url, result.snippet, quality, result.score)
                evidence.append(
                    Evidence(
                        source_type="public_web",
                        url=normalized_url,
                        source_domain=self.extract_source_domain(normalized_url),
                        source_quality=quality,
                        snippet=self._snippet(result.title, result.snippet),
                        confidence=confidence,
                    )
                )
                if len(evidence) >= 5:
                    break
            if len(evidence) >= 5:
                break

        diagnostics.update(
            {
                "query_count": len(queries),
                "evidence_count": len(evidence),
                "raw_evidence_count": raw_count,
                "deduplicated_evidence_count": len(evidence),
                "duplicate_removed_count": raw_count - len(evidence),
                "source_quality_summary": self._quality_summary(evidence),
                "low_confidence_count": sum(1 for item in evidence if item.confidence < 0.5),
                "elapsed_time_ms": total_elapsed,
            }
        )

        if fallback_reason or not evidence:
            diagnostics.update(
                {
                    "collector_mode_used": "mock",
                    "web_search_success": False,
                    "fallback_used": True,
                    "fallback_reason": fallback_reason or "Web search returned no usable public results.",
                }
            )
            return None

        diagnostics.update(
            {
                "collector_mode_used": "web",
                "web_search_success": True,
                "fallback_used": False,
                "fallback_reason": None,
                "evidence_count": len(evidence),
            }
        )
        return CollectorOutput(evidence=evidence, diagnostics=diagnostics)

    def _mock_output(self, input_data: CollectorInput, diagnostics: dict | None = None) -> CollectorOutput:
        task = input_data.task
        competitors = task.competitors[:2]
        diagnostics = diagnostics or self._base_diagnostics(input_data)
        diagnostics.update(
            {
                "collector_mode_used": "mock",
                "evidence_count": 4 + (1 if len(competitors) > 1 else 0),
            }
        )
        evidence = [
            Evidence(
                source_type="web",
                url=f"https://example.com/{task.product_name.lower()}-positioning",
                source_domain="example.com",
                source_quality="unknown",
                snippet=f"{task.product_name} 强调面向 {task.industry} 的自动化竞品研究工作流。",
                confidence=0.86,
            ),
            Evidence(
                source_type="pricing_page",
                url=f"https://example.com/{competitors[0].lower()}-pricing",
                source_domain="example.com",
                source_quality="official",
                snippet=f"{competitors[0]} 公开了分层定价，并将团队协作能力放在核心套餐中。",
                confidence=0.82,
            ),
            Evidence(
                source_type="review",
                url=f"https://example.com/reviews/{competitors[0].lower()}",
                source_domain="example.com",
                source_quality="review",
                snippet="用户认可快速上手能力，但希望生成报告中的来源引用更加清晰。",
                confidence=0.78,
            ),
            Evidence(
                source_type="document",
                local_ref="mock://industry-feature-matrix",
                source_domain="mock",
                source_quality="documentation",
                snippet="常见采购诉求包括证据可追溯、用户画像映射和可复用报告模板。",
                confidence=0.8,
            ),
        ]
        if len(competitors) > 1:
            evidence.append(
                Evidence(
                    source_type="web",
                    url=f"https://example.com/{competitors[1].lower()}-features",
                    source_domain="example.com",
                    source_quality="unknown",
                    snippet=f"{competitors[1]} 突出强调广泛集成能力和工作流仪表盘。",
                    confidence=0.76,
                )
            )
        diagnostics.update(
            {
                "evidence_count": len(evidence),
                "raw_evidence_count": len(evidence),
                "deduplicated_evidence_count": len(evidence),
                "duplicate_removed_count": 0,
                "source_quality_summary": self._quality_summary(evidence),
                "low_confidence_count": sum(1 for item in evidence if item.confidence < 0.5),
            }
        )
        return CollectorOutput(evidence=evidence, diagnostics=diagnostics)

    @staticmethod
    def _snippet(title: str, snippet: str) -> str:
        text = f"{title}: {snippet}" if title and title not in snippet else snippet
        return text[:500]

    @staticmethod
    def _confidence_for_result(url: str, snippet: str, quality: str, score: float | None = None) -> float:
        base = QUALITY_CONFIDENCE[quality]
        if score is None or quality in {"official", "documentation", "low_quality"}:
            return base
        score_confidence = max(0.6, min(0.9, 0.6 + float(score) * 0.3))
        return round((base * 0.7) + (score_confidence * 0.3), 2)

    @staticmethod
    def _source_quality(url: str, title: str, snippet: str, competitors: list[str]) -> str:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        text = f"{title} {snippet} {url}".lower()
        if not host or any(token in host for token in ("localhost", "spam", "click")):
            return "low_quality"
        if any(token in text for token in ("review", "compare", "alternative", "alternatives")):
            return "review"
        if any(token in host for token in ("techcrunch.", "theverge.", "36kr.", "infoq.", "gartner.", "forrester.", "wikipedia.org")):
            return "media"
        if any(token in path for token in ("docs", "document", "developer", "help", "support")) or any(
            token in host for token in ("docs.", "developer.", "help.", "support.")
        ):
            return "documentation"
        competitor_tokens = [self_token for competitor in competitors for self_token in competitor.lower().replace(" ", "").split(",") if self_token]
        if any(token in host.replace("-", "").replace(".", "") for token in competitor_tokens) or any(
            token in path for token in ("official", "pricing", "product", "features")
        ):
            return "official"
        if len(snippet.strip()) < 30:
            return "low_quality"
        return "unknown"

    @staticmethod
    def normalize_url(url: str) -> str:
        parsed = urlparse(url.strip())
        query = urlencode([(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in TRACKING_PARAMS])
        path = parsed.path.rstrip("/") or parsed.path
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))

    @staticmethod
    def extract_source_domain(url: str) -> str:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        if len(parts) >= 3 and parts[-2] in {"com", "com.cn", "co"}:
            return ".".join(parts[-3:])
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return host or "unknown"

    @staticmethod
    def _quality_summary(evidence: list[Evidence]) -> dict:
        summary: dict[str, int] = {}
        for item in evidence:
            summary[item.source_quality] = summary.get(item.source_quality, 0) + 1
        return summary
