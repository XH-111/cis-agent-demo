import json

from sqlalchemy.orm import Session

from app.db_models import EvidenceRecordRow, TaskRunRecord
from app.schemas import Evidence


class EvidenceService:
    def __init__(self, db: Session):
        self.db = db

    def save_many(self, task_id: str, evidence: list[Evidence], run_id: str | None = None) -> list[Evidence]:
        saved: list[Evidence] = []
        for item in evidence:
            item_to_save = item.model_copy(update={"run_id": run_id}) if run_id else item
            row = EvidenceRecordRow(
                evidence_id=item_to_save.evidence_id,
                task_id=task_id,
                run_id=run_id,
                payload_json=item_to_save.model_dump_json(),
            )
            self.db.merge(row)
            saved.append(item_to_save)
        self.db.commit()
        return saved

    def list_for_task(self, task_id: str, run_id: str | None = None) -> list[Evidence]:
        if run_id is None:
            latest_run = (
                self.db.query(TaskRunRecord)
                .filter_by(task_id=task_id)
                .order_by(TaskRunRecord.started_at.desc(), TaskRunRecord.created_at.desc())
                .first()
            )
            if latest_run is not None:
                run_id = latest_run.run_id
        query = self.db.query(EvidenceRecordRow).filter_by(task_id=task_id)
        if run_id is not None:
            query = query.filter_by(run_id=run_id)
        rows = query.all()
        return [Evidence.model_validate(json.loads(row.payload_json)) for row in rows]

    def clear_for_task(self, task_id: str) -> int:
        deleted = self.db.query(EvidenceRecordRow).filter_by(task_id=task_id).delete()
        self.db.commit()
        return deleted

    def clear_for_task(self, task_id: str) -> int:
        deleted = self.db.query(EvidenceRecordRow).filter_by(task_id=task_id).delete()
        self.db.commit()
        return deleted
