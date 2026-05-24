from app.agents.base import run_with_trace
from app.schemas import FinalReportInput, FinalReportOutput, Report
from app.services.trace_service import TraceService


class FinalReportAgent:
    name = "FinalReport"

    def __init__(self, trace_service: TraceService):
        self.trace_service = trace_service

    def run(self, input_data: FinalReportInput) -> FinalReportOutput:
        task = input_data.task

        def produce() -> FinalReportOutput:
            evidence_summary = [
                f"{item.evidence_id}: {item.source_type} / {item.url or item.local_ref} / 置信度 {item.confidence:.2f}"
                for item in input_data.evidence
            ]
            report = Report.model_validate(input_data.report.model_dump(mode="json"))
            report.qa_result = input_data.qa_result
            report.json_report["qa_result"] = input_data.qa_result.model_dump(mode="json")
            report.json_report["evidence_summary"] = evidence_summary
            return FinalReportOutput(report=report, evidence_summary=evidence_summary)

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="FinalReport",
            message_type="final",
            schema_name="FinalReportOutput",
            input_summary="整合报告、QA 结果和证据摘要，生成最终报告对象",
            retry_count=input_data.retry_count,
            fn=produce,
        )
