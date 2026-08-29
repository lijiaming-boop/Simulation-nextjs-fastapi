"""通知集成（M3）：agent 关键事件推送 webhook

支持三种格式：generic（自定义 JSON）、wecom（企业微信机器人）、dingtalk（钉钉机器人）。
未配置 NOTIFY_WEBHOOK_URL 时为无操作。发送失败仅记录，不阻断业务流程。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

STATUS_TITLES = {
    "completed": "✅ 测算完成",
    "needs_input": "⚠️ 测算需补充数据",
    "pending_approval": "🕓 测算待审批",
    "error": "❌ 测算失败",
}


def notify(event: str, title: str, detail: Optional[Dict[str, Any]] = None) -> bool:
    """推送一条通知；返回是否成功（失败静默，不阻断业务）"""
    url = os.getenv("NOTIFY_WEBHOOK_URL", "").strip()
    if not url:
        return False
    fmt = os.getenv("NOTIFY_FORMAT", "generic").strip().lower()
    detail = detail or {}

    if fmt == "wecom":
        payload = {"msgtype": "text", "text": {"content": f"{title}\n{detail.get('summary', '')}"}}
    elif fmt == "dingtalk":
        payload = {"msgtype": "text", "text": {"content": f"{title} {detail.get('summary', '')}"}}
    else:
        payload = {"event": event, "title": title, "detail": detail}

    try:
        resp = httpx.post(url, json=payload, timeout=10)
        return resp.status_code < 400
    except Exception:
        return False


def notify_run_finished(session_id: str, final: dict) -> bool:
    """agent 运行结束后的通知入口（批量/交互共用）"""
    status = final.get("status", "")
    title = STATUS_TITLES.get(status, f"ℹ️ 测算状态: {status}")
    return notify(
        event="agent.run.finished",
        title=f"{title}（会话 {session_id[:24]}…）",
        detail={"session_id": session_id, "status": status,
                "summary": (final.get("summary") or "")[:200]},
    )
