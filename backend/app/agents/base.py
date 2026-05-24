from collections.abc import Callable
from time import perf_counter
from uuid import uuid4

from pydantic import ValidationError

from app.schemas import AgentMessage, TraceRecord
from app.services.trace_service import TraceService


class AgentExecutionError(RuntimeError):
    pass


def run_with_trace(
    *,
    trace_service: TraceService,
    task_id: str,
    agent_name: str,
    to_agent: str,
    message_type: str,
    schema_name: str,
    input_summary: str,
    retry_count: int,
    fn: Callable[[], dict],
) -> dict:
    trace_id = f"trace_{uuid4().hex[:12]}"
    start = perf_counter()
    try:
        output = fn()
        AgentMessage(
            trace_id=trace_id,
            task_id=task_id,
            from_agent=agent_name,
            to_agent=to_agent,
            message_type=message_type,
            schema_name=schema_name,
            payload=output,
        )
        trace = TraceRecord(
            trace_id=trace_id,
            task_id=task_id,
            agent_name=agent_name,
            input_summary=input_summary,
            output_summary=f"已生成 {schema_name}",
            schema_validation_result="passed",
            elapsed_time_ms=int((perf_counter() - start) * 1000),
            retry_count=retry_count,
        )
        trace_service.save(trace)
        return output
    except (ValidationError, ValueError, RuntimeError) as exc:
        trace = TraceRecord(
            trace_id=trace_id,
            task_id=task_id,
            agent_name=agent_name,
            input_summary=input_summary,
            output_summary="Agent 输出未通过校验",
            schema_validation_result="failed",
            elapsed_time_ms=int((perf_counter() - start) * 1000),
            retry_count=retry_count,
            error_message=str(exc),
        )
        trace_service.save(trace)
        raise AgentExecutionError(str(exc)) from exc
