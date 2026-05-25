import os

from sqlalchemy.orm import Session

from app.agents.langgraph_runner import LangGraphWorkflowRunner
from app.agents.runner import MockWorkflowRunner


def resolve_workflow_engine(requested: str | None = None) -> str:
    value = (requested or os.getenv("WORKFLOW_ENGINE") or "custom").strip().lower()
    if value == "langgraph":
        return "langgraph"
    return "custom"


def create_workflow_runner(db: Session, requested: str | None = None):
    engine = resolve_workflow_engine(requested)
    if engine == "langgraph":
        return LangGraphWorkflowRunner(db), engine
    return MockWorkflowRunner(db), engine
