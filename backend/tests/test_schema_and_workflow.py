import pytest
import time
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
    QaResult,
    QaOutput,
    Report,
    ReportWriterInput,
    ReportWriterOutput,
)
from app.services.llm_client import LlmResponse
from app.services.report_service import ReportService
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


def test_llm_writer_without_api_key_falls_back_to_mock(db_session, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    task = make_task(db_session)
    result = MockWorkflowRunner(db_session).run(task.task_id, writer_mode="llm")
    assert result["qa_result"].status == "passed"
    assert result["report"] is not None
    assert result["report"].json_report["writer_mode"] == "mock"
    diagnostics = result["report"].json_report["writer_diagnostics"]
    assert diagnostics["writer_mode_requested"] == "llm"
    assert diagnostics["writer_mode_used"] == "mock"
    assert diagnostics["fallback_used"] is True
    assert "LLM_API_KEY" in diagnostics["llm_fallback_reason"]


class FakeLlmClient:
    def __init__(self, content: str):
        self.content = content
        self.provider = "fake"
        self.model = "fake-model"
        self.base_url = "https://fake.local/v1"
        self.is_available = True

    def chat_json(self, messages, timeout: float = 30.0):
        time.sleep(0.02)
        return LlmResponse(
            available=True,
            content=self.content,
            provider="fake",
            model="fake-model",
            attempted=True,
            success=True,
            elapsed_time_ms=20,
            response_preview=self.content[:300],
        )


def test_llm_writer_success_records_diagnostics_and_elapsed_time(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = CollectorAgent(trace_service).run(CollectorInput(task=task)).evidence
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence))
    writer = ReportWriterAgent(
        trace_service,
        llm_client=FakeLlmClient(
            '{"markdown_report":"# LLM Report","json_report":{},"claims":[{"claim_id":"c1","text":"source-backed claim","evidence_ids":["'
            + evidence[0].evidence_id
            + '"]}]}'
        ),
    )
    writer_output = writer.run(ReportWriterInput(task=task, knowledge=analysis, evidence=evidence, writer_mode="llm"))
    assert writer_output.report is not None
    diagnostics = writer_output.report.json_report["writer_diagnostics"]
    assert diagnostics["writer_mode_requested"] == "llm"
    assert diagnostics["writer_mode_used"] == "llm"
    assert diagnostics["llm_call_attempted"] is True
    assert diagnostics["llm_call_success"] is True
    traces = [trace for trace in trace_service.list_for_task(task.task_id) if trace.agent_name == "ReportWriterAgent"]
    assert traces[-1].elapsed_time_ms > 0


def test_llm_claim_missing_evidence_routes_to_report_writer(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = CollectorAgent(trace_service).run(CollectorInput(task=task)).evidence
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence))
    writer = ReportWriterAgent(
        trace_service,
        llm_client=FakeLlmClient(
            '{"markdown_report":"# Bad","json_report":{},"claims":[{"claim_id":"c1","text":"unsupported"}]}'
        ),
    )
    writer_output = writer.run(ReportWriterInput(task=task, knowledge=analysis, evidence=evidence, writer_mode="llm"))
    qa_result = QaAgent(trace_service).run(
        QaInput(task=task, evidence=evidence, analysis=analysis, report_output=writer_output)
    ).qa_result
    assert qa_result.status == "failed"
    assert qa_result.route_to == "ReportWriterAgent"
    assert any(trace.schema_validation_result == "failed" for trace in trace_service.list_for_task(task.task_id))


def test_llm_invalid_json_falls_back_to_mock_and_records_trace_error(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = CollectorAgent(trace_service).run(CollectorInput(task=task)).evidence
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence))
    writer = ReportWriterAgent(trace_service, llm_client=FakeLlmClient("not valid json"))
    writer_output = writer.run(ReportWriterInput(task=task, knowledge=analysis, evidence=evidence, writer_mode="llm"))
    assert writer_output.report is not None
    assert writer_output.report.json_report["writer_mode"] == "mock"
    traces = trace_service.list_for_task(task.task_id)
    assert any(trace.schema_validation_result == "failed" and trace.error_message for trace in traces)
    assert any("LLM returned invalid JSON" in (trace.error_message or "") for trace in traces)


def test_latest_report_for_task_uses_latest_saved_row(db_session):
    task = make_task(db_session)
    service = ReportService(db_session)
    claim = Claim(text="supported", category="feature", evidence_ids=["ev_1"], confidence=0.9)
    old_report = Report(task_id=task.task_id, markdown="# Old", json_report={"version": "old"}, claims=[claim], qa_result=QaResult(task_id=task.task_id, status="passed"))
    new_report = Report(task_id=task.task_id, markdown="# New", json_report={"version": "new"}, claims=[claim], qa_result=QaResult(task_id=task.task_id, status="passed"))
    service.save_report(old_report)
    service.save_report(new_report)
    latest = service.get_latest_for_task(task.task_id)
    assert latest.report_id == new_report.report_id
    assert latest.json_report["version"] == "new"


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
