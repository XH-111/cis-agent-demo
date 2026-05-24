import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db_models  # noqa: F401
from app.agents.analyst import AnalystAgent
from app.agents.collector import CollectorAgent
from app.agents.planner import PlannerAgent
from app.agents.qa import QaAgent
from app.agents.report_writer import ReportWriterAgent
from app.database import Base
from app.schemas import AgentMessage, Claim, CreateTaskRequest, Evidence, QaResult
from app.services.task_service import TaskService
from app.services.trace_service import TraceService


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def make_task(db_session):
    return TaskService(db_session).create_task(
        CreateTaskRequest(
            product_name="CIS Demo",
            competitors=["AlphaCI", "BetaIntel"],
            region="China",
            industry="B2B SaaS",
        )
    )


def test_claim_requires_evidence_ids():
    with pytest.raises(ValidationError):
        Claim(text="Unsupported claim", category="feature", evidence_ids=[], confidence=0.5)


def test_evidence_requires_url_or_local_ref():
    with pytest.raises(ValidationError):
        Evidence(source_type="web", snippet="Missing source reference", confidence=0.7)


def test_agent_message_requires_trace_and_task_id():
    with pytest.raises(ValidationError):
        AgentMessage(
            trace_id="",
            task_id="",
            from_agent="PlannerAgent",
            to_agent="CollectorAgent",
            message_type="plan",
            schema_name="Dag",
            payload={},
        )


def test_qa_routes_missing_evidence_to_report_writer(db_session):
    task = make_task(db_session)
    qa = QaAgent(TraceService(db_session))
    result = qa.evaluate_report_payload(
        task.task_id,
        {"draft_report": {"claims": [{"text": "Missing evidence", "category": "feature", "evidence_ids": []}]}},
    )
    assert result.status == "failed"
    assert result.route_to == "ReportWriterAgent"
    assert result.rework_instructions[0].error_type == "missing_evidence"


def test_qa_can_route_missing_collection_evidence_to_collector(db_session):
    task = make_task(db_session)
    qa = QaAgent(TraceService(db_session))
    result = qa._result(
        task.task_id,
        rework_count=0,
        target_agent="CollectorAgent",
        error_type="missing_evidence",
        reason="No pricing source was collected.",
        suggested_action="Collect pricing page evidence.",
    )
    assert result.route_to == "CollectorAgent"


def test_max_rework_becomes_manual_review(db_session):
    task = make_task(db_session)
    qa = QaAgent(TraceService(db_session))
    result = qa._result(
        task.task_id,
        rework_count=3,
        target_agent="ReportWriterAgent",
        error_type="bad_report_format",
        reason="Still malformed.",
        suggested_action="Manual review required.",
    )
    assert result.status == "manual_review"
    assert result.route_to is None


def test_each_agent_execution_creates_trace(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    planner = PlannerAgent(trace_service)
    collector = CollectorAgent(trace_service)
    analyst = AnalystAgent(trace_service)
    writer = ReportWriterAgent(trace_service)
    qa = QaAgent(trace_service)

    planner.run(task)
    collected = collector.run(task)
    evidence = [Evidence.model_validate(item) for item in collected["evidence"]]
    knowledge = analyst.run(task, evidence)
    report = writer.run(task, knowledge)
    qa_payload = qa.run(task, report)

    assert QaResult.model_validate(qa_payload["qa_result"]).status == "passed"
    traces = trace_service.list_for_task(task.task_id)
    assert {trace.agent_name for trace in traces} == {
        "PlannerAgent",
        "CollectorAgent",
        "AnalystAgent",
        "ReportWriterAgent",
        "QaAgent",
    }
    assert all(trace.schema_validation_result == "passed" for trace in traces)
