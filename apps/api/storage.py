"""持久化会话存储（M1 平台底座）

PersistentSessionStore 与原内存 SessionStore 接口完全兼容（dict 协议），
但所有状态落库：SQLite（开发）/ PostgreSQL（生产）由 DATABASE_URL 决定。

写透语义：get() 返回的 LiveSession dict 在键赋值时自动持久化，
业务代码沿用 `s["result"] = ...` 的写法即可落库，无需改造；
嵌套结构（如 sim_cop_data[x]=y）变更后需显式调用 s.save()。

新增企业级能力：
- agent_runs / agent_steps 落库 → 运行可观测、进程重启后可断点恢复
- audit_logs → 谁在何时对哪个会话做了什么

已知边界（M1）：单进程写缓存（LiveSession），多 worker 部署时同会话
应粘滞到同一实例（网关按 session 路由）；Redis 运行态缓存为 M2 演进项。
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.session_manager import SessionManager

from .db import init_db, make_session
from .models import AgentAction, AgentRun, AgentStep, AuditLog, BatchJob, LLMCall, SessionRecord

# 仅存在于进程内的运行时键：不落库、不参与 JSON 序列化
RUNTIME_KEYS = {"ai_queue"}


def _default_session_data(module_type: str, sim_mode: str = "new_station") -> dict:
    """与原内存 SessionStore 相同的默认字段（接口兼容）"""
    data: Dict[str, Any] = {
        "ai_logs": [],
        "extracted_data": None,
        "quality_report": None,
        "filling_suggestions": None,
        "result": None,
        "sim_stage": "topology",
        "sim_mode": sim_mode,
        "sim_topology": None,
        "sim_cop_data": {},
        "sim_operating_conditions": None,
        "sim_result": None,
        "sim_project_name": "",
        "sim_baseline_power_kwh": None,
        "sim_schemes": [],
    }
    if module_type == "quote":
        data.update({
            "quote_survey_path": None,
            "quote_project_data": None,
            "quote_section9_result": None,
            "quote_bottom_sheet": None,
            "quote_edited_items": {},
            "quote_inquiry_prices": {},
            "quote_data_warnings": [],
            "quote_generated_files": [],
            "quote_parse_mode": None,
        })
    return data


class LiveSession(dict):
    """写透式会话字典：键赋值自动持久化（运行时键除外）"""

    def __init__(self, store: "PersistentSessionStore", session_id: str, initial: dict):
        super().__init__(initial)
        self._store = store
        self._sid = session_id

    def _persist(self, key: str) -> None:
        if key in RUNTIME_KEYS:
            return
        try:
            value = self[key]
            if isinstance(value, dict):
                value = dict(value)
            self._store._persist_field(self._sid, key, value)
        except Exception:
            # 持久化失败不阻断内存流程（与原内存实现的失败语义一致）
            pass

    def __setitem__(self, key, value) -> None:
        super().__setitem__(key, value)
        self._persist(key)

    def __delitem__(self, key) -> None:
        super().__delitem__(key)
        self._persist(key)

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        for k in dict(*args, **kwargs):
            self._persist(k)

    def setdefault(self, key, default=None):
        existed = key in self
        v = super().setdefault(key, default)
        if not existed:
            self._persist(key)
        return v

    def save(self) -> None:
        """显式全量落盘：嵌套结构（dict/list 内部变更）变更后调用"""
        for k in list(self.keys()):
            self._persist(k)


class PersistentSessionStore:
    """落库的会话存储，替代进程内 dict"""

    def __init__(self, manager: Optional[SessionManager] = None) -> None:
        self._manager = manager or SessionManager()
        self._main_loop = None  # 兼容 services.py 的线程→事件循环桥接
        self._write_lock = threading.Lock()
        self._live: Dict[str, LiveSession] = {}
        init_db()  # 幂等建表，保证存储可用

    # ==================== 兼容接口 ====================

    @property
    def manager(self) -> SessionManager:
        return self._manager

    def _row_to_live(self, row: SessionRecord) -> LiveSession:
        d: Dict[str, Any] = {
            "session_id": row.session_id,
            "module_type": row.module_type,
            "original_filename": row.original_filename,
            "user_id": row.user_id,
            "stage": row.stage,
            "session_dir": Path(row.session_dir),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        d.update(row.data or {})
        return LiveSession(self, row.session_id, d)

    def _create_row(self, session_dir: Path, module_type: str,
                    original_filename: Optional[str], user_id: Optional[str],
                    stage: str, sim_mode: str = "new_station") -> str:
        session_id = session_dir.name
        live = LiveSession(self, session_id, {
            "session_id": session_id,
            "module_type": module_type,
            "original_filename": original_filename,
            "user_id": user_id,
            "stage": stage,
            "session_dir": session_dir,
            "created_at": datetime.now().isoformat(),
            **_default_session_data(module_type, sim_mode),
        })
        with self._write_lock, make_session() as db:
            db.add(SessionRecord(
                session_id=session_id,
                module_type=module_type,
                original_filename=original_filename,
                user_id=user_id,
                stage=stage,
                session_dir=str(session_dir),
                data={k: v for k, v in live.items() if k not in RUNTIME_KEYS
                      and k not in ("session_id", "session_dir", "created_at")
                      and not isinstance(v, Path)},
            ))
            db.commit()
        self._live[session_id] = live
        return session_id

    def register(self, session_dir: Path, original_filename: str,
                 user_id: Optional[str], module_type: str) -> str:
        return self._create_row(session_dir, module_type, original_filename,
                                user_id, "upload")

    def init_sim_session(self, user_id: Optional[str],
                         sim_mode: str = "new_station") -> str:
        return self._create_row(self._manager.create_session_directory(),
                                "plant_simulation", None, user_id,
                                "simulation", sim_mode)

    def init_quote_session(self, user_id: Optional[str]) -> str:
        return self._create_row(self._manager.create_session_directory(),
                                "quote", None, user_id, "upload")

    def get(self, session_id: str) -> Optional[LiveSession]:
        if session_id in self._live:
            return self._live[session_id]
        with make_session() as db:
            row = db.get(SessionRecord, session_id)
            if row is None:
                return None
            live = self._row_to_live(row)
            self._live[session_id] = live
            return live

    def update_stage(self, session_id: str, stage: str) -> None:
        live = self._live.get(session_id)
        if live is not None:
            live["stage"] = stage  # 写透持久化
            return
        with self._write_lock, make_session() as db:
            row = db.get(SessionRecord, session_id)
            if row is not None:
                row.stage = stage
                db.commit()

    def append_ai_log(self, session_id: str, timestamp: str, message: str) -> None:
        live = self._live.get(session_id)
        if live is not None:
            logs = list(live.get("ai_logs") or [])
            logs.append({"timestamp": timestamp, "message": message})
            live["ai_logs"] = logs  # 写透持久化
            return
        with self._write_lock, make_session() as db:
            row = db.get(SessionRecord, session_id)
            if row is None:
                return
            data = dict(row.data or {})
            logs = list(data.get("ai_logs") or [])
            logs.append({"timestamp": timestamp, "message": message})
            data["ai_logs"] = logs
            row.data = data
            db.commit()

    def _persist_field(self, session_id: str, key: str, value: Any) -> None:
        """把单个键写入 DB 的 data JSON（写透的底层）"""
        with self._write_lock, make_session() as db:
            row = db.get(SessionRecord, session_id)
            if row is None:
                return
            data = dict(row.data or {})
            data[key] = value
            row.data = data
            if key == "stage":
                row.stage = value if isinstance(value, str) else row.stage
            db.commit()

    def list_sessions(self) -> List[Dict[str, Any]]:
        with make_session() as db:
            rows = db.query(SessionRecord).order_by(
                SessionRecord.created_at.desc()).all()
            return [{
                "session_id": r.session_id,
                "module_type": r.module_type,
                "original_filename": r.original_filename,
                "user_id": r.user_id,
                "stage": r.stage,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in rows]

    # ==================== Agent 运行持久化 ====================

    def create_run(self, session_id: str, mode: str) -> str:
        run_id = uuid.uuid4().hex[:16]
        with self._write_lock, make_session() as db:
            db.add(AgentRun(
                run_id=run_id, session_id=session_id,
                mode=mode, status="running",
                llm_usage={"brain_calls": 0, "input_tokens": 0, "output_tokens": 0},
            ))
            db.commit()
        return run_id

    def update_run(self, run_id: str, **fields: Any) -> None:
        allowed = {"status", "step_count", "llm_usage", "summary", "finished_at", "mode"}
        with self._write_lock, make_session() as db:
            row = db.get(AgentRun, run_id)
            if row is None:
                return
            for k, v in fields.items():
                if k in allowed:
                    setattr(row, k, v)
            db.commit()

    def get_latest_run(self, session_id: str,
                       statuses: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        with make_session() as db:
            q = db.query(AgentRun).filter(AgentRun.session_id == session_id)
            if statuses:
                q = q.filter(AgentRun.status.in_(statuses))
            row = q.order_by(AgentRun.started_at.desc()).first()
            if row is None:
                return None
            return {
                "run_id": row.run_id, "session_id": row.session_id,
                "mode": row.mode, "status": row.status,
                "step_count": row.step_count, "llm_usage": row.llm_usage,
                "summary": row.summary,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }

    def add_step(self, run_id: str, step: Dict[str, Any]) -> None:
        with self._write_lock, make_session() as db:
            db.add(AgentStep(
                run_id=run_id,
                step_no=step.get("step"),
                tool=step.get("tool", ""),
                args=step.get("args") or {},
                reason=step.get("reason"),
                ok=step.get("ok"),
                observation=step.get("observation"),
                duration_ms=step.get("duration_ms"),
                decision=step.get("decision"),
            ))
            run = db.get(AgentRun, run_id)
            if run is not None:
                run.step_count = (run.step_count or 0) + 1
                usage = step.get("decision") or {}
                if usage.get("input_tokens") is not None:
                    llm = dict(run.llm_usage or {})
                    llm["brain_calls"] = llm.get("brain_calls", 0) + 1
                    llm["input_tokens"] = llm.get("input_tokens", 0) + (usage.get("input_tokens") or 0)
                    llm["output_tokens"] = llm.get("output_tokens", 0) + (usage.get("output_tokens") or 0)
                    run.llm_usage = llm
            db.commit()

    def get_run_steps(self, run_id: str) -> List[Dict[str, Any]]:
        with make_session() as db:
            rows = db.query(AgentStep).filter(
                AgentStep.run_id == run_id).order_by(AgentStep.step_no).all()
            return [{
                "step": r.step_no, "tool": r.tool, "args": r.args,
                "reason": r.reason, "ok": r.ok, "observation": r.observation,
                "duration_ms": r.duration_ms, "decision": r.decision,
            } for r in rows]

    def trace_from_db(self, session_id: str) -> Optional[Dict[str, Any]]:
        """从库中重建完整轨迹（/agent/trace 端点的数据源）"""
        run = self.get_latest_run(session_id)
        if run is None:
            return None
        return {
            "run_id": run["run_id"],
            "mode": run["mode"],
            "status": run["status"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "llm_usage": run["llm_usage"],
            "steps": self.get_run_steps(run["run_id"]),
            "final": {"status": run["status"], "summary": run["summary"]},
        }

    # ==================== 审计 ====================

    def audit(self, user_id: Optional[str], action: str,
              session_id: Optional[str] = None, detail: Optional[dict] = None) -> None:
        with self._write_lock, make_session() as db:
            db.add(AuditLog(
                user_id=user_id, action=action,
                session_id=session_id, detail=detail or {},
            ))
            db.commit()

    # ==================== LLM 网关计量（M2） ====================

    def record_llm_call(self, user_id: Optional[str], purpose: str, model: str,
                        input_tokens: int, output_tokens: int,
                        duration_ms: int, ok: bool = True) -> None:
        with self._write_lock, make_session() as db:
            db.add(LLMCall(
                user_id=user_id, purpose=purpose, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                duration_ms=duration_ms, ok=ok,
            ))
            db.commit()

    def llm_tokens_used_today(self, user_id: Optional[str]) -> int:
        """某用户当日（自然日）消耗的 output token 总量"""
        from sqlalchemy import func
        today = datetime.now().date()
        with make_session() as db:
            total = db.query(func.coalesce(func.sum(LLMCall.output_tokens), 0)).filter(
                LLMCall.user_id == user_id,
                LLMCall.ok.is_(True),
                func.date(LLMCall.created_at) == today.isoformat(),
            ).scalar()
            return int(total or 0)

    def llm_usage_summary(self, user_id: Optional[str] = None,
                          days: int = 30) -> Dict[str, Any]:
        """近 N 天用量汇总（按用途分组），供成本报表"""
        from sqlalchemy import func
        since = datetime.now().timestamp() - days * 86400
        since_dt = datetime.fromtimestamp(since)
        with make_session() as db:
            q = db.query(
                LLMCall.purpose,
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.input_tokens), 0),
                func.coalesce(func.sum(LLMCall.output_tokens), 0),
            ).filter(LLMCall.created_at >= since_dt, LLMCall.ok.is_(True))
            if user_id:
                q = q.filter(LLMCall.user_id == user_id)
            rows = q.group_by(LLMCall.purpose).all()
        return {
            "window_days": days,
            "by_purpose": [
                {"purpose": p, "calls": c, "input_tokens": i, "output_tokens": o}
                for p, c, i, o in rows
            ],
        }

    # ==================== Human-in-the-loop 待办（M2） ====================

    def create_action(self, run_id: str, session_id: str, action_type: str,
                      reason: str = "", detail: Optional[dict] = None,
                      user_id: Optional[str] = None) -> int:
        with self._write_lock, make_session() as db:
            action = AgentAction(
                run_id=run_id, session_id=session_id, user_id=user_id,
                action_type=action_type, status="pending",
                reason=reason, detail=detail or {},
            )
            db.add(action)
            db.commit()
            return action.id

    def list_pending_actions(self, user_id: Optional[str] = None,
                             include_all: bool = False) -> List[Dict[str, Any]]:
        with make_session() as db:
            q = db.query(AgentAction).filter(AgentAction.status == "pending")
            if not include_all and user_id is not None:
                q = q.filter(AgentAction.user_id == user_id)
            rows = q.order_by(AgentAction.created_at.desc()).all()
            return [{
                "id": r.id, "run_id": r.run_id, "session_id": r.session_id,
                "user_id": r.user_id, "action_type": r.action_type,
                "status": r.status, "reason": r.reason, "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in rows]

    def get_action(self, action_id: int) -> Optional[Dict[str, Any]]:
        with make_session() as db:
            r = db.get(AgentAction, action_id)
            if r is None:
                return None
            return {
                "id": r.id, "run_id": r.run_id, "session_id": r.session_id,
                "user_id": r.user_id, "action_type": r.action_type,
                "status": r.status, "reason": r.reason, "detail": r.detail,
            }

    def resolve_action(self, action_id: int, status: str = "resolved") -> None:
        with self._write_lock, make_session() as db:
            r = db.get(AgentAction, action_id)
            if r is not None:
                r.status = status
                r.resolved_at = datetime.now()
                db.commit()

    # ==================== 批量测算（M3） ====================

    def create_batch(self, user_id: Optional[str], mode: str, total: int) -> str:
        batch_id = uuid.uuid4().hex[:12]
        with self._write_lock, make_session() as db:
            db.add(BatchJob(
                batch_id=batch_id, user_id=user_id, mode=mode,
                status="pending", total=total,
            ))
            db.commit()
        return batch_id

    def update_batch(self, batch_id: str, **fields: Any) -> None:
        allowed = {"status", "completed", "failed", "detail", "finished_at"}
        with self._write_lock, make_session() as db:
            row = db.get(BatchJob, batch_id)
            if row is None:
                return
            for k, v in fields.items():
                if k in allowed:
                    setattr(row, k, v)
            db.commit()

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        with make_session() as db:
            r = db.get(BatchJob, batch_id)
            if r is None:
                return None
            return {
                "batch_id": r.batch_id, "user_id": r.user_id, "mode": r.mode,
                "status": r.status, "total": r.total,
                "completed": r.completed, "failed": r.failed,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }

    # ==================== 历史测算库（M3） ====================

    def list_completed_results(self, module_type: str = "air_conditioner",
                               limit: int = 50) -> List[Dict[str, Any]]:
        """已完成测算的历史记录（含地区/站型/节能率摘要）"""
        with make_session() as db:
            rows = db.query(SessionRecord).filter(
                SessionRecord.module_type == module_type,
                SessionRecord.stage == "result",
            ).order_by(SessionRecord.created_at.desc()).limit(limit * 3).all()
        out = []
        for r in rows:
            data = r.data or {}
            result = data.get("result") or {}
            if not result:
                continue
            extracted = data.get("extracted_data") or {}
            out.append({
                "session_id": r.session_id,
                "original_filename": r.original_filename,
                "user_id": r.user_id,
                "region": extracted.get("project_region"),
                "station_type": extracted.get("station_type"),
                "rate_min": result.get("energy_saving_rate_min"),
                "rate_max": result.get("energy_saving_rate_max"),
                "rate_range": result.get("energy_saving_rate_range"),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
            if len(out) >= limit:
                break
        return out
