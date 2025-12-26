# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个基于 AI + Excel 计算引擎的中央空调节能率智能测算工具，采用混合架构：
- **AI 辅助层**：使用 Claude Skills 进行数据提取、质量检查、填充建议
- **计算引擎层**：使用 xlwings/openpyxl 调用 Excel 模板中的物理公式计算节能率
- **前端展示层**：Streamlit Web UI，提供5阶段工作流

## 常用命令

### 启动应用
```bash
# 开发环境启动
streamlit run app.py

# 生产环境启动（需要配置防火墙）
streamlit run app.py --server.port=8501 --server.address=0.0.0.0
```

### 测试
```bash
# 运行所有测试
pytest

# 运行指定测试模块
pytest tests/unit/test_data_filler.py
pytest tests/integration/

# 显示详细输出和打印信息
pytest -v -s

# 设置正确的 PYTHONPATH
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest
```

### Skill 调用

**前置要求：**
```bash
# 设置 API Key
export ANTHROPIC_API_KEY='your-api-key-here'
```

**在 Python 代码中调用（推荐）：**
```python
from core.skill_caller import SkillCaller

caller = SkillCaller(timeout=300)
result = caller.call_skill(
    "extract-and-check-data",
    "input.xlsx",
    "output.json"
)

# 访问返回结果
ai_responses = result["ai_responses"]  # AI 助手的文本回复列表
all_messages = result["all_messages"]  # 所有消息（调试用）
result_text = result["result_text"]    # 合并的文本（向后兼容）
```

**返回值结构：**
```python
{
    "success": True,
    "ai_responses": ["AI回复1", "AI回复2", ...],  # AssistantMessage 的文本内容
    "all_messages": ["消息1", "消息2", ...],      # 所有消息的字符串表示
    "result_text": "合并的所有消息文本"            # 向后兼容字段
}
```

**特性：**
- 使用 Claude Agent SDK 进行异步调用
- 自动发现 `.claude/skills/` 目录下的 skills
- 支持超时控制和错误处理
- 提取 AssistantMessage 的文本内容供前端展示
- 保持向后兼容的同步接口

### 临时文件管理
```bash
# 任务执行完后删除临时文件
rm -rf ./tmp/*
```

## 核心架构

### 数据流向
```
调研表Excel → extract-and-check-data Skill → JSON数据 + 质量报告
                ↓
        suggest-data-filling Skill → 填充建议
                ↓
        DataFiller → 完整数据集
                ↓
        ExcelCalculator → 节能率结果
```

### 核心模块职责

| 模块 | 文件 | 核心职责 | 关键依赖 |
|------|------|----------|----------|
| **UI流程编排** | `app.py` | 5阶段流程控制（上传→提取+质量检查→填充建议→计算→结果）、用户交互 | Streamlit session state |
| **Skill调用器** | `core/skill_caller.py` | 封装subprocess调用Claude CLI | 处理超时、错误重试 |
| **数据填充器** | `core/data_filler.py` | 应用填充建议生成完整数据 | Pandas JSON处理 |
| **Excel计算器** | `core/excel_calculator.py` | 写入数据、调用Excel公式、提取结果 | xlwings(优先)/openpyxl(降级) |
| **单元格映射** | `config/cell_mapping.py` | JSON字段→Excel单元格位置映射 | 硬编码的行列映射表 |

### Claude Skills（AI辅助层）

Skills 位于 `.claude/skills/` 目录，采用目录结构组织：

1. **extract-and-check-data**：从调研表Excel提取数据并进行质量检查
   - 输入：调研表路径（`00_sample/02-中央空调节能调研表.xlsx`）
   - 输出：`tmp/extract_check_result.json`（包含extracted_data和quality_report）
   - 关键功能：
     - **项目地区提取（三级优先级）**：
       1. **优先级1**: 从"冷站"sheet的"站房名称"字段推断（如"深圳工业园区F栋" → 华南）
       2. **优先级2**: 从调研表文件名推断（如"惠州光弘-调研表.xlsx" → 华南）
       3. **优先级3**: 从"项目总体情况"sheet扫描省市关键词（兜底机制）
       - 支持识别全国主要城市：北上广深、省会城市、计划单列市等
     - 提取12个月运行数据（月度耗电量、供水温度、泵频率、水温差、冷却塔温度）
     - 检查数据完整性（必填字段、数值范围、逻辑一致性）
     - 计算完整率和置信度
     - 输出问题列表和总结
   - 同时保存单独的 `tmp/extracted_data.json` 和 `tmp/quality_report.json` 供后续使用

2. **suggest-data-filling**：基于季节模式和插值法推荐填充值
   - 输入：质量报告 + 提取数据
   - 输出：`tmp/filling_suggestions.json`
   - 关键功能：
     - **自动读取项目地区**：从 extracted_data.json 的 project_region 字段获取（高置信度）
     - 能耗数据估算：季节代表月法（夏季用7月、春秋用5/10月、冬季用1月）
     - 运行参数插值：线性插值、季节复制、典型值兜底
   - 填充策略：季节代表月法、线性插值

### Excel计算模板

模板文件：`00_sample/机房智能化节能评估表-按冷站电量数据.xlsx`

**Sheet1（数据输入）**：
- 月度数据写入列：D-O（1-12月）
- 关键行号：见 `config/cell_mapping.py` 的 `MONTHLY_ROWS`

**Sheet2（计算结果）**：
- 基础信息：项目地区(H4)
- 结果提取：总节能率(P29)、分项节能量(P11/P16/P21/P25)

**核心物理系数**：
- 冷机供水温度优化：4%/℃
- 水泵变频优化：能耗 ∝ 频率^2.5
- 冷却塔优化：1.5%/℃

## 关键技术约束

### Excel引擎优先级
1. **xlwings**（首选）：需要LibreOffice/Excel，支持公式重算，精度高
2. **openpyxl**（降级）：纯Python，不需外部依赖，但公式需手动触发

代码中会自动检测并降级：
```python
# core/excel_calculator.py
try:
    import xlwings as xw
    use_xlwings = True
except ImportError:
    use_xlwings = False
```

### Streamlit配置要求

**必须配置文件**：
- `.streamlit/config.toml`：端口、CORS、主题设置
- `.streamlit/secrets.toml`：管理员密码（用于下载保护）

**Session State管理**：
- 5个阶段状态：upload → extract_check → filling → calculate → result
- 每个阶段数据缓存在 `st.session_state` 中

### 临时文件约定

所有中间文件存放在 `./tmp/` 目录：
- `extract_check_result.json`：提取和质量检查的合并结果
- `extracted_data.json`：提取的原始数据
- `quality_report.json`：质量检查报告
- `filling_suggestions.json`：填充建议
- `filled_data.json`：填充后的完整数据
- `result_*.xlsx`：计算结果Excel（供下载）

**重要**：任务执行完后应删除 `./tmp/` 中的临时文件。

### 数据质量判断标准

**置信度分级**（基于数据完整度）：
- **高置信度**：≥80%，结果可靠，可直接使用
- **中等置信度**：50-80%，部分数据需要智能填充，谨慎使用
- **低置信度**：<50%，**自动中断计算流程**，要求用户补充数据后重新上传

**流程中断机制**：
- 当 `confidence_level == "low"` 时，系统会在"提取+质量检查"阶段中断
- 前端显示"数据质量不达标"错误界面
- 展示所有严重(critical)和高优先级(high)问题
- 提供"返回重新上传"按钮，不允许进入填充建议阶段
- 确保低质量数据不会进入计算流程

**问题严重等级**：
- CRITICAL：核心字段缺失（如月度耗电量）
- HIGH：关键字段缺失（如供水温度）
- MEDIUM：次要字段缺失或数值异常
- LOW：建议优化的字段

## 修改常见场景

### 场景1：调整数据提取或质量检查逻辑
修改 `.claude/skills/extract-and-check-data/SKILL.md`，更新调研表行号、字段映射或检查规则。

### 场景2：修改计算公式
1. 编辑 `00_sample/机房智能化节能评估表-按冷站电量数据.xlsx` 的Excel公式
2. 更新 `config/cell_mapping.py` 中的单元格映射（如果新增输入/输出字段）

### 场景3：添加气象数据城市
编辑 `config/weather_data.json`（如果存在），添加新城市的月度湿球温度数据。

### 场景4：UI流程调整
修改 `app.py`，注意维护 `st.session_state.stage` 状态机的一致性。

## 测试注意事项

1. **测试数据准备**：使用 `tests/fixtures/` 中的样例数据
2. **PYTHONPATH设置**：必须设置正确的PYTHONPATH，否则导入失败
3. **Excel模板依赖**：集成测试需要 `00_sample/机房智能化节能评估表-按冷站电量数据.xlsx` 存在
4. **Skill测试隔离**：单元测试应mock Skill调用，避免依赖Claude CLI

### 示例调研表端到端测试

项目包含6份不同质量等级的示例调研表，用于全面测试系统功能：

**运行示例调研表测试：**
```bash
# 使用测试脚本（推荐）
./scripts/run_sample_survey_tests.sh

# 或手动运行
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
export ANTHROPIC_API_KEY='your-api-key'
pytest tests/integration/test_sample_surveys_e2e.py::TestAllSurveysBatch -v -s
```

**测试覆盖场景：**
- 齐全数据（高置信度）
- 仅有夏季/缺冬季/缺夏季（中等置信度，需填充）
- 参差不齐（中等置信度，插值填充）
- 数据缺失过多（低置信度，流程中断）

详见：`docs/testing/sample-surveys-testing-guide.md`

## 部署要点

**生产环境检查清单**：
1. Python 3.8+ 安装
2. 依赖安装：`pip install -r requirements.txt`
3. `.streamlit/secrets.toml` 配置管理员密码
4. 防火墙开放8501端口（仅内网）
5. （可选）安装 LibreOffice 以启用 xlwings

详见 `DEPLOYMENT.md`。

## 项目地区识别规则

系统支持从调研表自动识别项目所属地区，用于匹配气象数据。采用**三级优先级**提取策略，大幅提高识别成功率。

**识别方法（按优先级）：**
1. **站房名称推断（优先级1）**：从"冷站"sheet的"站房名称"字段提取城市关键词
2. **文件名推断（优先级2）**：从调研表文件名或路径提取城市关键词
3. **项目总体情况扫描（优先级3，兜底）**：从"项目总体情况"sheet扫描所有单元格匹配省市关键词

**支持的地区和关键词：**
- **华南**：广东、广西、海南、福建、深圳、广州、厦门、珠海、东莞、佛山、惠州、中山、江门、湛江、汕头
- **华东**：上海、江苏、浙江、安徽、江西、南京、杭州、苏州、无锡、宁波、合肥、南昌、温州、常州、徐州
- **华中**：湖北、湖南、河南、武汉、长沙、郑州、洛阳、株洲、岳阳
- **西南**：四川、重庆、贵州、云南、西藏、成都、贵阳、昆明、拉萨
- **西北**：陕西、甘肃、青海、宁夏、新疆、西安、兰州、银川、乌鲁木齐、西宁
- **华北**：北京、天津、河北、山西、内蒙古、石家庄、太原、呼和浩特、唐山、保定、廊坊
- **东北**：辽宁、吉林、黑龙江、沈阳、大连、长春、哈尔滨、鞍山、抚顺

**提取示例：**

| 提取源 | 示例 | 推断地区 |
|--------|------|----------|
| 站房名称 | "深圳工业园区F栋制冷站" | 华南 |
| 站房名称 | "北京总部冷站" | 华北 |
| 文件名 | "惠州光弘-调研表.xlsx" | 华南 |
| 文件名 | "石家庄仁和药业中央空调节能调研表.xlsx" | 华北 |
| 项目总体情况 | 单元格包含"武汉市" | 华中 |

## 相关文档

- **产品需求**：`02_prd/PRD-空调节能率智能测算工具.md`
- **技术方案**：`03_plan/技术方案详细设计-LLM混合架构.md`
- **实施总结**：`IMPLEMENTATION_SUMMARY.md`
- **部署指南**：`DEPLOYMENT.md`

## 项目依赖版本

见 `requirements.txt`：
- streamlit >= 1.28.0
- pandas >= 2.0.0
- xlwings >= 0.30.0（可选）
- openpyxl >= 3.1.0
- plotly >= 5.0.0（用于可视化）
- pytest >= 7.0.0（测试）
