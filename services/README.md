# services/ — 边车服务（占位）

> 状态：**占位**（P2/P3 阶段迁入）
> 上级：[REFACTOR.md](../REFACTOR.md)

集中放置非 Python 业务的独立进程（Go-Gin 反向代理与 OIDC 授权服务器）。

## 迁移映射

| 目标位置 | 来源 | 说明 | 迁移时机 |
|---------|-----|------|---------|
| `services/proxy/` | 根目录 `proxy/` | Go-Gin 反向代理 + Casdoor Cookie 注入 | P3 |
| `services/oauth/` | 根目录 `oauth-server/` | 轻量级 OAuth 2.0 / OIDC 服务器 | P3 |

## 迁移原则

1. **Go 侧零改动**：仅目录位置变化，不改代码；构建脚本 `build.sh` / `build-linux.ps1` 需更新相对路径。
2. **端口保持不变**：proxy 8080、oauth 服务端口保持现有配置。
3. **与新 FastAPI 的联动**：P1 期 Go proxy 需要新增路由把 `/api/*` 转发到 FastAPI（8000），`/*` 依然转发到 Streamlit（8501），P4 下线 Streamlit 后 `/*` 转发到 Next.js。

## 部署编排（P3 引入）

计划在项目根提供 `docker-compose.yml`：

```yaml
services:
  web:        # Next.js
    build: ./apps/web
    ports: ["3000:3000"]
  api:        # FastAPI
    build: ./apps/api
    ports: ["8000:8000"]
  proxy:      # Go-Gin
    build: ./services/proxy
    ports: ["8080:8080"]
    depends_on: [web, api, oauth]
  oauth:      # OIDC
    build: ./services/oauth
    ports: ["9000:9000"]
```
