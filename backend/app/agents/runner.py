from sqlalchemy.orm import Session

from app.agents.analyst import AnalystAgent
from app.agents.collector import CollectorAgent
from app.agents.final_report import FinalReportAgent
from app.agents.planner import PlannerAgent
from app.agents.qa import QaAgent
from app.agents.report_writer import ReportWriterAgent
from app.schemas import (
    AnalystInput,
    AnalystOutput,
    CollectorInput,
    DemoMode,
    Evidence,
    FinalReportInput,
    PlannerInput,
    PlannerOutput,
    QaInput,
    QaResult,
    ReportWriterInput,
    ReportWriterOutput,
    ReworkHistoryItem,
    Task,
)
from app.services.evidence_service import EvidenceService
from app.services.report_service import ReportService
from app.services.task_service import TaskService
from app.services.trace_service import TraceService


class MockWorkflowRunner:
    def __init__(self, db: Session):
        self.db = db
        self.task_service = TaskService(db)
        self.trace_service = TraceService(db)
        self.evidence_service = EvidenceService(db)
        self.report_service = ReportService(db)
        self.planner = PlannerAgent(self.trace_service)
        self.collector = CollectorAgent(self.trace_service)
        self.analyst = AnalystAgent(self.trace_service)
        self.writer = ReportWriterAgent(self.trace_service)
        self.qa = QaAgent(self.trace_service)
        self.final_report = FinalReportAgent(self.trace_service)

    def run(
        self,
        task_id: str,
        demo_mode: DemoMode = "normal",
        auto_rework: bool = False,
        writer_mode: str = "mock",
    ) -> dict:
        task = self.task_service.update_status(task_id, "running")
        plan = self.planner.run(PlannerInput(task=task))
        history: list[ReworkHistoryItem] = []

        if demo_mode == "qa_missing_evidence":
            qa_result = self.qa.run(QaInput(task=task, evidence=[], demo_mode=demo_mode)).qa_result
            self._save_qa(qa_result, history)
            if not auto_rework:
                self.task_service.update_status(task_id, self._status_for_qa(qa_result), rework_count=qa_result.rework_count)
                return {"plan": plan, "qa_result": qa_result, "report": None}
            return self._auto_rework(
                task=task,
                plan=plan,
                qa_result=qa_result,
                history=history,
                evidence=[],
                analysis=None,
                writer_output=None,
                writer_mode=writer_mode,
            )

        evidence, analysis, writer_output = self._produce_outputs(
            task=task,
            demo_mode=demo_mode,
            retry_count=0,
            writer_mode=writer_mode,
        )

        qa_result = self.qa.run(
            QaInput(
                task=task,
                evidence=evidence,
                analysis=analysis,
                report_output=writer_output,
                demo_mode=demo_mode,
            )
        ).qa_result
        self._save_qa(qa_result, history)

        if demo_mode != "normal" and not auto_rework:
            self.task_service.update_status(task_id, self._status_for_qa(qa_result), rework_count=qa_result.rework_count)
            return {"plan": plan, "qa_result": qa_result, "report": None}

        if qa_result.status == "failed" and auto_rework:
            return self._auto_rework(
                task=task,
                plan=plan,
                qa_result=qa_result,
                history=history,
                evidence=evidence,
                analysis=analysis,
                writer_output=writer_output,
                writer_mode=writer_mode,
            )

        return self._finalize_or_fail(task, plan, qa_result, history, evidence, writer_output)

    def _produce_outputs(
        self,
        *,
        task: Task,
        demo_mode: DemoMode,
        retry_count: int,
        writer_mode: str,
        evidence: list[Evidence] | None = None,
        analysis: AnalystOutput | None = None,
    ) -> tuple[list[Evidence], AnalystOutput, ReportWriterOutput]:
        if evidence is None:
            collector_output = self.collector.run(CollectorInput(task=task, retry_count=retry_count))
            evidence = collector_output.evidence
            self.evidence_service.save_many(task.task_id, evidence)

        if analysis is None:
            analysis = self.analyst.run(
                AnalystInput(
                    task=task,
                    evidence=evidence,
                    retry_count=retry_count,
                    force_invalid_extraction=demo_mode == "qa_invalid_extraction",
                )
            )

        writer_output = self.writer.run(
            ReportWriterInput(
                task=task,
                knowledge=analysis,
                evidence=evidence,
                retry_count=retry_count,
                force_bad_format=demo_mode == "qa_bad_report",
                writer_mode=writer_mode,
            )
        )
        return evidence, analysis, writer_output

    def _auto_rework(
        self,
        *,
        task: Task,
        plan: PlannerOutput,
        qa_result: QaResult,
        history: list[ReworkHistoryItem],
        evidence: list[Evidence],
        analysis: AnalystOutput | None,
        writer_output: ReportWriterOutput | None,
        writer_mode: str,
    ) -> dict:
        current_task = task
        current_qa = qa_result
        current_evidence = evidence
        current_analysis = analysis
        current_writer_output = writer_output

        while current_qa.status == "failed":
            instruction = current_qa.rework_instructions[0] if current_qa.rework_instructions else None
            if instruction is None or current_qa.route_to is None:
                break

            history_item = ReworkHistoryItem(
                round=current_qa.rework_count,
                from_status=current_qa.status,
                error_type=instruction.error_type,
                route_to=current_qa.route_to,
                action=instruction.suggested_action,
            )
            history.append(history_item)

            current_task = self.task_service.update_status(
                current_task.task_id,
                "qa_failed",
                rework_count=current_qa.rework_count,
            )

            if current_qa.route_to == "CollectorAgent":
                collector_output = self.collector.run(
                    CollectorInput(task=current_task, retry_count=current_qa.rework_count)
                )
                current_evidence = collector_output.evidence
                self.evidence_service.save_many(current_task.task_id, current_evidence)
                current_analysis = self.analyst.run(
                    AnalystInput(task=current_task, evidence=current_evidence, retry_count=current_qa.rework_count)
                )
                current_writer_output = self.writer.run(
                    ReportWriterInput(
                        task=current_task,
                        knowledge=current_analysis,
                        evidence=current_evidence,
                        retry_count=current_qa.rework_count,
                        writer_mode=writer_mode,
                    )
                )
            elif current_qa.route_to == "AnalystAgent":
                current_analysis = self.analyst.run(
                    AnalystInput(task=current_task, evidence=current_evidence, retry_count=current_qa.rework_count)
                )
                current_writer_output = self.writer.run(
                    ReportWriterInput(
                        task=current_task,
                        knowledge=current_analysis,
                        evidence=current_evidence,
                        retry_count=current_qa.rework_count,
                        writer_mode=writer_mode,
                    )
                )
            elif current_qa.route_to == "ReportWriterAgent":
                if current_analysis is None:
                    current_analysis = self.analyst.run(
                        AnalystInput(task=current_task, evidence=current_evidence, retry_count=current_qa.rework_count)
                    )
                current_writer_output = self.writer.run(
                    ReportWriterInput(
                        task=current_task,
                        knowledge=current_analysis,
                        evidence=current_evidence,
                        retry_count=current_qa.rework_count,
                        writer_mode=writer_mode,
                    )
                )
            else:
                break

            current_qa = self.qa.run(
                QaInput(
                    task=current_task,
                    evidence=current_evidence,
                    analysis=current_analysis,
                    report_output=current_writer_output,
                    retry_count=current_task.rework_count,
                    demo_mode="normal",
                )
            ).qa_result
            history[-1].result_status = current_qa.status
            self._save_qa(current_qa, history)

        return self._finalize_or_fail(
            current_task,
            plan,
            current_qa,
            history,
            current_evidence,
            current_writer_output,
        )

    def _finalize_or_fail(
        self,
        task: Task,
        plan: PlannerOutput,
        qa_result: QaResult,
        history: list[ReworkHistoryItem],
        evidence: list[Evidence],
        writer_output: ReportWriterOutput | None,
    ) -> dict:
        qa_result.rework_history = history

        if qa_result.status == "passed" and writer_output is not None and writer_output.report is not None:
            final_output = self.final_report.run(
                FinalReportInput(
                    task=task,
                    report=writer_output.report,
                    qa_result=qa_result,
                    evidence=evidence,
                    retry_count=qa_result.rework_count,
                )
            )
            self.report_service.save_report(final_output.report)
            self.task_service.update_status(task.task_id, "completed", rework_count=qa_result.rework_count)
            self._save_qa(qa_result, history)
            return {"plan": plan, "qa_result": qa_result, "report": final_output.report}

        self.task_service.update_status(task.task_id, self._status_for_qa(qa_result), rework_count=qa_result.rework_count)
        self._save_qa(qa_result, history)
        return {"plan": plan, "qa_result": qa_result, "report": None}

    def _save_qa(self, qa_result: QaResult, history: list[ReworkHistoryItem]) -> None:
        qa_result.rework_history = list(history)
        self.report_service.save_qa(qa_result)

    @staticmethod
    def _status_for_qa(qa_result: QaResult) -> str:
        if qa_result.status == "manual_review":
            return "manual_review"
        if qa_result.status == "failed":
            return "qa_failed"
        return "completed"


def default_dag(status: str) -> dict:
    completed = status == "completed"
    manual = status == "manual_review"
    active = status in {"running", "qa_failed", "completed", "manual_review"}
    return {
        "nodes": [
            {"id": "PlannerAgent", "label": "规划任务范围和 DAG", "status": "completed" if active else "pending"},
            {"id": "CollectorAgent", "label": "采集 Mock 证据", "status": "completed" if completed or manual else ("completed" if status == "qa_failed" else "pending")},
            {"id": "AnalystAgent", "label": "抽取结构化竞品知识", "status": "completed" if completed or manual else ("completed" if status == "qa_failed" else "pending")},
            {"id": "ReportWriterAgent", "label": "撰写带证据报告", "status": "completed" if completed else ("failed" if status == "qa_failed" else "pending")},
            {"id": "QaAgent", "label": "校验输出质量", "status": "completed" if completed else ("manual_review" if manual else ("failed" if status == "qa_failed" else "pending"))},
            {"id": "FinalReport", "label": "最终报告", "status": "completed" if completed else ("manual_review" if manual else "pending")},
        ],
        "edges": [
            {"source": "PlannerAgent", "target": "CollectorAgent", "label": "计划"},
            {"source": "CollectorAgent", "target": "AnalystAgent", "label": "证据"},
            {"source": "AnalystAgent", "target": "ReportWriterAgent", "label": "知识"},
            {"source": "ReportWriterAgent", "target": "QaAgent", "label": "草稿"},
            {"source": "QaAgent", "target": "FinalReport", "label": "通过"},
            {"source": "QaAgent", "target": "CollectorAgent", "label": "缺少证据"},
            {"source": "QaAgent", "target": "AnalystAgent", "label": "抽取错误"},
            {"source": "QaAgent", "target": "ReportWriterAgent", "label": "返工"},
        ],
    }
