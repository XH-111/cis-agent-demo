from typing import Any

from pydantic import ValidationError

from app.agents.base import AgentExecutionError, AgentOutputValidationError, run_with_trace
from app.schemas import Claim, QaResult, Report, ReportWriterInput, ReportWriterOutput
from app.services.evidence_relevance_service import is_relevant_evidence
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
            "llm_schema_validation_success": None,
            "llm_schema_validation_errors": [],
            "llm_category_normalization_count": 0,
            "claim_count_by_competitor": {},
            "missing_claim_competitors": [],
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
            raw_claims = self._mock_claim_payloads(input_data)
            diagnostics.update(self._coverage_diagnostics(task.competitors, raw_claims))
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
                    *[
                        f"- **{claim.competitor or 'overall'} / {claim.claim_id}** {claim.text} Evidence: {', '.join(claim.evidence_ids)}"
                        for claim in claims
                    ],
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
                    "competitor_coverage": self._coverage_diagnostics(task.competitors, [claim.model_dump(mode="json") for claim in claims]),
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
                        "llm_schema_validation_success": False,
                        "llm_schema_validation_errors": [str(exc)],
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
                diagnostics.update(
                    {
                        "llm_error_message": "LLM output missing claims list.",
                        "llm_schema_validation_success": False,
                        "llm_schema_validation_errors": ["LLM output missing claims list."],
                    }
                )
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
                        "llm_schema_validation_success": False,
                        "llm_schema_validation_errors": ["LLM claim missing evidence_ids."],
                    }
                )
                raise AgentOutputValidationError(
                    "LLM claim missing evidence_ids.",
                    output={"claims": claims_payload, "markdown": payload.get("markdown_report", ""), "diagnostics": diagnostics},
                )

            normalized_count = sum(1 for claim in claims_payload if not claim.get("category"))
            try:
                claims = [
                    Claim(
                        claim_id=claim["claim_id"],
                        competitor=claim.get("competitor"),
                        text=claim["text"],
                        evidence_ids=claim["evidence_ids"],
                        category=claim.get("category", "recommendation"),
                        confidence=claim.get("confidence", 0.7),
                    )
                    for claim in claims_payload
                ]
            except (KeyError, ValidationError) as exc:
                diagnostics.update(
                    {
                        "writer_mode_used": "llm",
                        "fallback_used": False,
                        "llm_error_type": exc.__class__.__name__,
                        "llm_error_message": str(exc),
                        "llm_schema_validation_success": False,
                        "llm_schema_validation_errors": [str(exc)],
                        "llm_category_normalization_count": normalized_count,
                    }
                )
                raise AgentOutputValidationError(
                    f"LLM output failed Claim schema validation: {exc}",
                    output={"claims": claims_payload, "markdown": payload.get("markdown_report", ""), "diagnostics": diagnostics},
                ) from exc
            diagnostics.update(
                {
                    "writer_mode_used": "llm",
                    "llm_schema_validation_success": True,
                    "llm_schema_validation_errors": [],
                    "llm_category_normalization_count": normalized_count,
                    **self._coverage_diagnostics(task.competitors, [claim.model_dump(mode="json") for claim in claims]),
                }
            )
            report = Report(
                task_id=task.task_id,
                markdown=payload.get("markdown_report", ""),
                json_report={
                    **(payload.get("json_report") if isinstance(payload.get("json_report"), dict) else {}),
                    "claims": [claim.model_dump(mode="json") for claim in claims],
                    "competitor_coverage": self._coverage_diagnostics(task.competitors, [claim.model_dump(mode="json") for claim in claims]),
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
        claims = [Claim(**item) for item in self._mock_claim_payloads(input_data)]
        diagnostics.update(self._coverage_diagnostics(task.competitors, [claim.model_dump(mode="json") for claim in claims]))
        markdown = "\n".join(
            [
                f"# Competitor Analysis Report: {task.product_name}",
                "",
                "## Executive Summary",
                f"{task.product_name} can differentiate through structured outputs, QA routing, and source-backed claims.",
                "",
                "## Key Claims",
                *[
                    f"- **{claim.competitor or 'overall'} / {claim.claim_id}** {claim.text} Evidence: {', '.join(claim.evidence_ids)}"
                    for claim in claims
                ],
            ]
        )
        report = Report(
            task_id=task.task_id,
            markdown=markdown,
            json_report={
                "knowledge": knowledge.model_dump(mode="json"),
                "claims": [claim.model_dump(mode="json") for claim in claims],
                "competitor_coverage": self._coverage_diagnostics(task.competitors, [claim.model_dump(mode="json") for claim in claims]),
                "writer_mode": "mock",
                "llm_fallback_reason": fallback_reason,
                "writer_diagnostics": diagnostics,
            },
            claims=claims,
            qa_result=QaResult(task_id=task.task_id, status="passed"),
        )
        return ReportWriterOutput(report=report, writer_mode="mock", llm_fallback_reason=fallback_reason, diagnostics=diagnostics)

    @staticmethod
    def _evidence_ids_by_competitor(input_data: ReportWriterInput) -> dict[str, list[str]]:
        grouped = {competitor: [] for competitor in input_data.task.competitors}
        for item in input_data.evidence:
            if item.competitor in grouped and is_relevant_evidence(item):
                grouped[item.competitor].append(item.evidence_id)
        if not any(grouped.values()) and not input_data.evidence:
            competitor_analysis = input_data.knowledge.product_profile.custom_dimensions.get("competitor_analysis", {})
            if isinstance(competitor_analysis, dict):
                for competitor, details in competitor_analysis.items():
                    if competitor in grouped and isinstance(details, dict):
                        ids = details.get("evidence_ids")
                        if isinstance(ids, list):
                            grouped[competitor] = [str(item) for item in ids if item]
        if not any(grouped.values()) and len(input_data.task.competitors) == 1:
            grouped[input_data.task.competitors[0]] = input_data.knowledge.product_profile.evidence_ids
        return grouped

    def _mock_claim_payloads(self, input_data: ReportWriterInput) -> list[dict[str, Any]]:
        grouped = self._evidence_ids_by_competitor(input_data)
        claims: list[dict[str, Any]] = []
        for index, competitor in enumerate(input_data.task.competitors, start=1):
            ids = grouped.get(competitor, [])
            if not ids:
                continue
            claims.append(
                {
                    "claim_id": f"claim_{index:03d}",
                    "competitor": competitor,
                    "text": f"{competitor} is evaluated only with high/medium relevance evidence; current public evidence supports a cautious competitor-specific conclusion.",
                    "category": "positioning",
                    "evidence_ids": [] if input_data.simulate_missing_evidence and index == 1 else ids[:2],
                    "confidence": 0.82,
                }
            )
        if not claims:
            ids = ["insufficient_evidence"] if input_data.evidence else input_data.knowledge.product_profile.evidence_ids
            claims.append(
                {
                    "claim_id": "claim_001",
                    "competitor": None,
                    "text": "当前公开证据不足，暂不做强结论。",
                    "category": "risk",
                    "evidence_ids": [] if input_data.simulate_missing_evidence else ids,
                    "confidence": 0.55,
                }
            )
        return claims

    @staticmethod
    def _coverage_diagnostics(competitors: list[str], claim_payloads: list[dict[str, Any]]) -> dict[str, Any]:
        claim_count_by_competitor = {competitor: 0 for competitor in competitors}
        for claim in claim_payloads:
            competitor = claim.get("competitor")
            if competitor in claim_count_by_competitor:
                claim_count_by_competitor[competitor] += 1
        return {
            "claim_count_by_competitor": claim_count_by_competitor,
            "missing_claim_competitors": [competitor for competitor, count in claim_count_by_competitor.items() if count == 0],
        }

    def _messages(self, input_data: ReportWriterInput) -> list[dict[str, str]]:
        prompt_data: dict[str, Any] = {
            "task": input_data.task.model_dump(mode="json"),
            "knowledge": input_data.knowledge.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in input_data.evidence],
        }
        system = (
            "You are ReportWriterAgent. Write only from supplied Evidence and Knowledge. "
            "Do not invent sources. Every key claim must bind evidence_ids. "
            "The markdown_report should target 1800-2200 Chinese characters when evidence coverage is sufficient. "
            "Do not pad with unsupported facts. If evidence is insufficient, the report may be shorter, but must explain the evidence gaps, uncertainty, and next validation steps. "
            "Structure markdown_report with these sections: "
            "# 竞品分析报告; ## 1. 执行摘要; ## 2. 分析范围与证据说明; ## 3. 竞品概览; "
            "## 4. 功能能力对比; ## 5. 定价与商业模式分析; ## 6. 用户画像与目标场景; "
            "## 7. 风险、不确定性与证据缺口; ## 8. 建议与下一步验证方向. "
            "For each competitor, discuss positioning, feature signals, pricing/business-model signals, user/persona signals, and evidence gaps. "
            "Use tables where useful, but every concrete row-level conclusion must remain traceable to claim evidence_ids. "
            "Evidence ids are not automatically trustworthy: only use Evidence whose relevance_level is high or medium for concrete claims. "
            "Do not use unrelated Evidence. Low relevance Evidence may only support cautious risk notes. "
            "You must cover every input competitor. Each competitor needs its own subsection and at least one claim when its own evidence exists. "
            "Never use one competitor's evidence_ids to support another competitor's claim. "
            "If a competitor lacks evidence, write '当前公开证据不足，暂不做强结论。' and do not fabricate. "
            "Return strict JSON only. If evidence is insufficient, write '证据不足' instead of fabricating. "
            "For claims[].category, use only one of these exact enum values: "
            "positioning, feature, pricing, persona, risk, recommendation. "
            "Do not output Chinese category names or any other category value. "
            "If a competitor lacks high or medium relevant evidence, write '当前公开证据不足，暂不做强结论。' and do not fabricate. "
            "If unsure, use recommendation."
        )
        user = (
            "Return JSON with keys markdown_report, json_report, claims. "
            "markdown_report must be a complete, board-readable competitor analysis report, not a short summary. "
            "When evidence is sufficient, aim for 1800-2200 Chinese characters. "
            "Expand each required section with evidence-backed analysis and avoid generic filler. "
            "Each claim must include claim_id, competitor, text, evidence_ids, category, confidence. "
            "Create 2-4 claims per competitor when that competitor has enough high or medium relevance evidence. "
            "If a competitor has insufficient evidence, create only cautious risk/recommendation claims and clearly state the evidence gap. "
            "claims[].category must be exactly one of: positioning, feature, pricing, persona, risk, recommendation. "
            "claims[].competitor must be one of the input competitors. "
            "Each claim text should be specific enough to support report sections, but must not introduce facts absent from the supplied input. "
            "Example claim: "
            '{"claim_id":"claim_1","competitor":"Feishu","text":"source-backed conclusion","category":"positioning","evidence_ids":["ev_1"],"confidence":0.82}. '
            "Input:\n"
            f"{prompt_data}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
