from urllib.parse import urlparse

from app.agents.base import run_with_trace
from app.schemas import CollectorInput, CollectorOutput, Evidence
from app.services.trace_service import TraceService
from app.services.web_search_client import WebSearchClient


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
                if result.url in {item.url for item in evidence}:
                    continue
                evidence.append(
                    Evidence(
                        source_type="public_web",
                        url=result.url,
                        snippet=self._snippet(result.title, result.snippet),
                        confidence=self._confidence_for_result(result.url, result.snippet, result.score),
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
                snippet=f"{task.product_name} 强调面向 {task.industry} 的自动化竞品研究工作流。",
                confidence=0.86,
            ),
            Evidence(
                source_type="pricing_page",
                url=f"https://example.com/{competitors[0].lower()}-pricing",
                snippet=f"{competitors[0]} 公开了分层定价，并将团队协作能力放在核心套餐中。",
                confidence=0.82,
            ),
            Evidence(
                source_type="review",
                url=f"https://example.com/reviews/{competitors[0].lower()}",
                snippet="用户认可快速上手能力，但希望生成报告中的来源引用更加清晰。",
                confidence=0.78,
            ),
            Evidence(
                source_type="document",
                local_ref="mock://industry-feature-matrix",
                snippet="常见采购诉求包括证据可追溯、用户画像映射和可复用报告模板。",
                confidence=0.8,
            ),
        ]
        if len(competitors) > 1:
            evidence.append(
                Evidence(
                    source_type="web",
                    url=f"https://example.com/{competitors[1].lower()}-features",
                    snippet=f"{competitors[1]} 突出强调广泛集成能力和工作流仪表盘。",
                    confidence=0.76,
                )
            )
        diagnostics["evidence_count"] = len(evidence)
        return CollectorOutput(evidence=evidence, diagnostics=diagnostics)

    @staticmethod
    @staticmethod
    def _snippet(title: str, snippet: str) -> str:
        text = f"{title}: {snippet}" if title and title not in snippet else snippet
        return text[:500]

    @staticmethod
    def _confidence_for_result(url: str, snippet: str, score: float | None = None) -> float:
        host = urlparse(url).netloc.lower()
        path = urlparse(url).path.lower()
        if any(token in host for token in ("official", "docs.", "developer.", "support.", "help.")) or any(
            token in path for token in ("pricing", "product", "features", "docs", "help")
        ):
            return 0.9
        if len(snippet.strip()) < 30:
            return 0.4
        if score is not None:
            return max(0.6, min(0.9, 0.6 + float(score) * 0.3))
        if any(token in host for token in ("wikipedia.org", "gartner.", "forrester.", "techcrunch.", "theverge.", "36kr.", "infoq.")):
            return 0.75
        return 0.6
