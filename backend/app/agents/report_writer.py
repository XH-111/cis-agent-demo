from typing import Any

from app.agents.base import AgentExecutionError, AgentOutputValidationError, run_with_trace
from app.schemas import Claim, QaResult, Report, ReportWriterInput, ReportWriterOutput
from app.services.llm_client import LlmClient, parse_llm_json
from app.services.trace_service import TraceService


class ReportWriterAgent:
    name = "ReportWriterAgent"

    def __init__(self, trace_service: TraceService, llm_client: LlmClient | None = None):
        self.trace_service = trace_service
        self.llm_client = llm_client or LlmClient()

    def run(self, input_data: ReportWriterInput) -> ReportWriterOutput:
        if input_data.writer_mode == "llm":
            try:
                return self._run_llm_with_trace(input_data)
            except AgentExecutionError as exc:
                if exc.fallback_to_mock:
                    return self._run_mock(input_data, fallback_reason=str(exc), previous_diagnostics=exc.output)
                return ReportWriterOutput(
                    draft_report=exc.output or {"claims": [], "markdown": "LLM ReportWriter output failed validation."},
                    writer_mode="llm",
                    diagnostics=exc.output.get("diagnostics", {}) if isinstance(exc.output, dict) else {},
                )
        return self._run_mock(input_data)

    def _base_diagnostics(self, input_data: ReportWriterInput) -> dict[str, Any]:
        return {
            "writer_mode_requested": input_data.writer_mode,
            "writer_mode_used": "mock",
            "llm_enabled": self.llm_client.is_available,
            "llm_provider": self.llm_client.provider,
            "llm_model": self.llm_client.model,
            "llm_base_url_configured": bool(self.llm_client.base_url),
            "has_api_key": self.llm_client.is_available,
            "llm_call_attempted": False,
            "llm_call_success": False,
            "llm_elapsed_time_ms": 0,
            "llm_error_type": None,
            "llm_error_message": None,
            "llm_response_preview": None,
            "fallback_used": False,
            "llm_fallback_reason": None,
        }

    def _run_mock(
        self,
        input_data: ReportWriterInput,
        fallback_reason: str | None = None,
        previous_diagnostics: dict | None = None,
    ) -> ReportWriterOutput:
        task = input_data.task
        knowledge = input_data.knowledge

        def produce() -> ReportWriterOutput:
            diagnostics = previous_diagnostics or self._base_diagnostics(input_data)
            diagnostics.update(
                {
                    "writer_mode_used": "mock",
                    "fallback_used": bool(fallback_reason),
                    "llm_fallback_reason": fallback_reason,
                }
            )
            ids = knowledge.product_profile.evidence_ids
            raw_claims = [
                {
                    "text": f"{task.product_name} should compete on auditable report generation, not only raw collection.",
                    "category": "positioning",
                    "evidence_ids": [] if input_data.simulate_missing_evidence else ids,
                    "confidence": 0.84,
                },
                {
                    "text": "Pricing comparison should emphasize collaboration tiers and evidence governance.",
                    "category": "pricing",
                    "evidence_ids": knowledge.pricing_model.evidence_ids,
                    "confidence": 0.8,
                },
                {
                    "text": "Primary users need faster repeatable workflows with source-backed recommendations.",
                    "category": "persona",
                    "evidence_ids": knowledge.user_persona.evidence_ids,
                    "confidence": 0.82,
                },
            ]
            if input_data.simulate_missing_evidence:
                return ReportWriterOutput(
                    draft_report={"claims": raw_claims, "markdown": "# Draft\n\nInvalid claim missing evidence."},
                    writer_mode="mock",
                    llm_fallback_reason=fallback_reason,
                    diagnostics=diagnostics,
                )

            claims = [Claim(**item) for item in raw_claims]
            markdown = "\n".join(
                [
                    f"# Competitor Analysis Report: {task.product_name}",
                    "",
                    "## Executive Summary",
                    f"{task.product_name} can differentiate through structured outputs, QA routing, and source-backed claims.",
                    "",
                    "## Key Claims",
                    *[f"- **{claim.claim_id}** {claim.text} Evidence: {', '.join(claim.evidence_ids)}" for claim in claims],
                ]
            )
            if input_data.force_bad_format:
                markdown = "Competitor report without a level-1 heading\n\nThis content demonstrates QA report-format routing."

            report = Report(
                task_id=task.task_id,
                markdown=markdown,
                json_report={
                    "knowledge": knowledge.model_dump(mode="json"),
                    "claims": [claim.model_dump(mode="json") for claim in claims],
                    "writer_mode": "mock",
                    "llm_fallback_reason": fallback_reason,
                    "writer_diagnostics": diagnostics,
                },
                claims=claims,
                qa_result=QaResult(task_id=task.task_id, status="passed"),
            )
            return ReportWriterOutput(
                report=report,
                writer_mode="mock",
                llm_fallback_reason=fallback_reason,
                diagnostics=diagnostics,
            )

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="QaAgent",
            message_type="report",
            schema_name="ReportWriterOutput",
            input_summary=f"writer_mode_requested={input_data.writer_mode}; Generate Markdown and JSON report with claim evidence_ids",
            retry_count=input_data.retry_count,
            fn=produce,
        )

    def _run_llm_with_trace(self, input_data: ReportWriterInput) -> ReportWriterOutput:
        task = input_data.task

        def produce() -> ReportWriterOutput:
            diagnostics = self._base_diagnostics(input_data)
            messages = self._messages(input_data)
            llm_response = self.llm_client.chat_json(messages)
            diagnostics.update(
                {
                    "llm_call_attempted": llm_response.attempted,
                    "llm_call_success": llm_response.success,
                    "llm_elapsed_time_ms": llm_response.elapsed_time_ms,
                    "llm_error_type": llm_response.error_type,
                    "llm_error_message": llm_response.error_message,
                    "llm_response_preview": llm_response.response_preview,
                }
            )

            if not llm_response.available:
                diagnostics.update(
                    {
                        "writer_mode_used": "mock",
                        "fallback_used": True,
                        "llm_fallback_reason": llm_response.fallback_reason,
                    }
                )
                return self._mock_output_without_trace(input_data, diagnostics, llm_response.fallback_reason)

            try:
                payload = parse_llm_json(llm_response.content or "")
            except Exception as exc:  # noqa: BLE001
                diagnostics.update(
                    {
                        "llm_error_type": exc.__class__.__name__,
                        "llm_error_message": str(exc),
                        "fallback_used": True,
                        "llm_fallback_reason": f"LLM returned invalid JSON: {exc}",
                    }
                )
                raise AgentOutputValidationError(
                    f"LLM returned invalid JSON: {exc}",
                    output=diagnostics,
                    fallback_to_mock=True,
                ) from exc

            claims_payload = payload.get("claims")
            if not isinstance(claims_payload, list):
                diagnostics.update({"llm_error_message": "LLM output missing claims list."})
                raise AgentOutputValidationError(
                    "LLM output missing claims list.",
                    output={"claims": [], "markdown": payload.get("markdown_report", ""), "diagnostics": diagnostics},
                )

            if any(not claim.get("evidence_ids") for claim in claims_payload):
                diagnostics.update(
                    {
                        "writer_mode_used": "llm",
                        "fallback_used": False,
                        "llm_error_message": "LLM claim missing evidence_ids.",
                    }
                )
                raise AgentOutputValidationError(
                    "LLM claim missing evidence_ids.",
                    output={"claims": claims_payload, "markdown": payload.get("markdown_report", ""), "diagnostics": diagnostics},
                )

            claims = [
                Claim(
                    claim_id=claim["claim_id"],
                    text=claim["text"],
                    evidence_ids=claim["evidence_ids"],
                    category=claim.get("category", "recommendation"),
                    confidence=claim.get("confidence", 0.7),
                )
                for claim in claims_payload
            ]
            diagnostics.update({"writer_mode_used": "llm"})
            report = Report(
                task_id=task.task_id,
                markdown=payload.get("markdown_report", ""),
                json_report={
                    **(payload.get("json_report") if isinstance(payload.get("json_report"), dict) else {}),
                    "claims": [claim.model_dump(mode="json") for claim in claims],
                    "writer_mode": "llm",
                    "writer_diagnostics": diagnostics,
                },
                claims=claims,
                qa_result=QaResult(task_id=task.task_id, status="passed"),
            )
            return ReportWriterOutput(report=report, writer_mode="llm", diagnostics=diagnostics)

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="QaAgent",
            message_type="report",
            schema_name="ReportWriterOutput",
            input_summary=f"writer_mode_requested=llm; llm_provider={self.llm_client.provider}; llm_model={self.llm_client.model}; has_api_key={self.llm_client.is_available}",
            retry_count=input_data.retry_count,
            fn=produce,
        )

    def _mock_output_without_trace(
        self,
        input_data: ReportWriterInput,
        diagnostics: dict[str, Any],
        fallback_reason: str | None,
    ) -> ReportWriterOutput:
        task = input_data.task
        knowledge = input_data.knowledge
        ids = knowledge.product_profile.evidence_ids
        claims = [
            Claim(text=f"{task.product_name} should compete on auditable report generation, not only raw collection.", category="positioning", evidence_ids=ids, confidence=0.84),
            Claim(text="Pricing comparison should emphasize collaboration tiers and evidence governance.", category="pricing", evidence_ids=knowledge.pricing_model.evidence_ids, confidence=0.8),
            Claim(text="Primary users need faster repeatable workflows with source-backed recommendations.", category="persona", evidence_ids=knowledge.user_persona.evidence_ids, confidence=0.82),
        ]
        markdown = "\n".join(
            [
                f"# Competitor Analysis Report: {task.product_name}",
                "",
                "## Executive Summary",
                f"{task.product_name} can differentiate through structured outputs, QA routing, and source-backed claims.",
                "",
                "## Key Claims",
                *[f"- **{claim.claim_id}** {claim.text} Evidence: {', '.join(claim.evidence_ids)}" for claim in claims],
            ]
        )
        report = Report(
            task_id=task.task_id,
            markdown=markdown,
            json_report={
                "knowledge": knowledge.model_dump(mode="json"),
                "claims": [claim.model_dump(mode="json") for claim in claims],
                "writer_mode": "mock",
                "llm_fallback_reason": fallback_reason,
                "writer_diagnostics": diagnostics,
            },
            claims=claims,
            qa_result=QaResult(task_id=task.task_id, status="passed"),
        )
        return ReportWriterOutput(report=report, writer_mode="mock", llm_fallback_reason=fallback_reason, diagnostics=diagnostics)

    def _messages(self, input_data: ReportWriterInput) -> list[dict[str, str]]:
        prompt_data: dict[str, Any] = {
            "task": input_data.task.model_dump(mode="json"),
            "knowledge": input_data.knowledge.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in input_data.evidence],
        }
        system = (
            "You are ReportWriterAgent. Write only from supplied Evidence and Knowledge. "
            "Do not invent sources. Every key claim must bind evidence_ids. "
            "Return strict JSON only. If evidence is insufficient, write '证据不足' instead of fabricating."
        )
        user = (
            "Return JSON with keys markdown_report, json_report, claims. "
            "Each claim must include claim_id, text, evidence_ids. "
            "Optional claim fields: category, confidence. Input:\n"
            f"{prompt_data}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
