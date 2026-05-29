from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.agents.base import run_with_trace
from app.schemas import (
    AnalysisDimension,
    AnalysisDimensionPlan,
    Dag,
    DagEdge,
    DagNode,
    PlannerDownstreamGuidance,
    PlannerExtractedContext,
    PlannerInput,
    PlannerOutput,
    PlannerSurveyInput,
    Task,
)
from app.services.llm_client import LlmClient, parse_llm_json
from app.services.trace_service import TraceService


class PlannerAgent:
    name = "PlannerAgent"

    def __init__(self, trace_service: TraceService, llm_client: LlmClient | None = None):
        self.trace_service = trace_service
        self.llm_client = llm_client or LlmClient()

    def run(self, input_data: PlannerInput) -> PlannerOutput:
        task = input_data.task

        def produce() -> PlannerOutput:
            return self._plan(task)

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            run_id=input_data.run_id,
            agent_name=self.name,
            to_agent="CollectorAgent",
            message_type="plan",
            schema_name="PlannerOutput",
            input_summary=f"{task.product_name} vs {', '.join(task.competitors)}; region={task.region}; industry={task.industry}",
            retry_count=input_data.retry_count,
            fn=produce,
        )

    def _plan(self, task: Task) -> PlannerOutput:
        diagnostics = self._base_diagnostics()
        messages = self._messages(task)
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
                    "planner_mode_used": "deterministic",
                    "fallback_used": True,
                    "llm_fallback_reason": llm_response.fallback_reason,
                }
            )
            return self._deterministic_output(task, llm_response.fallback_reason, diagnostics)

        try:
            payload = self._normalize_llm_payload(parse_llm_json(llm_response.content or ""))
            diagnostics.update(
                {
                    "planner_mode_used": "llm_enhanced",
                    "llm_schema_validation_success": True,
                    "llm_schema_validation_errors": [],
                }
            )
            return self._enhanced_output_from_payload(task, payload, diagnostics)
        except Exception as exc:  # noqa: BLE001 - planner must not break workflow execution.
            diagnostics.update(
                {
                    "planner_mode_used": "deterministic",
                    "fallback_used": True,
                    "llm_fallback_reason": f"Planner LLM enhancement failed: {exc}",
                    "llm_schema_validation_success": False,
                    "llm_schema_validation_errors": [str(exc)],
                }
            )
            return self._deterministic_output(task, f"Planner LLM enhancement failed: {exc}", diagnostics)

    def _enhanced_output_from_payload(self, task: Task, payload: dict[str, Any], diagnostics: dict[str, Any]) -> PlannerOutput:
        extracted = self._build_extracted_context(task, payload)
        selected_dimensions = self._normalize_dimensions(payload.get("selected_dimensions"), extracted.intent_classification)
        analysis_dimension_plan = self._build_dimension_plan(
            task,
            selected_dimensions,
            extracted.analysis_focus_points,
            extracted.survey_needed,
        )
        survey_inputs = self._build_survey_inputs(payload.get("survey_inputs"), extracted)
        downstream_guidance = self._build_guidance(
            task,
            extracted=extracted,
            selected_dimensions=selected_dimensions,
            survey_inputs=survey_inputs,
        )
        planner_notes = self._normalize_string_list(payload.get("planner_notes"))
        planner_notes.append("Planner used LLM-enhanced intent extraction and deterministic plan normalization.")
        missing_information = self._dedupe(
            [
                *extracted.missing_information,
                *self._normalize_string_list(payload.get("missing_information")),
                *self._default_missing_information(task),
            ]
        )
        confidence = self._safe_confidence(payload.get("confidence", extracted.confidence), fallback=extracted.confidence or 0.75)
        diagnostics.update(
            {
                "intent_classification": extracted.intent_classification,
                "survey_needed": extracted.survey_needed,
                "selected_dimension_count": len(selected_dimensions),
            }
        )
        return PlannerOutput(
            dag=self._default_dag(),
            plan=self._default_plan(),
            intent_summary=self._safe_text(
                payload.get("intent_summary"),
                fallback=self._default_intent_summary(task, extracted.intent_classification, extracted.survey_needed),
            ),
            intent_classification=extracted.intent_classification,
            extracted_context=extracted,
            selected_dimensions=selected_dimensions,
            analysis_dimension_plan=analysis_dimension_plan,
            survey_needed=extracted.survey_needed,
            survey_objective=survey_inputs.objective if survey_inputs else None,
            survey_inputs=survey_inputs,
            missing_information=missing_information,
            planner_notes=self._dedupe(planner_notes),
            confidence=confidence,
            downstream_guidance=downstream_guidance,
            diagnostics=diagnostics,
        )

    def _deterministic_output(
        self,
        task: Task,
        fallback_reason: str | None,
        diagnostics: dict[str, Any],
    ) -> PlannerOutput:
        intent = self._infer_intent_from_task(task)
        survey_needed = self._deterministic_survey_needed(task, intent)
        focus_points = self._deterministic_focus_points(task, intent)
        selected_dimensions = self._normalize_dimensions(None, intent)
        extracted = PlannerExtractedContext(
            intent_classification=intent,
            industry=task.industry,
            domain=task.industry,
            product_name=task.product_name,
            product_type=task.industry,
            target_users=self._infer_target_users(task),
            region=task.region,
            competitors_mentioned=list(task.competitors),
            analysis_focus_points=focus_points,
            requested_outputs=self._deterministic_requested_outputs(task, survey_needed),
            survey_needed=survey_needed,
            survey_reason=self._deterministic_survey_reason(task, intent) if survey_needed else None,
            missing_information=self._default_missing_information(task),
            confidence=0.35,
        )
        survey_inputs = self._build_survey_inputs({}, extracted)
        analysis_dimension_plan = self._build_dimension_plan(
            task,
            selected_dimensions,
            extracted.analysis_focus_points,
            survey_needed,
        )
        planner_notes = ["Planner used deterministic fallback logic."]
        if fallback_reason:
            planner_notes.append(fallback_reason)
        downstream_guidance = self._build_guidance(
            task,
            extracted=extracted,
            selected_dimensions=selected_dimensions,
            survey_inputs=survey_inputs,
        )
        diagnostics.update(
            {
                "intent_classification": extracted.intent_classification,
                "survey_needed": extracted.survey_needed,
                "selected_dimension_count": len(selected_dimensions),
            }
        )
        return PlannerOutput(
            dag=self._default_dag(),
            plan=self._default_plan(),
            intent_summary=self._default_intent_summary(task, intent, survey_needed),
            intent_classification=intent,
            extracted_context=extracted,
            selected_dimensions=selected_dimensions,
            analysis_dimension_plan=analysis_dimension_plan,
            survey_needed=survey_needed,
            survey_objective=survey_inputs.objective if survey_inputs else None,
            survey_inputs=survey_inputs,
            missing_information=self._default_missing_information(task),
            planner_notes=planner_notes,
            confidence=0.35,
            downstream_guidance=downstream_guidance,
            diagnostics=diagnostics,
        )

    def _base_diagnostics(self) -> dict[str, Any]:
        return {
            "planner_mode_requested": "llm_enhanced",
            "planner_mode_used": "deterministic",
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
            "fallback_used": False,
            "llm_fallback_reason": None,
        }

    def _default_dag(self) -> Dag:
        return Dag(
            nodes=[
                DagNode(id="PlannerAgent", label="规划任务范围和 DAG", status="completed"),
                DagNode(id="CollectorAgent", label="采集 Mock 证据", status="pending"),
                DagNode(id="EvidenceGate", label="相关证据前置校验", status="pending"),
                DagNode(id="PageFetcher", label="抓取轻量正文摘要", status="pending"),
                DagNode(id="AnalystAgent", label="抽取结构化竞品知识", status="pending"),
                DagNode(id="ReportWriterAgent", label="撰写带证据报告", status="pending"),
                DagNode(id="QaAgent", label="校验 Schema 和证据", status="pending"),
                DagNode(id="FinalReport", label="最终报告", status="pending"),
            ],
            edges=[
                DagEdge(source="PlannerAgent", target="CollectorAgent", label="计划"),
                DagEdge(source="CollectorAgent", target="EvidenceGate", label="证据"),
                DagEdge(source="EvidenceGate", target="PageFetcher", label="相关证据通过"),
                DagEdge(source="PageFetcher", target="AnalystAgent", label="正文摘要"),
                DagEdge(source="AnalystAgent", target="ReportWriterAgent", label="知识"),
                DagEdge(source="ReportWriterAgent", target="QaAgent", label="草稿"),
                DagEdge(source="QaAgent", target="FinalReport", label="通过"),
                DagEdge(source="QaAgent", target="CollectorAgent", label="缺少证据"),
                DagEdge(source="QaAgent", target="AnalystAgent", label="抽取错误"),
                DagEdge(source="QaAgent", target="ReportWriterAgent", label="格式错误"),
            ],
        )

    @staticmethod
    def _default_plan() -> list[str]:
        return [
            "Collect competitor evidence for positioning, features, pricing, and target users.",
            "Normalize findings into structured competitor knowledge schemas.",
            "Produce source-bound claims with evidence_ids and run QA validation.",
        ]

    def _build_extracted_context(self, task: Task, payload: dict[str, Any]) -> PlannerExtractedContext:
        raw_context = payload.get("extracted_context")
        if isinstance(raw_context, dict):
            merged_context = dict(raw_context)
        else:
            merged_context = {}
        merged_context.setdefault("intent_classification", payload.get("intent_classification", self._infer_intent_from_task(task)))
        merged_context.setdefault("industry", payload.get("industry", task.industry))
        merged_context.setdefault("domain", payload.get("field") or payload.get("domain") or task.industry)
        merged_context.setdefault("product_name", payload.get("product_name", task.product_name))
        merged_context.setdefault("product_type", payload.get("product_type", task.industry))
        merged_context.setdefault("target_users", payload.get("target_users") or self._infer_target_users(task))
        merged_context.setdefault("region", payload.get("region", task.region))
        merged_context.setdefault("competitors_mentioned", payload.get("competitors_mentioned") or list(task.competitors))
        merged_context.setdefault("analysis_focus_points", payload.get("analysis_focus_points") or self._deterministic_focus_points(task, merged_context["intent_classification"]))
        merged_context.setdefault("requested_outputs", payload.get("requested_outputs") or self._deterministic_requested_outputs(task, bool(payload.get("survey_needed"))))
        merged_context.setdefault("survey_needed", payload.get("survey_needed", self._deterministic_survey_needed(task, merged_context["intent_classification"])))
        merged_context.setdefault("survey_reason", payload.get("survey_reason"))
        merged_context.setdefault("missing_information", payload.get("missing_information") or self._default_missing_information(task))
        merged_context.setdefault("confidence", self._safe_confidence(payload.get("confidence"), fallback=0.8))
        try:
            context = PlannerExtractedContext.model_validate(merged_context)
        except ValidationError as exc:
            raise ValueError(f"Planner extracted_context validation failed: {exc}") from exc
        if context.survey_needed and not context.survey_reason:
            context = context.model_copy(update={"survey_reason": self._deterministic_survey_reason(task, context.intent_classification)})
        return context

    def _build_dimension_plan(
        self,
        task: Task,
        selected_dimensions: list[str],
        focus_points: list[str],
        survey_needed: bool,
    ) -> AnalysisDimensionPlan:
        dimension_plans: list[AnalysisDimension] = []
        for priority, dimension in enumerate(selected_dimensions, start=1):
            keywords = [dimension]
            if dimension == "positioning":
                keywords.extend(["positioning", "differentiation", task.industry])
            elif dimension == "feature":
                keywords.extend(["features", "workflow", "integration"])
            elif dimension == "pricing":
                keywords.extend(["pricing", "plan", "enterprise"])
            elif dimension == "persona":
                keywords.extend(["target users", "team", "use cases"])
            elif dimension == "ux":
                keywords.extend(["ux", "usability", "pain points"])
            elif dimension == "feedback":
                keywords.extend(["feedback", "pain points", "survey"])
            elif dimension == "hypothesis":
                keywords.extend(["hypothesis", "validation", "assumption"])
            elif dimension == "prioritization":
                keywords.extend(["prioritization", "feature requests", "importance"])
            dimension_plans.append(
                AnalysisDimension(
                    dimension_id=dimension,
                    label=dimension.replace("_", " ").title(),
                    description=f"Planner-selected dimension for {task.industry} analysis.",
                    keywords=self._dedupe([word for word in keywords if word]),
                    required=dimension in {"positioning", "feature", "pricing", "persona"},
                    priority=priority,
                    metadata={"owner": "planner", "survey_related": dimension in {"feedback", "hypothesis", "prioritization"}},
                )
            )
        research_goals = [
            *[f"Compare competitor signals for {focus_point}." for focus_point in focus_points[:4]],
            "Confirm competitor-specific evidence before strong conclusions.",
        ]
        if survey_needed:
            research_goals.append("Prepare structured feedback or questionnaire objectives for downstream survey support.")
        query_hints = {
            competitor: self._build_query_hints_for_competitor(competitor, task, selected_dimensions, survey_needed)
            for competitor in task.competitors
        }
        return AnalysisDimensionPlan(
            selected_dimensions=selected_dimensions,
            dimension_plans=dimension_plans,
            research_goals=self._dedupe(research_goals),
            query_hints=query_hints,
            metadata={
                "planner_owner": "PlannerAgent",
                "survey_needed": survey_needed,
                "focus_points": focus_points,
            },
        )

    def _build_survey_inputs(self, raw_inputs: Any, extracted: PlannerExtractedContext) -> PlannerSurveyInput | None:
        if not extracted.survey_needed:
            return None
        data = raw_inputs if isinstance(raw_inputs, dict) else {}
        objective = self._safe_text(
            data.get("objective"),
            fallback=f"Collect structured user feedback for {extracted.product_name or 'the target product'} and its competitors.",
        )
        respondent_type = self._safe_text(
            data.get("respondent_type"),
            fallback="Current users, target buyers, or evaluators who can compare alternatives.",
        )
        question_themes = self._normalize_string_list(data.get("question_themes"))
        if not question_themes:
            question_themes = ["pain points", "improvement opportunities", "feature prioritization", "adoption barriers"]
        hypotheses = self._normalize_string_list(data.get("hypotheses"))
        if not hypotheses:
            hypotheses = ["Users have unmet workflow pain points that existing competitors do not fully address."]
        return PlannerSurveyInput(
            objective=objective,
            respondent_type=respondent_type,
            question_themes=question_themes,
            hypotheses=hypotheses,
            metadata={"planner_generated": True, "survey_reason": extracted.survey_reason},
        )

    def _build_guidance(
        self,
        task: Task,
        *,
        extracted: PlannerExtractedContext,
        selected_dimensions: list[str],
        survey_inputs: PlannerSurveyInput | None,
    ) -> PlannerDownstreamGuidance:
        collector = [
            f"Prioritize competitor-specific public evidence for: {', '.join(selected_dimensions)}.",
            f"Use region filter '{task.region}' and industry context '{task.industry}' when forming evidence queries.",
            "Prefer official, documentation, pricing, and high-relevance sources before weaker public mentions.",
        ]
        analyst = [
            f"Compare competitors through these dimensions: {', '.join(selected_dimensions)}.",
            "Keep conclusions conservative when evidence coverage is thin or competitor-specific signals are missing.",
            "Separate confirmed evidence from assumptions and unresolved gaps.",
        ]
        writer = [
            f"Emphasize {extracted.intent_classification.replace('_', ' ')} in the report framing.",
            "Structure claims around competitor-specific evidence, uncertainty, and validation next steps.",
            "Call out evidence gaps explicitly instead of smoothing them over.",
        ]
        qa = [
            "Verify that claims align with the requested intent and focus points.",
            "Check competitor coverage, evidence relevance, and unsupported cross-competitor inference.",
            "If survey support is requested, ensure the report does not pretend survey data already exists.",
        ]
        survey = []
        if survey_inputs:
            survey = [
                f"Objective: {survey_inputs.objective}",
                f"Respondent type: {survey_inputs.respondent_type}",
                f"Question themes: {', '.join(survey_inputs.question_themes)}.",
                "Keep outputs aggregate-only and safe for conversion into SurveyEvidence.",
            ]
        return PlannerDownstreamGuidance(
            collector=collector,
            analyst=analyst,
            writer=writer,
            qa=qa,
            survey=survey,
        )

    def _messages(self, task: Task) -> list[dict[str, str]]:
        system = (
            "You are the PlannerAgent for a competitive product analysis platform. "
            "Your task is to understand the user's analysis request and return a strictly valid JSON planning result for downstream modules.\n\n"
            "Your output must:\n"
            "1. identify the user's high-level intent,\n"
            "2. extract product-analysis context,\n"
            "3. determine whether survey support is needed,\n"
            "4. generate planning guidance for downstream modules,\n"
            "5. strictly follow the required JSON structure and field types.\n\n"
            "intent_classification must be exactly one of:\n"
            "- competitive_analysis\n"
            "- product_positioning\n"
            "- feature_comparison\n"
            "- ux_review\n"
            "- improvement_opportunity\n"
            "- survey_design\n"
            "- survey_analysis\n"
            "- market_research\n"
            "- unknown\n\n"
            "Classification rule:\n"
            "- If the request combines product comparison with questionnaire generation for pain-point discovery, validation, or improvement planning, use improvement_opportunity.\n"
            "- Use survey_design only when the main task is simply to create a questionnaire without a broader improvement-analysis purpose.\n\n"
            "Return exactly one JSON object with these fields and types:\n"
            "- intent_summary: string\n"
            "- intent_classification: string\n"
            "- industry: string\n"
            "- domain: string\n"
            "- product_name: string\n"
            "- product_type: string\n"
            "- target_users: string[]\n"
            "- region: string\n"
            "- competitors_mentioned: string[]\n"
            "- analysis_focus_points: string[]\n"
            "- requested_outputs: string[]\n"
            "- survey_needed: boolean\n"
            "- survey_reason: string\n"
            "- missing_information: string[]\n"
            "- confidence: number\n"
            "- selected_dimensions: string[]\n"
            "- survey_objective: string\n"
            '- survey_inputs: {"objective": string, "respondent_type": string, "question_themes": string[], "hypotheses": string[]}\n'
            '- planner_notes: string[]\n'
            '- downstream_guidance: {"collector": string[], "analyst": string[], "writer": string[], "qa": string[], "survey": string[]}\n\n'
            "Important typing rules:\n"
            "- Every list-like field must be a JSON array.\n"
            "- Never return a string where an array is required.\n"
            "- Even a single item must still be returned as an array.\n"
            "- Do not return null.\n"
            "- If some information is uncertain, infer reasonably and put uncertainties into missing_information.\n"
            "- confidence must be a number between 0 and 1.\n"
            "- Return JSON only.\n"
            "- No markdown.\n"
            "- No explanations.\n"
            "- No code fences."
        )
        user = (
            "User request example:\n"
            "“我想分析苹果和三星旗舰手机的优劣，并生成一个关于手机续航问题的用户问卷”\n\n"
            "Expected style:\n"
            "{\n"
            '"intent_summary": "分析苹果和三星旗舰手机的优劣，并准备围绕手机续航问题的用户问卷。",\n'
            '"intent_classification": "improvement_opportunity",\n'
            '"industry": "旗舰智能手机",\n'
            '"domain": "智能手机硬件",\n'
            '"product_name": "苹果和三星旗舰手机对比",\n'
            '"product_type": "旗舰手机",\n'
            '"target_users": ["计划购买旗舰手机的消费者", "重度使用者"],\n'
            '"region": "中国",\n'
            '"competitors_mentioned": ["苹果", "三星"],\n'
            '"analysis_focus_points": ["续航表现", "性能取舍", "影像体验", "系统体验"],\n'
            '"requested_outputs": ["竞品优劣分析", "手机续航问卷"],\n'
            '"survey_needed": true,\n'
            '"survey_reason": "用户希望围绕续航问题收集反馈，以支持改进机会分析。",\n'
            '"missing_information": ["未指定问卷样本规模", "未指定受访者细分标准"],\n'
            '"confidence": 0.95,\n'
            '"selected_dimensions": ["feature", "pricing", "persona", "feedback", "prioritization"],\n'
            '"survey_objective": "收集用户对旗舰手机续航问题、使用场景和改进期望的结构化反馈。",\n'
            '"survey_inputs": {\n'
            '"objective": "收集用户对旗舰手机续航问题、使用场景和改进期望的结构化反馈。",\n'
            '"respondent_type": "使用或计划购买苹果、三星旗舰手机的用户。",\n'
            '"question_themes": ["续航痛点", "充电频率", "高负载场景", "改进优先级"],\n'
            '"hypotheses": ["用户对旗舰手机续航的主要不满来自高负载场景掉电过快。"]\n'
            "},\n"
            '"planner_notes": ["已识别为竞品分析 + 问卷生成场景。"],\n'
            '"downstream_guidance": {\n'
            '"collector": ["收集苹果和三星旗舰手机在续航、充电、性能和影像方面的公开证据。"],\n'
            '"analyst": ["比较两家旗舰手机在续航相关优劣势和使用场景差异。"],\n'
            '"writer": ["突出优劣对比、续航问题和问卷设计目的。"],\n'
            '"qa": ["验证所有优劣结论是否有对应证据支撑。"],\n'
            '"survey": ["围绕续航痛点、充电体验和改进优先级设计题目。"]\n'
            "}\n"
            "}\n\n"
            "Now return exactly one JSON object for this task input:\n"
            f"{task.model_dump(mode='json')}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    @classmethod
    def _normalize_llm_payload(cls, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Planner LLM output must be a JSON object.")

        normalized = dict(payload)
        for field_name in (
            "target_users",
            "competitors_mentioned",
            "analysis_focus_points",
            "requested_outputs",
            "missing_information",
            "selected_dimensions",
            "planner_notes",
        ):
            normalized_value = cls._normalize_array_like_value(normalized.get(field_name), allow_empty=True)
            if normalized_value is not None:
                normalized[field_name] = normalized_value

        survey_inputs = normalized.get("survey_inputs")
        if isinstance(survey_inputs, dict):
            normalized_survey_inputs = dict(survey_inputs)
            for field_name in ("question_themes", "hypotheses"):
                normalized_value = cls._normalize_array_like_value(normalized_survey_inputs.get(field_name), allow_empty=True)
                if normalized_value is not None:
                    normalized_survey_inputs[field_name] = normalized_value
            normalized["survey_inputs"] = normalized_survey_inputs

        downstream_guidance = normalized.get("downstream_guidance")
        if isinstance(downstream_guidance, dict):
            normalized_guidance = dict(downstream_guidance)
            for field_name in ("collector", "analyst", "writer", "qa", "survey"):
                normalized_value = cls._normalize_array_like_value(normalized_guidance.get(field_name), allow_empty=True)
                if normalized_value is not None:
                    normalized_guidance[field_name] = normalized_value
            normalized["downstream_guidance"] = normalized_guidance

        extracted_context = normalized.get("extracted_context")
        if isinstance(extracted_context, dict):
            normalized_extracted_context = dict(extracted_context)
            for field_name in (
                "target_users",
                "competitors_mentioned",
                "analysis_focus_points",
                "requested_outputs",
                "missing_information",
            ):
                normalized_value = cls._normalize_array_like_value(normalized_extracted_context.get(field_name), allow_empty=True)
                if normalized_value is not None:
                    normalized_extracted_context[field_name] = normalized_value
            normalized["extracted_context"] = normalized_extracted_context

        return normalized

    @staticmethod
    def _normalize_array_like_value(value: Any, *, allow_empty: bool) -> list[str] | None:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else ([] if allow_empty else None)
        if value is None:
            return [] if allow_empty else None
        return None

    @staticmethod
    def _normalize_dimensions(raw_dimensions: Any, intent: str) -> list[str]:
        if isinstance(raw_dimensions, list):
            normalized = [str(item).strip().lower().replace(" ", "_") for item in raw_dimensions if str(item).strip()]
        else:
            normalized = []
        if normalized:
            return PlannerAgent._dedupe(normalized)
        defaults = {
            "competitive_analysis": ["positioning", "feature", "pricing", "persona"],
            "product_positioning": ["positioning", "feature", "persona", "pricing"],
            "feature_comparison": ["feature", "positioning", "pricing", "persona"],
            "ux_review": ["ux", "persona", "feature", "risk"],
            "improvement_opportunity": ["feature", "ux", "feedback", "prioritization"],
            "survey_design": ["feedback", "hypothesis", "prioritization", "persona"],
            "survey_analysis": ["feedback", "hypothesis", "persona", "risk"],
            "market_research": ["positioning", "pricing", "persona", "market"],
            "unknown": ["positioning", "feature", "pricing", "persona"],
        }
        return defaults.get(intent, defaults["unknown"])

    @staticmethod
    def _infer_intent_from_task(task: Task) -> str:
        text = f"{task.product_name} {task.industry}".lower()
        keyword_map = [
            ("survey_design", ["survey", "questionnaire", "问卷", "调研设计"]),
            ("survey_analysis", ["survey analysis", "survey result", "问卷分析", "反馈分析"]),
            ("improvement_opportunity", ["improvement", "opportunity", "pain point", "改进", "优化", "痛点", "机会点", "priorit"]),
            ("ux_review", ["ux", "usability", "体验", "易用性"]),
            ("feature_comparison", ["feature", "功能对比", "compare features"]),
            ("product_positioning", ["positioning", "定位"]),
            ("market_research", ["market", "市场研究", "市场调研"]),
            ("competitive_analysis", ["competitor", "competitive", "竞品", "对标", "分析"]),
        ]
        for label, keywords in keyword_map:
            if any(keyword in text for keyword in keywords):
                return label
        return "competitive_analysis"

    @staticmethod
    def _deterministic_survey_needed(task: Task, intent: str) -> bool:
        if intent in {"improvement_opportunity", "survey_design", "survey_analysis", "ux_review"}:
            return True
        text = f"{task.product_name} {task.industry}".lower()
        keywords = ["improvement", "pain point", "改进", "优化", "痛点", "questionnaire", "survey", "feedback", "priorit"]
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _deterministic_survey_reason(task: Task, intent: str) -> str:
        if intent in {"survey_design", "survey_analysis"}:
            return "The request explicitly points to questionnaire or structured feedback work."
        if intent == "ux_review":
            return "UX-oriented requests benefit from structured user pain-point collection."
        return "The request appears to seek improvement opportunities, pain points, or validation that benefit from survey support."

    @staticmethod
    def _deterministic_focus_points(task: Task, intent: str) -> list[str]:
        base = ["positioning", "features", "pricing", "target users"]
        if intent == "feature_comparison":
            return ["core features", "differentiators", "integration breadth", "pricing trade-offs"]
        if intent == "product_positioning":
            return ["category positioning", "buyer messaging", "target segment fit", "evidence gaps"]
        if intent == "ux_review":
            return ["user workflows", "pain points", "usability risks", "experience gaps"]
        if intent == "improvement_opportunity":
            return ["user pain points", "feature gaps", "improvement opportunities", "validation hypotheses"]
        if intent in {"survey_design", "survey_analysis"}:
            return ["feedback themes", "hypotheses", "feature prioritization", "respondent segmentation"]
        if "saas" in task.industry.lower():
            return ["positioning", "workflow features", "pricing", "enterprise users"]
        return base

    @staticmethod
    def _deterministic_requested_outputs(task: Task, survey_needed: bool) -> list[str]:
        outputs = ["competitive report", "structured competitor knowledge", "traceable claims"]
        if survey_needed:
            outputs.append("survey or questionnaire brief")
        return outputs

    @staticmethod
    def _infer_target_users(task: Task) -> list[str]:
        text = f"{task.product_name} {task.industry}".lower()
        if "saas" in text or "enterprise" in text:
            return ["operators", "team leads", "buyers", "enterprise evaluators"]
        if "retail" in text or "ecommerce" in text or "电商" in text:
            return ["consumers", "category managers", "marketing teams"]
        if "coding" in text or "developer" in text:
            return ["developers", "engineering teams", "technical evaluators"]
        return ["target users not clearly specified"]

    @staticmethod
    def _default_missing_information(task: Task) -> list[str]:
        missing = [
            "No dedicated free-form user brief is stored in Task; Planner inferred intent from product_name, industry, region, and competitors.",
        ]
        if not task.region.strip():
            missing.append("Region is missing.")
        return missing

    def _default_intent_summary(self, task: Task, intent: str, survey_needed: bool) -> str:
        suffix = " Survey support is recommended." if survey_needed else ""
        return (
            f"Plan a {intent.replace('_', ' ')} workflow for {task.product_name} in {task.industry}, "
            f"compare competitors {', '.join(task.competitors)}, and keep evidence traceable.{suffix}"
        )

    def _build_query_hints_for_competitor(
        self,
        competitor: str,
        task: Task,
        selected_dimensions: list[str],
        survey_needed: bool,
    ) -> list[str]:
        hints = [
            f"{competitor} official {task.industry}",
            f"{competitor} pricing official",
            f"{competitor} features documentation",
        ]
        if "persona" in selected_dimensions:
            hints.append(f"{competitor} customers use cases")
        if "ux" in selected_dimensions:
            hints.append(f"{competitor} reviews usability pain points")
        if survey_needed:
            hints.append(f"{competitor} review feedback user pain points")
        return self._dedupe(hints)

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _safe_text(value: Any, *, fallback: str | None = None) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return fallback

    @staticmethod
    def _safe_confidence(value: Any, *, fallback: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
