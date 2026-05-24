# CIS AI Challenge Demo Requirements Summary

## Goal

Build an initial end-to-end demo for a multi-agent competitor analysis system. The demo intentionally avoids real LLM agents, crawlers, RAG, vector search, and complex analysis, but it must provide the production-facing skeleton for replacing mocks later.

## Workflow

```text
PlannerAgent -> CollectorAgent -> AnalystAgent -> ReportWriterAgent -> QaAgent -> FinalReport
```

QA can route failed work back to:

- `CollectorAgent` for missing evidence
- `AnalystAgent` for invalid extraction or contradiction
- `ReportWriterAgent` for bad report format

`max_rework = 3`; when exceeded, the task is marked `manual_review`.

## Backend Scope

- FastAPI application with CORS and health check
- Pydantic schemas for product knowledge, evidence, claims, agent messages, QA, traces, tasks, and reports
- SQLAlchemy + SQLite persistence
- Mock agent runner with structured inputs and outputs
- Trace logging for every agent execution
- REST APIs for task lifecycle, DAG, traces, evidence, QA, and report retrieval

## Schema Rules

- `Claim.evidence_ids` is required and must be non-empty.
- `Evidence` requires `source_type`, either `url` or `local_ref`, `collected_at`, `snippet`, and `confidence`.
- `AgentMessage` requires `trace_id`, `task_id`, `from_agent`, `to_agent`, `message_type`, and `schema_name`.
- Invalid agent outputs must fail validation and cannot silently pass.

## Frontend Scope

- Task creation
- DAG execution status
- Competitor knowledge display
- Markdown and JSON report display
- Clickable claims with evidence/source panel
- QA result panel
- Trace viewer with agent filter

## Tests

Pytest coverage must include:

- Claim without evidence fails validation
- Evidence without URL/local reference fails validation
- AgentMessage without trace/task id fails validation
- QA routing for missing evidence
- `manual_review` after max rework is exceeded
- Every agent execution creates a `TraceRecord`

## Scoring Focus

- Agent collaboration and trustworthy outputs: structured messages, clear roles, traceable claims, real feedback loop
- Engineering completeness: backend, frontend, persistence, APIs, observability, tests
- Product experience: live demo workflow, readable report, source drill-down, QA and trace panels
- Code quality and documentation: modular code, README, LangGraph replacement notes
- Compliance: mock public-source evidence only, no private or sensitive data collection
