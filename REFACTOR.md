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
│  前端  Next.js 16 (App Router + Turbopack) + TypeScript │
│        Tailwind v4 + React 19                           │
├─────────────────────────────────────────────────────────┤
│  BFF   FastAPI + Pydantic v2 + Uvicorn                  │
│        SSE 推送 AI 流式日志 + DirectLLMClient           │
├─────────────────────────────────────────────────────────┤
│  业务  core/ + config/ + .claude/skills/  （原样复用）  │
├─────────────────────────────────────────────────────────┤
│  网关  proxy/ + oauth-server/（Go-Gin，保留）           │
└─────────────────────────────────────────────────────────┘
```

## 目标目录结构

```
conditioner_saving/
├── apps/
│   ├── web/                    # Next.js 16 前端（空调 + 空压）
│   └── api/                    # FastAPI 后端（空调 + 空压）
├── core/                       # 业务核心（保持原位，FastAPI 直接 import）
├── config/                     # 配置（保持原位）
├── .claude/skills/             # AI 技能脚本（保持原位）
├── proxy/                      # Go-Gin 反向代理（保持原位）
├── oauth-server/               # Go-Gin OAuth 服务器（保持原位）
├── simulation/                 # 保留原位（不在本次重构范围）
├── simulation_ui.py            # 保留原位（Streamlit 承载）
├── app.py                      # Streamlit（仅仿真入口）
├── tests/                      # 保留
└── docs/                       # 保留
```

## 分阶段推进

| 阶段 | 目标 | 状态 | Commit |
|------|------|------|--------|
| **P0. 骨架 & 占位** | 建立 apps/packages/services 目录与 README | ✅ 完成 | `8564a8d` |
| **P1. FastAPI 中间层** | 用 FastAPI 包装 core，暴露 /upload /extract /calculate /result 等端点 | ✅ 完成 | `8564a8d` ~ `98f3aa0` |
| **P2. Next.js MVP** | Next.js 16 + Tailwind v4 前端，迁移空调+空压上传→提取→建议→计算→结果五步流程 | ✅ 完成 | `d73e7da` |
| **P3. 空压迁移 + LLM** | subprocess 文本提取 + DirectLLMClient 结构化分析（替代 Agent SDK）+ AirCompressorCalculator | ✅ 完成 | `1f67a90` |
| **P4. 下线 Streamlit 入口** | `app.py` 空调/空压按钮禁用 + 迁移公告，仅保留仿真入口 | ✅ 完成 | `5d1b8d9` |

## 关键约束

1. **业务层零改动**：core/SkillCaller、DataFiller、ExcelCalculator、SessionManager、AirCompressorCalculator 保持接口不变，仅由 FastAPI Route 调用替代 Streamlit 直接调用。
2. **并行运行**：P1 完成前 Streamlit 继续可用，避免推倒重来。
3. **认证平滑迁移**：Go proxy 已将 Casdoor 用户信息注入 Cookie，FastAPI 从 Cookie/Bearer 读取即可，OIDC 层零改动。
4. **AI 流式响应**：`SkillCaller.stream_callback` 桥接到 FastAPI `EventSourceResponse`，前端用 `EventSource` 消费。
5. **会话隔离**：`SessionManager` 保留，API 层用用户 ID + session_id 定位 `tmp/session_xxx/` 目录。
6. **仿真模块隔离**：`simulation/` 与 `simulation_ui.py` 不参与本次重构，Streamlit `app.py` 中的仿真入口保留；P4 结束后 Streamlit 只承载仿真页面。
7. **LLM 直连通道**：Claude Agent SDK 与自定义 `ANTHROPIC_BASE_URL` 代理存在认证冲突，新增 `core/llm_client.py` 的 `DirectLLMClient`（httpx 直连 Messages API）作为统一 LLM 调用通道。

## 已完成交付物

### FastAPI 后端（`apps/api/`）

| 端点 | 用途 | 状态 |
|------|------|------|
| `GET /api/health` | 健康检查 | ✅ |
| `POST /api/upload` | 上传调研表，创建 session（支持 air_conditioner / air_compressor） | ✅ |
| `GET /api/sessions` | 列出全部 session | ✅ |
| `GET /api/session/{id}` | 查询单个 session（含 ai_logs、extracted_data） | ✅ |
| `POST /api/extract/{id}` | 后台提取（空调 subprocess / 空压 subprocess+LLM） | ✅ |
| `GET /api/extract/{id}/stream` | SSE 推 AI 流式日志 | ✅ |
| `POST /api/suggest/{id}` | 生成填充建议（规则脚本 + 可选 LLM 增强） | ✅ |
| `GET /api/suggest/{id}` | 获取填充建议结果 | ✅ |
| `POST /api/calculate/{id}` | 后台计算（空调 ExcelCalculator / 空压 AirCompressorCalculator） | ✅ |
| `GET /api/result/{id}` | 返回最终结果 JSON | ✅ |
| `POST /api/llm/chat` | LLM 直连演示端点 | ✅ |

### Next.js 前端（`apps/web/`）

- **技术栈**：Next.js 16 (App Router + Turbopack) + React 19 + TypeScript + Tailwind v4
- **Workflow 组件**：状态机 `idle → uploading → uploaded → extracting → extracted → suggesting → suggested → calculating → done`
- **5 步工作流**：上传 → 提取 → 填充建议（LLM 增强） → 计算 → 结果
- **SSE 日志面板**：黑底绿字、自动滚动、heartbeat 友好
- **模块切换**：中央空调 / 空压机 下拉选择

### 启动命令

```bash
# FastAPI 后端
.venv\Scripts\python.exe -m uvicorn apps.api.main:app --reload --port 8000

# Next.js 前端
cd apps/web && npm run dev    # http://localhost:3000

# Streamlit（仅仿真）
streamlit run app.py --server.port 8501
```

## 后续规划

- **UI 打磨**：引入 shadcn/ui 组件库 + 暗色主题 + 调研表数据预览表格
- **docker-compose**：一键编排 Next.js + FastAPI + Go proxy + OAuth 四个进程
- **认证集成**：FastAPI 从 Cookie/Bearer 读取 Casdoor 用户信息
- **冷站仿真迁移**（可选）：将 simulation 迁入 Next.js，独立页面
