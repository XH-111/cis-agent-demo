from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaskRecord(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    competitors_json: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False)
    industry: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="created", nullable=False)
    rework_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class TraceRecordRow(Base):
    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    task_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    agent_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EvidenceRecordRow(Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class ReportRecordRow(Base):
    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class QaRecordRow(Base):
    __tablename__ = "qa_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
