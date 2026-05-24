from app.agents.base import run_with_trace
from app.schemas import Evidence, FeatureTree, PricingModel, ProductProfile, Task, UserPersona
from app.services.trace_service import TraceService


class AnalystAgent:
    name = "AnalystAgent"

    def __init__(self, trace_service: TraceService):
        self.trace_service = trace_service

    def run(self, task: Task, evidence: list[Evidence], retry_count: int = 0) -> dict:
        def produce() -> dict:
            ids = [item.evidence_id for item in evidence]
            profile = ProductProfile(
                product_name=task.product_name,
                positioning="面向企业竞品分析的 AI 辅助情报工作台，强调可审计输出。",
                target_segments=["产品市场团队", "战略团队", "销售赋能团队"],
                strengths=["证据可追溯", "结构化 Schema", "QA 反馈闭环"],
                weaknesses=["当前 Demo 仍使用 Mock 采集覆盖", "尚未接入实时网页新鲜度校验"],
                evidence_ids=ids[:2],
                custom_dimensions={"区域": task.region, "行业": task.industry},
            )
            feature_tree = FeatureTree(
                core_features={
                    "采集": ["来源捕获", "证据归一化"],
                    "分析": ["功能分类", "定价抽取", "用户画像生成"],
                    "治理": ["结论证据绑定", "QA 路由", "Trace 查看"],
                },
                differentiators=["可点击的结论到证据链路", "人工复核兜底机制"],
                evidence_ids=ids,
            )
            pricing = PricingModel(
                model="分层 SaaS 定价基准",
                tiers=["入门版", "团队版", "企业版"],
                pricing_notes="竞品通常将协作能力和集成能力打包到更高阶套餐中。",
                evidence_ids=ids[1:3] or ids[:1],
            )
            persona = UserPersona(
                persona_name="竞品情报负责人",
                goals=["减少人工调研时间", "保证结论有来源支撑", "标准化报告格式"],
                pain_points=["来源分散", "证据质量不透明", "质检周期长"],
                buying_triggers=["进入新市场", "季度规划", "销售战卡更新"],
                evidence_ids=ids[2:4] or ids[:1],
            )
            return {
                "product_profile": profile.model_dump(mode="json"),
                "feature_tree": feature_tree.model_dump(mode="json"),
                "pricing_model": pricing.model_dump(mode="json"),
                "user_persona": persona.model_dump(mode="json"),
            }

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="ReportWriterAgent",
            message_type="analysis",
            schema_name="CompetitorKnowledge",
            input_summary=f"分析 {len(evidence)} 条证据记录",
            retry_count=retry_count,
            fn=produce,
        )
