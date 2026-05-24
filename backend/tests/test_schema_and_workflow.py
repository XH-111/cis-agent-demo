import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db_models  # noqa: F401
from app.agents.analyst import AnalystAgent
from app.agents.collector import CollectorAgent
from app.agents.final_report import FinalReportAgent
from app.agents.planner import PlannerAgent
from app.agents.qa import QaAgent
from app.agents.report_writer import ReportWriterAgent
from app.agents.runner import MockWorkflowRunner
from app.database import Base
from app.schemas import (
    AgentMessage,
    AnalystInput,
    AnalystOutput,
    Claim,
    CollectorInput,
    CollectorOutput,
    CreateTaskRequest,
    Evidence,
    FinalReportInput,
    FinalReportOutput,
    PlannerInput,
    PlannerOutput,
    QaInput,
    QaOutput,
    ReportWriterInput,
    ReportWriterOutput,
)
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


def build_agent_outputs(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    planner = PlannerAgent(trace_service)
    collector = CollectorAgent(trace_service)
    analyst = AnalystAgent(trace_service)
    writer = ReportWriterAgent(trace_service)
    qa = QaAgent(trace_service)

    plan = planner.run(PlannerInput(task=task))
    collected = collector.run(CollectorInput(task=task))
    analysis = analyst.run(AnalystInput(task=task, evidence=collected.evidence))
    report_output = writer.run(ReportWriterInput(task=task, knowledge=analysis))
    qa_output = qa.run(QaInput(task=task, evidence=collected.evidence, analysis=analysis, report_output=report_output))
    return task, trace_service, plan, collected, analysis, report_output, qa_output


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


def test_each_agent_run_uses_input_output_schema(db_session):
    task, _, plan, collected, analysis, report_output, qa_output = build_agent_outputs(db_session)
    assert isinstance(PlannerInput(task=task), PlannerInput)
    assert isinstance(plan, PlannerOutput)
    assert isinstance(collected, CollectorOutput)
    assert isinstance(analysis, AnalystOutput)
    assert isinstance(report_output, ReportWriterOutput)
    assert isinstance(qa_output, QaOutput)
    assert qa_output.qa_result.status == "passed"


def test_missing_evidence_routes_to_collector(db_session):
    task = make_task(db_session)
    qa = QaAgent(TraceService(db_session))
    result = qa.run(QaInput(task=task, evidence=[], demo_mode="qa_missing_evidence")).qa_result
    assert result.status == "failed"
    assert result.route_to == "CollectorAgent"
    assert result.rework_instructions[0].error_type == "missing_evidence"
    assert result.rework_instructions[0].failed_schema == "Evidence"


def test_invalid_extraction_routes_to_analyst(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = CollectorAgent(trace_service).run(CollectorInput(task=task)).evidence
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence, force_invalid_extraction=True))
    report_output = ReportWriterAgent(trace_service).run(ReportWriterInput(task=task, knowledge=analysis))
    result = QaAgent(trace_service).run(
        QaInput(
            task=task,
            evidence=evidence,
            analysis=analysis,
            report_output=report_output,
            demo_mode="qa_invalid_extraction",
        )
    ).qa_result
    assert result.status == "failed"
    assert result.route_to == "AnalystAgent"
    assert result.rework_instructions[0].error_type == "invalid_extraction"
    assert result.rework_instructions[0].failed_schema == "ProductProfile"


def test_bad_report_format_routes_to_report_writer(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = CollectorAgent(trace_service).run(CollectorInput(task=task)).evidence
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence))
    report_output = ReportWriterAgent(trace_service).run(
        ReportWriterInput(task=task, knowledge=analysis, force_bad_format=True)
    )
    result = QaAgent(trace_service).run(
        QaInput(task=task, evidence=evidence, analysis=analysis, report_output=report_output, demo_mode="qa_bad_report")
    ).qa_result
    assert result.status == "failed"
    assert result.route_to == "ReportWriterAgent"
    assert result.rework_instructions[0].error_type == "bad_report_format"
    assert result.rework_instructions[0].failed_schema == "Report.markdown"


def test_max_rework_becomes_manual_review(db_session):
    task = make_task(db_session)
    task.rework_count = 3
    qa = QaAgent(TraceService(db_session))
    result = qa.run(QaInput(task=task, evidence=[], demo_mode="qa_missing_evidence")).qa_result
    assert result.status == "manual_review"
    assert result.route_to is None


def test_final_report_agent_creates_trace(db_session):
    task, trace_service, _, collected, _, report_output, qa_output = build_agent_outputs(db_session)
    assert report_output.report is not None
    output = FinalReportAgent(trace_service).run(
        FinalReportInput(task=task, report=report_output.report, qa_result=qa_output.qa_result, evidence=collected.evidence)
    )
    assert isinstance(output, FinalReportOutput)
    traces = trace_service.list_for_task(task.task_id)
    assert "FinalReport" in {trace.agent_name for trace in traces}


def test_normal_workflow_still_passes(db_session):
    task = make_task(db_session)
    result = MockWorkflowRunner(db_session).run(task.task_id, demo_mode="normal")
    assert result["qa_result"].status == "passed"
    assert result["report"] is not None
    traces = TraceService(db_session).list_for_task(task.task_id)
    assert {trace.agent_name for trace in traces} >= {
        "PlannerAgent",
        "CollectorAgent",
        "AnalystAgent",
        "ReportWriterAgent",
        "QaAgent",
        "FinalReport",
    }
    assert all(trace.schema_validation_result == "passed" for trace in traces)


@pytest.mark.parametrize(
    ("demo_mode", "expected_route"),
    [
        ("qa_missing_evidence", "CollectorAgent"),
        ("qa_invalid_extraction", "AnalystAgent"),
        ("qa_bad_report", "ReportWriterAgent"),
    ],
)
def test_auto_rework_routes_and_then_passes(db_session, demo_mode, expected_route):
    task = make_task(db_session)
    result = MockWorkflowRunner(db_session).run(task.task_id, demo_mode=demo_mode, auto_rework=True)
    qa_result = result["qa_result"]
    assert qa_result.status == "passed"
    assert qa_result.rework_count == 1
    assert qa_result.rework_history
    assert qa_result.rework_history[0].route_to == expected_route
    assert qa_result.rework_history[0].result_status == "passed"
    assert result["report"] is not None

    traces = TraceService(db_session).list_for_task(task.task_id)
    agent_names = [trace.agent_name for trace in traces]
    assert "QaAgent" in agent_names
    assert agent_names.count("QaAgent") >= 2
    assert expected_route in agent_names


def test_auto_rework_respects_manual_review_limit(db_session):
    task = make_task(db_session)
    TaskService(db_session).update_status(task.task_id, "running", rework_count=3)
    task = TaskService(db_session).get_task(task.task_id)
    qa = QaAgent(TraceService(db_session))
    result = qa.run(QaInput(task=task, evidence=[], demo_mode="qa_missing_evidence")).qa_result
    assert result.status == "manual_review"
    assert result.route_to is None
