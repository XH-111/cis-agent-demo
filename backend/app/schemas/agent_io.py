from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.models import Dag, Evidence, FeatureTree, PricingModel, ProductProfile, QaResult, Report, Task, UserPersona


DemoMode = Literal["normal", "qa_missing_evidence", "qa_invalid_extraction", "qa_bad_report"]


class PlannerInput(BaseModel):
    task: Task
    retry_count: int = 0


class PlannerOutput(BaseModel):
    dag: Dag
    plan: list[str] = Field(min_length=1)


class CollectorInput(BaseModel):
    task: Task
    retry_count: int = 0


class CollectorOutput(BaseModel):
    evidence: list[Evidence]


class AnalystInput(BaseModel):
    task: Task
    evidence: list[Evidence]
    retry_count: int = 0
    force_invalid_extraction: bool = False


class AnalystOutput(BaseModel):
    product_profile: ProductProfile
    feature_tree: FeatureTree
    pricing_model: PricingModel
    user_persona: UserPersona


class ReportWriterInput(BaseModel):
    task: Task
    knowledge: AnalystOutput
    evidence: list[Evidence] = Field(default_factory=list)
    retry_count: int = 0
    simulate_missing_evidence: bool = False
    force_bad_format: bool = False
    writer_mode: Literal["mock", "llm"] = "mock"


class ReportWriterOutput(BaseModel):
    report: Report | None = None
    draft_report: dict | None = None
    writer_mode: Literal["mock", "llm"] = "mock"
    llm_fallback_reason: str | None = None
    diagnostics: dict = Field(default_factory=dict)


class QaInput(BaseModel):
    task: Task
    evidence: list[Evidence] = Field(default_factory=list)
    analysis: AnalystOutput | None = None
    report_output: ReportWriterOutput | None = None
    retry_count: int = 0
    demo_mode: DemoMode = "normal"


class QaOutput(BaseModel):
    qa_result: QaResult


class FinalReportInput(BaseModel):
    task: Task
    report: Report
    qa_result: QaResult
    evidence: list[Evidence]
    retry_count: int = 0


class FinalReportOutput(BaseModel):
    report: Report
    evidence_summary: list[str]
