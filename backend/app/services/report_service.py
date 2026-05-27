import json

from sqlalchemy.orm import Session
from sqlalchemy import literal_column

from app.db_models import QaRecordRow, ReportRecordRow, TaskRunRecord
from app.schemas import QaResult, Report


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    def save_report(self, report: Report, run_id: str | None = None) -> Report:
        report_to_save = report.model_copy(update={"run_id": run_id}) if run_id else report
        row = ReportRecordRow(
            report_id=report_to_save.report_id,
            task_id=report_to_save.task_id,
            run_id=run_id,
            payload_json=report_to_save.model_dump_json(),
        )
        self.db.merge(row)
        self.db.commit()
        return report_to_save

    def get_report(self, report_id: str) -> Report:
        row = self.db.get(ReportRecordRow, report_id)
        if row is None:
            raise KeyError(report_id)
        return Report.model_validate(json.loads(row.payload_json))

    def get_latest_for_task(self, task_id: str) -> Report:
        latest_run = (
            self.db.query(TaskRunRecord)
            .filter_by(task_id=task_id)
            .order_by(TaskRunRecord.started_at.desc(), TaskRunRecord.created_at.desc())
            .first()
        )
        if latest_run is not None:
            return self.get_for_task_run(task_id, latest_run.run_id)
        row = self.db.query(ReportRecordRow).filter_by(task_id=task_id).order_by(literal_column("rowid").desc()).first()
        if row is None:
            raise KeyError(task_id)
        return Report.model_validate(json.loads(row.payload_json))

    def get_for_task_run(self, task_id: str, run_id: str) -> Report:
        row = self.db.query(ReportRecordRow).filter_by(task_id=task_id, run_id=run_id).order_by(literal_column("rowid").desc()).first()
        if row is None:
            raise KeyError(run_id)
        return Report.model_validate(json.loads(row.payload_json))

    def save_qa(self, result: QaResult, run_id: str | None = None) -> QaResult:
        result_to_save = result.model_copy(update={"run_id": run_id}) if run_id else result
        row = QaRecordRow(task_id=result_to_save.task_id, run_id=run_id, payload_json=result_to_save.model_dump_json())
        self.db.add(row)
        self.db.commit()
        return result_to_save

    def latest_qa(self, task_id: str) -> QaResult:
        latest_run = (
            self.db.query(TaskRunRecord)
            .filter_by(task_id=task_id)
            .order_by(TaskRunRecord.started_at.desc(), TaskRunRecord.created_at.desc())
            .first()
        )
        if latest_run is not None:
            return self.qa_for_task_run(task_id, latest_run.run_id)
        row = self.db.query(QaRecordRow).filter_by(task_id=task_id).order_by(QaRecordRow.id.desc()).first()
        if row is None:
            raise KeyError(task_id)
        return QaResult.model_validate(json.loads(row.payload_json))

    def qa_for_task_run(self, task_id: str, run_id: str) -> QaResult:
        row = self.db.query(QaRecordRow).filter_by(task_id=task_id, run_id=run_id).order_by(QaRecordRow.id.desc()).first()
        if row is None:
            raise KeyError(run_id)
        return QaResult.model_validate(json.loads(row.payload_json))

    def clear_for_task(self, task_id: str) -> dict[str, int]:
        reports = self.db.query(ReportRecordRow).filter_by(task_id=task_id).delete()
        qa_results = self.db.query(QaRecordRow).filter_by(task_id=task_id).delete()
        self.db.commit()
        return {"reports": reports, "qa_results": qa_results}
