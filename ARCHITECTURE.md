# 架构设计：Agent 与传统代码的边界

本文回答这个项目最核心的设计问题：**哪些环节交给 LLM，哪些环节必须是确定性代码，为什么。**
以及配套的硬约束机制、成本模型、可观测性与评测方法。

## 1. 分层总览

```
┌─────────────────────────────────────────────────────────────┐
│ 接入层  FastAPI /agent/run (SSE) │ 分阶段端点(兼容) │ 前端     │
├─────────────────────────────────────────────────────────────┤
│ 编排层  AgentOrchestrator：ReAct 循环 + 白名单硬约束          │
│         Brain: LLMBrain（JSON 强约束决策）│ RuleBrain（零成本）│
├─────────────────────────────────────────────────────────────┤
│ 工具层  ToolRegistry：extract/suggest/apply/calculate + 控制 │
├─────────────────────────────────────────────────────────────┤
│ 引擎层  formulas Excel 公式引擎 │ 规则提取/质检 │ 气象服务     │
├─────────────────────────────────────────────────────────────┤
│ 基础设施  SessionManager（会话隔离）│ trace 落盘 │ Go OIDC 网关│
└─────────────────────────────────────────────────────────────┘
```

## 2. 决策边界：每个环节谁来执行

| 环节 | 执行者 | LLM 参与 | 理由 |
|---|---|---|---|
| 调研表数据提取 | 规则脚本（openpyxl+pandas） | 无 | 单元格行位固定，规则精确且可单测；LLM 反而引入幻觉风险 |
| 数据质量检查 | 规则引擎（范围/逻辑/完整率） | 无 | 判定标准是业务规则，必须 100% 可复现 |
| 填充建议生成 | 规则引擎（插值→季节值→默认值） | 无 | 数学方法，无需语言理解 |
| 填充执行 | `DataFiller`（机械执行） | 无 | 只填 null、保护字段不可改写——安全边界必须由代码保证 |
| 节能率计算 | `formulas` 库跑 Excel 模板公式 | 无 | 精度要求 ≤2%；物理公式（COP、泵相似定律频率^2.5）在模板里由领域专家维护 |
| **下一步调哪个工具** | **Brain（LLM/规则双实现）** | **是** | 流程编排是"理解当前状态做规划"的典型 LLM 场景 |
| **每步面向用户的叙事** | **Brain（LLM）** | **是** | 把结构化观察翻译成销售/解决方案专家能读的中文 |
| **最终结论摘要** | **Brain（LLM）** | **是** | 面向客户的解读：节能率范围怎么用、置信度怎么影响报价 |
| 空压调研表字段提取 | claude-agent-sdk 会话 | 是 | Word/PPT 非结构化文本，必须语言模型 |
| 冷站仿真代码生成 | claude-agent-sdk 会话 | 是 | agent 动态编写 8760h 仿真 Python 代码，ast 自检 + 报错自愈 |
| 报价语义冲突检测 | LLM（detect-conflicts skill） | 是 | "客户要闭环控制但目录是标准件"这类判断需要语义理解 |

**一句话原则：算得准的交给公式，看得懂的交给模型；凡是进入报价的数字，必须来自确定性引擎。**

## 3. 硬约束机制（模型无法绕过）

软决策给自主性，硬约束给可靠性。orchestrator 在每一步用**工具白名单**收窄
Brain 的选择空间，越权选择会被直接拒绝并作为观察结果反馈（见
`agent/orchestrator.py::_allowed_tools`）：

| 约束 | 触发条件 | 强制行为 |
|---|---|---|
| 工具前置依赖 | 未提取就想填充/计算 | 白名单中不出现该工具 |
| 质量门禁（低置信度） | 数据完整率 <50% | 白名单只剩 `request_user_input`，流程以 needs_input 终止 |
| 站房类型拦截 | 提取判定 unsupported（热水泵/蓄冷/中低温机组） | 同上，附识别依据 |
| 不可填充拦截 | 规则引擎返回 `can_proceed=false` | 同上，附缺失字段清单 |
| 填充依赖过重 | 建议填充占比 >50%（RuleBrain 阈值） | 转人工确认（LLM 模式下为可选判断） |
| 白名单越权 | Brain 返回白名单外工具 | 拒绝执行，错误观察进轨迹 |
| 连续失败熔断 | 同一状态连续 3 次工具异常 | 中止运行，error 终态 |
| 步骤预算 | 默认 max_steps=10 | 强制结束，防止原地打转烧 token |

## 4. LLM 成本模型

改造前（v1）：每个阶段经 `SkillCaller` 起一个完整 claude-agent-sdk 会话——
包括纯规则脚本环节，为"执行一条 python 命令"付一整个 agent 会话的钱。

改造后：工具执行零 token，LLM 只出现在决策点：

| 场景 | 决策调用次数 | 说明 |
|---|---|---|
| 顺利完成（如惠州齐全表） | 5 次（4 次选工具 + 1 次 finish 摘要） | 每次 ≤800 输出 token |
| 数据不达标（中断） | 2 次（提取后门禁 + 求助措辞） | 提前终止，成本更低 |
| 评测模式（RuleBrain） | 0 | 结果逐字节可复现 |

token 用量按次记录在 `agent_trace.json` 的 `llm_usage` 中（依赖
`core/llm_client.DirectLLMClient.create_message_with_usage`）。

## 5. 可观测性：agent_trace.json

每次运行落盘完整轨迹（`agent/trace.py`），`GET /api/agent/{id}/trace` 直接返回：

```json
{
  "mode": "agent | deterministic",
  "llm_usage": {"brain_calls": 5, "input_tokens": 9200, "output_tokens": 1150},
  "steps": [
    {"step": 1, "tool": "extract_survey", "args": {"survey_path": "..."},
     "reason": "开始提取调研表数据并做质量检查",
     "ok": true, "duration_ms": 4210,
     "observation": {"completeness": 0.92, "confidence_level": "high", "...": "..."},
     "decision": {"model": "...", "input_tokens": 1840, "output_tokens": 96}}
  ],
  "final": {"status": "completed", "summary": "节能率范围为 8.6% - 13.1% ..."}
}
```

每步含模型给出的决策理由、工具观察结果、耗时与 token——答辩演示时可以
逐帧回放"agent 当时在想什么、看到了什么、做了什么"。

## 6. 评测方法

- **评测集**：6 份标注样例调研表（`00_sample/示例调研表/`），文件名自带预期节能率
  （如 `【齐全】15.2%惠州光弘`）与数据质量等级，构成天然锚点。
- **指标**：流程决策正确率（该算的算完/该拦的拦下）、节能率与锚点偏差（到计算区间
  的距离，≤2pp 达标）、低质量数据中断正确率、地区识别正确率。
- **运行**：`python -m evaluation.run_eval`（确定性模式，零 token，可复现）；
  `--save-baseline` 固化基线，`--compare-baseline` 做回归检查。
- **诚实原则**：未达标用例在报告中给出根因，不藏分。评测的真实战绩：
  它曾定位出"月份表头被误读成能耗"的静默错数 bug 和"深度调研模板变体完整率被
  低估"的门禁误拦，两者均已修复（修复后决策正确率 6/6）；剩余偏差
  （最大 5.42pp）来自行业默认值填充参数与人工口径的差异，属已知限制。

## 7. 已知缺口与路线图

1. **默认填充参数校准**（评测已定位）：深度调研模板变体的泵频率/温差/塔温由
   行业默认值填充，与人工测算口径差异导致该用例偏差 5.42pp → 用历史项目数据
   校准 `INDUSTRY_DEFAULTS`。
2. **齐全样例 2.13pp 边缘超标**：可能对应"推荐值"口径差异，需业务确认系数。
3. **前端 Agent 视图**：`/agent/*` 端点已就绪，Next.js 侧可加轨迹回放组件。
4. **空压/仿真线接入统一编排**：把 claude-agent-sdk 驱动的空压提取与冷站仿真
   注册为 `ToolRegistry` 中的 LLM 型工具，由同一 orchestrator 编排。
5. **多用户会话存储**：`SessionStore` 目前为进程内 dict（POC 级），生产换 Redis。

## 8. 平台底座（M1）

| 能力 | 实现 | 位置 |
|---|---|---|
| 持久化 | SQLAlchemy（SQLite/PostgreSQL 双兼容，`DATABASE_URL` 切换）；sessions / agent_runs / agent_steps / audit_logs 四张表 | `apps/api/models.py`、`apps/api/storage.py` |
| 写透会话 | `get()` 返回 LiveSession dict，键赋值自动落库——业务代码沿用内存写法零改造；嵌套结构变更后调 `save()` | `storage.py::LiveSession` |
| 断点恢复 | 每步经 `on_step` 落库；启动时遗留 running 标记 interrupted；`POST /agent/{id}/run/resume` 从会话目录产物 hydrate 续跑，步号与 token 累计不重置 | `agent/orchestrator.py::hydrate_from_session`、`apps/api/db.py::mark_stale_runs_interrupted` |
| 认证与 ACL | `REQUIRE_AUTH=true` 强制网关身份头；路由级 `acl_guard` 对所有带 session_id 的请求做归属校验，越权 403 + 审计 | `apps/api/deps.py`、`routers.py::acl_guard` |
| 审计 | 上传/下载/运行/恢复写 audit_logs | `deps.py::audit` |
| 部署 | Dockerfile + docker-compose（db/api/web）；CI 含 lint、单测、评测基线门禁 | `docker-compose.yml`、`.github/workflows/ci.yml` |

已知边界：SSE 事件队列与 LiveSession 写缓存为进程内实现，多副本部署需网关按
session_id 粘滞路由；Redis 运行态缓存与发布订阅为 M2 演进项。

## 9. 关键代码索引

| 组件 | 位置 |
|---|---|
| ReAct 循环与白名单 | `agent/orchestrator.py` |
| LLM 决策 + JSON 强约束重试 | `agent/brain.py::LLMBrain` |
| 零成本规则策略 | `agent/brain.py::RuleBrain` |
| 工具注册表与确定性 handler | `agent/tools.py` |
| 轨迹记录 | `agent/trace.py` |
| SSE 端点 | `apps/api/routers.py`（/agent/run、/agent/{id}/stream、/agent/{id}/trace） |
| token 用量统计 | `core/llm_client.py::create_message_with_usage` |
| 评测入口 | `evaluation/run_eval.py` |
