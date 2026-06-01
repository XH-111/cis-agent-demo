# SWOT Step 3 And Python 3.12 Work Note

## Date

2026-05-31

## Scope

This change completes Step 3 of the planner-driven SWOT workflow by adding SWOT-specific QA validation, actionable rework guidance, targeted collector recollection, analyst-side SWOT refinement after rework, and minimal frontend visibility for SWOT quality and reroute behavior.

It also standardizes backend startup on the repository root Python 3.12 virtualenv so local runs do not accidentally fall back to the legacy `backend/.venv` Python 3.8 environment.

## Main Changes

- Added structured SWOT output to analyst and report flows.
- Added SWOT-specific QA checks for:
  - missing or weak evidence support
  - competitor mismatch in SWOT evidence assignment
  - over-inference in opportunities and threats
  - sparse competitor coverage in SWOT
  - planner dimension gaps reflected in SWOT
- Added actionable QA rework instructions with competitor, quadrant, fix type, and query focus metadata.
- Propagated SWOT rework metadata through `QaResult`, `ReworkInstruction`, `ReworkContext`, and workflow summary state.
- Updated collector query planning so planner hints and targeted recollection hints are merged instead of replacing default query behavior.
- Added analyst-side SWOT refinement after rework so weak items can be softened, rebound to same-competitor evidence, or made more conservative.
- Exposed SWOT QA issues, planner/collector guidance, structured SWOT, and reroute visibility in the frontend.
- Added a dedicated backend startup script that explicitly uses the repository root `.venv` Python 3.12 interpreter.
- Updated backend startup documentation to avoid accidental use of `backend/.venv`.

## Files Changed

- `README.md`
- `backend/app/agents/analyst.py`
- `backend/app/agents/collector.py`
- `backend/app/agents/langgraph_runner.py`
- `backend/app/agents/qa.py`
- `backend/app/agents/report_writer.py`
- `backend/app/agents/runner.py`
- `backend/app/api/routes.py`
- `backend/app/schemas/__init__.py`
- `backend/app/schemas/agent_io.py`
- `backend/app/schemas/models.py`
- `backend/app/schemas/workflow_state.py`
- `backend/tests/test_schema_and_workflow.py`
- `docs/agent_contract_reference.md`
- `docs/demo_status_and_next_steps.md`
- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/api/recorder.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/KnowledgeView.tsx`
- `frontend/src/components/PlannerSummaryCard.tsx`
- `frontend/src/components/QaPanel.tsx`
- `frontend/src/components/ReportView.tsx`
- `frontend/src/types.tsx`
- `scripts/start_backend.ps1`

## Validation Summary

Local validation completed during development:

- `backend/tests/test_schema_and_workflow.py` passed fully: `110 passed`
- targeted SWOT Step 3 tests passed
- frontend type check passed with `npx tsc --noEmit`
- backend startup was verified with the root `.venv` Python 3.12 interpreter and `/health` returned `200 OK`

## Known Limitations

- frontend production build still hit a local filesystem permission error when Vite tried to create `frontend/dist/assets`; this was not a TypeScript or Step 3 logic failure
- `backend/.venv` may still exist locally as a legacy Python 3.8 environment and should not be used for backend startup
- the current UI changes are intentionally minimal and focused on verification rather than a larger redesign

## Follow-up Suggestions

- add a guard or warning for legacy `backend/.venv` usage in more local scripts if the team keeps multiple environments around
- extend manual verification with a saved demo task that reliably produces uneven SWOT support across competitors
- consider a future dedicated trace or run-summary section for rework-context visualization once the workflow expands further
