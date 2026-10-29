"""数据库引擎与会话管理（M1 平台底座）

- 开发环境：SQLite（data/app.db，落盘持久化，重启不丢）
- 生产环境：PostgreSQL（仅改 DATABASE_URL，模型与代码零改动）
"""
import threading
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from .config import settings

_engine = None
_engine_lock = threading.Lock()


def get_engine():
    """按配置惰性创建引擎（线程安全）"""
    global _engine
    with _engine_lock:
        if _engine is None:
            url = settings.database_url
            if url.startswith("sqlite"):
                db_path = url.split("///", 1)[-1]
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                _engine = create_engine(
                    url,
                    connect_args={"check_same_thread": False},
                    pool_pre_ping=True,
                )

                # SQLite 多线程写优化：WAL + 忙等待
                @event.listens_for(_engine, "connect")
                def _sqlite_pragma(dbapi_conn, _):
                    cur = dbapi_conn.cursor()
                    cur.execute("PRAGMA journal_mode=WAL")
                    cur.execute("PRAGMA busy_timeout=5000")
                    cur.close()
            else:
                _engine = create_engine(url, pool_pre_ping=True, pool_size=10)
    return _engine


def make_session() -> Session:
    """短生命周期 DB 会话：每次操作独立开合，避免跨线程共享"""
    return Session(bind=get_engine(), expire_on_commit=False)


def init_db() -> None:
    """建表（幂等）。生产演进到 Alembic 管理迁移。"""
    from .models import Base
    Base.metadata.create_all(get_engine())


def mark_stale_runs_interrupted() -> int:
    """启动恢复：把上一进程遗留的 running 状态 agent 运行标记为 interrupted

    每一步的工具调用与观察都已落库/落盘，可通过 resume 端点从断点续跑。
    """
    from datetime import datetime
    from .models import AgentRun

    n = 0
    with make_session() as db:
        stale = db.query(AgentRun).filter(AgentRun.status == "running").all()
        for run in stale:
            run.status = "interrupted"
            run.summary = "进程重启导致中断，可调用 resume 从断点恢复"
            run.finished_at = datetime.now()
            n += 1
        db.commit()
    return n


def recover_stuck_sessions() -> int:
    """启动恢复（M1 补充）：把上次进程遗留的"任务中"阶段会话标记为 error

    旧分阶段路径（extract/suggest/calculate）的后台线程不可恢复，
    与其让前端永远停在 extracting 状态，不如显式置错并提示重试。
    agent 主线运行由 mark_stale_runs_interrupted 单独处理（可断点续跑）。
    """
    from .models import SessionRecord

    stuck_stages = ("extracting", "suggesting", "calculating", "agent_running")
    n = 0
    with make_session() as db:
        rows = db.query(SessionRecord).filter(
            SessionRecord.stage.in_(stuck_stages)).all()
        for row in rows:
            row.stage = "error"
            data = dict(row.data or {})
            data["calc_error"] = "服务重启导致任务中断，请重新发起该步骤"
            row.data = data
            n += 1
        db.commit()
    return n


def db_ping() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
