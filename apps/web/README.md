# apps/web — Next.js 前端（占位）

> 状态：**占位**（P1 阶段引入）
> 上级：[REFACTOR.md](../../REFACTOR.md)

## 计划技术栈

- Next.js 14 (App Router) + TypeScript
- Tailwind CSS + shadcn/ui + Radix UI
- Zustand（状态）+ TanStack Query（数据）
- Recharts / ECharts（图表）
- Framer Motion（微交互）

> 仿真模块（simulation/8760h 曲线）不在本前端范围，仍由 Streamlit 承载。

## 计划路由

```
/                    落地页
/upload              上传调研表（空调 / 空压 两个入口）
/session/[id]/extract    提取进度 + AI 流式日志
/session/[id]/review     数据校对与补填
/session/[id]/result     测算结果与图表
```

## 与后端交互

- API base：`http://localhost:8000/api`（生产环境经 Go proxy 反代）
- 认证：Cookie `Authorization: Bearer <jwt>`（复用现有 Casdoor OIDC）
- AI 流式：`EventSource('/api/extract/{sid}/stream')`

## 开发命令（占位，P1 时补充）

```bash
pnpm install
pnpm dev
```
