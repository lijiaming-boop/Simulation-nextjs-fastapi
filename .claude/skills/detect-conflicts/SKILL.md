# Detect Conflicts Skill

## 目的

对 project.json + price_catalog.json + 用户规则进行语义层面的冲突分析，处理代码规则覆盖不了的模糊场景。

## 输入

- `project.json`：调研表解析结果
- `price_catalog.json`：价格目录（问题 1 产出）
- 用户规则：从 `standard-energy-quote/SKILL.md` 的 `## 用户规则` 章节读取

## 输出

`conflict_report.json`：

```json
{
  "summary": {
    "total_items": 25,
    "auto": 20, "confirm": 3, "inquiry": 1, "nonstandard": 0, "blocked": 1
  },
  "issues": [
    {
      "item": "API接口开发(MES系统)",
      "status": "CONFIRM",
      "reason": "用户规则 RULE-001：统一按2万报价，但报价体系标准价3万/渠道价2.1万。需确认2万对应哪个价格口径。",
      "recommendation": "请确认：2万是标准价、渠道价还是统一价？"
    }
  ],
  "analysis_notes": [
    "报价模板备注'费用含税'，当前系统默认另算税费，如价格已含税则不另加。请确认税费口径。"
  ]
}
```

## AI 分析范围

代码已处理的确定性规则（不在此 Skill 范围内）：
- 多匹配产品 → CONFIRM（代码已检测）
- 无匹配产品 → INQUIRY（代码已检测）
- 接口方向判断 → NONSTANDARD（代码已检测）
- 税费冲突 → BLOCKED（代码已检测）

AI 需分析的语义场景：
- 含税/未税矛盾的深度分析（对比报价模板原文 vs 系统计算方式）
- 用户口头规则与报价体系的结构化冲突（如 RULE-001 API 2万 vs 报价体系3万）
- 边界规则的非结构化判断（如调研表描述中隐含的 AI/控制需求）
- 其他代码规则无法覆盖的边缘场景

## 缓存策略

`conflict_report.json` 作为缓存。同一对 project.json + price_catalog.json 不重复调 AI。

## 执行步骤

1. 加载 project.json、price_catalog.json
2. 读取 `.claude/skills/standard-energy-quote/SKILL.md` 中的 `## 用户规则` 章节
3. 遍历 project.json 中所有物料项
4. 对于代码已标记为 AUTO 的项，检查是否符合用户规则覆盖条件
5. 对于代码标记为 CONFIRM/BLOCKED 的项，补充详细的冲突分析
6. 输出 conflict_report.json
