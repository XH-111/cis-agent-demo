import json
from datetime import datetime

from app.agents.planner import PlannerAgent
from app.schemas import PlannerInput, Task
from app.services.llm_client import LlmResponse


class FakeTraceService:
    def __init__(self):
        self.saved = []
        self.current_run_id = None

    def set_run_context(self, run_id: str | None) -> None:
        self.current_run_id = run_id

    def save(self, trace):
        if trace.run_id is None and self.current_run_id:
            trace = trace.model_copy(update={"run_id": self.current_run_id})
        self.saved.append(trace)
        return trace


class FakeLlmClient:
    def __init__(self, *, available: bool, content: str | None = None, fallback_reason: str | None = None):
        self.is_available = available
        self.content = content
        self.fallback_reason = fallback_reason
        self.provider = "fake"
        self.model = "fake-model"
        self.base_url = "https://fake.local/v1"

    def chat_json(self, messages, timeout: float | None = None):
        if not self.is_available:
            return LlmResponse(
                available=False,
                content=None,
                fallback_reason=self.fallback_reason or "fake llm unavailable",
                provider=self.provider,
                model=self.model,
                attempted=True,
                success=False,
                error_type="unavailable",
                error_message=self.fallback_reason or "fake llm unavailable",
            )
        return LlmResponse(
            available=True,
            content=self.content,
            provider=self.provider,
            model=self.model,
            attempted=True,
            success=True,
            elapsed_time_ms=5,
            response_preview=(self.content or "")[:200],
        )


def make_phone_task() -> Task:
    now = datetime.utcnow()
    return Task(
        task_id="task_planner_phone_unit",
        product_name="我想要分析小米和华为旗舰手机的优劣；",
        competitors=["小米", "华为"],
        region="中国",
        industry="旗舰智能手机",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )


def make_broad_phone_task() -> Task:
    now = datetime.utcnow()
    return Task(
        task_id="task_planner_broad_phone_unit",
        product_name="Analyze flagship smartphones",
        competitors=["TBD"],
        region="Global",
        industry="Smartphones",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )


def make_semispecific_crm_task() -> Task:
    now = datetime.utcnow()
    return Task(
        task_id="task_planner_crm_unit",
        product_name="Benchmark our CRM against Salesforce and HubSpot",
        competitors=["Salesforce", "HubSpot"],
        region="Global",
        industry="CRM",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )


def make_mixed_intent_task() -> Task:
    now = datetime.utcnow()
    return Task(
        task_id="task_planner_mixed_unit",
        product_name="Analyze this product and generate a survey",
        competitors=["TBD"],
        region="Global",
        industry="B2B SaaS",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )


def make_broad_note_taking_task() -> Task:
    now = datetime.utcnow()
    return Task(
        task_id="task_planner_notes_unit",
        product_name="Compare AI note-taking tools, identify market gaps, and recommend whether user research is necessary.",
        competitors=["TBD"],
        region="Global",
        industry="AI note-taking",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )


def print_structured_fields(output) -> None:
    printed = {
        "intent_summary": output.intent_summary,
        "intent_classification": output.intent_classification,
        "ambiguity_level": output.ambiguity_level,
        "scope_type": output.scope_type,
        "scope_size": output.scope_size,
        "survey_needed": output.survey_needed,
        "survey_recommended": output.survey_recommended,
        "survey_objective": output.survey_objective,
        "selected_dimensions": output.selected_dimensions,
        "confirmed_scope": output.confirmed_scope.model_dump(mode="json") if output.confirmed_scope else None,
        "inferred_scope": output.inferred_scope.model_dump(mode="json") if output.inferred_scope else None,
        "suggested_scope": output.suggested_scope.model_dump(mode="json") if output.suggested_scope else None,
        "recommended_next_constraints": output.recommended_next_constraints,
        "assumptions": output.assumptions,
        "candidate_competitors": [item.model_dump(mode="json") for item in output.candidate_competitors],
        "clarification_targets": output.clarification_targets,
        "planning_stages": [item.model_dump(mode="json") for item in output.planning_stages],
        "missing_information": output.missing_information,
        "confidence": output.confidence,
        "extracted_context": output.extracted_context.model_dump(mode="json") if output.extracted_context else None,
        "analysis_dimension_plan": output.analysis_dimension_plan.model_dump(mode="json") if output.analysis_dimension_plan else None,
        "survey_inputs": output.survey_inputs.model_dump(mode="json") if output.survey_inputs else None,
        "downstream_guidance": output.downstream_guidance.model_dump(mode="json") if output.downstream_guidance else None,
        "diagnostics": output.diagnostics,
    }
    print("\n[PlannerAgent structured fields]")
    print(json.dumps(printed, ensure_ascii=False, indent=2))


def test_planneragent_phone_prompt_fallback_output_is_complete():
    trace_service = FakeTraceService()
    planner = PlannerAgent(
        trace_service,
        llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"),
    )

    output = planner.run(PlannerInput(task=make_phone_task(), run_id="run_phone_unit_1"))
    print_structured_fields(output)

    assert output.dag.nodes
    assert output.dag.edges
    assert output.plan
    assert output.intent_summary
    assert output.intent_classification
    assert output.extracted_context is not None
    assert output.selected_dimensions
    assert output.analysis_dimension_plan is not None
    assert output.survey_needed is False
    assert output.survey_recommended is False
    assert output.survey_inputs is None
    assert output.confirmed_scope is not None
    assert output.confirmed_scope.competitors == make_phone_task().competitors
    assert output.downstream_guidance is not None
    assert output.missing_information
    assert output.diagnostics["planner_mode_used"] == "deterministic"
    assert output.diagnostics["fallback_used"] is True
    assert trace_service.saved
    assert trace_service.saved[0].agent_name == "PlannerAgent"
    return
    assert output.confirmed_scope is not None
    assert output.confirmed_scope.competitors == ["灏忕背", "鍗庝负"]
    assert output.confirmed_scope is not None
    assert output.confirmed_scope.competitors == ["灏忕背", "鍗庝负"]
    assert output.downstream_guidance is not None
    assert output.missing_information
    assert output.diagnostics["planner_mode_used"] == "deterministic"
    assert output.diagnostics["fallback_used"] is True
    assert trace_service.saved
    assert trace_service.saved[0].agent_name == "PlannerAgent"


def test_planneragent_broad_category_request_produces_scope_candidates_and_stages():
    trace_service = FakeTraceService()
    planner = PlannerAgent(
        trace_service,
        llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"),
    )

    output = planner.run(PlannerInput(task=make_broad_phone_task(), run_id="run_broad_phone_unit_1"))
    print_structured_fields(output)

    assert output.scope_type == "category_scan"
    assert output.scope_size == "broad"
    assert output.ambiguity_level == "high"
    assert output.candidate_competitors
    assert output.candidate_competitors[0].name in {"Apple iPhone", "Samsung Galaxy"}
    assert output.extracted_context is not None
    assert output.extracted_context.competitors_mentioned == []
    assert output.confirmed_scope is not None
    assert output.confirmed_scope.competitors == []
    assert output.inferred_scope is not None
    assert "Apple iPhone" in output.inferred_scope.competitors
    assert output.suggested_scope is not None
    assert "Apple iPhone" in output.suggested_scope.competitors
    assert output.recommended_next_constraints
    assert "competitor_set" in output.clarification_targets
    assert any("Competitor set is still underspecified" in item for item in output.missing_information)
    assert all("No dedicated free-form user brief" not in item for item in output.missing_information)
    assert output.planning_stages
    assert output.planning_stages[0].stage_id == "define_scope"
    assert output.analysis_dimension_plan is not None
    assert "category_scope" in output.analysis_dimension_plan.query_hints
    assert "TBD" not in output.analysis_dimension_plan.query_hints
    assert "benchmarking" not in output.selected_dimensions
    assert output.survey_needed is False
    assert output.confirmed_scope.region is None
    assert output.confidence <= 0.35


def test_planneragent_semispecific_request_detects_business_scope_gaps():
    trace_service = FakeTraceService()
    planner = PlannerAgent(
        trace_service,
        llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"),
    )

    output = planner.run(PlannerInput(task=make_semispecific_crm_task(), run_id="run_crm_unit_1"))
    print_structured_fields(output)

    assert output.scope_type in {"specific_product_benchmark", "mixed_intent", "semi_specific_benchmark", "strategic_ambiguous"}
    assert output.ambiguity_level in {"low", "medium", "high"}
    assert output.candidate_competitors
    assert any(candidate.name == "Salesforce" for candidate in output.candidate_competitors)
    assert output.extracted_context is not None
    assert output.extracted_context.competitors_mentioned == ["Salesforce", "HubSpot"]
    assert "business_purpose" in output.clarification_targets
    assert any("Business purpose is unclear" in item for item in output.missing_information)
    assert output.recommended_next_constraints


def test_planneragent_mixed_intent_request_keeps_survey_and_staged_planning_coherent():
    trace_service = FakeTraceService()
    planner = PlannerAgent(
        trace_service,
        llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"),
    )

    output = planner.run(PlannerInput(task=make_mixed_intent_task(), run_id="run_mixed_unit_1"))
    print_structured_fields(output)

    assert output.scope_type in {"mixed_intent", "broad_competitive_analysis"}
    assert output.survey_needed is True
    assert output.survey_recommended is True
    assert output.survey_inputs is not None
    assert output.planning_stages
    assert any(stage.stage_id == "survey_validation_plan" for stage in output.planning_stages)
    assert output.downstream_guidance is not None
    assert any("staged analysis" in line.lower() for line in output.downstream_guidance.writer)
    assert output.extracted_context is not None
    assert output.extracted_context.competitors_mentioned == []
    assert output.extracted_context.survey_reason is not None
    assert "explicitly includes survey or questionnaire work" in output.extracted_context.survey_reason.lower()
    assert output.confirmed_scope is not None
    assert output.confirmed_scope.region is None
    return


def test_planneragent_phone_prompt_llm_output_is_complete():
    trace_service = FakeTraceService()
    planner = PlannerAgent(
        trace_service,
        llm_client=FakeLlmClient(
            available=True,
            content=json.dumps(
                {
                    "intent_summary": "分析小米和华为旗舰手机的优劣，并准备围绕手机续航问题的用户问卷。",
                    "intent_classification": "improvement_opportunity",
                    "industry": "旗舰智能手机",
                    "domain": "智能手机硬件",
                    "product_name": "小米和华为旗舰手机对比",
                    "product_type": "旗舰手机",
                    "target_users": ["计划购买旗舰手机的消费者", "重度使用者"],
                    "region": "中国",
                    "competitors_mentioned": ["小米", "华为"],
                    "analysis_focus_points": ["续航表现", "性能取舍", "影像体验", "系统体验"],
                    "requested_outputs": ["竞品优劣分析", "手机续航问卷"],
                    "survey_needed": True,
                    "survey_reason": "用户明确希望生成一个关于手机续航问题的问卷。",
                    "missing_information": ["未指定问卷样本规模。", "未指定目标受访者细分。"],
                    "confidence": 0.95,
                    "selected_dimensions": ["feature", "pricing", "persona", "feedback", "prioritization"],
                    "survey_objective": "收集用户对旗舰手机续航问题、使用场景和改进期望的结构化反馈。",
                    "survey_inputs": {
                        "objective": "收集用户对旗舰手机续航问题、使用场景和改进期望的结构化反馈。",
                        "respondent_type": "使用或计划购买小米、华为旗舰手机的用户。",
                        "question_themes": ["续航痛点", "充电频率", "高负载场景", "改进优先级"],
                        "hypotheses": ["用户对旗舰手机续航的主要不满来自高负载场景掉电过快。"],
                    },
                    "planner_notes": ["已识别为竞品分析 + 问卷生成场景。"],
                    "downstream_guidance": {
                        "collector": ["收集小米和华为旗舰手机在续航、充电、性能和影像方面的公开证据。"],
                        "analyst": ["比较两家旗舰手机在续航相关优劣势和使用场景差异。"],
                        "writer": ["突出优劣对比、续航问题和问卷设计目的。"],
                        "qa": ["验证所有优劣结论是否有对应证据支撑。"],
                        "survey": ["围绕续航痛点、充电体验和改进优先级设计题目。"],
                    },
                }
            ),
        ),
    )

    output = planner.run(PlannerInput(task=make_phone_task(), run_id="run_phone_unit_2"))
    print_structured_fields(output)

    assert output.intent_summary
    assert output.intent_classification == "improvement_opportunity"
    assert output.extracted_context is not None
    assert output.extracted_context.competitors_mentioned == ["小米", "华为"]
    assert output.selected_dimensions
    assert output.analysis_dimension_plan is not None
    assert output.survey_needed is True
    assert output.survey_objective
    assert output.survey_inputs is not None
    assert "续航痛点" in output.survey_inputs.question_themes
    assert output.downstream_guidance is not None
    assert output.downstream_guidance.collector
    assert output.downstream_guidance.survey
    assert output.missing_information
    assert output.confidence > 0.8
    assert output.diagnostics["planner_mode_used"] == "llm_enhanced"
    assert output.diagnostics["llm_schema_validation_success"] is True
    assert trace_service.saved
    assert trace_service.saved[0].schema_validation_result == "passed"


def test_planneragent_phone_prompt_invalid_llm_json_falls_back_to_complete_output():
    trace_service = FakeTraceService()
    planner = PlannerAgent(
        trace_service,
        llm_client=FakeLlmClient(available=True, content="not valid json"),
    )

    output = planner.run(PlannerInput(task=make_phone_task(), run_id="run_phone_unit_3"))
    print_structured_fields(output)

    assert output.dag.nodes
    assert output.plan
    assert output.intent_summary
    assert output.intent_classification
    assert output.extracted_context is not None
    assert output.analysis_dimension_plan is not None
    assert output.survey_needed is False
    assert output.survey_recommended is False
    assert output.survey_inputs is None
    assert output.downstream_guidance is not None
    assert output.diagnostics["planner_mode_used"] == "deterministic"
    assert output.diagnostics["fallback_used"] is True
    assert output.diagnostics["llm_schema_validation_success"] is False
    return
    assert output.survey_needed is True
    assert output.survey_recommended is True
    assert output.survey_inputs is not None
    assert output.downstream_guidance is not None
    assert output.diagnostics["planner_mode_used"] == "deterministic"
    assert output.diagnostics["fallback_used"] is True
    assert output.diagnostics["llm_schema_validation_success"] is False


def test_planneragent_standard_competitive_analysis_keeps_feedback_optional_and_scope_clean():
    trace_service = FakeTraceService()
    planner = PlannerAgent(
        trace_service,
        llm_client=FakeLlmClient(
            available=True,
            content=json.dumps(
                {
                    "intent_summary": "Compare AI note-taking tools with a broad market scan.",
                    "intent_classification": "competitive_analysis",
                    "region": "United States",
                    "competitors_mentioned": ["Notion AI", "Obsidian"],
                    "selected_dimensions": ["benchmarking", "feature", "feedback", "pricing"],
                    "survey_needed": False,
                    "missing_information": [
                        "No dedicated free-form user brief is stored in Task; Planner inferred intent from product_name, industry, region, and competitors.",
                        "Target users are not specified.",
                    ],
                    "confidence": 0.72,
                }
            ),
        ),
    )

    output = planner.run(PlannerInput(task=make_broad_note_taking_task(), run_id="run_notes_unit_1"))
    print_structured_fields(output)

    assert output.intent_classification == "competitive_analysis"
    assert output.extracted_context is not None
    assert output.extracted_context.competitors_mentioned == []
    assert output.extracted_context.region == "Global"
    assert "benchmarking" not in output.selected_dimensions
    assert output.confirmed_scope is not None
    assert output.confirmed_scope.competitors == []
    assert output.inferred_scope is not None
    assert "Notion AI" in output.inferred_scope.competitors
    assert all("No dedicated free-form user brief" not in item for item in output.missing_information)
    assert any("confirmed user scope" in note.lower() for note in output.planner_notes)
    assert output.analysis_dimension_plan is not None
    feedback_dimension = next(
        dimension for dimension in output.analysis_dimension_plan.dimension_plans if dimension.dimension_id == "feedback"
    )
    assert feedback_dimension.required is False


def test_planneragent_feedback_dimension_required_for_improvement_and_survey_intents():
    trace_service = FakeTraceService()
    planner = PlannerAgent(
        trace_service,
        llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"),
    )

    output = planner.run(PlannerInput(task=make_mixed_intent_task(), run_id="run_mixed_unit_2"))
    print_structured_fields(output)

    assert output.analysis_dimension_plan is not None
    feedback_dimension = next(
        dimension for dimension in output.analysis_dimension_plan.dimension_plans if dimension.dimension_id == "feedback"
    )
    prioritization_dimension = next(
        dimension for dimension in output.analysis_dimension_plan.dimension_plans if dimension.dimension_id == "prioritization"
    )
    assert feedback_dimension.required is True
    assert prioritization_dimension.required is True


def test_planneragent_highly_specific_benchmark_stays_low_ambiguity_and_does_not_expand_competitors():
    now = datetime.utcnow()
    task = Task(
        task_id="task_specific_phone_benchmark",
        product_name=(
            "Compare Xiaomi and Huawei flagship smartphones in China. Focus on battery life, charging speed, "
            "camera performance, and operating system experience. Generate a competitive analysis plan and determine whether a user survey is needed."
        ),
        competitors=["Xiaomi", "Huawei"],
        region="China",
        industry="Smartphones",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )
    trace_service = FakeTraceService()
    planner = PlannerAgent(trace_service, llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"))

    output = planner.run(PlannerInput(task=task, run_id="run_specific_phone_benchmark"))
    print_structured_fields(output)

    assert output.ambiguity_level == "low"
    assert output.scope_type == "specific_product_benchmark"
    assert output.scope_size == "narrow"
    assert [candidate.name for candidate in output.candidate_competitors] == ["Xiaomi", "Huawei"]
    assert output.analysis_dimension_plan is not None
    assert set(output.analysis_dimension_plan.query_hints.keys()) == {"Xiaomi", "Huawei"}
    assert output.survey_needed is False
    assert output.survey_recommended is True
    assert output.extracted_context is not None
    assert output.extracted_context.survey_reason is not None
    assert "decision outcome or follow-up option" in output.extracted_context.survey_reason.lower()


def test_planneragent_explicit_competitor_request_with_user_feedback_does_not_trigger_survey_or_scope_broadening():
    now = datetime.utcnow()
    task = Task(
        task_id="task_specific_feedback_benchmark",
        product_name=(
            "Compare Apple and Samsung flagship phones for premium buyers in China. "
            "Focus on battery performance, imaging, pricing, and user feedback."
        ),
        competitors=["Apple", "Samsung"],
        region="China",
        industry="Smartphones",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )
    trace_service = FakeTraceService()
    planner = PlannerAgent(trace_service, llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"))

    output = planner.run(PlannerInput(task=task, run_id="run_specific_feedback_benchmark"))
    print_structured_fields(output)

    assert output.ambiguity_level == "low"
    assert [candidate.name for candidate in output.candidate_competitors] == ["Apple", "Samsung"]
    assert output.survey_needed is False
    assert output.survey_recommended is False
    assert output.extracted_context is not None
    assert output.extracted_context.survey_reason is None
    assert output.analysis_dimension_plan is not None
    assert "category_scope" not in output.analysis_dimension_plan.query_hints


def test_planneragent_broad_category_request_still_produces_category_candidates():
    trace_service = FakeTraceService()
    planner = PlannerAgent(trace_service, llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"))

    output = planner.run(PlannerInput(task=make_broad_phone_task(), run_id="run_broad_phone_unit_2"))
    print_structured_fields(output)

    assert output.scope_type == "category_scan"
    assert output.ambiguity_level == "high"
    assert output.candidate_competitors
    assert output.candidate_competitors[0].name in {"Apple iPhone", "Samsung Galaxy"}
    assert output.analysis_dimension_plan is not None
    assert "category_scope" in output.analysis_dimension_plan.query_hints


def test_planneragent_survey_direction_request_is_treated_as_required_deliverable():
    now = datetime.utcnow()
    task = Task(
        task_id="task_survey_direction_phone",
        product_name=(
            "Analyze Xiaomi and Huawei flagship smartphones and tell me where the biggest improvement opportunities are. "
            "Also generate a survey direction focused on battery complaints."
        ),
        competitors=["Xiaomi", "Huawei"],
        region="Global",
        industry="Smartphones",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )
    trace_service = FakeTraceService()
    planner = PlannerAgent(trace_service, llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"))

    output = planner.run(PlannerInput(task=task, run_id="run_survey_direction_phone"))
    print_structured_fields(output)

    assert output.survey_needed is True
    assert output.survey_recommended is True
    assert output.survey_inputs is not None
    assert output.extracted_context is not None
    assert output.extracted_context.survey_reason is not None
    assert "explicitly includes survey or questionnaire work" in output.extracted_context.survey_reason.lower()


def test_planneragent_questionnaire_decision_request_keeps_survey_optional_and_inputs_null():
    now = datetime.utcnow()
    task = Task(
        task_id="task_questionnaire_decision_phone",
        product_name=(
            "Compare Apple and Samsung flagship phones and help me identify product gaps, especially around battery life "
            "and charging. Then decide whether a questionnaire should be created."
        ),
        competitors=["Apple", "Samsung"],
        region="Global",
        industry="Smartphones",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )
    trace_service = FakeTraceService()
    planner = PlannerAgent(trace_service, llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"))

    output = planner.run(PlannerInput(task=task, run_id="run_questionnaire_decision_phone"))
    print_structured_fields(output)

    assert output.survey_needed is False
    assert output.survey_recommended is True
    assert output.survey_inputs is None
    assert output.extracted_context is not None
    assert output.extracted_context.survey_reason is not None
    assert "decision outcome or follow-up option" in output.extracted_context.survey_reason.lower()


def test_planneragent_user_survey_investigation_request_gets_stronger_survey_signal():
    now = datetime.utcnow()
    task = Task(
        task_id="task_crm_survey_investigation",
        product_name="Benchmark our CRM against HubSpot and Salesforce, identify weaknesses, and suggest what we should investigate with a user survey.",
        competitors=["HubSpot", "Salesforce"],
        region="Global",
        industry="CRM",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )
    trace_service = FakeTraceService()
    planner = PlannerAgent(trace_service, llm_client=FakeLlmClient(available=False, fallback_reason="LLM disabled in unit test"))

    output = planner.run(PlannerInput(task=task, run_id="run_crm_survey_investigation"))
    print_structured_fields(output)

    assert output.survey_needed is True
    assert output.survey_recommended is True
    assert output.survey_inputs is not None
    assert output.extracted_context is not None
    assert output.extracted_context.survey_reason is not None
    assert "explicitly includes survey or questionnaire work" in output.extracted_context.survey_reason.lower()


def test_planneragent_keeps_region_conservative_and_uses_inferred_industry_consistently():
    now = datetime.utcnow()
    task = Task(
        task_id="task_unknown_industry_benchmark",
        product_name="Benchmark Notion AI against ChatGPT and Perplexity for knowledge workers. Focus on features, workflow fit, pricing, and target users.",
        competitors=["Notion AI", "ChatGPT", "Perplexity"],
        region="Global",
        industry="Unknown",
        status="created",
        rework_count=0,
        created_at=now,
        updated_at=now,
    )
    trace_service = FakeTraceService()
    planner = PlannerAgent(
        trace_service,
        llm_client=FakeLlmClient(
            available=True,
            content=json.dumps(
                {
                    "intent_summary": "Benchmark Notion AI against ChatGPT and Perplexity for knowledge workers.",
                    "intent_classification": "competitive_analysis",
                    "industry": "AI-powered productivity software",
                    "domain": "knowledge work tools",
                    "product_name": "Notion AI, ChatGPT, and Perplexity comparison",
                    "product_type": "AI assistants",
                    "target_users": ["knowledge workers"],
                    "region": "United States",
                    "competitors_mentioned": ["Notion AI", "ChatGPT", "Perplexity"],
                    "analysis_focus_points": ["features", "workflow fit", "pricing", "target users"],
                    "requested_outputs": ["competitive benchmark report"],
                    "survey_needed": False,
                    "survey_reason": None,
                    "missing_information": ["Preferred output format"],
                    "confidence": 0.93,
                    "selected_dimensions": ["feature", "pricing", "persona", "positioning"],
                }
            ),
        ),
    )

    output = planner.run(PlannerInput(task=task, run_id="run_unknown_industry_benchmark"))
    print_structured_fields(output)

    assert output.extracted_context is not None
    assert output.extracted_context.region == "Global"
    assert output.survey_needed is False
    assert output.survey_recommended is False
    assert output.extracted_context.survey_reason is None
    assert output.analysis_dimension_plan is not None
    assert all("Unknown analysis" not in dimension.description for dimension in output.analysis_dimension_plan.dimension_plans)
    all_hints = [hint for hints in output.analysis_dimension_plan.query_hints.values() for hint in hints]
    assert all("official Unknown" not in hint for hint in all_hints)
    assert output.downstream_guidance is not None
    assert any("AI-powered productivity software" in line for line in output.downstream_guidance.collector)
