# PlannerAgent LLM Upgrade Work Note

## Date

2026-05-29

## Scope

This change upgrades `PlannerAgent` from a fixed deterministic planner into an LLM-enhanced orchestration agent while preserving backward compatibility for existing workflow execution, API consumers, trace behavior, and frontend DAG rendering.

## Main Changes

- Added LLM-assisted intent recognition and structured context extraction inside `PlannerAgent`.
- Preserved legacy `PlannerOutput.dag` and `PlannerOutput.plan` fields for existing consumers.
- Added planner output extensions for:
  - `intent_summary`
  - `intent_classification`
  - `extracted_context`
  - `selected_dimensions`
  - `analysis_dimension_plan`
  - `survey_needed`
  - `survey_objective`
  - `survey_inputs`
  - `missing_information`
  - `planner_notes`
  - `confidence`
  - `downstream_guidance`
  - `diagnostics`
- Added deterministic fallback behavior when the LLM is unavailable or returns invalid data.
- Kept `PlannerAgent` as the single place for routing-oriented planning decisions.
- Updated workflow state and runner integration so both workflow engines can carry planner outputs without breaking existing behavior.
- Preserved trace creation and `run_id` propagation for planner execution.

## Files Changed

- `backend/app/agents/base.py`
- `backend/app/agents/langgraph_runner.py`
- `backend/app/agents/planner.py`
- `backend/app/api/routes.py`
- `backend/app/schemas/__init__.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/models.py`
- `backend/app/schemas/workflow_state.py`

## Compatibility Notes

- `dag` and `plan` remain available and unchanged in shape for legacy consumers.
- The change is additive at the schema level and avoids removing old fields.
- No new agent node was inserted into the live workflow.
- Survey support is planner-driven metadata for now, not a new executed workflow branch.

## Validation Summary

Local validation was completed during development with:

- workflow and schema regression tests
- planner-only unit tests
- manual planner-only runs with real `LlmClient`

The real LLM validation entry worked at the code path level, but the latest manual run still fell back because the configured model endpoint was not reachable from the current environment.

## Known Limitations

- `Task` still does not contain a dedicated free-form user brief field, so planner fallback inference is limited to existing task fields.
- Survey activation currently prepares structured downstream inputs but does not yet execute a separate survey workflow node.
- Real LLM behavior still depends on local network and endpoint availability.

## Follow-up Suggestions

- Add a dedicated user brief field to improve planner intent extraction quality.
- Introduce a real survey/questionnaire execution path on the LangGraph workflow first.
- Let downstream agents selectively consume planner guidance when their contracts are ready.
