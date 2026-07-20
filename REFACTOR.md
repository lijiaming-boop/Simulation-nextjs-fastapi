# 重构路线图（Streamlit → Next.js + FastAPI）

> 分支：`refactor/nextjs-fastapi`
> 基线：`master` @ 1013020
> 目标：将 Streamlit 单体拆分为「前端可完全设计定制的 Next.js + Python 业务后端 FastAPI」，
> 保留现有 core/config/skills 业务能力，保留 Go-Gin proxy/OAuth 网关不变。

## 重构范围

**覆盖**：空调节能测算 + 空压机节能测算 两个业务模块。

**不覆盖**（保持原位不迁移）：
- 🚫 冷站全年能效仿真：`simulation/` 包 + `simulation_ui.py`（继续由 Streamlit 承载）
- 后续如需迁移，另立独立分支处理

## 目标架构

```
┌─────────────────────────────────────────────────────────┐
│  前端  Next.js 14 (App Router) + TypeScript             │
│        Tailwind CSS + shadcn/ui + Zustand               │
├─────────────────────────────────────────────────────────┤
│  BFF   FastAPI + Pydantic v2 + Uvicorn                  │
│        SSE 推送 AI 流式日志                              │
├─────────────────────────────────────────────────────────┤
│  业务  packages/core + packages/config + packages/skills │
│        （从根目录 core/、config/、.claude/skills 平移）  │
├─────────────────────────────────────────────────────────┤
│  网关  services/proxy + services/oauth（Go-Gin，保留）   │
└─────────────────────────────────────────────────────────┘
```

## 目标目录结构

```
conditioner_saving/
├── apps/
│   ├── web/                    # Next.js 前端（新建，仅空调 + 空压）
│   └── api/                    # FastAPI 后端（新建，仅空调 + 空压）
├── packages/
│   ├── core/                   # ← 现有根目录 core/
│   ├── config/                 # ← 现有根目录 config/
│   └── skills/                 # ← 现有 .claude/skills/
├── services/
│   ├── proxy/                  # ← 现有 proxy/
│   └── oauth/                  # ← 现有 oauth-server/
├── simulation/                 # 保留原位（不在本次重构范围）
├── simulation_ui.py            # 保留原位（Streamlit 承载）
├── tests/                      # 保留
├── docs/                       # 保留
└── docker-compose.yml          # 一键编排（P3 引入）
```

## 分阶段推进

| 阶段 | 目标 | 状态 |
|------|------|------|
| **P0. 骨架 & 占位** | 建立 apps/packages/services 目录与 README | ✅ 完成（本次提交） |
| **P1. FastAPI 中间层** | 用 FastAPI 包装 core，暴露 /upload /extract /calculate 等端点；Streamlit 并行运行 | ⏳ 未开始 |
| **P2. Next.js MVP（空调）** | 迁移空调模块 UI：上传→提取→结果三步流程 | ⏳ 未开始 |
| **P3. 空压迁移 + 编排** | 迁移空压机模块 UI；引入 docker-compose | ⏳ 未开始 |
| **P4. 下线空调/空压的 Streamlit 入口** | `app.py` 只保留仿真入口，或改为独立 `simulation_app.py`；`.streamlit/` 保留 | ⏳ 未开始 |

## 关键约束

1. **业务层零改动**：core/SkillCaller、DataFiller、ExcelCalculator、SessionManager、AirCompressorCalculator 保持接口不变，仅由 FastAPI Route 调用替代 Streamlit 直接调用。
2. **并行运行**：P1 完成前 Streamlit 继续可用，避免推倒重来。
3. **认证平滑迁移**：Go proxy 已将 Casdoor 用户信息注入 Cookie，FastAPI 从 Cookie/Bearer 读取即可，OIDC 层零改动。
4. **AI 流式响应**：`SkillCaller.stream_callback` 桥接到 FastAPI `EventSourceResponse`，前端用 `EventSource` 消费。
5. **会话隔离**：`SessionManager` 保留，API 层用用户 ID + session_id 定位 `tmp/session_xxx/` 目录。
6. **仿真模块隔离**：`simulation/` 与 `simulation_ui.py` 不参与本次重构，Streamlit `app.py` 中的仿真入口保留；P4 结束后 Streamlit 只承载仿真页面。

## 下一步（P1 待办摘要）

- [x] 在 `apps/api/` 建 FastAPI skeleton，Pydantic v2 + Uvicorn
- [x] 复用 packages/core（用相对 import 或 pyproject.toml workspace）
- [x] 端点 1：`POST /api/upload` — 保存文件、创建 session、返回 session_id
- [x] 端点 2：`POST /api/extract/{session_id}` — 触发 extract-and-check-data
- [x] 端点 3：`GET  /api/extract/{session_id}/stream` — SSE 推 AI 日志
- [ ] 端点 4：`POST /api/calculate/{session_id}` — 触发 Excel 公式计算
- [ ] 端点 5：`GET  /api/result/{session_id}` — 返回最终结果 JSON
- [x] 从 proxy Cookie 中读用户信息的鉴权 dependency
