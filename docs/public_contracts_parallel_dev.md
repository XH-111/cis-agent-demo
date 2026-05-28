# Phase 10.5 Public Contracts Freeze

This document freezes the minimum shared contracts for parallel Planner, Survey / Questionnaire, and RAG development. It is intentionally limited to public schema and integration boundaries. It does not define business logic for Planner recommendation, Survey generation, or RAG retrieval.

## Scope

Phase 10.5 freezes:

- Shared Pydantic schema names and minimum fields.
- Reserved `WorkflowState` fields.
- Reserved Agent names for Trace / DAG / routing.
- Cross-line interface contracts.
- Directory ownership guidelines.

Phase 10.5 does not implement:

- Dynamic Planner dimension recommendation.
- SurveyAgent / QuestionnaireAgent business logic.
- Chunker / Indexer / Retriever internals.
- Custom runner extensions.
- Large frontend page changes.

## Planner -> Collector / Analyst / RAG

Planner output may be expanded by later work, but these names are frozen:

- `selected_dimensions`
- `analysis_dimension_plan`
- `research_goals`
- `query_hints`
- `metadata`

Minimum contract:

```json
{
  "selected_dimensions": ["positioning", "feature", "pricing", "persona"],
  "analysis_dimension_plan": {
    "selected_dimensions": ["positioning", "pricing"],
    "dimension_plans": [
      {
        "dimension_id": "pricing",
        "label": "Pricing",
        "description": "Pricing and packaging signals",
        "keywords": ["pricing", "plan", "enterprise"],
        "required": true,
        "priority": 1,
        "metadata": {}
      }
    ],
    "research_goals": ["Find official pricing and enterprise packaging signals."],
    "query_hints": {
      "AlphaCI": ["AlphaCI pricing official", "AlphaCI enterprise plan"]
    },
    "metadata": {}
  }
}
```

Rules:

- Planner creates plans only. It must not execute search, survey ingestion, chunking, indexing, or retrieval.
- Collector may read `query_hints`, but must keep its own timeout, fallback, relevance, and source-quality handling.
- Analyst may read `selected_dimensions` / `analysis_dimension_plan` to shape analysis output.
- RAG may read dimension plans to build retrieval queries, but retrieval logic belongs to the RAG line.

## Survey -> Evidence

Survey / Questionnaire output must be convertible to standard `Evidence`. The survey-specific public contract is `SurveyEvidence`.

Minimum `SurveyEvidence`:

```json
{
  "survey_id": "survey_run_1",
  "run_id": "run_123",
  "competitor": "AlphaCI",
  "question_ids": ["q_1", "q_2"],
  "sample_size": 12,
  "is_mock": true,
  "snippet": "Aggregated survey summary without private respondent data.",
  "confidence": 0.65,
  "metadata": {}
}
```

When converted to `Evidence`, it must preserve:

- `run_id`
- `source_type = "survey"`
- `competitor`
- `snippet`
- `confidence`
- `relevance_level`
- `question_ids`
- `sample_size`
- `is_mock`

Rules:

- Do not store private respondent data in Evidence.
- Mock survey output must set `is_mock=true`.
- CSV import should save aggregated summaries and metadata only.
- Survey evidence must not bypass run isolation.

## RAG -> Analyst / QA

RAG output must use `Chunk`, `RetrievalResult`, and later `ClaimSupportResult`.

Minimum `Chunk`:

```json
{
  "chunk_id": "chunk_1",
  "run_id": "run_123",
  "evidence_id": "ev_123",
  "competitor": "AlphaCI",
  "source_url": "https://example.com/pricing",
  "source_domain": "example.com",
  "text": "Short citation-safe chunk text.",
  "metadata": {}
}
```

Minimum `RetrievalResult`:

```json
{
  "chunk_id": "chunk_1",
  "evidence_id": "ev_123",
  "run_id": "run_123",
  "competitor": "AlphaCI",
  "text": "Retrieved chunk text.",
  "score": 0.82,
  "citation_metadata": {
    "source_url": "https://example.com/pricing",
    "source_domain": "example.com",
    "source_quality": "official",
    "relevance_level": "high"
  }
}
```

Minimum `ClaimSupportResult`:

```json
{
  "claim_id": "claim_1",
  "supported": true,
  "support_score": 0.77,
  "retrieval_results": [],
  "reason": "Retrieved chunks support the claim.",
  "metadata": {}
}
```

Rules:

- RAG can only index relevant Evidence or chunks derived from relevant Evidence.
- `Chunk` and `RetrievalResult` must keep `run_id`, `evidence_id`, and `competitor`.
- QA retrieval verification strengthens Claim support checks, but it must not allow Claims without `evidence_ids`.
- Analyst may fall back to Evidence-based analysis if retrieval is unavailable.

## Shared Field Names

Do not rename these fields without a dedicated migration:

- `task_id`
- `run_id`
- `competitor`
- `evidence_id`
- `claim_id`
- `dimension_id`
- `selected_dimensions`
- `analysis_dimension_plan`
- `source_type`
- `source_url`
- `source_domain`
- `source_quality`
- `relevance_score`
- `relevance_level`
- `relevance_reason`
- `confidence`
- `chunk_id`
- `score`
- `citation_metadata`
- `survey_id`
- `question_ids`
- `sample_size`
- `is_mock`
- `route_to`
- `target_agent`
- `error_type`
- `suggested_action`

## Metadata Extension Points

The following fields are intended for line-specific extension:

- `AnalysisDimension.metadata`
- `AnalysisDimensionPlan.metadata`
- `DimensionResult.metadata`
- `Chunk.metadata`
- `RetrievalResult.citation_metadata`
- `ClaimSupportResult.metadata`
- `SurveyEvidence.metadata`
- `ReworkContext.metadata`
- `RouteInstruction.metadata`
- `WorkflowState.workflow_summary`

Rules:

- Store experimental fields in `metadata` before promoting them to top-level schema.
- Metadata must not contain API keys, private personal data, or full copyrighted page bodies.

## Branch Directory Boundaries

### `feature/planner-dimensions`

Allowed:

- `backend/app/agents/planner.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/models.py` for Planner contract fields only
- `backend/app/schemas/workflow_state.py` for Planner state fields only
- Planner tests and docs

Avoid:

- Retriever internals
- Chunker / Indexer
- Survey ingestion
- `backend/app/agents/runner.py`

### `feature/survey-agent`

Allowed:

- New Survey / Questionnaire Agent files
- Survey service files
- Survey schema additions
- Survey tests and docs
- Optional isolated frontend Survey components

Avoid:

- Retriever internals
- Planner recommendation logic
- `backend/app/agents/runner.py`

### `feature/rag-pipeline`

Allowed:

- `backend/app/services/page_fetcher.py`
- New Chunker / Indexer / Retriever service files
- RAG schema additions
- `backend/app/agents/analyst.py` to consume retrieval results
- `backend/app/agents/qa.py` to verify claim support
- `backend/app/agents/langgraph_runner.py` for LangGraph-only RAG nodes
- RAG tests and docs

Avoid:

- Survey question design
- Planner dimension recommendation rules except reading `AnalysisDimensionPlan`
- `backend/app/agents/runner.py`

## High-Risk Public Files

Coordinate before modifying:

- `backend/app/schemas/models.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/workflow_state.py`
- `backend/app/agents/langgraph_runner.py`
- `backend/app/api/routes.py`
- `backend/tests/test_schema_and_workflow.py`
- `frontend/src/App.tsx`
- `frontend/src/api/types.ts`
- `frontend/src/components/DagView.tsx`
- `frontend/src/components/EvidencePanel.tsx`
- `AGENTS.md`

## Merge Order

Recommended order:

1. `phase-10.5-public-contracts-freeze`
2. `feature/planner-dimensions`
3. `feature/rag-pipeline`
4. `feature/survey-agent`

Survey may merge earlier if it stays as an independent module that only outputs `SurveyEvidence` / `Evidence` and does not modify the LangGraph main path.

## Custom Runner Rule

Do not extend `CustomWorkflowRunner` for Planner, Survey, RAG, Chunker, Indexer, Retriever, or HumanReview. New workflow nodes target `LangGraphWorkflowRunner` only.
