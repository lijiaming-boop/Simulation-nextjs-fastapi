# HVAC Energy Agent — 暖通节能率智能测算 Agent

> 面向暖通/空调节能售前场景的领域 Agent：上传一份客户调研表，Agent 在硬约束护栏内
> 自主编排"提取 → 质检 → 填充 → 计算 → 结论"的完整测算流程，LLM 只花在决策与叙事上，
> 计算交给确定性物理公式引擎，偏差可回归验证。

[架构设计](./ARCHITECTURE.md) · [回归评测报告](./evaluation/report.md) · [产品需求(PRD)](./02_prd/PRD-空调节能率智能测算工具.md) · [历史版本文档](./docs/legacy/)

## 业务场景

中央空调节能改造的售前环节，销售（AR）与解决方案专家（SR）协作的三个痛点：

- **响应慢**：AR 拿到客户调研表后，SR 人工测算一份方案以天计；
- **数据脏**：调研表由客户手填，缺月、错值、季节性范围值（如"16~20"）比比皆是；
- **不标准**：节能率测算依赖个人经验，报价口径不统一。

本系统把这条链路交给 Agent：**售前人员上传调研表，Agent 自动完成数据提取、质量
评估、缺失数据填充、物理公式测算，并产出面向客户的结论摘要**——数据质量不达标时
自主中断并说明缺什么，而不是硬算一个不可信的结果。

| 业务线 | 现状 | Agent 能力 |
|---|---|---|
| 空调节能率测算（主线） | ✅ 已 Agent 化（`agent/`） | 自主编排 + 质量门禁 + 轨迹可观测 |
| 空压机节能测算 | ✅ 可用 | LLM 非结构化字段提取（Excel/Word/PPT） |
| 冷站全年 8760h 仿真 | ✅ 可用 | Agent 动态生成仿真代码并自检自愈 |
| 标准能管报价生成 | ✅ 可用 | LLM 语义冲突检测（调研表 × 价格目录） |

## Agent 架构

```
┌────────────────────────────────────────────────────────────────┐
│ Next.js 前端（SSE 订阅 agent 轨迹）   FastAPI /agent/run 端点   │
└──────────────────────────────┬─────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────┐
│                  AgentOrchestrator（ReAct 循环）                │
│   决策(Brain) → 执行(Tool) → 观察 → 再决策 → … → finish/求助    │
│                                                                │
│   Brain（软决策，唯一 LLM 成本点）       硬约束（代码强制执行）   │
│   ├─ LLMBrain：白名单内选工具           ├─ 工具前置依赖         │
│   │   + JSON 强约束 + 失败重试          ├─ 质量门禁：完整率<50%  │
│   └─ RuleBrain：零成本规则策略          │   或 unsupported 站房  │
│       （评测/离线/无Key 场景）          │   → 强制转人工         │
│                                        └─ 步骤预算 + 熔断       │
└──────────────┬─────────────────────────────────────────────────┘
               ▼ ToolRegistry（确定性工具，执行零 token）
┌──────────────┬──────────────┬──────────────┬──────────────────┐
│ extract_survey│suggest_filling│apply_filling │calculate_saving  │
│ 规则提取+质检  │ 插值/季节填充 │ 机械执行填充  │ formulas 双sheet  │
└──────────────┴──────────────┴──────────────┴──────────────────┘
               ▼                                   ▼
      Excel 物理公式引擎（模板内嵌 COP/泵定律）   agent_trace.json（逐帧轨迹）
```

**设计要点：LLM 与传统代码的边界。** 节能率计算精度要求 ≤2%，因此公式引擎、
数据填充、质量检查全部是确定性函数（agent 的"手"，零 token）；LLM 只负责
感知与决策（agent 的"脑"）：白名单内选工具、每步面向用户的叙事、最终结论摘要。
硬约束（门禁/依赖/预算）在代码里强制执行，模型无法绕过——自主性有边界，结果才可信。

## 量化指标（回归评测，确定性模式可复现）

评测集为 6 份标注样例调研表（文件名自带预期节能率锚点，见 `evaluation/`）：

| 指标 | 数值 |
|---|---|
| 流程决策正确率（该算的算完/该拦的拦下） | **100%**（6/6，含深度调研模板变体） |
| 低质量数据中断正确率 | 2/2 |
| 节能率与人工锚点偏差 | 平均 1.97pp，最大 5.42pp（≤2pp 达标 2/4；最大偏差来自行业默认值填充的模板变体，见评测报告） |
| 地区识别正确率（三级推断） | 100% |
| 单次测算 LLM 成本 | 决策点 3~5 次小额调用；工具执行零 token |
| 评测模式 LLM 成本 | 0（RuleBrain 驱动，结果逐字节可复现） |

完整明细与已知缺口根因：[evaluation/report.md](./evaluation/report.md)

## 快速开始

```bash
# 1. 安装依赖（Python 3.10+）
pip install -r requirements.txt

# 2. 配置 LLM（可选——不配置也能跑，agent 自动降级为零成本规则策略）
copy .env.example .env    # 填入 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL

# 3. 启动后端
uvicorn apps.api.main:app --port 8000

# 4. 启动前端（可选，亦可直接 curl）
cd apps/web && npm install && npm run dev

# 5. Agent 模式跑一次完整测算
curl -X POST "localhost:8000/api/upload?module_type=air_conditioner" -F "file=@调研表.xlsx"
curl -X POST "localhost:8000/api/agent/run/<session_id>?mode=auto"
#    mode=deterministic 为零 LLM 成本模式；SSE 轨迹: /api/agent/<id>/stream
#    逐帧复盘:         /api/agent/<id>/trace

# 6. 回归评测（零成本，产出 evaluation/report.md）
python -m evaluation.run_eval
python -m evaluation.run_eval --compare-baseline   # 基线回归检查

# 7. 单元测试
pytest tests/unit/test_agent_orchestrator.py -v
```

## 项目结构

```
├── agent/                  # ★ Agent 核心（P1 改造新增）
│   ├── tools.py            #     工具注册表：确定性能力 → JSON Schema 工具
│   ├── brain.py            #     决策核心：LLMBrain（JSON 强约束）+ RuleBrain（零成本）
│   ├── orchestrator.py     #     ReAct 循环 + 白名单硬约束 + 事件流
│   └── trace.py            #     轨迹记录器（步骤/观察/token 用量 → agent_trace.json）
├── evaluation/             # ★ 回归评测（P2 改造新增）
│   ├── dataset.py          #     6 份标注样例的预期锚点
│   ├── metrics.py          #     决策正确率/节能率偏差/中断正确率
│   └── run_eval.py         #     评测 CLI（--save-baseline / --compare-baseline）
├── apps/api/               # FastAPI 后端（含 /agent/run、/agent/trace 端点）
├── apps/web/               # Next.js 16 前端（SSE 订阅 agent 轨迹）
├── core/                   # 业务引擎：ExcelCalculator(formulas)、DataFiller、
│   │                       # AirCompressorCalculator、SkillCaller(claude-agent-sdk)
│   └── llm_client.py       # 直连 Messages API 客户端（含 token 用量统计）
├── .claude/skills/         # Agent Skill 集（提取/填充/仿真/报价等，SKILL.md + 脚本）
├── config/                 # 单元格映射、模板配置、气象数据
├── 00_sample/              # 模板测算表 + 标注样例调研表（评测集来源）
├── simulation/             # 冷站 8760h 仿真引擎（agent 动态生成仿真代码）
├── quote_module/           # 标准能管报价生成流水线
├── proxy/ oauth-server/    # Go 反向代理 + OIDC 认证网关
├── ARCHITECTURE.md         # ★ 架构与决策边界设计说明（P3 改造新增）
└── evaluation/report.md    # ★ 最新回归评测报告
```

## 技术栈

Python 3.10+ · claude-agent-sdk · httpx 直连 Messages API · FastAPI + SSE ·
formulas（纯 Python Excel 公式引擎）· pandas/openpyxl · Next.js 16 + React 19 +
Tailwind v4 · Go Gin（OIDC 网关）· pytest（unit/integration/e2e 三层）

## 许可证

内部工具，版权归公司所有。
