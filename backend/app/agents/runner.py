from sqlalchemy.orm import Session

from app.agents.analyst import AnalystAgent
from app.agents.collector import CollectorAgent
from app.agents.planner import PlannerAgent
from app.agents.qa import QaAgent
from app.agents.report_writer import ReportWriterAgent
from app.schemas import Evidence, QaResult, Report
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

    def run(self, task_id: str) -> dict:
        task = self.task_service.update_status(task_id, "running")
        plan = self.planner.run(task)

        collector_output = self.collector.run(task)
        evidence = [Evidence.model_validate(item) for item in collector_output["evidence"]]
        self.evidence_service.save_many(task.task_id, evidence)

        knowledge = self.analyst.run(task, evidence)

        # 首版草稿故意触发 QA 打回，用于演示反馈闭环。
        draft = self.writer.run(task, knowledge, simulate_missing_evidence=True)
        qa_payload = self.qa.run(task, draft)
        qa_result = QaResult.model_validate(qa_payload["qa_result"])
        self.report_service.save_qa(qa_result)

        if qa_result.status == "failed" and qa_result.route_to == "ReportWriterAgent":
            task = self.task_service.update_status(task_id, "qa_failed", rework_count=qa_result.rework_count)
            fixed = self.writer.run(task, knowledge, retry_count=qa_result.rework_count)
            qa_payload = self.qa.run(task, fixed, retry_count=qa_result.rework_count)
            qa_result = QaResult.model_validate(qa_payload["qa_result"])
            self.report_service.save_qa(qa_result)
            if qa_result.status == "passed":
                report = Report.model_validate(fixed["report"])
                report.qa_result = qa_result
                self.report_service.save_report(report)
                self.task_service.update_status(task_id, "completed", rework_count=qa_result.rework_count)
                return {"plan": plan, "qa_result": qa_result, "report": report}

        if qa_result.status == "manual_review":
            self.task_service.update_status(task_id, "manual_review", rework_count=qa_result.rework_count)
        else:
            self.task_service.update_status(task_id, "failed", rework_count=qa_result.rework_count)
        return {"plan": plan, "qa_result": qa_result, "report": None}


def default_dag(status: str) -> dict:
    completed = status == "completed"
    manual = status == "manual_review"
    return {
        "nodes": [
            {"id": "PlannerAgent", "label": "规划任务范围和 DAG", "status": "completed" if status != "created" else "pending"},
            {"id": "CollectorAgent", "label": "采集 Mock 证据", "status": "completed" if completed or manual else "pending"},
            {"id": "AnalystAgent", "label": "抽取结构化竞品知识", "status": "completed" if completed or manual else "pending"},
            {"id": "ReportWriterAgent", "label": "撰写带证据报告", "status": "completed" if completed else "pending"},
            {"id": "QaAgent", "label": "校验输出质量", "status": "completed" if completed else ("manual_review" if manual else "pending")},
            {"id": "FinalReport", "label": "最终报告", "status": "completed" if completed else ("manual_review" if manual else "pending")},
        ],
        "edges": [
            {"source": "PlannerAgent", "target": "CollectorAgent", "label": "计划"},
            {"source": "CollectorAgent", "target": "AnalystAgent", "label": "证据"},
            {"source": "AnalystAgent", "target": "ReportWriterAgent", "label": "知识"},
            {"source": "ReportWriterAgent", "target": "QaAgent", "label": "草稿"},
            {"source": "QaAgent", "target": "FinalReport", "label": "通过"},
            {"source": "QaAgent", "target": "ReportWriterAgent", "label": "返工"},
        ],
    }
