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
from app.agents.langgraph_runner import LangGraphWorkflowRunner
from app.agents.planner import PlannerAgent
from app.agents.qa import QaAgent
from app.agents.report_writer import ReportWriterAgent
from app.agents.runner import MockWorkflowRunner
from app.agents.runner_factory import resolve_workflow_engine
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
    ReworkInstruction,
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


def test_analyst_mode_mock_still_works(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = CollectorAgent(trace_service).run(CollectorInput(task=task)).evidence
    output = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence, analyst_mode="mock"))
    assert output.diagnostics["analyst_mode_used"] == "mock"
    assert output.product_profile.evidence_ids


def test_analyst_mode_evidence_extracts_features(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = [
        Evidence(source_type="public_web", url="https://example.com/features", source_domain="example.com", source_quality="official", snippet="The product supports AI automation, collaboration workflow, integration API, analytics and security features.", confidence=0.9),
        Evidence(source_type="public_web", url="https://example.com/pricing", source_domain="example.com", source_quality="official", snippet="Pricing includes free trial, subscription plan and enterprise quote.", confidence=0.9),
        Evidence(source_type="public_web", url="https://example.com/customers", source_domain="example.com", source_quality="unknown", snippet="Enterprise team, developer, marketer and product team users evaluate the product.", confidence=0.7),
    ]
    output = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence, analyst_mode="evidence"))
    assert output.diagnostics["analyst_mode_used"] == "evidence"
    assert "AI" in output.feature_tree.core_features
    assert output.feature_tree.evidence_ids


def test_analyst_evidence_extracts_pricing_and_persona(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = [
        Evidence(source_type="public_web", url="https://example.com/features", source_domain="example.com", source_quality="official", snippet="AI automation collaboration workflow and API integration for teams.", confidence=0.9),
        Evidence(source_type="public_web", url="https://example.com/pricing", source_domain="example.com", source_quality="official", snippet="Pricing page shows free trial, subscription plan and enterprise quote.", confidence=0.9),
        Evidence(source_type="public_web", url="https://example.com/users", source_domain="example.com", source_quality="unknown", snippet="Enterprise team, developer, marketer, product team and student users are mentioned.", confidence=0.7),
    ]
    output = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence, analyst_mode="evidence"))
    assert output.pricing_model.evidence_ids
    assert "pricing" in output.pricing_model.pricing_notes.lower()
    assert output.user_persona.evidence_ids
    assert output.user_persona.persona_name in {"企业团队", "团队用户", "开发者", "市场团队", "产品团队", "学生"}


def test_analyst_insufficient_evidence_is_conservative_and_qa_suggests(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = [
        Evidence(source_type="public_web", url="https://example.com/brief", source_domain="example.com", source_quality="unknown", snippet="Brief public source.", confidence=0.6)
    ]
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence, analyst_mode="evidence"))
    assert "Evidence is insufficient" in analysis.product_profile.positioning
    claim = Claim(text="Conservative claim", category="recommendation", evidence_ids=[evidence[0].evidence_id], confidence=0.6)
    report = Report(task_id=task.task_id, markdown="# Report", json_report={"claims": [claim.model_dump(mode="json")]}, claims=[claim])
    qa_result = QaAgent(trace_service).run(QaInput(task=task, evidence=evidence, analysis=analysis, report_output=ReportWriterOutput(report=report))).qa_result
    assert qa_result.status == "passed"
    assert any("结构化分析证据不足" in suggestion for suggestion in qa_result.soft_suggestions)


def test_analyst_trace_records_mode_and_counts(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = [
        Evidence(source_type="public_web", url="https://example.com/features", source_domain="example.com", source_quality="official", snippet="AI automation collaboration workflow, pricing plan and enterprise team.", confidence=0.9),
        Evidence(source_type="public_web", url="https://example.com/pricing", source_domain="example.com", source_quality="official", snippet="Free trial subscription pricing plan for developer team.", confidence=0.9),
        Evidence(source_type="public_web", url="https://example.com/security", source_domain="example.com", source_quality="documentation", snippet="Security analytics API integration documentation.", confidence=0.85),
    ]
    AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence, analyst_mode="evidence"))
    trace = next(item for item in trace_service.list_for_task(task.task_id) if item.agent_name == "AnalystAgent")
    diagnostics = json.loads(trace.output_summary)
    assert diagnostics["analyst_mode_requested"] == "evidence"
    assert diagnostics["analyst_mode_used"] == "evidence"
    assert diagnostics["extracted_feature_count"] > 0


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
    assert output.evidence[0].source_domain == "feishu.cn"
    assert output.evidence[0].source_quality == "official"
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


def test_collector_deduplicates_normalized_urls(db_session):
    class DuplicateSearchClient(FakeWebSearchClient):
        def __init__(self):
            super().__init__()
            self.called = False

        def search(self, query: str, limit: int = 5):
            if self.called:
                return WebSearchResponse(available=True, attempted=True, success=True, elapsed_time_ms=1, results=[])
            self.called = True
            return WebSearchResponse(
                available=True,
                attempted=True,
                success=True,
                elapsed_time_ms=1,
                results=[
                    SearchResult(title="A", url="https://www.feishu.cn/pricing/?utm_source=x&fbclid=y", snippet="Feishu pricing product features official page."),
                    SearchResult(title="A copy", url="https://www.feishu.cn/pricing", snippet="Feishu pricing product features official page duplicated."),
                ],
            )

    task = make_task(db_session)
    trace_service = TraceService(db_session)
    output = CollectorAgent(trace_service, web_search_client=DuplicateSearchClient()).run(
        CollectorInput(task=task, collector_mode="web")
    )
    assert len(output.evidence) == 1
    assert output.evidence[0].url == "https://www.feishu.cn/pricing"
    assert output.diagnostics["raw_evidence_count"] == 2
    assert output.diagnostics["deduplicated_evidence_count"] == 1
    assert output.diagnostics["duplicate_removed_count"] == 1


def test_collector_records_competitor_coverage(db_session):
    class CoverageSearchClient(FakeWebSearchClient):
        def search(self, query: str, limit: int = 5):
            if "AlphaCI" in query:
                return WebSearchResponse(
                    available=True,
                    attempted=True,
                    success=True,
                    results=[
                        SearchResult(title="AlphaCI official", url="https://alphaci.example/pricing", snippet="AlphaCI pricing product features for enterprise team."),
                        SearchResult(title="AlphaCI docs", url="https://docs.alphaci.example/features", snippet="AlphaCI documentation for AI automation workflow."),
                    ],
                )
            return WebSearchResponse(
                available=True,
                attempted=True,
                success=True,
                results=[
                    SearchResult(title="BetaIntel official", url="https://betaintel.example/pricing", snippet="BetaIntel pricing product features for enterprise team."),
                    SearchResult(title="BetaIntel docs", url="https://docs.betaintel.example/features", snippet="BetaIntel documentation for analytics workflow."),
                ],
            )

    task = make_task(db_session)
    trace_service = TraceService(db_session)
    output = CollectorAgent(trace_service, web_search_client=CoverageSearchClient()).run(
        CollectorInput(task=task, collector_mode="web")
    )
    assert output.diagnostics["competitor_coverage"]["AlphaCI"] >= 2
    assert output.diagnostics["competitor_coverage"]["BetaIntel"] >= 2
    assert output.diagnostics["missing_competitors"] == []


def test_web_collector_generates_queries_and_evidence_per_competitor(db_session):
    class RecordingSearchClient(FakeWebSearchClient):
        def __init__(self):
            super().__init__()
            self.queries = []

        def search(self, query: str, limit: int = 5):
            self.queries.append(query)
            competitor = "AlphaCI" if "AlphaCI" in query else "BetaIntel"
            return WebSearchResponse(
                available=True,
                attempted=True,
                success=True,
                results=[
                    SearchResult(title=f"{competitor} official", url=f"https://{competitor.lower()}.example/pricing", snippet=f"{competitor} official pricing product features enterprise plan."),
                    SearchResult(title=f"{competitor} docs", url=f"https://docs.{competitor.lower()}.example/features", snippet=f"{competitor} documentation shows collaboration workflow API."),
                ],
            )

    task = make_task(db_session)
    client = RecordingSearchClient()
    output = CollectorAgent(TraceService(db_session), web_search_client=client).run(
        CollectorInput(task=task, collector_mode="web")
    )
    assert any("AlphaCI" in query for query in client.queries)
    assert any("BetaIntel" in query for query in client.queries)
    assert {item.competitor for item in output.evidence} == {"AlphaCI", "BetaIntel"}
    assert output.diagnostics["evidence_count_by_competitor"]["AlphaCI"] >= 2
    assert output.diagnostics["evidence_count_by_competitor"]["BetaIntel"] >= 2


def test_analyst_groups_structured_knowledge_by_competitor(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = [
        Evidence(competitor="AlphaCI", source_type="public_web", url="https://alphaci.example/pricing", source_domain="alphaci.example", source_quality="official", snippet="AlphaCI AI automation pricing enterprise plan for product team.", confidence=0.9),
        Evidence(competitor="AlphaCI", source_type="public_web", url="https://alphaci.example/features", source_domain="alphaci.example", source_quality="official", snippet="AlphaCI collaboration workflow API integration for teams.", confidence=0.9),
        Evidence(competitor="BetaIntel", source_type="public_web", url="https://betaintel.example/pricing", source_domain="betaintel.example", source_quality="official", snippet="BetaIntel pricing subscription enterprise quote.", confidence=0.9),
        Evidence(competitor="BetaIntel", source_type="public_web", url="https://betaintel.example/features", source_domain="betaintel.example", source_quality="official", snippet="BetaIntel analytics security workflow for enterprise team.", confidence=0.9),
    ]
    output = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence, analyst_mode="evidence"))
    competitor_analysis = output.product_profile.custom_dimensions["competitor_analysis"]
    assert set(competitor_analysis) == {"AlphaCI", "BetaIntel"}
    assert all(competitor_analysis[item]["evidence_ids"] for item in task.competitors)
    assert output.diagnostics["evidence_count_by_competitor"] == {"AlphaCI": 2, "BetaIntel": 2}


def test_report_writer_mock_claims_cover_all_competitors(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = CollectorAgent(trace_service).run(CollectorInput(task=task)).evidence
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence))
    output = ReportWriterAgent(trace_service).run(ReportWriterInput(task=task, knowledge=analysis, evidence=evidence))
    assert output.report is not None
    assert {claim.competitor for claim in output.report.claims} == {"AlphaCI", "BetaIntel"}
    assert output.diagnostics["missing_claim_competitors"] == []


def test_qa_detects_missing_competitor_evidence(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = [
        Evidence(competitor="AlphaCI", source_type="public_web", url="https://alphaci.example/pricing", source_domain="alphaci.example", source_quality="official", snippet="AlphaCI pricing product features.", confidence=0.9)
    ]
    result = QaAgent(trace_service).run(QaInput(task=task, evidence=evidence)).qa_result
    assert result.status == "failed"
    assert result.route_to == "CollectorAgent"
    assert result.rework_instructions[0].failed_schema == "Evidence.competitor"


def test_qa_detects_missing_competitor_claim(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = [
        Evidence(competitor="AlphaCI", source_type="public_web", url="https://alphaci.example/pricing", source_domain="alphaci.example", source_quality="official", snippet="AlphaCI pricing product features.", confidence=0.9),
        Evidence(competitor="BetaIntel", source_type="public_web", url="https://betaintel.example/pricing", source_domain="betaintel.example", source_quality="official", snippet="BetaIntel pricing product features.", confidence=0.9),
    ]
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence))
    claim = Claim(competitor="AlphaCI", text="AlphaCI supported claim", category="feature", evidence_ids=[evidence[0].evidence_id], confidence=0.8)
    report = Report(task_id=task.task_id, markdown="# Report", json_report={"claims": [claim.model_dump(mode="json")]}, claims=[claim])
    result = QaAgent(trace_service).run(QaInput(task=task, evidence=evidence, analysis=analysis, report_output=ReportWriterOutput(report=report))).qa_result
    assert result.status == "failed"
    assert result.route_to == "ReportWriterAgent"
    assert result.rework_instructions[0].failed_schema == "Report.claims.competitor"


def test_qa_detects_claim_using_other_competitor_evidence(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    evidence = [
        Evidence(competitor="AlphaCI", source_type="public_web", url="https://alphaci.example/pricing", source_domain="alphaci.example", source_quality="official", snippet="AlphaCI pricing product features.", confidence=0.9),
        Evidence(competitor="BetaIntel", source_type="public_web", url="https://betaintel.example/pricing", source_domain="betaintel.example", source_quality="official", snippet="BetaIntel pricing product features.", confidence=0.9),
    ]
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=evidence))
    claims = [
        Claim(competitor="AlphaCI", text="AlphaCI claim with wrong evidence", category="feature", evidence_ids=[evidence[1].evidence_id], confidence=0.8),
        Claim(competitor="BetaIntel", text="BetaIntel supported claim", category="feature", evidence_ids=[evidence[1].evidence_id], confidence=0.8),
    ]
    report = Report(task_id=task.task_id, markdown="# Report", json_report={"claims": [claim.model_dump(mode="json") for claim in claims]}, claims=claims)
    result = QaAgent(trace_service).run(QaInput(task=task, evidence=evidence, analysis=analysis, report_output=ReportWriterOutput(report=report))).qa_result
    assert result.status == "failed"
    assert result.route_to == "ReportWriterAgent"
    assert result.rework_instructions[0].failed_schema == "Claim.evidence_ids"


def test_url_tracking_params_are_ignored():
    assert CollectorAgent.normalize_url("https://example.com/path/?utm_source=a&spm=b&x=1") == "https://example.com/path?x=1"


def test_source_domain_extraction():
    assert CollectorAgent.extract_source_domain("https://www.feishu.cn/pricing") == "feishu.cn"
    assert CollectorAgent.extract_source_domain("https://open.dingtalk.com/document") == "dingtalk.com"


def test_source_quality_confidence_rules():
    official_quality = CollectorAgent._source_quality("https://www.feishu.cn/pricing", "pricing", "Official pricing product features content.", ["飞书"])
    unknown_quality = CollectorAgent._source_quality("https://example.net/blog", "blog", "General market content with enough words to evaluate quality.", ["飞书"])
    low_quality = CollectorAgent._source_quality("https://spam.example/click", "x", "short", ["飞书"])
    assert CollectorAgent._confidence_for_result("https://www.feishu.cn/pricing", "Official pricing product features content.", official_quality) > CollectorAgent._confidence_for_result("https://example.net/blog", "General market content with enough words to evaluate quality.", unknown_quality)
    assert CollectorAgent._confidence_for_result("https://spam.example/click", "short", low_quality) < 0.5


def test_low_confidence_claim_generates_soft_suggestion(db_session):
    task = make_task(db_session)
    trace_service = TraceService(db_session)
    low_evidence = Evidence(
        source_type="public_web",
        url="https://spam.example/click",
        source_domain="example",
        source_quality="low_quality",
        snippet="short",
        confidence=0.4,
    )
    analysis = AnalystAgent(trace_service).run(AnalystInput(task=task, evidence=[low_evidence]))
    claim = Claim(text="Low confidence claim", category="risk", evidence_ids=[low_evidence.evidence_id], confidence=0.4)
    report = Report(task_id=task.task_id, markdown="# Report", json_report={"claims": [claim.model_dump(mode="json")]}, claims=[claim])
    writer_output = ReportWriterOutput(report=report)
    qa_result = QaAgent(trace_service).run(
        QaInput(task=task, evidence=[low_evidence], analysis=analysis, report_output=writer_output)
    ).qa_result
    assert qa_result.status == "passed"
    assert any("证据可信度较低" in item for item in qa_result.soft_suggestions)


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


def test_workflow_engine_resolve_priority(monkeypatch):
    monkeypatch.delenv("WORKFLOW_ENGINE", raising=False)
    assert resolve_workflow_engine(None) == "custom"
    monkeypatch.setenv("WORKFLOW_ENGINE", "langgraph")
    assert resolve_workflow_engine(None) == "langgraph"
    assert resolve_workflow_engine("custom") == "custom"
    assert resolve_workflow_engine("langgraph") == "langgraph"


def test_langgraph_normal_workflow_passes_and_finalizes(db_session):
    task = make_task(db_session)
    result = LangGraphWorkflowRunner(db_session).run(task.task_id, workflow_engine_requested="langgraph")
    assert result["qa_result"].status == "passed"
    assert result["report"] is not None
    summary = result["workflow_summary"]
    assert summary["workflow_engine_used"] == "langgraph"
    assert summary["node_sequence"][-1] == "final_report"
    traces = TraceService(db_session).list_for_task(task.task_id)
    assert {trace.agent_name for trace in traces} >= {"PlannerAgent", "CollectorAgent", "AnalystAgent", "ReportWriterAgent", "QaAgent", "FinalReport", "WorkflowEngine"}


@pytest.mark.parametrize(
    ("demo_mode", "expected_node"),
    [
        ("qa_missing_evidence", "collector"),
        ("qa_invalid_extraction", "analyst"),
        ("qa_bad_report", "report_writer"),
    ],
)
def test_langgraph_auto_rework_conditional_routes(db_session, demo_mode, expected_node):
    task = make_task(db_session)
    result = LangGraphWorkflowRunner(db_session).run(task.task_id, demo_mode=demo_mode, auto_rework=True)
    assert result["qa_result"].status == "passed"
    routes = result["workflow_summary"]["conditional_routes_taken"]
    assert routes
    assert routes[0]["to_node"] == expected_node
    assert result["workflow_summary"]["rework_count"] == 1


def test_langgraph_without_auto_rework_stops_on_qa_failure(db_session):
    task = make_task(db_session)
    result = LangGraphWorkflowRunner(db_session).run(task.task_id, demo_mode="qa_bad_report", auto_rework=False)
    assert result["qa_result"].status == "failed"
    assert result["report"] is None
    assert result["workflow_summary"]["conditional_routes_taken"] == []
    assert result["workflow_summary"]["final_status"] == "qa_failed"


def test_langgraph_max_rework_enters_manual_review_without_loop(db_session):
    task = make_task(db_session)
    TaskService(db_session).update_status(task.task_id, "running", rework_count=3)
    task = TaskService(db_session).get_task(task.task_id)
    runner = LangGraphWorkflowRunner(db_session)
    state = {
        "task_id": task.task_id,
        "task": task,
        "workflow_engine_requested": "langgraph",
        "workflow_engine_used": "langgraph",
        "demo_mode": "qa_missing_evidence",
        "collector_mode": "mock",
        "analyst_mode": "evidence",
        "writer_mode": "mock",
        "content_mode": None,
        "auto_rework": True,
        "rework_count": 3,
        "max_rework": 3,
        "evidence": [],
        "report": None,
        "qa_result": None,
        "route_to": None,
        "final_status": None,
        "errors": [],
        "node_sequence": [],
        "conditional_routes_taken": [],
        "workflow_summary": {},
    }
    output = runner.qa_node(state)
    assert output["qa_result"].status == "manual_review"
    assert runner.route_after_qa(output) == "final_report"


def test_langgraph_unknown_route_enters_manual_review_and_records_route(db_session):
    task = make_task(db_session)
    runner = LangGraphWorkflowRunner(db_session)

    class UnknownRouteQa:
        def run(self, input_data):
            result = QaResult(
                task_id=input_data.task.task_id,
                status="failed",
                hard_errors=["Unknown route demo"],
                route_to="CollectorAgent",
                rework_count=1,
                rework_instructions=[
                    ReworkInstruction(
                        target_agent="CollectorAgent",
                        error_type="missing_evidence",
                        reason="Unknown route demo",
                        suggested_action="Manual review required.",
                    )
                ],
            )
            object.__setattr__(result, "route_to", "UnknownAgent")
            return QaOutput(
                qa_result=result
            )

    runner.qa = UnknownRouteQa()
    state = {
        "task_id": task.task_id,
        "task": task,
        "workflow_engine_requested": "langgraph",
        "workflow_engine_used": "langgraph",
        "demo_mode": "normal",
        "collector_mode": "mock",
        "analyst_mode": "evidence",
        "writer_mode": "mock",
        "content_mode": None,
        "auto_rework": True,
        "rework_count": 0,
        "max_rework": 3,
        "evidence": [],
        "report": None,
        "qa_result": None,
        "route_to": None,
        "final_status": None,
        "errors": [],
        "node_sequence": [],
        "conditional_routes_taken": [],
        "workflow_summary": {},
    }
    output = runner.qa_node(state)
    assert output["final_status"] == "manual_review"
    assert output["conditional_routes_taken"][0]["reason"] == "unknown_route"
    assert output["conditional_routes_taken"][0]["to_node"] == "final_report"
    assert output["conditional_routes_taken"][0]["final_status"] == "manual_review"
    assert runner.route_after_qa(output) == "final_report"
    final_state = runner.final_report_node(output)
    assert final_state["final_status"] == "manual_review"


def test_langgraph_workflow_trace_contains_recoverable_summary_fields(db_session):
    task = make_task(db_session)
    result = LangGraphWorkflowRunner(db_session).run(task.task_id, workflow_engine_requested="langgraph")
    trace = next(trace for trace in TraceService(db_session).list_for_task(task.task_id) if trace.agent_name == "WorkflowEngine")
    summary = json.loads(trace.output_summary)
    for key in [
        "workflow_engine_requested",
        "workflow_engine_used",
        "node_sequence",
        "conditional_routes_taken",
        "rework_count",
        "final_status",
        "elapsed_time_ms",
    ]:
        assert key in summary
    assert summary["workflow_engine_used"] == result["workflow_summary"]["workflow_engine_used"]


def test_langgraph_conditional_routes_support_frontend_rework_history(db_session):
    task = make_task(db_session)
    result = LangGraphWorkflowRunner(db_session).run(task.task_id, demo_mode="qa_bad_report", auto_rework=True)
    routes = result["workflow_summary"]["conditional_routes_taken"]
    assert routes
    assert routes[0]["from_node"] == "qa"
    assert routes[0]["to_node"] == "report_writer"
    assert routes[0]["reason"] == "bad_report_format"


def test_langgraph_modes_and_competitor_coverage_still_work(db_session, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    task = make_task(db_session)
    result = LangGraphWorkflowRunner(db_session).run(
        task.task_id,
        collector_mode="mock",
        analyst_mode="evidence",
        writer_mode="llm",
        workflow_engine_requested="langgraph",
    )
    assert result["qa_result"].status == "passed"
    assert result["report"] is not None
    assert {claim.competitor for claim in result["report"].claims} == set(task.competitors)
    writer_trace = next(trace for trace in TraceService(db_session).list_for_task(task.task_id) if trace.agent_name == "ReportWriterAgent")
    writer_diagnostics = json.loads(writer_trace.output_summary)
    assert writer_diagnostics["writer_mode_requested"] == "llm"
