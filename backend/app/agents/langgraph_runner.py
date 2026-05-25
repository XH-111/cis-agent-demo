import json
import time
from uuid import uuid4

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agents.analyst import AnalystAgent
from app.agents.collector import CollectorAgent
from app.agents.final_report import FinalReportAgent
from app.agents.planner import PlannerAgent
from app.agents.qa import MAX_REWORK, QaAgent
from app.agents.report_writer import ReportWriterAgent
from app.schemas import (
    AnalystInput,
    CollectorInput,
    DemoMode,
    FinalReportInput,
    PlannerInput,
    QaInput,
    ReportWriterInput,
    ReworkHistoryItem,
    Task,
    TraceRecord,
)
from app.schemas.workflow_state import WorkflowState
from app.services.evidence_service import EvidenceService
from app.services.report_service import ReportService
from app.services.task_service import TaskService
from app.services.trace_service import TraceService


class LangGraphWorkflowRunner:
    def __init__(self, db: Session):
        self.db = db
        self.task_service = TaskService(db)
        self.trace_service = TraceService(db)
        self.evidence_service = EvidenceService(db)
        self.report_service = ReportService(db)
        self.planner = PlannerAgent(self.trace_service)
        self.collector = CollectorAgent(self.trace_service)
        self.analyst = AnalystAgent(self.trace_service)
        self.writer = ReportWriterAgent(self.trace_service)
        self.qa = QaAgent(self.trace_service)
        self.final_report = FinalReportAgent(self.trace_service)
        self.graph = self._build_graph()

    def run(
        self,
        task_id: str,
        demo_mode: DemoMode = "normal",
        auto_rework: bool = False,
        writer_mode: str = "mock",
        collector_mode: str = "mock",
        analyst_mode: str = "evidence",
        workflow_engine_requested: str = "langgraph",
        content_mode: str | None = None,
    ) -> dict:
        started = time.perf_counter()
        task = self.task_service.update_status(task_id, "running", rework_count=0)
        initial_state: WorkflowState = {
            "task_id": task_id,
            "trace_id": f"workflow_{uuid4().hex[:10]}",
            "task": task,
            "workflow_engine_requested": workflow_engine_requested,
            "workflow_engine_used": "langgraph",
            "demo_mode": demo_mode,
            "collector_mode": collector_mode,
            "analyst_mode": analyst_mode,
            "writer_mode": writer_mode,
            "content_mode": content_mode,
            "auto_rework": auto_rework,
            "rework_count": 0,
            "max_rework": MAX_REWORK,
            "planner_output": None,
            "collector_output": None,
            "analyst_output": None,
            "report_writer_output": None,
            "qa_output": None,
            "final_report_output": None,
            "evidence": [],
            "report": None,
            "qa_result": None,
            "route_to": None,
            "final_status": None,
            "errors": [],
            "node_sequence": [],
            "conditional_routes_taken": [],
            "workflow_summary": {},
        }
        final_state = self.graph.invoke(initial_state)
        elapsed = int((time.perf_counter() - started) * 1000)
        summary = self._workflow_summary(final_state, elapsed)
        self._save_workflow_trace(task_id, summary, elapsed)
        final_state["workflow_summary"] = summary
        return {
            "plan": final_state.get("planner_output"),
            "qa_result": final_state.get("qa_result"),
            "report": final_state.get("report"),
            "workflow_summary": summary,
        }

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("planner", self.planner_node)
        graph.add_node("collector", self.collector_node)
        graph.add_node("analyst", self.analyst_node)
        graph.add_node("report_writer", self.report_writer_node)
        graph.add_node("qa", self.qa_node)
        graph.add_node("final_report", self.final_report_node)
        graph.set_entry_point("planner")
        graph.add_edge("planner", "collector")
        graph.add_edge("collector", "analyst")
        graph.add_edge("analyst", "report_writer")
        graph.add_edge("report_writer", "qa")
        graph.add_conditional_edges(
            "qa",
            self.route_after_qa,
            {
                "collector": "collector",
                "analyst": "analyst",
                "report_writer": "report_writer",
                "final_report": "final_report",
                "end": END,
            },
        )
        graph.add_edge("final_report", END)
        return graph.compile()

    def planner_node(self, state: WorkflowState) -> WorkflowState:
        task = state["task"]
        output = self.planner.run(PlannerInput(task=task, retry_count=state["rework_count"]))
        return {**state, "planner_output": output, "node_sequence": [*state["node_sequence"], "planner"]}

    def collector_node(self, state: WorkflowState) -> WorkflowState:
        task = self._current_task(state)
        if state["demo_mode"] == "qa_missing_evidence" and state["rework_count"] == 0:
            return {**state, "task": task, "evidence": [], "collector_output": None, "node_sequence": [*state["node_sequence"], "collector"]}
        output = self.collector.run(
            CollectorInput(
                task=task,
                retry_count=state["rework_count"],
                collector_mode=state["collector_mode"],
            )
        )
        self.evidence_service.save_many(task.task_id, output.evidence)
        return {
            **state,
            "task": task,
            "collector_output": output,
            "evidence": output.evidence,
            "node_sequence": [*state["node_sequence"], "collector"],
        }

    def analyst_node(self, state: WorkflowState) -> WorkflowState:
        task = self._current_task(state)
        output = self.analyst.run(
            AnalystInput(
                task=task,
                evidence=state.get("evidence", []),
                retry_count=state["rework_count"],
                force_invalid_extraction=state["demo_mode"] == "qa_invalid_extraction" and state["rework_count"] == 0,
                analyst_mode=state["analyst_mode"],
            )
        )
        return {**state, "task": task, "analyst_output": output, "node_sequence": [*state["node_sequence"], "analyst"]}

    def report_writer_node(self, state: WorkflowState) -> WorkflowState:
        task = self._current_task(state)
        output = self.writer.run(
            ReportWriterInput(
                task=task,
                knowledge=state["analyst_output"],
                evidence=state.get("evidence", []),
                retry_count=state["rework_count"],
                force_bad_format=state["demo_mode"] == "qa_bad_report" and state["rework_count"] == 0,
                writer_mode=state["writer_mode"],
            )
        )
        return {
            **state,
            "task": task,
            "report_writer_output": output,
            "report": output.report,
            "node_sequence": [*state["node_sequence"], "report_writer"],
        }

    def qa_node(self, state: WorkflowState) -> WorkflowState:
        task = self._current_task(state)
        output = self.qa.run(
            QaInput(
                task=task,
                evidence=state.get("evidence", []),
                analysis=state.get("analyst_output"),
                report_output=state.get("report_writer_output"),
                retry_count=state["rework_count"],
                demo_mode=state["demo_mode"],
            )
        )
        qa_result = output.qa_result
        self.report_service.save_qa(qa_result)
        next_state: WorkflowState = {
            **state,
            "task": task,
            "qa_output": output,
            "qa_result": qa_result,
            "route_to": qa_result.route_to,
            "rework_count": qa_result.rework_count,
            "node_sequence": [*state["node_sequence"], "qa"],
        }
        if qa_result.status == "failed" and state["auto_rework"] and qa_result.route_to:
            instruction = qa_result.rework_instructions[0] if qa_result.rework_instructions else None
            next_node = self._agent_to_node(qa_result.route_to)
            is_unknown_route = next_node == "final_report"
            next_state["conditional_routes_taken"] = [
                *state["conditional_routes_taken"],
                {
                    "from_node": "qa",
                    "to_node": next_node,
                    "reason": "unknown_route" if is_unknown_route else (instruction.error_type if instruction else "qa_failed"),
                    "rework_count": qa_result.rework_count,
                    **({"final_status": "manual_review"} if is_unknown_route else {}),
                },
            ]
            if is_unknown_route:
                next_state["final_status"] = "manual_review"
                next_state["task"] = self.task_service.update_status(task.task_id, "manual_review", rework_count=qa_result.rework_count)
            else:
                next_state["demo_mode"] = "normal"
                next_state["task"] = self.task_service.update_status(task.task_id, "qa_failed", rework_count=qa_result.rework_count)
        return next_state

    def final_report_node(self, state: WorkflowState) -> WorkflowState:
        task = self._current_task(state)
        qa_result = state.get("qa_result")
        writer_output = state.get("report_writer_output")
        if qa_result and qa_result.status == "passed" and writer_output and writer_output.report:
            output = self.final_report.run(
                FinalReportInput(
                    task=task,
                    report=writer_output.report,
                    qa_result=qa_result,
                    evidence=state.get("evidence", []),
                    retry_count=qa_result.rework_count,
                )
            )
            self.report_service.save_report(output.report)
            self.task_service.update_status(task.task_id, "completed", rework_count=qa_result.rework_count)
            return {
                **state,
                "task": task,
                "final_report_output": output,
                "report": output.report,
                "final_status": "completed",
                "node_sequence": [*state["node_sequence"], "final_report"],
            }
        final_status = state.get("final_status") or (self._status_for_qa(qa_result) if qa_result else "failed")
        self.task_service.update_status(task.task_id, final_status, rework_count=qa_result.rework_count if qa_result else state["rework_count"])
        return {**state, "task": task, "report": None, "final_status": final_status, "node_sequence": [*state["node_sequence"], "final_report"]}

    def route_after_qa(self, state: WorkflowState) -> str:
        qa_result = state.get("qa_result")
        if qa_result is None:
            return "final_report"
        if qa_result.status == "passed":
            return "final_report"
        if qa_result.status == "manual_review" or qa_result.rework_count >= state["max_rework"]:
            state["final_status"] = "manual_review"
            return "final_report"
        if not state["auto_rework"]:
            return "final_report"
        if qa_result.route_to == "CollectorAgent":
            return "collector"
        if qa_result.route_to == "AnalystAgent":
            return "analyst"
        if qa_result.route_to == "ReportWriterAgent":
            return "report_writer"
        state["final_status"] = "manual_review"
        return "final_report"

    def _current_task(self, state: WorkflowState) -> Task:
        return self.task_service.get_task(state["task_id"])

    @staticmethod
    def _agent_to_node(agent_name: str) -> str:
        return {
            "CollectorAgent": "collector",
            "AnalystAgent": "analyst",
            "ReportWriterAgent": "report_writer",
        }.get(agent_name, "final_report")

    @staticmethod
    def _status_for_qa(qa_result) -> str:
        if qa_result is None:
            return "failed"
        if qa_result.status == "manual_review":
            return "manual_review"
        if qa_result.status == "failed":
            return "qa_failed"
        return "completed"

    @staticmethod
    def _workflow_summary(state: WorkflowState, elapsed_time_ms: int) -> dict:
        return {
            "workflow_engine_requested": state.get("workflow_engine_requested"),
            "workflow_engine_used": "langgraph",
            "node_sequence": state.get("node_sequence", []),
            "conditional_routes_taken": state.get("conditional_routes_taken", []),
            "rework_count": state.get("qa_result").rework_count if state.get("qa_result") else state.get("rework_count", 0),
            "final_status": state.get("final_status") or (state.get("qa_result").status if state.get("qa_result") else "failed"),
            "elapsed_time_ms": elapsed_time_ms,
            "error_message": "; ".join(state.get("errors", [])) if state.get("errors") else None,
        }

    def _save_workflow_trace(self, task_id: str, summary: dict, elapsed_time_ms: int) -> None:
        self.trace_service.save(
            TraceRecord(
                trace_id=f"trace_{uuid4().hex[:10]}",
                task_id=task_id,
                agent_name="WorkflowEngine",
                input_summary=f"workflow_engine_requested={summary['workflow_engine_requested']}",
                output_summary=json.dumps(summary, ensure_ascii=False),
                schema_validation_result="passed",
                model_name="langgraph-stategraph",
                elapsed_time_ms=elapsed_time_ms,
            )
        )
