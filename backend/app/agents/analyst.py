from collections import defaultdict

from app.agents.base import run_with_trace
from app.schemas import AnalystInput, AnalystOutput, Evidence, FeatureTree, PricingModel, ProductProfile, UserPersona
from app.services.trace_service import TraceService


FEATURE_KEYWORDS = {
    "AI": ["ai", "artificial intelligence", "智能", "人工智能"],
    "automation": ["automation", "自动化"],
    "collaboration": ["collaboration", "collaborative", "协作", "团队", "办公"],
    "pricing": ["pricing", "price", "plan", "定价", "价格", "套餐"],
    "integration": ["integration", "integrations", "集成"],
    "analytics": ["analytics", "analysis", "分析"],
    "security": ["security", "安全"],
    "mobile": ["mobile", "app", "移动端"],
    "API": ["api", "接口"],
    "workflow": ["workflow", "流程"],
}

PRICING_KEYWORDS = ["free", "trial", "pricing", "subscription", "enterprise", "plan", "quote", "免费", "试用", "订阅", "企业版", "套餐", "定价", "价格"]
PERSONA_KEYWORDS = {
    "企业团队": ["enterprise", "企业"],
    "团队用户": ["team", "团队"],
    "开发者": ["developer", "开发者"],
    "市场团队": ["marketer", "marketing", "市场"],
    "产品团队": ["product team", "product manager", "产品经理"],
    "学生": ["student", "学生"],
}


class AnalystAgent:
    name = "AnalystAgent"

    def __init__(self, trace_service: TraceService):
        self.trace_service = trace_service

    def run(self, input_data: AnalystInput) -> AnalystOutput:
        task = input_data.task

        def produce() -> AnalystOutput:
            if input_data.analyst_mode == "mock":
                return self._mock_output(input_data, fallback_reason=None)
            if input_data.analyst_mode == "llm":
                return self._evidence_output(
                    input_data,
                    fallback_reason="analyst_mode=llm is not implemented in this phase; fallback to evidence mode.",
                )
            return self._evidence_output(input_data, fallback_reason=None)

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="ReportWriterAgent",
            message_type="analysis",
            schema_name="AnalystOutput",
            input_summary=f"analyst_mode_requested={input_data.analyst_mode}; analyze {len(input_data.evidence)} evidence records",
            retry_count=input_data.retry_count,
            fn=produce,
        )

    def _mock_output(self, input_data: AnalystInput, fallback_reason: str | None) -> AnalystOutput:
        task = input_data.task
        ids = self._ids(input_data.evidence)
        diagnostics = self._diagnostics(
            input_data,
            "mock",
            ids,
            fallback_reason=fallback_reason,
            evidence_by_competitor=self._group_by_competitor(input_data.evidence, task.competitors),
            extracted_fields_by_competitor={competitor: {"profile": 1, "feature": 1, "pricing": 1, "persona": 1} for competitor in task.competitors},
        )
        competitor_analysis = {
            competitor: {
                "positioning": f"{competitor} is represented by mock competitor knowledge.",
                "features": ["collaboration", "workflow"],
                "pricing": ["paid/enterprise signal"],
                "persona": ["enterprise team"],
                "evidence_ids": [item.evidence_id for item in input_data.evidence if item.competitor == competitor] or ids[:1],
                "insufficient_evidence": False,
            }
            for competitor in task.competitors
        }
        profile = ProductProfile(
            product_name=task.product_name,
            positioning="" if input_data.force_invalid_extraction else f"{task.product_name} is a structured competitor analysis workspace.",
            target_segments=[] if input_data.force_invalid_extraction else ["product marketing team", "strategy team", "sales enablement team"],
            strengths=["traceable evidence", "structured Schema", "QA feedback loop"],
            weaknesses=["current demo still uses simplified extraction rules"],
            evidence_ids=ids[:2],
            custom_dimensions={
                "region": task.region,
                "industry": task.industry,
                "analyst_mode": "mock",
                "competitor_analysis": competitor_analysis,
            },
        )
        feature_tree = FeatureTree(
            core_features={competitor: ["collaboration", "workflow", "pricing"] for competitor in task.competitors},
            differentiators=["claim-to-evidence traceability", "manual review fallback"],
            evidence_ids=ids,
        )
        pricing = PricingModel(
            model="tiered SaaS benchmark",
            tiers=[f"{competitor}: starter/team/enterprise signals" for competitor in task.competitors],
            pricing_notes="Competitors usually package collaboration and integration capability into higher tiers.",
            evidence_ids=ids[1:3] or ids[:1],
        )
        persona = UserPersona(
            persona_name="competitor intelligence owner",
            goals=["reduce manual research time", "keep conclusions source-backed", "standardize report format"],
            pain_points=["sources are scattered", "evidence quality is opaque", "QA takes time"],
            buying_triggers=["new market entry", "quarterly planning", "sales battlecard refresh"],
            evidence_ids=ids[2:4] or ids[:1],
        )
        return AnalystOutput(product_profile=profile, feature_tree=feature_tree, pricing_model=pricing, user_persona=persona, diagnostics=diagnostics)

    def _evidence_output(self, input_data: AnalystInput, fallback_reason: str | None) -> AnalystOutput:
        task = input_data.task
        evidence_by_competitor = self._group_by_competitor(input_data.evidence, task.competitors)
        ids = self._ids(input_data.evidence)
        competitor_analysis: dict[str, dict] = {}
        core_features: dict[str, list[str]] = {}
        aggregate_feature_hits: dict[str, list[Evidence]] = defaultdict(list)
        pricing_tiers: list[str] = []
        persona_goals: list[str] = []
        persona_pain_points: list[str] = []
        persona_triggers: list[str] = []
        aggregate_persona_labels: list[str] = []
        extracted_fields_by_competitor: dict[str, dict[str, int]] = {}
        evidence_used_by_competitor: dict[str, list[str]] = {}

        for competitor in task.competitors:
            competitor_evidence = sorted(evidence_by_competitor.get(competitor, []), key=lambda item: item.confidence, reverse=True)
            competitor_ids = self._ids(competitor_evidence)
            feature_hits = self._feature_hits(competitor_evidence)
            pricing_evidence = self._keyword_evidence(competitor_evidence, PRICING_KEYWORDS)
            persona_hits = self._persona_hits(competitor_evidence)
            insufficient = len(competitor_evidence) < 2 or (len(feature_hits) + len(pricing_evidence) + len(persona_hits)) < 1

            feature_names = list(feature_hits.keys()) or ["insufficient evidence"]
            pricing_labels = self._pricing_tiers(pricing_evidence)
            persona_labels = list(persona_hits.keys()) or ["Evidence-insufficient persona"]
            aggregate_persona_labels.extend([item for item in persona_labels if item != "Evidence-insufficient persona"])
            positioning = (
                "Evidence is insufficient for a confident conclusion."
                if insufficient
                else f"{competitor} positioning is inferred only from its own public evidence: {self._compact(competitor_evidence[0].snippet)}"
            )

            competitor_analysis[competitor] = {
                "positioning": positioning,
                "features": feature_names,
                "pricing": pricing_labels,
                "persona": persona_labels,
                "evidence_ids": competitor_ids,
                "insufficient_evidence": insufficient,
            }
            evidence_used_by_competitor[competitor] = competitor_ids
            extracted_fields_by_competitor[competitor] = {
                "profile": 0 if insufficient else 1,
                "feature": len(feature_hits),
                "pricing": len(pricing_evidence),
                "persona": len(persona_hits),
            }
            for feature, values in feature_hits.items():
                aggregate_feature_hits[feature].extend(values)
                core_features[f"{competitor} / {feature}"] = self._feature_labels(feature, values)
            pricing_tiers.append(f"{competitor}: {', '.join(pricing_labels)}")
            persona_goals.append(f"{competitor}: evaluate fit for {', '.join(persona_labels[:2])}")
            persona_pain_points.append(f"{competitor}: needs more official, pricing, and user-feedback evidence cross-checks")
            persona_triggers.append(f"{competitor}: product selection and competitor replacement")

        for feature, values in aggregate_feature_hits.items():
            core_features.setdefault(feature, self._feature_labels(feature, values))

        missing_competitors = [competitor for competitor, records in evidence_by_competitor.items() if not records]
        insufficient = bool(missing_competitors) or any(item["insufficient_evidence"] for item in competitor_analysis.values())
        diagnostics = self._diagnostics(
            input_data,
            "evidence",
            ids,
            fallback_reason=fallback_reason or ("Evidence is insufficient for one or more competitors." if insufficient else None),
            insufficient=insufficient,
            feature_count=sum(item["feature"] for item in extracted_fields_by_competitor.values()),
            pricing_count=sum(item["pricing"] for item in extracted_fields_by_competitor.values()),
            persona_count=sum(item["persona"] for item in extracted_fields_by_competitor.values()),
            evidence_by_competitor=evidence_by_competitor,
            extracted_fields_by_competitor=extracted_fields_by_competitor,
            evidence_used_by_competitor=evidence_used_by_competitor,
        )
        profile = ProductProfile(
            product_name=task.product_name,
            positioning="" if input_data.force_invalid_extraction else (
                "Evidence is insufficient for a confident conclusion."
                if insufficient
                else f"{task.product_name} compares {', '.join(task.competitors)} using competitor-specific public evidence."
            ),
            target_segments=[] if input_data.force_invalid_extraction else (["Evidence is insufficient for a confident conclusion."] if insufficient else ["enterprise team", "product team"]),
            strengths=self._strengths_from_features(dict(aggregate_feature_hits)) or ["Evidence is insufficient for a confident conclusion."],
            weaknesses=["Conclusions remain limited by available public evidence coverage per competitor."],
            evidence_ids=ids[: min(5, len(ids))],
            custom_dimensions={
                "region": task.region,
                "industry": task.industry,
                "analyst_mode": "evidence",
                "insufficient_evidence": insufficient,
                "supporting_evidence_ids": ids,
                "competitor_analysis": competitor_analysis,
            },
        )
        feature_tree = FeatureTree(
            core_features=core_features or {"insufficient evidence": ["Evidence is insufficient for a confident conclusion."]},
            differentiators=self._strengths_from_features(dict(aggregate_feature_hits)) or ["Evidence is insufficient for a confident conclusion."],
            evidence_ids=ids,
        )
        pricing = PricingModel(
            model="Evidence-based competitor pricing summary" if not insufficient else "Evidence insufficient",
            tiers=pricing_tiers or ["Evidence is insufficient"],
            pricing_notes=self._pricing_notes([item for records in evidence_by_competitor.values() for item in records]),
            evidence_ids=[
                item.evidence_id
                for records in evidence_by_competitor.values()
                for item in self._keyword_evidence(records, PRICING_KEYWORDS)
            ] or ids[:1],
        )
        persona = UserPersona(
            persona_name=aggregate_persona_labels[0] if aggregate_persona_labels else "competitor evaluation team",
            goals=persona_goals or ["Evidence is insufficient for a confident conclusion."],
            pain_points=persona_pain_points or ["Need more competitor-specific evidence."],
            buying_triggers=persona_triggers or ["Evidence is insufficient for a confident conclusion."],
            evidence_ids=ids[: min(5, len(ids))],
        )
        return AnalystOutput(product_profile=profile, feature_tree=feature_tree, pricing_model=pricing, user_persona=persona, diagnostics=diagnostics)

    def _diagnostics(
        self,
        input_data: AnalystInput,
        used_mode: str,
        ids: list[str],
        *,
        fallback_reason: str | None,
        insufficient: bool = False,
        feature_count: int = 0,
        pricing_count: int = 0,
        persona_count: int = 0,
        evidence_by_competitor: dict[str, list[Evidence]] | None = None,
        extracted_fields_by_competitor: dict[str, dict[str, int]] | None = None,
        evidence_used_by_competitor: dict[str, list[str]] | None = None,
    ) -> dict:
        grouped = evidence_by_competitor or self._group_by_competitor(input_data.evidence, input_data.task.competitors)
        evidence_count_by_competitor = {competitor: len(records) for competitor, records in grouped.items()}
        competitors_covered = [competitor for competitor, count in evidence_count_by_competitor.items() if count > 0]
        missing_competitors = [competitor for competitor in input_data.task.competitors if evidence_count_by_competitor.get(competitor, 0) == 0]
        return {
            "analyst_mode_requested": input_data.analyst_mode,
            "analyst_mode_used": used_mode,
            "evidence_count": len(input_data.evidence),
            "evidence_used_count": len(ids),
            "extracted_profile_count": 0 if insufficient else len(competitors_covered),
            "extracted_feature_count": feature_count,
            "extracted_pricing_count": pricing_count,
            "extracted_persona_count": persona_count,
            "insufficient_evidence": insufficient,
            "fallback_used": bool(fallback_reason),
            "fallback_reason": fallback_reason,
            "analyst_fallback_reason": fallback_reason,
            "competitors_requested": input_data.task.competitors,
            "competitors_covered": competitors_covered,
            "missing_competitors": missing_competitors,
            "evidence_count_by_competitor": evidence_count_by_competitor,
            "evidence_used_by_competitor": evidence_used_by_competitor or {
                competitor: [item.evidence_id for item in records] for competitor, records in grouped.items()
            },
            "extracted_fields_by_competitor": extracted_fields_by_competitor or {},
        }

    @staticmethod
    def _group_by_competitor(evidence: list[Evidence], competitors: list[str]) -> dict[str, list[Evidence]]:
        grouped: dict[str, list[Evidence]] = {competitor: [] for competitor in competitors}
        if evidence and not any(item.competitor for item in evidence):
            for competitor in competitors:
                grouped[competitor] = list(evidence)
            return grouped
        for item in evidence:
            if item.competitor in grouped:
                grouped[item.competitor].append(item)
            elif item.competitor is None and len(competitors) == 1:
                grouped[competitors[0]].append(item)
        return grouped

    @staticmethod
    def _ids(evidence: list[Evidence]) -> list[str]:
        return [item.evidence_id for item in evidence] or ["insufficient_evidence"]

    @staticmethod
    def _compact(text: str) -> str:
        return text[:120].replace("\n", " ")

    def _feature_hits(self, evidence: list[Evidence]) -> dict[str, list[Evidence]]:
        hits: dict[str, list[Evidence]] = defaultdict(list)
        for item in evidence:
            text = item.snippet.lower()
            for feature, keywords in FEATURE_KEYWORDS.items():
                if any(keyword.lower() in text for keyword in keywords):
                    hits[feature].append(item)
        return dict(hits)

    @staticmethod
    def _keyword_evidence(evidence: list[Evidence], keywords: list[str]) -> list[Evidence]:
        matched = []
        for item in evidence:
            text = f"{item.snippet} {item.url or ''}".lower()
            if any(keyword.lower() in text for keyword in keywords):
                matched.append(item)
        return matched

    def _persona_hits(self, evidence: list[Evidence]) -> dict[str, list[Evidence]]:
        hits: dict[str, list[Evidence]] = defaultdict(list)
        for item in evidence:
            text = item.snippet.lower()
            for persona, keywords in PERSONA_KEYWORDS.items():
                if any(keyword.lower() in text for keyword in keywords):
                    hits[persona].append(item)
        return dict(hits)

    @staticmethod
    def _feature_labels(feature: str, evidence: list[Evidence]) -> list[str]:
        ids = ", ".join(item.evidence_id for item in evidence[:3])
        return [f"{feature} related evidence: {ids}"]

    @staticmethod
    def _strengths_from_features(feature_hits: dict[str, list[Evidence]]) -> list[str]:
        return [f"Public evidence mentions {feature} capability" for feature in list(feature_hits.keys())[:4]]

    @staticmethod
    def _pricing_notes(evidence: list[Evidence]) -> str:
        if not evidence:
            return "Evidence is insufficient for a confident pricing conclusion."
        return "Public evidence includes pricing/plan/subscription/enterprise signals; official pages should be used for final validation."

    @staticmethod
    def _pricing_tiers(evidence: list[Evidence]) -> list[str]:
        if not evidence:
            return ["Evidence is insufficient"]
        return [
            "free/trial signal" if any(word in item.snippet.lower() for word in ["free", "trial", "免费", "试用"]) else "paid/enterprise signal"
            for item in evidence[:3]
        ]
