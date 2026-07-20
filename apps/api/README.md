# apps/api — FastAPI 后端（占位）

> 状态：**占位**（P1 阶段引入）
> 上级：[REFACTOR.md](../../REFACTOR.md)

## 计划技术栈

- FastAPI + Pydantic v2
- Uvicorn（ASGI 服务器）
- sse-starlette（SSE 推流）
- python-multipart（文件上传）

## 计划端点

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/upload` | 接收调研表，创建 SessionManager 目录，返回 `session_id` |
| POST | `/api/extract/{session_id}` | 触发 `extract-and-check-data` skill |
| GET  | `/api/extract/{session_id}/stream` | SSE 推送 Claude Agent 流式日志 |
| POST | `/api/calculate/{session_id}` | 回填 + 公式计算 |
| GET  | `/api/result/{session_id}` | 返回最终结果 JSON |
| GET  | `/api/session/{session_id}` | 查询 session 元数据与阶段 |

## 与业务层的关系

FastAPI 只做 HTTP 适配，业务由 `packages/core` 完成：

```python
from packages.core import SkillCaller, DataFiller, ExcelCalculator, SessionManager
```

> **仿真模块不在本后端范围**：`simulation/` 包的全年能效仿真仍由 Streamlit `simulation_ui.py` 直接调用，不暴露为 HTTP 接口。

## 与 Streamlit 的关系（P1 期）

Streamlit `app.py` **保持可运行**，FastAPI 并行监听 8000 端口。
两者共享 `SessionManager` 的 `tmp/session_xxx/` 目录，实现平滑过渡。

## 开发命令（占位，P1 时补充）

```bash
uvicorn apps.api.main:app --reload --port 8000
```
