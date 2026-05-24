import json
import pytest
import time
import httpx
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
from app.services.web_search_client import SearchResult, WebSearchClient, WebSearchResponse


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


class FakeWebSearchClient:
    provider = "fake-search"
    api_key = "fake-key"
    base_url = "https://fake-search.local"

    def __init__(self, *, fail: bool = False):
        self.fail = fail

    def search(self, query: str, limit: int = 5):
        if self.fail:
            return WebSearchResponse(
                available=False,
                attempted=True,
                success=False,
                fallback_reason="Web search failed: timeout",
                error_type="TimeoutError",
                error_message="timeout",
            )
        return WebSearchResponse(
            available=True,
            attempted=True,
            success=True,
            elapsed_time_ms=12,
            results=[
                SearchResult(title="Official pricing", url="https://official.example.com/pricing", snippet="Official pricing and features summary."),
                SearchResult(title="Docs", url="https://docs.example.com/features", snippet="Documentation describes collaboration features."),
            ],
        )


class FakeHttpResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.request = httpx.Request("POST", "https://api.tavily.com/search")

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("Client error", request=self.request, response=httpx.Response(self.status_code, text=self.text, request=self.request))


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
    assert diagnostics["llm_schema_validation_success"] is True
    assert diagnostics["llm_schema_validation_errors"] == []
    assert diagnostics["llm_category_normalization_count"] == 1
    traces = [trace for trace in trace_service.list_for_task(task.task_id) if trace.agent_name == "ReportWriterAgent"]
    assert traces[-1].elapsed_time_ms > 0
    trace_diagnostics = json.loads(traces[-1].output_summary)
    assert trace_diagnostics["llm_schema_validation_success"] is True


def test_collector_mode_mock_workflow_still_passes(db_session):
    task = make_task(db_session)
    result = MockWorkflowRunner(db_session).run(task.task_id, collector_mode="mock")
    assert result["qa_result"].status == "passed"
    collector_trace = next(trace for trace in TraceService(db_session).list_for_task(task.task_id) if trace.agent_name == "CollectorAgent")
    diagnostics = json.loads(collector_trace.output_summary)
    assert diagnostics["collector_mode_requested"] == "mock"
    assert diagnostics["collector_mode_used"] == "mock"


def test_collector_web_without_api_key_falls_back_to_mock(db_session, monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    output = CollectorAgent(trace_service).run(CollectorInput(task=task, collector_mode="web"))
    assert output.evidence
    assert output.diagnostics["collector_mode_requested"] == "web"
    assert output.diagnostics["collector_mode_used"] == "mock"
    assert output.diagnostics["fallback_used"] is True
    assert output.diagnostics["fallback_reason"]


def test_tavily_results_convert_to_evidence(db_session, monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("SEARCH_API_KEY", "Bearer fake-search-key")
    monkeypatch.setenv("SEARCH_BASE_URL", "https://api.tavily.com")
    monkeypatch.setenv("SEARCH_MAX_RESULTS", "5")

    def fake_post(url, headers, json, timeout):
        assert url == "https://api.tavily.com/search"
        assert headers["Authorization"] == "Bearer fake-search-key"
        assert json["include_raw_content"] is False
        return FakeHttpResponse(
            {
                "results": [
                    {
                        "title": "Feishu official pricing",
                        "url": "https://www.feishu.cn/pricing",
                        "content": "飞书官网定价和功能页面摘要，介绍企业协作功能。",
                        "score": 0.92,
                    }
                ]
            }
        )

    monkeypatch.setattr("app.services.web_search_client.httpx.post", fake_post)
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    output = CollectorAgent(trace_service, web_search_client=WebSearchClient()).run(
        CollectorInput(task=task, collector_mode="web")
    )
    assert output.diagnostics["collector_mode_used"] == "web"
    assert output.evidence[0].source_type == "public_web"
    assert output.evidence[0].url == "https://www.feishu.cn/pricing"
    assert output.evidence[0].confidence >= 0.85


def test_tavily_empty_results_fallback_to_mock(db_session, monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("SEARCH_API_KEY", "fake-search-key")
    monkeypatch.setenv("SEARCH_BASE_URL", "https://api.tavily.com")

    def fake_post(url, headers, json, timeout):
        return FakeHttpResponse({"results": []})

    monkeypatch.setattr("app.services.web_search_client.httpx.post", fake_post)
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    output = CollectorAgent(trace_service, web_search_client=WebSearchClient()).run(
        CollectorInput(task=task, collector_mode="web")
    )
    assert output.diagnostics["collector_mode_used"] == "mock"
    assert output.diagnostics["fallback_used"] is True
    assert "no usable" in output.diagnostics["fallback_reason"]


def test_tavily_401_fallback_to_mock_and_records_reason(db_session, monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("SEARCH_API_KEY", "fake-search-key")
    monkeypatch.setenv("SEARCH_BASE_URL", "https://api.tavily.com")

    def fake_post(url, headers, json, timeout):
        return FakeHttpResponse({"detail": "Unauthorized"}, status_code=401)

    monkeypatch.setattr("app.services.web_search_client.httpx.post", fake_post)
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    output = CollectorAgent(trace_service, web_search_client=WebSearchClient()).run(
        CollectorInput(task=task, collector_mode="web")
    )
    assert output.diagnostics["collector_mode_used"] == "mock"
    assert output.diagnostics["fallback_used"] is True
    assert "401" in output.diagnostics["fallback_reason"] or "Client error" in output.diagnostics["fallback_reason"]


def test_search_status_does_not_return_api_key(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("SEARCH_API_KEY", "secret-search-key")
    monkeypatch.setenv("SEARCH_BASE_URL", "https://api.tavily.com")
    status = WebSearchClient().status()
    assert status["search_provider"] == "tavily"
    assert status["api_key_configured"] is True
    assert "secret-search-key" not in json.dumps(status)
    assert status["max_results"] == 5


def test_collector_web_results_convert_to_evidence(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    output = CollectorAgent(trace_service, web_search_client=FakeWebSearchClient()).run(
        CollectorInput(task=task, collector_mode="web")
    )
    assert output.evidence
    assert output.evidence[0].source_type == "public_web"
    assert output.evidence[0].url == "https://official.example.com/pricing"
    assert output.evidence[0].confidence == 0.9
    assert output.diagnostics["collector_mode_used"] == "web"
    assert output.diagnostics["web_search_success"] is True


def test_collector_web_timeout_does_not_crash_workflow(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    output = CollectorAgent(trace_service, web_search_client=FakeWebSearchClient(fail=True)).run(
        CollectorInput(task=task, collector_mode="web")
    )
    assert output.evidence
    assert output.diagnostics["collector_mode_used"] == "mock"
    assert output.diagnostics["fallback_used"] is True
    assert "timeout" in output.diagnostics["fallback_reason"]


def test_collector_trace_records_mode_and_fallback_reason(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    CollectorAgent(trace_service, web_search_client=FakeWebSearchClient(fail=True)).run(
        CollectorInput(task=task, collector_mode="web")
    )
    collector_trace = next(trace for trace in trace_service.list_for_task(task.task_id) if trace.agent_name == "CollectorAgent")
    diagnostics = json.loads(collector_trace.output_summary)
    assert diagnostics["collector_mode_requested"] == "web"
    assert diagnostics["collector_mode_used"] == "mock"
    assert diagnostics["fallback_reason"]


def test_collector_mode_web_and_writer_mode_llm_parameters_both_pass(db_session, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    task = make_task(db_session)
    result = MockWorkflowRunner(db_session).run(task.task_id, collector_mode="web", writer_mode="llm")
    assert result["qa_result"].status == "passed"
    traces = TraceService(db_session).list_for_task(task.task_id)
    collector_trace = next(trace for trace in traces if trace.agent_name == "CollectorAgent")
    writer_trace = next(trace for trace in traces if trace.agent_name == "ReportWriterAgent")
    collector_diagnostics = json.loads(collector_trace.output_summary)
    writer_diagnostics = json.loads(writer_trace.output_summary)
    assert collector_diagnostics["collector_mode_requested"] == "web"
    assert writer_diagnostics["writer_mode_requested"] == "llm"


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
    failed_trace = next(trace for trace in trace_service.list_for_task(task.task_id) if trace.agent_name == "ReportWriterAgent" and trace.schema_validation_result == "failed")
    trace_diagnostics = json.loads(failed_trace.output_summary)
    assert trace_diagnostics["llm_schema_validation_success"] is False
    assert trace_diagnostics["llm_schema_validation_errors"]


def test_llm_claim_schema_failure_records_validation_diagnostics(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = CollectorAgent(trace_service).run(CollectorInput(task=task)).evidence
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence))
    writer = ReportWriterAgent(
        trace_service,
        llm_client=FakeLlmClient(
            '{"markdown_report":"# Bad","json_report":{},"claims":[{"claim_id":"c1","text":"bad category","category":"任务基础信息","evidence_ids":["'
            + evidence[0].evidence_id
            + '"]}]}'
        ),
    )
    writer_output = writer.run(ReportWriterInput(task=task, knowledge=analysis, evidence=evidence, writer_mode="llm"))
    assert writer_output.report is None
    traces = trace_service.list_for_task(task.task_id)
    failed_trace = next(trace for trace in traces if trace.agent_name == "ReportWriterAgent" and trace.schema_validation_result == "failed")
    trace_diagnostics = json.loads(failed_trace.output_summary)
    assert trace_diagnostics["llm_schema_validation_success"] is False
    assert trace_diagnostics["llm_schema_validation_errors"]
    assert trace_diagnostics["llm_category_normalization_count"] == 0


def test_mock_writer_schema_diagnostics_are_null(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = CollectorAgent(trace_service).run(CollectorInput(task=task)).evidence
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence))
    writer_output = ReportWriterAgent(trace_service).run(ReportWriterInput(task=task, knowledge=analysis, evidence=evidence))
    assert writer_output.report is not None
    diagnostics = writer_output.report.json_report["writer_diagnostics"]
    assert diagnostics["writer_mode_used"] == "mock"
    assert diagnostics["llm_schema_validation_success"] is None


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
