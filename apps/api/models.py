"""SQLAlchemy ORM 模型（M1 平台底座）

SQLite（开发）与 PostgreSQL（生产）双兼容；JSON 列用于半结构化产物。
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now()


class SessionRecord(Base):
    """测算会话（SessionStore 的持久化形态）

    data 列存放各业务线的半结构化产物（extracted_data / quality_report /
    result / sim_* / quote_* 等），保持与原内存 SessionStore 的 dict 接口兼容。
    """
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    module_type: Mapped[str] = mapped_column(String(32), default="air_conditioner")
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(32), default="upload")
    session_dir: Mapped[str] = mapped_column(String(1024))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class AgentRun(Base):
    """一次 agent 运行（可恢复状态机）"""
    __tablename__ = "agent_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.session_id"), index=True
    )
    mode: Mapped[str] = mapped_column(String(16), default="auto")  # auto | deterministic
    # running / completed / needs_input / error / interrupted
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    llm_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentStep(Base):
    """agent 运行的单步记录（断点恢复的依据）"""
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agent_runs.run_id"), index=True
    )
    step_no: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    observation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    """审计日志：谁在何时对哪个会话做了什么"""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
