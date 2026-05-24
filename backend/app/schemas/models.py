from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


TaskStatus = Literal["created", "running", "qa_failed", "manual_review", "completed", "failed"]
AgentName = Literal["PlannerAgent", "CollectorAgent", "AnalystAgent", "ReportWriterAgent", "QaAgent", "FinalReport"]


class CreateTaskRequest(BaseModel):
    product_name: str = Field(min_length=1)
    competitors: list[str] = Field(min_length=1)
    region: str = Field(min_length=1)
    industry: str = Field(min_length=1)


class Task(BaseModel):
    task_id: str
    product_name: str
    competitors: list[str]
    region: str
    industry: str
    status: TaskStatus
    rework_count: int = 0
    created_at: datetime
    updated_at: datetime


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"ev_{uuid4().hex[:10]}")
    source_type: Literal["web", "document", "pricing_page", "review", "interview", "survey"]
    url: str | None = None
    local_ref: str | None = None
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    snippet: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def require_source_reference(self) -> "Evidence":
        if not self.url and not self.local_ref:
            raise ValueError("Evidence requires either url or local_ref")
        return self


class ProductProfile(BaseModel):
    product_name: str
    positioning: str
    target_segments: list[str]
    strengths: list[str]
    weaknesses: list[str]
    evidence_ids: list[str] = Field(min_length=1)
    custom_dimensions: dict[str, Any] = Field(default_factory=dict)


class FeatureTree(BaseModel):
    core_features: dict[str, list[str]]
    differentiators: list[str]
    evidence_ids: list[str] = Field(min_length=1)


class PricingModel(BaseModel):
    model: str
    tiers: list[str]
    pricing_notes: str
    evidence_ids: list[str] = Field(min_length=1)


class UserPersona(BaseModel):
    persona_name: str
    goals: list[str]
    pain_points: list[str]
    buying_triggers: list[str]
    evidence_ids: list[str] = Field(min_length=1)


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: f"claim_{uuid4().hex[:10]}")
    text: str = Field(min_length=1)
    category: Literal["positioning", "feature", "pricing", "persona", "risk", "recommendation"]
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class AgentMessage(BaseModel):
    trace_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    from_agent: AgentName
    to_agent: AgentName
    message_type: Literal["plan", "evidence", "analysis", "report", "qa", "final", "error"]
    schema_name: str = Field(min_length=1)
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReworkInstruction(BaseModel):
    target_agent: AgentName
    error_type: Literal["missing_evidence", "invalid_extraction", "contradiction", "bad_report_format"]
    reason: str
    suggested_action: str
    claim_id: str | None = None


class QaResult(BaseModel):
    task_id: str
    status: Literal["passed", "failed", "manual_review"]
    hard_errors: list[str] = Field(default_factory=list)
    soft_suggestions: list[str] = Field(default_factory=list)
    rework_instructions: list[ReworkInstruction] = Field(default_factory=list)
    route_to: AgentName | None = None
    rework_count: int = 0
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class TraceRecord(BaseModel):
    trace_id: str
    task_id: str
    agent_name: AgentName
    input_summary: str
    output_summary: str
    schema_validation_result: Literal["passed", "failed"]
    model_name: str = "mock-runner-v0"
    token_usage: int | None = None
    elapsed_time_ms: int
    retry_count: int = 0
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Report(BaseModel):
    report_id: str = Field(default_factory=lambda: f"report_{uuid4().hex[:10]}")
    task_id: str
    markdown: str
    json_report: dict[str, Any]
    claims: list[Claim]
    qa_result: QaResult | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DagNode(BaseModel):
    id: AgentName
    label: str
    status: Literal["pending", "running", "completed", "failed", "manual_review"]


class DagEdge(BaseModel):
    source: AgentName
    target: AgentName
    label: str = ""


class Dag(BaseModel):
    nodes: list[DagNode]
    edges: list[DagEdge]


class AgentRunResult(BaseModel):
    message: AgentMessage
    output: dict[str, Any]

    model_config = ConfigDict(arbitrary_types_allowed=True)
