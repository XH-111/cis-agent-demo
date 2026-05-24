from app.agents.base import run_with_trace
from app.schemas import Claim, QaResult, Report, ReportWriterInput, ReportWriterOutput
from app.services.trace_service import TraceService


class ReportWriterAgent:
    name = "ReportWriterAgent"

    def __init__(self, trace_service: TraceService):
        self.trace_service = trace_service

    def run(self, input_data: ReportWriterInput) -> ReportWriterOutput:
        task = input_data.task
        knowledge = input_data.knowledge

        def produce() -> ReportWriterOutput:
            ids = knowledge.product_profile.evidence_ids
            raw_claims = [
                {
                    "text": f"{task.product_name} 应重点竞争可审计报告生成能力，而不只是原始信息采集。",
                    "category": "positioning",
                    "evidence_ids": [] if input_data.simulate_missing_evidence else ids,
                    "confidence": 0.84,
                },
                {
                    "text": "定价对比应重点关注协作套餐分层和证据治理能力。",
                    "category": "pricing",
                    "evidence_ids": knowledge.pricing_model.evidence_ids,
                    "confidence": 0.8,
                },
                {
                    "text": "核心用户需要更快的可复用工作流，并要求建议能够追溯到来源证据。",
                    "category": "persona",
                    "evidence_ids": knowledge.user_persona.evidence_ids,
                    "confidence": 0.82,
                },
            ]
            if input_data.simulate_missing_evidence:
                return ReportWriterOutput(
                    draft_report={
                        "claims": raw_claims,
                        "markdown": "# 草稿\n\n存在缺少证据绑定的无效结论。",
                    }
                )

            claims = [Claim(**item) for item in raw_claims]
            markdown_lines = [
                f"# 竞品分析报告：{task.product_name}",
                "",
                "## 执行摘要",
                f"{task.product_name} 可以通过结构化输出、QA 打回路由和证据支撑结论形成差异化。",
                "",
                "## 关键结论",
                *[f"- **{claim.claim_id}** {claim.text} 证据：{', '.join(claim.evidence_ids)}" for claim in claims],
            ]
            markdown = "\n".join(markdown_lines)
            if input_data.force_bad_format:
                markdown = "竞品分析报告缺少一级标题\n\n该内容用于演示 QA 对报告格式的打回。"

            qa_placeholder = QaResult(task_id=task.task_id, status="passed")
            report = Report(
                task_id=task.task_id,
                markdown=markdown,
                json_report={
                    "knowledge": knowledge.model_dump(mode="json"),
                    "claims": [claim.model_dump(mode="json") for claim in claims],
                },
                claims=claims,
                qa_result=qa_placeholder,
            )
            return ReportWriterOutput(report=report)

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="QaAgent",
            message_type="report",
            schema_name="ReportWriterOutput",
            input_summary="生成包含 evidence_ids 的 Markdown 和 JSON 报告",
            retry_count=input_data.retry_count,
            fn=produce,
        )
