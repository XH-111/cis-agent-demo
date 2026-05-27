from app.agents.base import run_with_trace
from app.schemas import Dag, DagEdge, DagNode, PlannerInput, PlannerOutput
from app.services.trace_service import TraceService


class PlannerAgent:
    name = "PlannerAgent"

    def __init__(self, trace_service: TraceService):
        self.trace_service = trace_service

    def run(self, input_data: PlannerInput) -> PlannerOutput:
        task = input_data.task

        def produce() -> PlannerOutput:
            dag = Dag(
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
            return PlannerOutput(
                dag=dag,
                plan=[
                    "采集竞品定位、功能、定价和用户画像证据。",
                    "将发现归一化为结构化竞品知识 Schema。",
                    "生成带 evidence_ids 的关键结论并执行 QA 反馈闭环。",
                ],
            )

        return run_with_trace(
            trace_service=self.trace_service,
            task_id=task.task_id,
            agent_name=self.name,
            to_agent="CollectorAgent",
            message_type="plan",
            schema_name="PlannerOutput",
            input_summary=f"{task.product_name} 对比 {', '.join(task.competitors)}",
            retry_count=input_data.retry_count,
            fn=produce,
        )
