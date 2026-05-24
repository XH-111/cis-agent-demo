import json

from sqlalchemy.orm import Session

from app.db_models import EvidenceRecordRow
from app.schemas import Evidence


class EvidenceService:
    def __init__(self, db: Session):
        self.db = db

    def save_many(self, task_id: str, evidence: list[Evidence]) -> list[Evidence]:
        for item in evidence:
            row = EvidenceRecordRow(
                evidence_id=item.evidence_id,
                task_id=task_id,
                payload_json=item.model_dump_json(),
            )
            self.db.merge(row)
        self.db.commit()
        return evidence

    def list_for_task(self, task_id: str) -> list[Evidence]:
        rows = self.db.query(EvidenceRecordRow).filter_by(task_id=task_id).all()
        return [Evidence.model_validate(json.loads(row.payload_json)) for row in rows]
