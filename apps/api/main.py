"""apps.api — FastAPI 后端（重构 P1）

包装 core 模块，为 Next.js 前端提供 HTTP 接口。
启动：uvicorn apps.api.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import router as api_router
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

    return application


app = create_app()
