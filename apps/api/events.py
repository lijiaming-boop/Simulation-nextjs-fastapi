"""事件总线（多副本演进项）

agent 运行/后台任务的事件如何到达 SSE 订阅者，抽象为 EventBroker：

- InProcessEventBroker（默认）：进程内 asyncio.Queue + 主事件循环桥接，
  单副本部署零依赖，行为与 M1 之前完全一致。
- RedisEventBroker：REDIS_URL 配置后启用，事件写入 Redis List
  （LPUSH + BRPOP 阻塞消费 + EXPIRE 兜底）——与进程内队列语义对齐
  （缓冲、FIFO、可排空），多副本部署时任意副本产生的事件，
  订阅该会话 SSE 的副本都能消费，免去网关按 session 粘滞路由的强依赖。
  注意：Pub/Sub 不缓冲，迟到订阅会丢事件，故不用。

选择规则：配置了 REDIS_URL 且连接成功 → Redis；否则回退进程内并告警。
发布端（后台线程）调用 publish_event()；订阅端（SSE）用 stream_events()。
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, AsyncIterator, Dict, Optional

from .config import settings

# 进程内队列注册表：session_id → asyncio.Queue
_queues: Dict[str, asyncio.Queue] = {}
_main_loop: Optional[asyncio.AbstractEventLoop] = None
_main_loop_lock = threading.Lock()

_redis: Optional[Any] = None
_redis_failed = False


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """由首个 async 请求注入主事件循环（进程内模式的线程桥接依赖）"""
    global _main_loop
    with _main_loop_lock:
        _main_loop = loop


def _get_redis():
    """惰性连接 Redis（失败仅告警一次，之后回退进程内）"""
    global _redis, _redis_failed
    if _redis is not None or _redis_failed:
        return _redis
    url = getattr(settings, "redis_url", "") or ""
    if not url:
        _redis_failed = True
        return None
    try:
        import redis as redis_lib
        client = redis_lib.Redis.from_url(url, decode_responses=True,
                                          socket_connect_timeout=2)
        client.ping()
        _redis = client
        print(f"  事件总线     : Redis Pub/Sub（{url}）")
    except Exception as e:
        print(f"  ⚠️ 事件总线   : Redis 不可用（{e}），回退进程内队列——"
              "多副本部署时需要网关按 session_id 粘滞路由")
        _redis_failed = True
    return _redis


def redis_active() -> bool:
    return _get_redis() is not None


# ==================== 发布端（后台线程调用，同步） ====================

def publish_event(session_id: str, event: Dict[str, Any]) -> None:
    """把一条事件投递给该会话的 SSE 订阅者（线程安全）

    Redis 模式：直接 PUBLISH（同步客户端，线程内无需事件循环桥接）。
    进程内模式：call_soon_threadsafe 投递到主循环的 asyncio.Queue。
    """
    client = _get_redis()
    if client is not None:
        try:
            import json as _json
            pipe = client.pipeline()
            pipe.lpush(f"events:{session_id}",
                       _json.dumps(event, ensure_ascii=False))
            pipe.expire(f"events:{session_id}", 3600)
            pipe.execute()
            return
        except Exception:
            pass  # 发布失败降级到进程内（同副本订阅者仍可收到）
    _publish_inprocess(session_id, event)


def _publish_inprocess(session_id: str, event: Dict[str, Any]) -> None:
    q = _queues.get(session_id)
    loop = _main_loop
    if q is None:
        return
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(q.put_nowait, event)
    else:
        # 无运行中的主循环（如同步测试场景）：直接放入
        q.put_nowait(event)


# ==================== 订阅端（SSE async generator） ====================

async def stream_events(session_id: str, idle_timeout: float = 30.0,
                        terminal_types: tuple = ("done", "complete", "error"),
                        ) -> AsyncIterator[Dict[str, Any]]:
    """订阅会话事件直到终止事件；空闲超时发 ping 保持连接"""
    client = _get_redis()
    if client is not None:
        key = f"events:{session_id}"
        while True:
            msg = await asyncio.to_thread(
                client.brpop, [key], timeout=int(idle_timeout))
            if msg is None:
                yield {"__ping__": True}
                continue
            try:
                event = __import__("json").loads(msg[1])
            except Exception:
                continue
            yield event
            if event.get("type") in terminal_types:
                return
        # unreachable

    # 进程内模式
    q = _queues.get(session_id)
    if q is None:
        return
    while True:
        try:
            event = await asyncio.wait_for(q.get(), timeout=idle_timeout)
        except asyncio.TimeoutError:
            yield {"__ping__": True}
            continue
        yield event
        if event.get("type") in terminal_types:
            return


def drain_pending(session_id: str) -> list:
    """排空残留事件（线程已完成但事件尚未被消费）；Redis/进程内双实现"""
    out = []
    client = _get_redis()
    if client is not None:
        key = f"events:{session_id}"
        try:
            import json as _json
            pipe = client.pipeline()
            pipe.lrange(key, 0, -1)
            pipe.delete(key)
            items, _ = pipe.execute()
            for item in reversed(items):  # LPUSH 存储为倒序，恢复时间序
                try:
                    out.append(_json.loads(item))
                except Exception:
                    continue
            return out
        except Exception:
            return out
    q = _queues.get(session_id)
    if q is None:
        return out
    while True:
        try:
            out.append(q.get_nowait())
        except asyncio.QueueEmpty:
            break
    return out


def ensure_queue(session_id: str) -> asyncio.Queue:
    """确保进程内队列存在（Redis 模式下也创建，作为降级通道）"""
    if session_id not in _queues:
        _queues[session_id] = asyncio.Queue()
    return _queues[session_id]


def drop_queue(session_id: str) -> None:
    _queues.pop(session_id, None)
