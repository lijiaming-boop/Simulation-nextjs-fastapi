"""apps.api — FastAPI 后端（重构 P1）

包装 core 模块，为 Next.js 前端提供 HTTP 接口。
启动：uvicorn apps.api.main:app --reload --port 8000
"""
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import json as _json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .routers import public_router, router as api_router
from .deps import startup_banner


def create_app() -> FastAPI:
    """应用工厂"""
    application = FastAPI(
        title="空调/空压节能测算 API",
        description="封装 core 业务模块的 HTTP 接口，为 Next.js 前端提供 REST + SSE 服务",
        version="0.1.0",
        lifespan=startup_banner,
    )

    # CORS：开发期允许 Next.js dev 端口（3000）
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8080",  # Go proxy
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix="/api")
    application.include_router(public_router, prefix="/api")  # /health 匿名探活

    # 最小可观测（清单5）：request_id + JSON 结构化访问日志
    logger = logging.getLogger("api.access")

    @application.middleware("http")
    async def access_log(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(_json.dumps({
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "user": request.headers.get("x-user-info", "") and "authenticated" or "anonymous",
        }, ensure_ascii=False))
        return response

    return application


app = create_app()
