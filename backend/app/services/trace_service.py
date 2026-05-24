import json

from sqlalchemy.orm import Session

from app.db_models import TraceRecordRow
from app.schemas import TraceRecord


class TraceService:
    def __init__(self, db: Session):
        self.db = db

    def save(self, trace: TraceRecord) -> TraceRecord:
        row = TraceRecordRow(
            trace_id=trace.trace_id,
            task_id=trace.task_id,
            agent_name=trace.agent_name,
            payload_json=trace.model_dump_json(),
        )
        self.db.add(row)
        self.db.commit()
        return trace

    def list_for_task(self, task_id: str) -> list[TraceRecord]:
        rows = self.db.query(TraceRecordRow).filter_by(task_id=task_id).order_by(TraceRecordRow.id.asc()).all()
        return [TraceRecord.model_validate(json.loads(row.payload_json)) for row in rows]
