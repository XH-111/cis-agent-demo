import json

from sqlalchemy.orm import Session

from app.db_models import QaRecordRow, ReportRecordRow
from app.schemas import QaResult, Report


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    def save_report(self, report: Report) -> Report:
        row = ReportRecordRow(
            report_id=report.report_id,
            task_id=report.task_id,
            payload_json=report.model_dump_json(),
        )
        self.db.merge(row)
        self.db.commit()
        return report

    def get_report(self, report_id: str) -> Report:
        row = self.db.get(ReportRecordRow, report_id)
        if row is None:
            raise KeyError(report_id)
        return Report.model_validate(json.loads(row.payload_json))

    def get_latest_for_task(self, task_id: str) -> Report:
        row = self.db.query(ReportRecordRow).filter_by(task_id=task_id).order_by(ReportRecordRow.report_id.desc()).first()
        if row is None:
            raise KeyError(task_id)
        return Report.model_validate(json.loads(row.payload_json))

    def save_qa(self, result: QaResult) -> QaResult:
        row = QaRecordRow(task_id=result.task_id, payload_json=result.model_dump_json())
        self.db.add(row)
        self.db.commit()
        return result

    def latest_qa(self, task_id: str) -> QaResult:
        row = self.db.query(QaRecordRow).filter_by(task_id=task_id).order_by(QaRecordRow.id.desc()).first()
        if row is None:
            raise KeyError(task_id)
        return QaResult.model_validate(json.loads(row.payload_json))
