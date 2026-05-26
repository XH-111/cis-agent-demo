from app.agents.base import run_with_trace
from app.schemas import QaInput, QaOutput, QaResult, ReworkInstruction
from app.services.trace_service import TraceService

MAX_REWORK = 3


class QaAgent:
    name = "QaAgent"

    def __init__(self, trace_service: TraceService):
        self.trace_service = trace_service

    def _result(
        self,
        task_id: str,
        rework_count: int,
        target_agent: str,
        error_type: str,
        reason: str,
        suggested_action: str,
        claim_id: str | None = None,
        failed_claim: str | None = None,
        failed_schema: str | None = None,
    ) -> QaResult:
        if rework_count >= MAX_REWORK:
            return QaResult(
                task_id=task_id,
                status="manual_review",
                hard_errors=[reason],
                route_to=None,
                rework_count=rework_count,
                rework_instructions=[
                    ReworkInstruction(
                        target_agent=target_agent,
                        error_type=error_type,
                        reason=reason,
                        suggested_action="已超过最大返工次数，请人工复核。",
                        claim_id=claim_id,
                        failed_claim=failed_claim,
                        failed_schema=failed_schema,
                    )
                ],
            )

        return QaResult(
            task_id=task_id,
            status="failed",
            hard_errors=[reason],
            rework_instructions=[
                ReworkInstruction(
                    target_agent=target_agent,
                    error_type=error_type,
                    reason=reason,
                    suggested_action=suggested_action,
                    claim_id=claim_id,
                    failed_claim=failed_claim,
                    failed_schema=failed_schema,
                )
            ],
            route_to=target_agent,
            rework_count=rework_count + 1,
        )

    def _missing_relevant_evidence_result(self, input_data: QaInput, missing: list[str]) -> QaResult:
        return self._result(
            input_data.task.task_id,
            input_data.task.rework_count,
            "CollectorAgent",
            "missing_relevant_evidence",
            f"Missing relevant public evidence for competitors: {', '.join(missing)}. 未找到与该竞品明确相关的公开证据，暂不生成强结论。",
            "Re-run CollectorAgent with precise per-competitor search; do not use unrelated search results as Evidence.",
            failed_schema="Evidence.relevance",
        )

    def evaluate(self, input_data: QaInput) -> QaResult:
        task = input_data.task
        rework_count = task.rework_count

        if input_data.demo_mode == "qa_missing_evidence" or not input_data.evidence:
            return self._result(
                task.task_id,
                rework_count,
                "CollectorAgent",
                "missing_evidence",
                "当前任务没有可用 Evidence，无法支撑后续分析和报告结论。",
                "请重新运行 CollectorAgent，补充至少一条带 url 或 local_ref 的 Evidence。",
                failed_schema="Evidence",
            )

        evidence_coverage_issue = self._competitor_evidence_coverage_issue(input_data)
        if evidence_coverage_issue is not None:
            return evidence_coverage_issue

        relevance_coverage_issue = self._competitor_relevance_coverage_issue(input_data)
        if relevance_coverage_issue is not None:
            return relevance_coverage_issue

        if input_data.analysis is None:
            return self._result(
                task.task_id,
                rework_count,
                "AnalystAgent",
                "invalid_extraction",
                "缺少 AnalystAgent 的结构化分析输出。",
                "请重新运行 AnalystAgent，生成 ProductProfile、FeatureTree、PricingModel 和 UserPersona。",
                failed_schema="AnalystOutput",
            )

        profile = input_data.analysis.product_profile
        if input_data.demo_mode == "qa_invalid_extraction" or not profile.positioning or not profile.target_segments:
            return self._result(
                task.task_id,
                rework_count,
                "AnalystAgent",
                "invalid_extraction",
                "ProductProfile 关键字段为空，疑似抽取错误或结构化结果冲突。",
                "请重新运行 AnalystAgent，修复 ProductProfile 的 positioning 和 target_segments。",
                failed_schema="ProductProfile",
            )

        if self._has_unsupported_analysis(input_data):
            return self._result(
                task.task_id,
                rework_count,
                "AnalystAgent",
                "invalid_extraction",
                "AnalystAgent 输出存在明显 unsupported conclusion，需要回到结构化抽取阶段修正。",
                "请重新运行 AnalystAgent，确保结构化结论绑定 Evidence 且避免 unsupported conclusion。",
                failed_schema="AnalystOutput",
            )

        if input_data.report_output is None:
            return self._result(
                task.task_id,
                rework_count,
                "ReportWriterAgent",
                "bad_report_format",
                "缺少 ReportWriterAgent 的报告输出。",
                "请重新运行 ReportWriterAgent，生成 Markdown 和 JSON 报告。",
                failed_schema="ReportWriterOutput",
            )

        if input_data.report_output.draft_report:
            for claim in input_data.report_output.draft_report.get("claims", []):
                if not claim.get("evidence_ids"):
                    return self._result(
                        task.task_id,
                        rework_count,
                        "ReportWriterAgent",
                        "bad_report_format",
                        "报告草稿中存在未绑定 evidence_ids 的结论。",
                        "请为该结论补充明确的 evidence_ids，或删除无法被证据支撑的结论。",
                        failed_claim=claim.get("text"),
                    )

        if input_data.report_output.report is None:
            return self._result(
                task.task_id,
                rework_count,
                "ReportWriterAgent",
                "bad_report_format",
                "报告输出为空，无法进入最终报告阶段。",
                "请重新生成包含 markdown_report、json_report 和 claims 的报告对象。",
                failed_schema="Report",
            )

        report = input_data.report_output.report
        if input_data.demo_mode == "qa_bad_report" or not report.markdown.startswith("#"):
            return self._result(
                task.task_id,
                rework_count,
                "ReportWriterAgent",
                "bad_report_format",
                "Markdown 报告必须以一级标题开头。",
                "请重新生成包含一级标题和关键结论章节的 Markdown 报告。",
                failed_schema="Report.markdown",
            )

        for claim in report.claims:
            if not claim.evidence_ids:
                return self._result(
                    task.task_id,
                    rework_count,
                    "ReportWriterAgent",
                    "bad_report_format",
                    f"结论 {claim.claim_id} 缺少 evidence_ids。",
                    "请为每条关键结论绑定 evidence_ids。",
                    claim_id=claim.claim_id,
                    failed_claim=claim.text,
                )

        unrelated_claim_issue = self._unrelated_evidence_claim_issue(input_data)
        if unrelated_claim_issue is not None:
            return unrelated_claim_issue

        claim_coverage_issue = self._competitor_claim_coverage_issue(input_data)
        if claim_coverage_issue is not None:
            return claim_coverage_issue

        quality_suggestions, _ = self._quality_suggestions(input_data)
        return QaResult(
            task_id=task.task_id,
            status="passed",
            soft_suggestions=[
                suggestion
                for suggestion in [
                    "生产环境接入前，请将 Mock 证据替换为真实采集器输出。",
                    input_data.report_output.llm_fallback_reason if input_data.report_output else None,
                    *self._analysis_suggestions(input_data.analysis),
                    *quality_suggestions,
                ]
                if suggestion
            ],
            rework_count=rework_count,
        )

    def _competitor_evidence_coverage_issue(self, input_data: QaInput) -> QaResult | None:
        if not any(item.competitor for item in input_data.evidence):
            return None
        evidence_count_by_competitor = {
            competitor: sum(1 for item in input_data.evidence if item.competitor == competitor)
            for competitor in input_data.task.competitors
        }
        missing = [competitor for competitor, count in evidence_count_by_competitor.items() if count == 0]
        if not missing:
            return None
        return self._result(
            input_data.task.task_id,
            input_data.task.rework_count,
            "CollectorAgent",
            "missing_evidence",
            f"Missing competitor evidence coverage: {', '.join(missing)}.",
            "Re-run CollectorAgent with per-competitor search and ensure every competitor has Evidence.",
            failed_schema="Evidence.competitor",
        )

    def _competitor_relevance_coverage_issue(self, input_data: QaInput) -> QaResult | None:
        if not any(item.competitor for item in input_data.evidence):
            return None
        relevant_count_by_competitor = {
            competitor: sum(
                1
                for item in input_data.evidence
                if item.competitor == competitor and item.relevance_level in {"high", "medium"}
            )
            for competitor in input_data.task.competitors
        }
        missing = [competitor for competitor, count in relevant_count_by_competitor.items() if count == 0]
        if missing:
            return self._missing_relevant_evidence_result(input_data, missing)
        return None

    def _unrelated_evidence_claim_issue(self, input_data: QaInput) -> QaResult | None:
        if input_data.report_output is None or input_data.report_output.report is None:
            return None
        evidence_by_id = {item.evidence_id: item for item in input_data.evidence}
        for claim in input_data.report_output.report.claims:
            for evidence_id in claim.evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence and evidence.relevance_level == "unrelated":
                    return self._result(
                        input_data.task.task_id,
                        input_data.task.rework_count,
                        "ReportWriterAgent",
                        "bad_report_format",
                        f"Claim {claim.claim_id} uses unrelated evidence {evidence_id}.",
                        "Re-run ReportWriterAgent and bind claims only to high/medium relevance Evidence from the same competitor.",
                        claim_id=claim.claim_id,
                        failed_claim=claim.text,
                        failed_schema="Claim.evidence_ids.relevance",
                    )
        return None

    def _competitor_claim_coverage_issue(self, input_data: QaInput) -> QaResult | None:
        if input_data.report_output is None or input_data.report_output.report is None:
            return None
        report = input_data.report_output.report
        evidence_by_id = {item.evidence_id: item for item in input_data.evidence}
        if not any(item.competitor for item in input_data.evidence) and not any(claim.competitor for claim in report.claims):
            return None

        claim_count_by_competitor = {
            competitor: sum(1 for claim in report.claims if claim.competitor == competitor)
            for competitor in input_data.task.competitors
        }
        missing_claims = [competitor for competitor, count in claim_count_by_competitor.items() if count == 0]
        if missing_claims:
            return self._result(
                input_data.task.task_id,
                input_data.task.rework_count,
                "ReportWriterAgent",
                "bad_report_format",
                f"Missing competitor claim coverage: {', '.join(missing_claims)}.",
                "Re-run ReportWriterAgent and generate at least one source-backed claim for each competitor with available Evidence.",
                failed_schema="Report.claims.competitor",
            )

        mismatched = []
        for claim in report.claims:
            if not claim.competitor:
                continue
            for evidence_id in claim.evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence and evidence.competitor and evidence.competitor != claim.competitor:
                    mismatched.append(
                        {
                            "claim_id": claim.claim_id,
                            "claim_competitor": claim.competitor,
                            "evidence_id": evidence_id,
                            "evidence_competitor": evidence.competitor,
                        }
                    )
        if mismatched:
            return self._result(
                input_data.task.task_id,
                input_data.task.rework_count,
                "ReportWriterAgent",
                "bad_report_format",
                f"Claim evidence competitor mismatch: {mismatched[0]['claim_id']} uses {mismatched[0]['evidence_id']}.",
                "Re-run ReportWriterAgent and bind each claim only to Evidence from the same competitor.",
                claim_id=mismatched[0]["claim_id"],
                failed_schema="Claim.evidence_ids",
            )
        return None

    def _quality_suggestions(self, input_data: QaInput) -> tuple[list[str], dict]:
        suggestions: list[str] = []
        evidence_by_id = {item.evidence_id: item for item in input_data.evidence}
        low_confidence_claim_count = 0
        evidence_count_by_competitor = {
            competitor: sum(1 for item in input_data.evidence if item.competitor == competitor)
            for competitor in input_data.task.competitors
        }
        claims = input_data.report_output.report.claims if input_data.report_output and input_data.report_output.report else []
        claim_count_by_competitor = {
            competitor: sum(1 for claim in claims if claim.competitor == competitor)
            for competitor in input_data.task.competitors
        }
        missing_evidence_competitors = [competitor for competitor, count in evidence_count_by_competitor.items() if count == 0]
        missing_relevant_evidence_competitors = [
            competitor
            for competitor in input_data.task.competitors
            if not any(
                item.competitor == competitor and item.relevance_level in {"high", "medium"}
                for item in input_data.evidence
            )
        ]
        missing_claim_competitors = [competitor for competitor, count in claim_count_by_competitor.items() if count == 0]
        mismatched_evidence_claims = []
        unrelated_evidence_claims = []
        low_relevance_claims = []

        if len(input_data.evidence) < 3:
            suggestions.append("Web Collector 返回 Evidence 数量少于 3，建议补充更多公开来源。")

        if missing_evidence_competitors and not any(item.competitor for item in input_data.evidence):
            legacy_missing = [
                competitor
                for competitor in input_data.task.competitors
                if not any(competitor.lower() in f"{item.url or ''} {item.snippet}".lower() for item in input_data.evidence)
            ]
            if legacy_missing:
                suggestions.append(f"部分竞品缺少证据覆盖，建议补充来源：{', '.join(legacy_missing)}。")

        missing_domain_count = sum(1 for item in input_data.evidence if not item.source_domain)
        if missing_domain_count:
            suggestions.append("部分 Evidence 缺少 source_domain，建议检查来源解析逻辑。")

        if input_data.report_output and input_data.report_output.report:
            for claim in input_data.report_output.report.claims:
                related = [evidence_by_id[item] for item in claim.evidence_ids if item in evidence_by_id]
                if related and all(item.confidence < 0.5 for item in related):
                    low_confidence_claim_count += 1
                    suggestions.append("该结论引用的证据可信度较低，建议补充官方或高质量来源。")
                if related and all(item.relevance_level == "low" for item in related):
                    low_relevance_claims.append(claim.claim_id)
                    suggestions.append("该结论引用的证据与竞品实体相关性较弱，建议补充明确命中竞品名称或官网域名的来源。")
                for evidence_id in claim.evidence_ids:
                    evidence = evidence_by_id.get(evidence_id)
                    if claim.competitor and evidence and evidence.competitor and claim.competitor != evidence.competitor:
                        mismatched_evidence_claims.append(
                            {
                                "claim_id": claim.claim_id,
                                "claim_competitor": claim.competitor,
                                "evidence_id": evidence_id,
                                "evidence_competitor": evidence.competitor,
                            }
                        )
                    if evidence and evidence.relevance_level == "unrelated":
                        unrelated_evidence_claims.append(
                            {
                                "claim_id": claim.claim_id,
                                "evidence_id": evidence_id,
                                "competitor": claim.competitor,
                                "relevance_level": evidence.relevance_level,
                            }
                        )

        diagnostics = {
            "evidence_quality_checked": True,
            "low_confidence_claim_count": low_confidence_claim_count,
            "soft_suggestion_count": len(suggestions),
            "competitor_coverage_checked": True,
            "relevance_checked": True,
            "missing_evidence_competitors": missing_evidence_competitors,
            "missing_relevant_evidence_competitors": missing_relevant_evidence_competitors,
            "missing_claim_competitors": missing_claim_competitors,
            "mismatched_evidence_claims": mismatched_evidence_claims,
            "unrelated_evidence_claims": unrelated_evidence_claims,
            "low_relevance_claims": low_relevance_claims,
            "competitor_coverage_result": {
                competitor: {
                    "evidence_count": evidence_count_by_competitor.get(competitor, 0),
                    "relevant_evidence_count": sum(
                        1
                        for item in input_data.evidence
                        if item.competitor == competitor and item.relevance_level in {"high", "medium"}
                    ),
                    "unrelated_evidence_count": sum(
                        1
                        for item in input_data.evidence
                        if item.competitor == competitor and item.relevance_level == "unrelated"
                    ),
                    "claim_count": claim_count_by_competitor.get(competitor, 0),
                }
                for competitor in input_data.task.competitors
            },
        }
        return suggestions, diagnostics

    @staticmethod
    def _analysis_suggestions(analysis) -> list[str]:
        suggestions = []
        objects = [analysis.product_profile, analysis.feature_tree, analysis.pricing_model, analysis.user_persona]
        if any(not getattr(item, "evidence_ids", []) for item in objects):
            suggestions.append("结构化分析存在未绑定 evidence_ids 的字段，建议补充来源证据。")
        if "Evidence is insufficient" in analysis.product_profile.positioning:
            suggestions.append("结构化分析证据不足，建议补充更多来源。")
        if not analysis.feature_tree.core_features or not analysis.pricing_model.tiers or not analysis.user_persona.goals:
            suggestions.append("结构化分析字段较空，建议补充更多 Evidence 后重新分析。")
        return suggestions

    @staticmethod
    def _has_unsupported_analysis(input_data: QaInput) -> bool:
        text = " ".join(
            [
                input_data.analysis.product_profile.positioning if input_data.analysis else "",
                " ".join(input_data.analysis.product_profile.strengths) if input_data.analysis else "",
                input_data.analysis.pricing_model.pricing_notes if input_data.analysis else "",
            ]
        ).lower()
        return "unsupported conclusion" in text

    def run(self, input_data: QaInput) -> QaOutput:
        task = input_data.task

        def produce() -> QaOutput:
            result = self.evaluate(input_data)
            if result.status == "passed":
                _, diagnostics = self._quality_suggestions(input_data)
            else:
                _, diagnostics = self._quality_suggestions(input_data)
                diagnostics["soft_suggestion_count"] = len(result.soft_suggestions)
            return QaOutput(qa_result=result, diagnostics=diagnostics)

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="FinalReport",
            message_type="qa",
            schema_name="QaOutput",
            input_summary="Validate Schema, evidence coverage, report format, and competitor coverage",
            retry_count=input_data.retry_count,
            fn=produce,
        )
