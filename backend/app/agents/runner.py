from sqlalchemy.orm import Session

from app.agents.analyst import AnalystAgent
from app.agents.collector import CollectorAgent
from app.agents.final_report import FinalReportAgent
from app.agents.planner import PlannerAgent
from app.agents.qa import QaAgent
from app.agents.report_writer import ReportWriterAgent
from app.schemas import (
    AnalystInput,
    CollectorInput,
    DemoMode,
    FinalReportInput,
    PlannerInput,
    QaInput,
    QaResult,
    ReportWriterInput,
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

    def run(self, task_id: str, demo_mode: DemoMode = "normal") -> dict:
        task = self.task_service.update_status(task_id, "running")
        plan = self.planner.run(PlannerInput(task=task))

        if demo_mode == "qa_missing_evidence":
            qa_output = self.qa.run(QaInput(task=task, evidence=[], demo_mode=demo_mode))
            qa_result = qa_output.qa_result
            self.report_service.save_qa(qa_result)
            self.task_service.update_status(task_id, self._status_for_qa(qa_result), rework_count=qa_result.rework_count)
            return {"plan": plan, "qa_result": qa_result, "report": None}

        collector_output = self.collector.run(CollectorInput(task=task))
        evidence = collector_output.evidence
        self.evidence_service.save_many(task.task_id, evidence)

        analysis = self.analyst.run(
            AnalystInput(
                task=task,
                evidence=evidence,
                force_invalid_extraction=demo_mode == "qa_invalid_extraction",
            )
        )

        writer_output = self.writer.run(
            ReportWriterInput(
                task=task,
                knowledge=analysis,
                force_bad_format=demo_mode == "qa_bad_report",
            )
        )

        qa_output = self.qa.run(
            QaInput(
                task=task,
                evidence=evidence,
                analysis=analysis,
                report_output=writer_output,
                demo_mode=demo_mode,
            )
        )
        qa_result = qa_output.qa_result
        self.report_service.save_qa(qa_result)

        if demo_mode != "normal":
            self.task_service.update_status(task_id, self._status_for_qa(qa_result), rework_count=qa_result.rework_count)
            return {"plan": plan, "qa_result": qa_result, "report": None}

        if qa_result.status == "failed" and qa_result.route_to == "ReportWriterAgent":
            task = self.task_service.update_status(task_id, "qa_failed", rework_count=qa_result.rework_count)
            fixed_output = self.writer.run(
                ReportWriterInput(task=task, knowledge=analysis, retry_count=qa_result.rework_count)
            )
            qa_output = self.qa.run(
                QaInput(
                    task=task,
                    evidence=evidence,
                    analysis=analysis,
                    report_output=fixed_output,
                    retry_count=qa_result.rework_count,
                )
            )
            qa_result = qa_output.qa_result
            self.report_service.save_qa(qa_result)
            writer_output = fixed_output

        if qa_result.status == "passed" and writer_output.report is not None:
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
            self.task_service.update_status(task_id, "completed", rework_count=qa_result.rework_count)
            return {"plan": plan, "qa_result": qa_result, "report": final_output.report}

        self.task_service.update_status(task_id, self._status_for_qa(qa_result), rework_count=qa_result.rework_count)
        return {"plan": plan, "qa_result": qa_result, "report": None}

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
