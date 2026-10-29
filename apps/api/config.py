"""应用配置（M1 平台底座）

统一管理部署相关配置，开发环境零配置可跑（SQLite + 免认证），
生产环境通过环境变量切换 Postgres + 强制认证。
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/config.py -> 项目根
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """部署配置（全部可通过环境变量覆盖）"""

    # 数据库：开发默认 SQLite（落盘持久化），生产用
    #   postgresql+psycopg://user:pass@db:5432/hvac
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'app.db'}"

    # 强制认证：True 时所有请求必须携带网关注入的身份头（X-User-Info），
    # 且会话按归属校验访问权限。开发/测试默认 False 保持零配置可跑。
    require_auth: bool = False

    # 网关注入身份的 header 名（见 proxy/main.go）
    auth_header: str = "X-User-Info"

    # 特权角色（可访问任意会话，逗号分隔）
    privileged_roles: str = "admin,sr"

    # 环境标识
    environment: str = "development"

    # Redis（可选）：配置后 SSE 事件经 Pub/Sub 投递，多副本无需粘滞路由；
    # 留空则使用进程内队列（单副本，零依赖）
    redis_url: str = ""

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    @property
    def privileged_role_set(self) -> set:
        return {r.strip() for r in self.privileged_roles.split(",") if r.strip()}


settings = Settings()
