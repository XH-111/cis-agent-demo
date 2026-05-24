from app.agents.base import run_with_trace
from app.schemas import QaResult, Report, ReworkInstruction, Task
from app.services.trace_service import TraceService

MAX_REWORK = 3


class QaAgent:
    name = "QaAgent"

    def __init__(self, trace_service: TraceService):
        self.trace_service = trace_service

    def evaluate_report_payload(self, task_id: str, payload: dict, rework_count: int = 0) -> QaResult:
        draft = payload.get("draft_report")
        if draft:
            claims = draft.get("claims", [])
            for claim in claims:
                if not claim.get("evidence_ids"):
                    return self._result(
                        task_id,
                        rework_count,
                        "ReportWriterAgent",
                        "missing_evidence",
                        "草稿结论缺少 evidence_ids。",
                        "请为该结论补充明确的 evidence_ids，或删除无法被证据支撑的结论。",
                    )

        report_data = payload.get("report", payload)
        report = Report.model_validate(report_data)
        if not report.markdown.startswith("#"):
            return self._result(
                task_id,
                rework_count,
                "ReportWriterAgent",
                "bad_report_format",
                "Markdown 报告必须以一级标题开头。",
                "请重新生成包含一级标题和关键结论章节的 Markdown 报告。",
            )
        for claim in report.claims:
            if not claim.evidence_ids:
                return self._result(
                    task_id,
                    rework_count,
                    "ReportWriterAgent",
                    "missing_evidence",
                    f"结论 {claim.claim_id} 缺少 evidence_ids。",
                    "请为每条关键结论绑定 evidence_ids。",
                    claim_id=claim.claim_id,
                )
        return QaResult(
            task_id=task_id,
            status="passed",
            soft_suggestions=["生产环境接入前，请将 Mock 证据替换为真实采集器输出。"],
            rework_count=rework_count,
        )

    def _result(
        self,
        task_id: str,
        rework_count: int,
        target_agent: str,
        error_type: str,
        reason: str,
        suggested_action: str,
        claim_id: str | None = None,
    ) -> QaResult:
        if rework_count >= MAX_REWORK:
            return QaResult(
                task_id=task_id,
                status="manual_review",
                hard_errors=[reason],
                route_to=None,
                rework_count=rework_count,
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
                )
            ],
            route_to=target_agent,
            rework_count=rework_count + 1,
        )

    def run(self, task: Task, payload: dict, retry_count: int = 0) -> dict:
        def produce() -> dict:
            result = self.evaluate_report_payload(task.task_id, payload, task.rework_count)
            return {"qa_result": result.model_dump(mode="json")}

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="FinalReport",
            message_type="qa",
            schema_name="QaResult",
            input_summary="校验 Schema、证据覆盖和报告格式",
            retry_count=retry_count,
            fn=produce,
        )
