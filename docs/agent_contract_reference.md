# Agent Contract Reference

## Scope

This document is implementation-grounded. It describes the current input/output contracts of the agents and workflow-adjacent nodes in this repository, based on code inspection.

Inspected implementation sources:

- `AGENTS.md`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/models.py`
- `backend/app/schemas/workflow_state.py`
- `backend/app/agents/base.py`
- `backend/app/agents/planner.py`
- `backend/app/agents/collector.py`
- `backend/app/agents/analyst.py`
- `backend/app/agents/report_writer.py`
- `backend/app/agents/qa.py`
- `backend/app/agents/final_report.py`
- `backend/app/agents/runner.py`
- `backend/app/agents/langgraph_runner.py`
- `backend/app/agents/runner_factory.py`
- `backend/app/api/routes.py`
- `backend/app/services/evidence_relevance_service.py`
- `backend/app/services/page_fetcher.py`
- `backend/app/services/evidence_service.py`
- `backend/app/services/report_service.py`
- `backend/app/services/trace_service.py`
- `backend/tests/test_schema_and_workflow.py`
- `backend/tests/test_planner_agent_unit.py`
- `frontend/src/api/types.ts`
- `docs/public_contracts_parallel_dev.md`
- `docs/planneragent_llm_upgrade_work_note.md`
- `docs/phase_8_langgraph_workflow_engine.md`
- `docs/architecture.md`

Notation used in this document:

- Implemented: actively produced and consumed by runtime code.
- Reserved: defined in schema or state, but not actively used in runtime flow yet.
- Legacy: preserved mainly for backward compatibility.
- Debug/trace: primarily for diagnostics, audit, or trace display.

## 1. Agent Inventory

| Agent | File | Role | Upstream Inputs | Downstream Outputs |
|---|---|---|---|---|
| `PlannerAgent` | `backend/app/agents/planner.py` | Parse task intent and emit plan plus planner metadata | `PlannerInput` | `PlannerOutput` |
| `CollectorAgent` | `backend/app/agents/collector.py` | Collect public evidence in `mock` or `web` mode | `CollectorInput` | `CollectorOutput` |
| `EvidenceGate` | `backend/app/agents/langgraph_runner.py` | Check competitor relevance coverage before analysis | `WorkflowState.evidence` | `evidence_gate_output`, sometimes synthetic `QaResult` |
| `PageFetcher` | `backend/app/services/page_fetcher.py` and `backend/app/agents/langgraph_runner.py` | Enrich relevant evidence with compliant page excerpts | `WorkflowState.evidence` | enriched `Evidence`, `page_fetch_output` |
| `AnalystAgent` | `backend/app/agents/analyst.py` | Convert evidence into structured competitor knowledge | `AnalystInput` | `AnalystOutput` |
| `ReportWriterAgent` | `backend/app/agents/report_writer.py` | Generate Markdown, JSON report, and claims | `ReportWriterInput` | `ReportWriterOutput` |
| `QaAgent` | `backend/app/agents/qa.py` | Validate schema, evidence quality, competitor coverage, and claim bindings | `QaInput` | `QaOutput` |
| `FinalReportAgent` | `backend/app/agents/final_report.py` | Attach final QA result and evidence summary to report | `FinalReportInput` | `FinalReportOutput` |
| `SurveyAgent` | not implemented | Reserved future survey capability | reserved only | none today |
| `QuestionnaireAgent` | not implemented | Reserved future questionnaire capability | reserved only | none today |

## 2. I/O Schema Table

| Agent | Input Schema | Output Schema | Definition File | Usage Style |
|---|---|---|---|---|
| `PlannerAgent` | `PlannerInput` | `PlannerOutput` | `backend/app/schemas/agent_io.py` | direct Pydantic |
| `CollectorAgent` | `CollectorInput` | `CollectorOutput` | `backend/app/schemas/agent_io.py` | direct Pydantic |
| `AnalystAgent` | `AnalystInput` | `AnalystOutput` | `backend/app/schemas/agent_io.py` | direct Pydantic |
| `ReportWriterAgent` | `ReportWriterInput` | `ReportWriterOutput` | `backend/app/schemas/agent_io.py` | direct Pydantic |
| `QaAgent` | `QaInput` | `QaOutput` | `backend/app/schemas/agent_io.py` | direct Pydantic |
| `FinalReportAgent` | `FinalReportInput` | `FinalReportOutput` | `backend/app/schemas/agent_io.py` | direct Pydantic |
| `EvidenceGate` | none formal | none formal | implemented inline in `backend/app/agents/langgraph_runner.py` | inferred from `WorkflowState` and dict |
| `PageFetcher` | none formal | none formal | implemented in `backend/app/services/page_fetcher.py` | service-based enrichment |

## 3. Shared Core Models

These are the main cross-agent payloads, defined in `backend/app/schemas/models.py`.

### `Task`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `task_id` | `str` | yes | none | task identity | `TaskService.create_task` | all agents | core contract |
| `product_name` | `str` | yes | none | task subject and best available user brief proxy | API/task creation | Planner, Writer | core contract |
| `competitors` | `list[str]` | yes | none | canonical competitors | API/task creation | all agents | core contract |
| `region` | `str` | yes | none | geographic context | API/task creation | Planner, Collector, Analyst | core contract |
| `industry` | `str` | yes | none | industry/domain context | API/task creation | Planner, Collector, Analyst | core contract |
| `status` | `TaskStatus` | yes | none | persisted workflow status | task service | runners, API | debug/state |
| `rework_count` | `int` | no | `0` | current rework round | task service | QA and rerun loops | core routing |
| `created_at` | `datetime` | yes | none | audit timestamp | task service | mostly persistence | debug/audit |
| `updated_at` | `datetime` | yes | none | audit timestamp | task service | mostly persistence | debug/audit |

### `Evidence`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `evidence_id` | `str` | no | generated | stable evidence handle | schema default / persistence | Analyst, Writer, QA, FinalReport | core contract |
| `run_id` | `str \| None` | no | `None` | run isolation | `EvidenceService.save_many`, `PageFetcher.enrich` | APIs, persistence | debug/audit |
| `competitor` | `str \| None` | no | `None` | bind evidence to specific competitor | Collector | Analyst, Writer, QA, EvidenceGate | core contract |
| `source_type` | literal | yes | none | provenance class | Collector, future survey | QA, FinalReport, frontend | core contract |
| `url` | `str \| None` | conditional | `None` | source URL | Collector | PageFetcher, QA, frontend | core contract |
| `local_ref` | `str \| None` | conditional | `None` | non-URL source reference | future/local inputs | validator, frontend | reserved/core |
| `collected_at` | `datetime` | no | `datetime.utcnow()` | collection time | schema default | persistence, frontend | audit |
| `snippet` | `str` | yes | none | short evidence text | Collector | relevance scoring, Analyst, fallback UI | core contract |
| `confidence` | `float` | yes | none | source confidence | Collector | QA, frontend | core contract |
| `source_domain` | `str \| None` | no | `None` | normalized domain | Collector | relevance scoring, QA, frontend | core contract |
| `source_quality` | literal | no | `"unknown"` | source trust tier | Collector | PageFetcher, QA, frontend | core contract |
| `relevance_score` | `float` | no | `1.0` | numeric entity relevance | `apply_relevance` | EvidenceGate, QA, frontend | core contract |
| `relevance_level` | literal | no | `"high"` | categorical relevance gate | `apply_relevance` | EvidenceGate, Analyst, Writer, QA, PageFetcher | core contract |
| `relevance_reason` | `str` | no | mock default | explain relevance decision | `apply_relevance` | frontend, trace/debug | core contract |
| `entity_match_signals` | `dict[str, Any]` | no | `{}` | details of competitor matching | `apply_relevance` | frontend/debug | core contract |
| `content_mode` | literal | no | `"snippet"` | whether content came from snippet or page fetch | Collector/PageFetcher | Analyst, frontend | core contract |
| `page_fetch_success` | `bool` | no | `False` | page fetch outcome | PageFetcher | frontend/debug | core contract |
| `page_title` | `str \| None` | no | `None` | page title | PageFetcher | frontend/debug | weakly used |
| `content_excerpt` | `str \| None` | no | `None` | trimmed fetched body excerpt | PageFetcher | Analyst | core contract |
| `content_chars` | `int \| None` | no | `None` | excerpt char count | PageFetcher | frontend/debug | debug |
| `fetch_status_code` | `int \| None` | no | `None` | fetch response status | PageFetcher | frontend/debug | debug |
| `page_fetch_error` | `str \| None` | no | `None` | fallback reason | PageFetcher | frontend/debug | debug |
| `fetched_at` | `datetime \| None` | no | `None` | page fetch time | PageFetcher | frontend/debug | audit |

### Knowledge Models Produced by `AnalystAgent`

#### `ProductProfile`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `product_name` | `str` | yes | none | analyzed product label | Analyst | Writer, frontend | core contract |
| `positioning` | `str` | yes | none | top-level positioning summary | Analyst | QA, Writer | core contract |
| `target_segments` | `list[str]` | yes | none | audience summary | Analyst | QA, Writer | core contract |
| `strengths` | `list[str]` | yes | none | extracted strengths | Analyst | Writer | core contract |
| `weaknesses` | `list[str]` | yes | none | extracted weaknesses | Analyst | Writer | core contract |
| `evidence_ids` | `list[str]` | yes | none | supporting evidence refs | Analyst | QA, Writer | core contract |
| `custom_dimensions` | `dict[str, Any]` | no | `{}` | extension bucket; currently stores competitor-level analysis and runtime metadata | Analyst | Writer fallback path | core contract extension |

#### `FeatureTree`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `core_features` | `dict[str, list[str]]` | yes | none | grouped feature findings | Analyst | Writer, frontend | core contract |
| `differentiators` | `list[str]` | yes | none | key differentiators | Analyst | Writer | core contract |
| `evidence_ids` | `list[str]` | yes | none | support refs | Analyst | QA, Writer | core contract |

#### `PricingModel`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `model` | `str` | yes | none | pricing summary label | Analyst | Writer | core contract |
| `tiers` | `list[str]` | yes | none | pricing/package signals | Analyst | Writer | core contract |
| `pricing_notes` | `str` | yes | none | pricing caution/notes | Analyst | Writer, QA | core contract |
| `evidence_ids` | `list[str]` | yes | none | support refs | Analyst | QA, Writer | core contract |

#### `UserPersona`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `persona_name` | `str` | yes | none | primary persona label | Analyst | Writer | core contract |
| `goals` | `list[str]` | yes | none | persona goals | Analyst | Writer, QA | core contract |
| `pain_points` | `list[str]` | yes | none | persona pain points | Analyst | Writer | core contract |
| `buying_triggers` | `list[str]` | yes | none | persona triggers | Analyst | Writer | core contract |
| `evidence_ids` | `list[str]` | yes | none | support refs | Analyst | QA, Writer | core contract |

### `Claim`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `claim_id` | `str` | no | generated | stable claim id | Writer | QA, frontend | core contract |
| `competitor` | `str \| None` | no | `None` | bind claim to competitor | Writer | QA, frontend | core contract |
| `text` | `str` | yes | none | claim text | Writer | QA, frontend | core contract |
| `category` | enum | yes | none | claim class | Writer | QA, frontend | core contract |
| `evidence_ids` | `list[str]` | yes | none | evidence binding | Writer | QA, frontend | core contract |
| `confidence` | `float` | yes | none | claim confidence | Writer | frontend, QA | core contract |

### `QaResult`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `task_id` | `str` | yes | none | owning task | QA / EvidenceGate synthetic QA | runners, APIs | core contract |
| `run_id` | `str \| None` | no | `None` | run isolation | report service | APIs | debug/audit |
| `status` | literal | yes | none | pass/fail/manual_review | QA / EvidenceGate | routing, API | core contract |
| `hard_errors` | `list[str]` | no | `[]` | blocking errors | QA / EvidenceGate | frontend/API | core contract |
| `soft_suggestions` | `list[str]` | no | `[]` | non-blocking suggestions | QA | frontend/API | core contract |
| `rework_instructions` | `list[ReworkInstruction]` | no | `[]` | reroute payload | QA / EvidenceGate | runners/frontend | core contract |
| `rework_history` | `list[ReworkHistoryItem]` | no | `[]` | human-readable rework history | custom runner save path | frontend/API | weakly used |
| `route_to` | `AgentName \| None` | no | `None` | reroute target | QA / EvidenceGate | runners | core contract |
| `rework_count` | `int` | no | `0` | loop counter | QA / EvidenceGate | runners | core contract |
| `checked_at` | `datetime` | no | `datetime.utcnow()` | QA timestamp | schema default | API | audit |

## 4. Agent I/O Schemas

All of the following are defined in `backend/app/schemas/agent_io.py`.

### `PlannerInput`

| Field | Type | Req | Default | Purpose | Consumption |
|---|---|---:|---|---|---|
| `task` | `Task` | yes | none | source task | consumed by `PlannerAgent.run()` |
| `run_id` | `str \| None` | no | `None` | run binding for trace | used in planner trace |
| `retry_count` | `int` | no | `0` | trace retry metadata | used by `run_with_trace()` |

### `PlannerOutput`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `dag` | `Dag` | yes | none | workflow DAG for legacy/frontend consumers | `_default_dag()` | run response, frontend DAG, tests | legacy + active |
| `plan` | `list[str]` | yes | none | high-level plan summary | `_default_plan()` | run response, tests | legacy + active |
| `intent_summary` | `str \| None` | no | `None` | plain-language intent summary | LLM/fallback | LangGraph state only | planner-specific |
| `intent_classification` | `str` | no | `"competitive_analysis"` | normalized task intent | LLM/fallback | state, workflow summary, API | planner-specific |
| `extracted_context` | `PlannerExtractedContext \| None` | no | `None` | structured extracted task context | LLM/fallback | state, tests | planner-specific |
| `selected_dimensions` | `list[str]` | no | `[]` | analysis focus dimensions | Planner | state, workflow summary | planner-specific |
| `analysis_dimension_plan` | `AnalysisDimensionPlan \| None` | no | `None` | future structured dimension plan | Planner | state, tests | planner guidance |
| `survey_needed` | `bool` | no | `False` | whether survey support is suggested | Planner | state, workflow summary | survey-related |
| `survey_objective` | `str \| None` | no | `None` | derived survey objective | Planner | state | survey-related |
| `survey_inputs` | `PlannerSurveyInput \| None` | no | `None` | future survey execution inputs | Planner | state, tests | survey-related |
| `missing_information` | `list[str]` | no | `[]` | uncertainty/gap list | Planner | tests, run response | planner guidance |
| `planner_notes` | `list[str]` | no | `[]` | notes and fallback info | Planner | state, tests | planner guidance |
| `confidence` | `float` | no | `0.0` | planner confidence | Planner | LangGraph stores as `planner_confidence` | planner guidance |
| `downstream_guidance` | `PlannerDownstreamGuidance \| None` | no | `None` | future per-agent instructions | Planner | tests only today | planner guidance |
| `diagnostics` | `dict` | no | `{}` | trace/debug payload | Planner | trace/tests | debug/trace |

Runtime note:

- `survey_objective` is derived from `survey_inputs.objective`, not taken directly from raw LLM payload.

### `CollectorInput`

| Field | Type | Req | Default | Purpose | Consumed | Classification |
|---|---|---:|---|---|---|---|
| `task` | `Task` | yes | none | task context | Collector | core |
| `run_id` | `str \| None` | no | `None` | run binding | trace/persistence path | debug/audit |
| `retry_count` | `int` | no | `0` | trace retry metadata | trace | debug |
| `collector_mode` | `"mock" \| "web"` | no | `"mock"` | collection mode | Collector | core |
| `gate_context` | `dict` | no | `{}` | intended EvidenceGate rework context | currently not read by `CollectorAgent` | reserved/weakly used |

### `CollectorOutput`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `evidence` | `list[Evidence]` | yes | none | collected evidence records | Collector | Analyst, QA, EvidenceGate, PageFetcher | core contract |
| `diagnostics` | `dict` | no | `{}` | collection stats and fallback info | Collector | trace/tests | debug/trace |

### `AnalystInput`

| Field | Type | Req | Default | Purpose | Consumed | Classification |
|---|---|---:|---|---|---|---|
| `task` | `Task` | yes | none | task context | Analyst | core |
| `run_id` | `str \| None` | no | `None` | run binding | trace/persistence path | debug/audit |
| `evidence` | `list[Evidence]` | yes | none | evidence to analyze | Analyst | core |
| `retry_count` | `int` | no | `0` | trace retry metadata | trace | debug |
| `force_invalid_extraction` | `bool` | no | `False` | intentionally break outputs for QA demos/tests | Analyst mock/evidence output branches | demo/test only |
| `analyst_mode` | `"mock" \| "evidence" \| "llm"` | no | `"evidence"` | analysis mode | Analyst | core |

Runtime note:

- `analyst_mode="llm"` is not implemented; code falls back to evidence mode with diagnostics.

### `AnalystOutput`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `product_profile` | `ProductProfile` | yes | none | structured positioning summary | Analyst | Writer, QA | core contract |
| `feature_tree` | `FeatureTree` | yes | none | structured feature summary | Analyst | Writer, QA | core contract |
| `pricing_model` | `PricingModel` | yes | none | structured pricing summary | Analyst | Writer, QA | core contract |
| `user_persona` | `UserPersona` | yes | none | structured persona summary | Analyst | Writer, QA | core contract |
| `diagnostics` | `dict` | no | `{}` | evidence-use, coverage, mode info | Analyst | trace/tests | debug/trace |

### `ReportWriterInput`

| Field | Type | Req | Default | Purpose | Consumed | Classification |
|---|---|---:|---|---|---|---|
| `task` | `Task` | yes | none | task context | Writer | core |
| `run_id` | `str \| None` | no | `None` | run binding | trace/persistence path | debug/audit |
| `knowledge` | `AnalystOutput` | yes | none | structured knowledge | Writer | core |
| `evidence` | `list[Evidence]` | no | `[]` | evidence for claim binding and prompts | Writer | core |
| `retry_count` | `int` | no | `0` | trace retry metadata | trace | debug |
| `simulate_missing_evidence` | `bool` | no | `False` | create invalid draft for tests | Writer | demo/test only |
| `force_bad_format` | `bool` | no | `False` | create invalid markdown for tests | Writer | demo/test only |
| `writer_mode` | `"mock" \| "llm"` | no | `"mock"` | generation mode | Writer | core |

### `ReportWriterOutput`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `report` | `Report \| None` | no | `None` | main success output | Writer | QA, FinalReport, API | core contract |
| `draft_report` | `dict \| None` | no | `None` | partial/invalid output path | Writer | QA | weakly used |
| `writer_mode` | `"mock" \| "llm"` | no | `"mock"` | actual mode used | Writer | frontend/debug | debug/state |
| `llm_fallback_reason` | `str \| None` | no | `None` | reason for LLM fallback | Writer | QA suggestions, frontend/debug | debug |
| `diagnostics` | `dict` | no | `{}` | writer/LLM validation diagnostics | Writer | trace/tests | debug/trace |

Runtime note:

- `Report.qa_result` inside `report` is a placeholder `passed` result at Writer time and is overwritten only by `FinalReportAgent` on success.

### `QaInput`

| Field | Type | Req | Default | Purpose | Consumed | Classification |
|---|---|---:|---|---|---|---|
| `task` | `Task` | yes | none | task context | QA | core |
| `run_id` | `str \| None` | no | `None` | run binding | persistence path | debug/audit |
| `evidence` | `list[Evidence]` | no | `[]` | evidence under validation | QA | core |
| `analysis` | `AnalystOutput \| None` | no | `None` | analyst output to validate | QA | core optional |
| `report_output` | `ReportWriterOutput \| None` | no | `None` | report output to validate | QA | core optional |
| `retry_count` | `int` | no | `0` | trace retry metadata | trace | debug |
| `demo_mode` | demo enum | no | `"normal"` | simulate QA routes | QA | demo/test only |

### `QaOutput`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `qa_result` | `QaResult` | yes | none | authoritative QA result | QA | routing, API, FinalReport | core contract |
| `diagnostics` | `dict` | no | `{}` | QA diagnostics details | QA | trace/tests | debug/trace |

Runtime note:

- persisted QA APIs expose `QaResult`, not `QaOutput.diagnostics`.

### `FinalReportInput`

| Field | Type | Req | Default | Purpose | Consumed | Classification |
|---|---|---:|---|---|---|---|
| `task` | `Task` | yes | none | task context | FinalReportAgent | core |
| `run_id` | `str \| None` | no | `None` | run binding | persistence path | debug/audit |
| `report` | `Report` | yes | none | report to finalize | FinalReportAgent | core |
| `qa_result` | `QaResult` | yes | none | final QA result | FinalReportAgent | core |
| `evidence` | `list[Evidence]` | yes | none | source evidence for summary | FinalReportAgent | core |
| `retry_count` | `int` | no | `0` | trace retry metadata | trace | debug |

### `FinalReportOutput`

| Field | Type | Req | Default | Purpose | Produced | Consumed | Classification |
|---|---|---:|---|---|---|---|---|
| `report` | `Report` | yes | none | finalized report | FinalReportAgent | persistence/API | core contract |
| `evidence_summary` | `list[str]` | yes | none | human-readable evidence summary | FinalReportAgent | report JSON/UI/debug | core contract |

## 5. Planner-Related Models

These are all defined in `backend/app/schemas/models.py`.

### `PlannerExtractedContext`

Purpose: normalized interpretation of task intent and context.

Fields:

- `intent_classification`: planner intent label. Implemented, but only stored and surfaced.
- `industry`: inferred industry context.
- `domain`: domain/subdomain.
- `product_name`: interpreted product target.
- `product_type`: inferred product type.
- `target_users`: inferred target users.
- `region`: region context.
- `competitors_mentioned`: competitors recognized from task or payload.
- `analysis_focus_points`: extracted focus points.
- `requested_outputs`: inferred desired deliverables.
- `survey_needed`: whether survey support is indicated.
- `survey_reason`: explanation for survey flag.
- `missing_information`: uncertainties and absent inputs.
- `confidence`: extraction confidence.

Current usage:

- populated in `PlannerAgent._build_extracted_context()`
- stored in `WorkflowState.extracted_context`
- surfaced in planner tests and direct planner scripts
- not consumed by Collector, Analyst, Writer, or QA yet

Classification: planner-specific, partially underused.

### `AnalysisDimensionPlan`

Purpose: planner-selected dimensions plus future retrieval/query guidance.

Important fields:

- `selected_dimensions`
- `dimension_plans`
- `research_goals`
- `query_hints`
- `metadata`

Current usage:

- produced by `PlannerAgent._build_dimension_plan()`
- stored in `WorkflowState.analysis_dimension_plan`
- validated in tests
- not read by `CollectorAgent`, `AnalystAgent`, or any RAG node yet

Classification: planner guidance, reserved for stronger downstream use.

### `PlannerSurveyInput`

Purpose: future survey/questionnaire execution input.

Fields:

- `objective`
- `respondent_type`
- `question_themes`
- `hypotheses`
- `metadata`

Current usage:

- produced by `PlannerAgent._build_survey_inputs()`
- stored in `PlannerOutput` and `WorkflowState`
- tested in planner unit tests
- no `SurveyAgent` consumes it yet

Classification: survey-related, reserved.

### `PlannerDownstreamGuidance`

Purpose: human-readable per-agent guidance.

Fields:

- `collector`
- `analyst`
- `writer`
- `qa`
- `survey`

Current usage:

- produced by `PlannerAgent._build_guidance()`
- exposed in `PlannerOutput`
- tested
- not consumed by runtime downstream agents

Classification: planner guidance, currently unused in runtime.

## 6. Survey and Reserved Future Models

Defined in `backend/app/schemas/models.py`.

### `SurveyEvidence`

Purpose: future survey/questionnaire output that can later be transformed into standard `Evidence`.

Fields:

- `survey_id`
- `run_id`
- `competitor`
- `question_ids`
- `sample_size`
- `is_mock`
- `snippet`
- `confidence`
- `metadata`

Current usage:

- schema tests only
- `WorkflowState.survey_evidence` reserved
- no agent or API path actively produces or consumes it today

Classification: reserved future contract.

### Other Reserved Models

- `DimensionResult`
- `Chunk`
- `RetrievalResult`
- `ClaimSupportResult`
- `ReworkContext`
- `RouteInstruction`

Current usage:

- schema validation and state reservation
- not part of active mainline runtime

## 7. Cross-Agent Contract Flow

### Custom Runner

Actual runtime chain in `backend/app/agents/runner.py`:

```text
PlannerAgent
-> CollectorAgent
-> AnalystAgent
-> ReportWriterAgent
-> QaAgent
-> FinalReportAgent
```

Flow:

- `PlannerOutput` is returned as `plan` in API response.
- `CollectorOutput.evidence` is persisted and passed into `AnalystInput.evidence`.
- `AnalystOutput` is passed into `ReportWriterInput.knowledge`.
- `ReportWriterOutput` is passed into `QaInput.report_output`.
- `QaResult` drives reroute loops when `auto_rework=true`.
- `FinalReportInput` is only created if QA passes and `writer_output.report` exists.

### LangGraph Runner

Actual runtime chain in `backend/app/agents/langgraph_runner.py`:

```text
PlannerAgent
-> CollectorAgent
-> EvidenceGate
-> PageFetcher
-> AnalystAgent
-> ReportWriterAgent
-> QaAgent
-> FinalReportAgent
```

Flow:

- `PlannerOutput` is written into `WorkflowState.planner_output`, plus planner fields are broken out into dedicated state fields.
- `CollectorOutput.evidence` is persisted into `WorkflowState.evidence`.
- `EvidenceGate` reads `WorkflowState.evidence` and writes `evidence_gate_output`, `qa_result`, `route_to`, `final_status`, and route history when relevant evidence is missing.
- `PageFetcher` enriches `WorkflowState.evidence` and writes `page_fetch_output`.
- `AnalystAgent` reads enriched `WorkflowState.evidence`.
- `ReportWriterAgent` reads `WorkflowState.analyst_output` and `WorkflowState.evidence`.
- `QaAgent` reads evidence, analysis, and report output.
- `route_after_qa()` uses `QaResult.status`, `route_to`, and `rework_count`.
- `FinalReportAgent` only runs on pass path.

## 8. Workflow State Mapping

Defined in `backend/app/schemas/workflow_state.py`.

| State Field | Type | Written By | Read By | Status |
|---|---|---|---|---|
| `task_id`, `run_id`, `task`, `task_run` | identity/meta | runner init | all nodes | active |
| `run_status` | `str \| None` | runner init | not meaningfully used | weakly used |
| `workflow_engine_requested`, `workflow_engine_used` | meta | runner init | workflow summary/API | active |
| `demo_mode`, `collector_mode`, `analyst_mode`, `writer_mode`, `content_mode`, `auto_rework`, `rework_count`, `max_rework` | control flags | runner init / route nodes | nodes and routers | active |
| `planner_output` | `PlannerOutput \| None` | planner node | API return | active |
| `collector_output` | `CollectorOutput \| None` | collector node | mostly debug | weakly used |
| `analyst_output` | `AnalystOutput \| None` | analyst node | writer, QA | active |
| `report_writer_output` | `ReportWriterOutput \| None` | writer node | QA, final | active |
| `qa_output` | `QaOutput \| None` | QA node | mostly debug | weakly used |
| `final_report_output` | `FinalReportOutput \| None` | final node | mostly debug | weakly used |
| `evidence_gate_output` | `dict[str, Any]` | EvidenceGate | route functions, frontend summary | active |
| `page_fetch_output` | `dict[str, Any]` | PageFetcher node | workflow summary/frontend | active |
| `evidence` | `list[Evidence]` | collector/page fetcher | gate, analyst, QA, final | active |
| `intent_summary` | `str \| None` | planner node | not used downstream | underused |
| `intent_classification` | `str \| None` | planner node | workflow summary | partially used |
| `extracted_context` | `PlannerExtractedContext \| None` | planner node | not used downstream | underused |
| `selected_dimensions` | `list[str]` | planner node | workflow summary only | underused |
| `analysis_dimension_plan` | `AnalysisDimensionPlan \| None` | planner node | not used downstream | reserved/underused |
| `survey_needed` | `bool` | planner node | workflow summary only | underused |
| `survey_objective` | `str \| None` | planner node | not used downstream | underused |
| `survey_inputs` | `PlannerSurveyInput \| None` | planner node | not used downstream | reserved |
| `planner_notes` | `list[str]` | planner node | not used downstream | underused |
| `planner_confidence` | `float \| None` | planner node | not used downstream | underused |
| `dimension_results` | `list[DimensionResult]` | nobody today | nobody today | reserved |
| `survey_evidence` | `list[SurveyEvidence]` | nobody today | nobody today | reserved |
| `chunks` | `list[Chunk]` | nobody today | nobody today | reserved |
| `retrieval_results` | `list[RetrievalResult]` | nobody today | nobody today | reserved |
| `claim_support_results` | `list[ClaimSupportResult]` | nobody today | nobody today | reserved |
| `rework_context` | `ReworkContext \| None` | nobody today | nobody today | reserved |
| `report` | `Report \| None` | writer/final nodes | API return | active |
| `qa_result` | `QaResult \| None` | EvidenceGate or QA node | routers/final/API | active |
| `route_to` | `str \| None` | EvidenceGate or QA node | route functions | active |
| `final_status` | `str \| None` | EvidenceGate / QA / final node | summary/API | active |
| `errors` | `list[str]` | runner init | workflow summary | weakly used |
| `node_sequence` | `list[str]` | every node | workflow summary/frontend | active |
| `conditional_routes_taken` | `list[ConditionalRoute]` | EvidenceGate / QA node | workflow summary/frontend | active |
| `workflow_summary` | `dict[str, Any]` | runner after invoke | API/frontend | active |

Implementation note:

- `LangGraphWorkflowRunner` also inserts `run_isolation_strategy` and `run_cleanup_summary` into state-like data, but these fields are not declared in `WorkflowState`.

## 9. Contract Risks and Mismatches

### Planner fields exist but mostly do not drive downstream runtime

The following are produced and carried, but not used by Collector, Analyst, Writer, or QA logic:

- `intent_summary`
- `extracted_context`
- `selected_dimensions`
- `analysis_dimension_plan`
- `survey_objective`
- `survey_inputs`
- `planner_notes`
- `planner_confidence`
- `downstream_guidance`

### `CollectorInput.gate_context` is passed but not consumed

- LangGraph passes `state["evidence_gate_output"]` into `CollectorInput.gate_context`.
- `CollectorAgent` does not read it.
- This does not yet satisfy the documented intent that Collector should use rework context to target missing competitors.

### `AnalysisDimensionPlan.query_hints` is documented for downstream use but unused

- Docs say Collector may read planner query hints.
- Current `CollectorAgent` builds queries internally and ignores planner output.

### `Report.qa_result` is a placeholder before finalization

- `ReportWriterAgent` creates `Report.qa_result=QaResult(status="passed")` before real QA executes.
- `FinalReportAgent` overwrites it only on pass path.
- Consumers should treat Writer-stage report QA as provisional.

### `QaOutput.diagnostics` is not part of persisted QA API contract

- Runtime QA trace stores diagnostics.
- `/api/tasks/{task_id}/qa` returns persisted `QaResult`, not `QaOutput`.

### Custom runner and LangGraph runner do not expose equivalent contracts

- Custom runner does not execute `EvidenceGate` or `PageFetcher`.
- LangGraph runner does.
- Custom workflow summary in `backend/app/api/routes.py` is synthesized, not state-native.
- Custom path exposes fewer workflow-level structured outputs.

### `EvidenceGate` and `PageFetcher` do not have formal agent I/O schemas

- They rely on `WorkflowState` and ad hoc dict outputs.
- This is weaker than the schema-first intent described in project docs.

### Final failure/manual states do not go through a formal final-output schema path

- `FinalReportAgent.run()` is only called on QA pass path.
- On failed/manual states, runners set `report=None` and only expose status through workflow summary and QA.
- This is narrower than the documented intent that final state should remain fully explainable as a final execution artifact.

### Trace `run_id` propagation is not uniform at call sites

- `PlannerAgent` explicitly passes `run_id` into `run_with_trace()`.
- Other agents rely on `TraceService.set_run_context()` for implicit trace binding.

## 10. Most Important Live Contracts

If you need to understand the current production-relevant path first, start with these:

1. `Evidence`
2. `AnalystOutput`
3. `Claim`
4. `Report`
5. `QaResult`
6. `WorkflowState.evidence_gate_output`
7. `WorkflowState.page_fetch_output`

Most important active agent-to-agent flows:

1. `CollectorOutput.evidence -> AnalystInput.evidence`
2. `Evidence.relevance_level/source_quality -> EvidenceGate/PageFetcher/QA`
3. `AnalystOutput -> ReportWriterInput.knowledge`
4. `Report.claims[*].evidence_ids -> QaAgent`
5. `QaResult.route_to/rework_count/status -> reroute behavior`

## 11. Best Next Fields to Consume

If the goal is to make `PlannerAgent` meaningfully guide downstream behavior, the next best fields to wire into runtime are:

1. `analysis_dimension_plan.query_hints`
   Use in `CollectorAgent` query construction.

2. `selected_dimensions`
   Use in `AnalystAgent` to prioritize extraction emphasis.

3. `downstream_guidance.writer`
   Use in `ReportWriterAgent` prompt framing or section emphasis.

4. `survey_needed` and `survey_inputs`
   Use to trigger a real `SurveyAgent` or `QuestionnaireAgent` branch in LangGraph.

5. `rework_context` and `CollectorInput.gate_context`
   Use to make Collector rework targeted instead of generic.

## 12. Summary

Current implementation already has a strong core contract around:

- `Evidence`
- competitor binding
- relevance gating
- evidence-backed `Claim`
- `QaResult` reroute semantics
- run-scoped persistence

The largest contract gap is not missing schemas, but under-consumed schemas:

- Planner outputs are now rich and structured.
- Survey/RAG public contracts are defined.
- Workflow state already reserves future integration fields.
- But most of those fields are not yet active participants in downstream runtime behavior.
