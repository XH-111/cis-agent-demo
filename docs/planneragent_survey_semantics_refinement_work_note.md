# PlannerAgent Survey Semantics Refinement Work Note

## Date

2026-05-30

## Scope

This change is a small semantic refinement pass for `PlannerAgent` focused only on survey signaling consistency. It keeps the existing planner contract, legacy `dag` / `plan` compatibility, and deterministic fallback behavior intact.

## Main Changes

- Clarified the semantic boundary between `survey_needed` and `survey_recommended`.
- Strengthened explicit survey-deliverable requests such as:
  - `generate a survey`
  - `survey direction`
  - `suggest what we should investigate with a user survey`
- Kept questionnaire-decision requests lighter so they can stay recommendation-oriented without forcing full survey generation.
- Kept benchmark-only requests conservative by default so pure comparisons do not become survey-heavy tasks.
- Preserved `survey_inputs` generation only for stronger survey-required cases.

## Behavior Rules

- `survey_needed = true`
  - used when survey or questionnaire work is part of the requested deliverable
  - generates `survey_inputs` when enough context exists

- `survey_recommended = true`
  - used when survey work is useful as a follow-up validation step
  - does not by itself imply full survey generation

- questionnaire-decision requests
  - keep `survey_needed = false`
  - allow `survey_recommended = true`
  - keep `survey_reason` decision-oriented and optional in tone
  - usually keep `survey_inputs = null`

## Files Changed

- `backend/app/agents/planner.py`
- `backend/tests/test_planner_agent_unit.py`
- `docs/planneragent_survey_semantics_refinement_work_note.md`

## Compatibility Notes

- No planner schema fields were removed.
- `survey_needed`, `survey_objective`, and `survey_inputs` remain intact.
- Legacy `dag` and `plan` fields remain unchanged in shape.
- No workflow node or routing contract was changed in this pass.

## Outcome

- Downstream consumers can treat `survey_needed` as the strong execution-oriented signal.
- `survey_recommended` now more clearly represents optional validation follow-up.
- `survey_reason` wording now better matches the actual signaling strength.
- Explicit survey asks are stronger, while benchmark-only requests stay conservative.

## Follow-up Suggestions

- Replace the current planner-only survey metadata with a dedicated survey/questionnaire execution branch on the LangGraph path when that work is prioritized.
- Remove the older superseded survey helper path inside `PlannerAgent` after the broader planner refactor is stabilized.
