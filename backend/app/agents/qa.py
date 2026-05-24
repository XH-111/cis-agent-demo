from app.agents.base import run_with_trace
from app.schemas import QaInput, QaOutput, QaResult, ReworkInstruction
from app.services.trace_service import TraceService

MAX_REWORK = 3


class QaAgent:
    name = "QaAgent"

    def __init__(self, trace_service: TraceService):
        self.trace_service = trace_service

    def _result(
        self,
        task_id: str,
        rework_count: int,
        target_agent: str,
        error_type: str,
        reason: str,
        suggested_action: str,
        claim_id: str | None = None,
        failed_claim: str | None = None,
        failed_schema: str | None = None,
    ) -> QaResult:
        if rework_count >= MAX_REWORK:
            return QaResult(
                task_id=task_id,
                status="manual_review",
                hard_errors=[reason],
                route_to=None,
                rework_count=rework_count,
                rework_instructions=[
                    ReworkInstruction(
                        target_agent=target_agent,
                        error_type=error_type,
                        reason=reason,
                        suggested_action="已超过最大返工次数，请人工复核。",
                        claim_id=claim_id,
                        failed_claim=failed_claim,
                        failed_schema=failed_schema,
                    )
                ],
            )

        return QaResult(
            task_id=task_id,
            status="failed",
            hard_errors=[reason],
            rework_instructions=[
                ReworkInstruction(
                    target_agent=target_agent,
                    error_type=error_type,
                    reason=reason,
                    suggested_action=suggested_action,
                    claim_id=claim_id,
                    failed_claim=failed_claim,
                    failed_schema=failed_schema,
                )
            ],
            route_to=target_agent,
            rework_count=rework_count + 1,
        )

    def evaluate(self, input_data: QaInput) -> QaResult:
        task = input_data.task
        rework_count = task.rework_count

        if input_data.demo_mode == "qa_missing_evidence" or not input_data.evidence:
            return self._result(
                task.task_id,
                rework_count,
                "CollectorAgent",
                "missing_evidence",
                "当前任务没有可用 Evidence，无法支撑后续分析和报告结论。",
                "请重新运行 CollectorAgent，补充至少一条带 url 或 local_ref 的 Evidence。",
                failed_schema="Evidence",
            )

        if input_data.analysis is None:
            return self._result(
                task.task_id,
                rework_count,
                "AnalystAgent",
                "invalid_extraction",
                "缺少 AnalystAgent 的结构化分析输出。",
                "请重新运行 AnalystAgent，生成 ProductProfile、FeatureTree、PricingModel 和 UserPersona。",
                failed_schema="AnalystOutput",
            )

        profile = input_data.analysis.product_profile
        if input_data.demo_mode == "qa_invalid_extraction" or not profile.positioning or not profile.target_segments:
            return self._result(
                task.task_id,
                rework_count,
                "AnalystAgent",
                "invalid_extraction",
                "ProductProfile 关键字段为空，疑似抽取错误或结构化结果冲突。",
                "请重新运行 AnalystAgent，修复 ProductProfile 的 positioning 和 target_segments。",
                failed_schema="ProductProfile",
            )

        if input_data.report_output is None:
            return self._result(
                task.task_id,
                rework_count,
                "ReportWriterAgent",
                "bad_report_format",
                "缺少 ReportWriterAgent 的报告输出。",
                "请重新运行 ReportWriterAgent，生成 Markdown 和 JSON 报告。",
                failed_schema="ReportWriterOutput",
            )

        if input_data.report_output.draft_report:
            for claim in input_data.report_output.draft_report.get("claims", []):
                if not claim.get("evidence_ids"):
                    return self._result(
                        task.task_id,
                        rework_count,
                        "ReportWriterAgent",
                        "bad_report_format",
                        "报告草稿中存在未绑定 evidence_ids 的结论。",
                        "请为该结论补充明确的 evidence_ids，或删除无法被证据支撑的结论。",
                        failed_claim=claim.get("text"),
                    )

        if input_data.report_output.report is None:
            return self._result(
                task.task_id,
                rework_count,
                "ReportWriterAgent",
                "bad_report_format",
                "报告输出为空，无法进入最终报告阶段。",
                "请重新生成包含 markdown_report、json_report 和 claims 的报告对象。",
                failed_schema="Report",
            )

        report = input_data.report_output.report
        if input_data.demo_mode == "qa_bad_report" or not report.markdown.startswith("#"):
            return self._result(
                task.task_id,
                rework_count,
                "ReportWriterAgent",
                "bad_report_format",
                "Markdown 报告必须以一级标题开头。",
                "请重新生成包含一级标题和关键结论章节的 Markdown 报告。",
                failed_schema="Report.markdown",
            )

        for claim in report.claims:
            if not claim.evidence_ids:
                return self._result(
                    task.task_id,
                    rework_count,
                    "ReportWriterAgent",
                    "bad_report_format",
                    f"结论 {claim.claim_id} 缺少 evidence_ids。",
                    "请为每条关键结论绑定 evidence_ids。",
                    claim_id=claim.claim_id,
                    failed_claim=claim.text,
                )

        return QaResult(
            task_id=task.task_id,
            status="passed",
            soft_suggestions=[
                suggestion
                for suggestion in [
                    "生产环境接入前，请将 Mock 证据替换为真实采集器输出。",
                    input_data.report_output.llm_fallback_reason if input_data.report_output else None,
                ]
                if suggestion
            ],
            rework_count=rework_count,
        )

    def run(self, input_data: QaInput) -> QaOutput:
        task = input_data.task

        def produce() -> QaOutput:
            return QaOutput(qa_result=self.evaluate(input_data))

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="FinalReport",
            message_type="qa",
            schema_name="QaOutput",
            input_summary="校验 Schema、证据覆盖和报告格式",
            retry_count=input_data.retry_count,
            fn=produce,
        )
