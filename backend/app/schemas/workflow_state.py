from typing import Any, Literal, TypedDict

from app.schemas.agent_io import (
    AnalystOutput,
    CollectorOutput,
    FinalReportOutput,
    PlannerOutput,
    QaOutput,
    ReportWriterOutput,
)
from app.schemas.models import (
    AnalysisDimensionPlan,
    Chunk,
    ClaimSupportResult,
    DimensionResult,
    Evidence,
    PlannerExtractedContext,
    PlannerSurveyInput,
    QaResult,
    Report,
    RetrievalResult,
    ReworkContext,
    SurveyEvidence,
    Task,
    TaskRun,
)


WorkflowEngine = Literal["custom", "langgraph"]


class ConditionalRoute(TypedDict, total=False):
    from_node: str
    to_node: str
    reason: str
    rework_count: int


class WorkflowState(TypedDict, total=False):
    task_id: str
    run_id: str
    trace_id: str | None
    task: Task
    task_run: TaskRun | None
    run_status: str | None
    workflow_engine_requested: str
    workflow_engine_used: str
    demo_mode: str
    collector_mode: str
    analyst_mode: str
    writer_mode: str
    content_mode: str | None
    auto_rework: bool
    rework_count: int
    max_rework: int
    planner_output: PlannerOutput | None
    collector_output: CollectorOutput | None
    analyst_output: AnalystOutput | None
    report_writer_output: ReportWriterOutput | None
    qa_output: QaOutput | None
    final_report_output: FinalReportOutput | None
    evidence_gate_output: dict[str, Any]
    page_fetch_output: dict[str, Any]
    evidence: list[Evidence]
    intent_summary: str | None
    intent_classification: str | None
    extracted_context: PlannerExtractedContext | None
    selected_dimensions: list[str]
    analysis_dimension_plan: AnalysisDimensionPlan | None
    survey_needed: bool
    survey_objective: str | None
    survey_inputs: PlannerSurveyInput | None
    planner_notes: list[str]
    planner_confidence: float | None
    dimension_results: list[DimensionResult]
    survey_evidence: list[SurveyEvidence]
    chunks: list[Chunk]
    retrieval_results: list[RetrievalResult]
    claim_support_results: list[ClaimSupportResult]
    rework_context: ReworkContext | None
    report: Report | None
    qa_result: QaResult | None
    route_to: str | None
    final_status: str | None
    errors: list[str]
    node_sequence: list[str]
    conditional_routes_taken: list[ConditionalRoute]
    workflow_summary: dict[str, Any]
