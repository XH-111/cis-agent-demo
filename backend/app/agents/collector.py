from app.agents.base import run_with_trace
from app.schemas import Evidence, Task
from app.services.trace_service import TraceService


class CollectorAgent:
    name = "CollectorAgent"

    def __init__(self, trace_service: TraceService):
        self.trace_service = trace_service

    def run(self, task: Task, retry_count: int = 0) -> dict:
        def produce() -> dict:
            competitors = task.competitors[:2]
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
            return {"evidence": [item.model_dump(mode="json") for item in evidence]}

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="AnalystAgent",
            message_type="evidence",
            schema_name="list[Evidence]",
            input_summary=f"为 {task.region} 的 {task.industry} 场景采集 3-5 条 Mock 来源",
            retry_count=retry_count,
            fn=produce,
        )
