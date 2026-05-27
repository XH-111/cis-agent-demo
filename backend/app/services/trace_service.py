import json

from sqlalchemy.orm import Session

from app.db_models import TraceRecordRow
from app.schemas import TraceRecord


class TraceService:
    def __init__(self, db: Session):
        self.db = db
        self.current_run_id: str | None = None

    def set_run_context(self, run_id: str | None) -> None:
        self.current_run_id = run_id

    def save(self, trace: TraceRecord) -> TraceRecord:
        if trace.run_id is None and self.current_run_id:
            trace = trace.model_copy(update={"run_id": self.current_run_id})
        row = TraceRecordRow(
            trace_id=trace.trace_id,
            task_id=trace.task_id,
            run_id=trace.run_id,
            agent_name=trace.agent_name,
            payload_json=trace.model_dump_json(),
        )
        self.db.add(row)
        self.db.commit()
        return trace

    def list_for_task(self, task_id: str, run_id: str | None = None) -> list[TraceRecord]:
        query = self.db.query(TraceRecordRow).filter_by(task_id=task_id)
        if run_id is not None:
            query = query.filter_by(run_id=run_id)
        rows = query.order_by(TraceRecordRow.id.asc()).all()
        return [TraceRecord.model_validate(json.loads(row.payload_json)) for row in rows]
