from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents.runner import MockWorkflowRunner, default_dag
from app.database import get_db
from app.schemas import CreateTaskRequest
from app.services.evidence_service import EvidenceService
from app.services.llm_client import LlmClient
from app.services.report_service import ReportService
from app.services.task_service import TaskService
from app.services.trace_service import TraceService
from app.services.web_search_client import WebSearchClient

router = APIRouter(prefix="/api")


@router.get("/llm/status")
def llm_status():
    return LlmClient().status()


@router.post("/llm/test")
def test_llm_connection():
    return LlmClient().test_connection()


@router.get("/collector/status")
def collector_status():
    return WebSearchClient().status()


@router.get("/search/status")
def search_status():
    return WebSearchClient().status()


@router.post("/search/test")
def test_search_connection(payload: dict = Body(default_factory=dict)):
    query = payload.get("query") or "飞书 B2B SaaS 功能 定价 官网"
    return WebSearchClient().test_connection(str(query))


@router.post("/tasks")
def create_task(request: CreateTaskRequest, db: Session = Depends(get_db)):
    return TaskService(db).create_task(request)


@router.get("/tasks")
def list_tasks(db: Session = Depends(get_db)):
    return TaskService(db).list_tasks()


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    try:
        return TaskService(db).get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@router.post("/tasks/{task_id}/run")
def run_task(
    task_id: str,
    demo_mode: str = Query("normal", pattern="^(normal|qa_missing_evidence|qa_invalid_extraction|qa_bad_report)$"),
    auto_rework: bool = Query(False),
    writer_mode: str = Query("mock", pattern="^(mock|llm)$"),
    collector_mode: str = Query("mock", pattern="^(mock|web)$"),
    analyst_mode: str = Query("evidence", pattern="^(mock|evidence|llm)$"),
    db: Session = Depends(get_db),
):
    try:
        return MockWorkflowRunner(db).run(
            task_id,
            demo_mode=demo_mode,
            auto_rework=auto_rework,
            writer_mode=writer_mode,
            collector_mode=collector_mode,
            analyst_mode=analyst_mode,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@router.get("/tasks/{task_id}/dag")
def get_dag(task_id: str, db: Session = Depends(get_db)):
    try:
        task = TaskService(db).get_task(task_id)
        return default_dag(task.status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@router.get("/tasks/{task_id}/traces")
def get_traces(task_id: str, db: Session = Depends(get_db)):
    return TraceService(db).list_for_task(task_id)


@router.get("/tasks/{task_id}/evidence")
def get_evidence(task_id: str, db: Session = Depends(get_db)):
    return EvidenceService(db).list_for_task(task_id)


@router.get("/tasks/{task_id}/qa")
def get_qa(task_id: str, db: Session = Depends(get_db)):
    try:
        return ReportService(db).latest_qa(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="QA result not found") from exc


@router.get("/tasks/{task_id}/report")
def get_task_report(task_id: str, db: Session = Depends(get_db)):
    try:
        return ReportService(db).get_latest_for_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc


@router.get("/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    try:
        return ReportService(db).get_report(report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
