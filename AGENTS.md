# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目概述

这是一个基于 AI + Excel 计算引擎的中央空调节能率智能测算工具，采用混合架构：
- **AI 辅助层**：使用 Codex Skills 进行数据提取、质量检查、填充建议
- **计算引擎层**：使用 formulas 库（纯 Python）调用 Excel 模板中的物理公式计算节能率
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
- 使用 Codex Agent SDK 进行异步调用
- 自动发现 `.Codex/skills/` 目录下的 skills
- 支持超时控制和错误处理
- 提取 AssistantMessage 的文本内容供前端展示
- 保持向后兼容的同步接口

### 临时文件管理
```bash
# 任务执行完后删除临时文件
rm -rf ./tmp/*
```

### 会话管理

```bash
# 列出所有会话目录（按时间倒序）
ls -lt tmp/session_*/

# 查看特定会话的内容
ls -lh tmp/session_20251230_153045/

# 手动清理旧会话（保留最近10个）
python -c "from core.session_manager import SessionManager; SessionManager().cleanup_old_sessions(keep_count=10)"

# 删除特定会话
rm -rf tmp/session_20251230_153045/
```

## 核心架构

### 数据流向
```
用户上传调研表Excel (保留原始文件名)
        ↓
extract-and-check-data Skill
  - 提取数据（使用原始文件名进行地区推断）
  - 识别站房类型（standard/secondary_pump/unsupported）
  - 质量检查
        ↓
JSON数据 + 质量报告 + 站房类型
        ↓
[如果 station_type == unsupported] → 流程中断，提示用户
        ↓
suggest-data-filling Skill → 填充建议
        ↓
DataFiller → 完整数据集（包含 station_type）
        ↓
ExcelCalculator（自动选择模板）→ 节能率结果
  - standard → 标准版模板
  - secondary_pump → 二次泵版模板
```

### 核心模块职责

| 模块 | 文件 | 核心职责 | 关键依赖 |
|------|------|----------|----------|
| **UI流程编排** | `app.py` | 5阶段流程控制（上传→提取+质量检查→填充建议→计算→结果）、用户交互 | Streamlit session state |
| **Skill调用器** | `core/skill_caller.py` | 封装subprocess调用Codex CLI | 处理超时、错误重试 |
| **数据填充器** | `core/data_filler.py` | 应用填充建议生成完整数据 | Pandas JSON处理 |
| **Excel计算器** | `core/excel_calculator.py` | 写入数据、调用Excel公式、提取结果 | formulas 库（纯 Python） |
| **单元格映射** | `config/cell_mapping.py` | JSON字段→Excel单元格位置映射 | 硬编码的行列映射表 |

### Codex Skills（AI辅助层）

Skills 位于 `.Codex/skills/` 目录，采用目录结构组织：

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
     - **流程控制**：通过 `can_proceed` 字段决定是否可继续计算
     - **不可填充检测**：识别 project_region 缺失、能耗数据 < 6个月等情况
     - **智能填充**：线性插值（高置信度）、季节代表值（中）、行业默认值（低）
   - 填充策略：线性插值（优先）→ 季节代表值 → 相邻均值 → 行业默认值
   - 输出格式：
     - `can_proceed` (bool): 是否可继续计算
     - `unfillable_fields` (array): 不可填充字段列表
     - `fillable_suggestions` (array): 可填充建议列表

### Excel计算模板

模板文件：`00_sample/模板测算表/节能评估表-按冷站电量数据-标准版.xlsx`（和二次泵版）

**Sheet结构（3个）**：
1. **【1】按冷站电量数据-上限** - 估算节能率上限（理想情况）
2. **【2】按冷站电量数据-下限** - 估算节能率下限（保守估计）
3. **全国主要城市气象情况** - 气象数据（辅助计算）

**双Sheet计算机制**：
- 系统会同时计算上限和下限两个sheet
- 上限：基于最优运行条件，理想化假设
- 下限：基于常规优化参数，考虑实际约束
- 输出节能率范围：下限% - 上限%

**Sheet1和Sheet2的差异**：
- 行列结构完全相同（数据输入位置、结果提取位置一致）
- 仅公式中的系数不同（优化幅度、安全系数等）
- 因此使用同一套 CellMapping 映射

**数据输入** (Sheet1和Sheet2):
- 月度数据写入列：D-O（1-12月）
- 关键行号：见 `config/cell_mapping.py` 的 `MONTHLY_ROWS`

**结果提取** (Sheet1和Sheet2):
- 基础信息：项目地区(H4)
- 结果提取：总节能率(O30)、分项节能量(P11/P16/P21/P25/P28)

**核心物理系数**：
- 冷机供水温度优化：4%/℃（上限和下限可能不同）
- 水泵变频优化：能耗 ∝ 频率^2.5
- 冷却塔优化：1.5%/℃（上限和下限可能不同）

### 数据回填机制

**实现方法**（`core/excel_calculator.py::_calculate_with_formulas`）:

1. **阶段1 - 数据写入**：使用 openpyxl 将 filled_data.json 的数据写入 Excel 文件
   - 项目地区 → Sheet2 H4
   - 月度数据（12个月 × 7个字段）→ Sheet1 D-O 列对应行

2. **阶段2 - 公式计算**：使用 formulas 库加载已写入数据的文件并计算
   - `xl_model = formulas.ExcelModel().loads(excel_path).finish()`
   - `result_data = xl_model.calculate()`

3. **阶段3 - 结果提取**：从 result_data 提取计算结果

**重要**: 早期实现尝试使用 `calculate(inputs={...})`，但 formulas 库会忽略 inputs 参数。
当前实现通过先写入文件再计算解决了这个问题。

**验证**: `tests/unit/test_excel_data_filling.py` 确保数据回填准确性

## 关键技术约束

### Excel 计算引擎

**当前实现：** 使用 `formulas` 库（纯 Python）

- **formulas 库**：Excel 公式解析和计算引擎
  - 无需外部依赖（不需要 Excel/LibreOffice）
  - 纯 Python 实现，跨平台兼容
  - 支持大部分 Excel 公式和函数
  - 适合服务器端自动化部署

**代码位置：** `core/excel_calculator.py`

**关键方法：**
- `_calculate_with_formulas()`: 使用 formulas 库执行计算
- 计算失败会**显式抛出异常**（不再有 mock 降级方案——2026-08 重构时移除，
  避免给前端返回假节能率）

**使用示例：**
```python
# core/excel_calculator.py 会自动使用 formulas 引擎
calc = ExcelCalculator(template_path)
result_path = calc.calculate(filled_data_path, output_path)
```

### Streamlit配置要求

**必须配置文件**：
- `.streamlit/config.toml`：端口、CORS、主题设置
- `.streamlit/secrets.toml`：管理员密码（用于下载保护）

**Session State管理**：
- 5个阶段状态：upload → extract_check → filling → calculate → result
- 每个阶段数据缓存在 `st.session_state` 中

### 临时文件约定

**会话目录结构**：
- 每次上传任务创建独立的会话目录
- 目录命名格式：`tmp/session_YYYYMMDD_HHMMSS/`
- 会话目录由 `core.session_manager.SessionManager` 管理

**会话目录中的文件**：
- `upload_survey.xlsx`：用户上传的调研表
- `extract_check_result.json`：提取和质量检查的合并结果
- `extracted_data.json`：提取的原始数据
- `quality_report.json`：质量检查报告
- `filling_suggestions.json`：填充建议
- `filled_data.json`：填充后的完整数据
- `result_data.json`：计算结果JSON
- `calculation_result.xlsx`：计算结果Excel（供下载）

**优势**：
- ✅ 多用户同时使用时数据隔离
- ✅ 可以保留历史会话记录
- ✅ 避免文件覆盖和混乱
- ✅ 方便调试和问题追溯

**清理策略**（可选）：
- 自动保留最近 10 个会话
- 可通过 `SessionManager.cleanup_old_sessions()` 手动清理
- 建议定期清理避免磁盘占用过多

**向后兼容**：
- `tmp/.gitkeep` 保留以维护 Git 目录结构
- 旧代码中的硬编码 `tmp/` 路径已全部迁移到会话目录

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
修改 `.Codex/skills/extract-and-check-data/SKILL.md`，更新调研表行号、字段映射或检查规则。

**季节性范围值解析：**

系统支持从调研表中提取季节性范围值（如"16~20"），自动拆分为多个月的数据。解析策略：

1. **解析策略（按优先级）**：
   - 精确匹配：单个数值（如"18.5"）→ 直接作为该月数据
   - 范围值解析：季节范围（如"16~20"）→ 自动拆分为季节内各月
   - 空值处理：空单元格 → 标记为缺失，后续填充

2. **季节定义**：
   - **春季**（3-5月）：3月、4月、5月
   - **夏季**（6-8月）：6月、7月、8月
   - **秋季**（9-11月）：9月、10月、11月
   - **冬季**（12-2月）：12月、1月、2月

3. **范围值处理规则**：
   - 检测格式：`数值1~数值2`（支持中文波浪号～和英文~）
   - 计算代表值：`(最小值 + 最大值) / 2`
   - 分配给当前月所在季节的所有月份

4. **实现位置**：
   - Skill脚本：`.Codex/skills/extract-and-check-data/scripts/extract_survey_data.py`
   - 核心函数：`parse_value(cell_value, current_month)` 和 `get_season_for_month(month)`

**范围值解析示例：**

| 单元格值 | 月份 | 所在季节 | 解析结果 | 说明 |
|---------|------|---------|---------|------|
| "16~20" | 7月 | 夏季 | 18.0 | 范围中值，分配给6/7/8月 |
| "15～18" | 12月 | 冬季 | 16.5 | 范围中值，分配给12/1/2月 |
| "22.5" | 任意 | - | 22.5 | 精确值，直接使用 |
| 空单元格 | 任意 | - | None | 标记缺失，后续填充 |

**注意事项：**
- 范围值会自动分配给整个季节（如夏季的"16~20"会同时填充到6/7/8月）
- 如果调研表同一季节不同月份有不同范围值，以最后提取的值为准
- 解析失败的单元格会被标记为缺失数据，触发质量检查警告

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
4. **Skill测试隔离**：单元测试应mock Skill调用，避免依赖Codex CLI

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

详见 `DEPLOYMENT.md`。

## 项目地区识别规则

系统支持从调研表自动识别项目所属地区，用于匹配气象数据。采用**三级优先级**提取策略，大幅提高识别成功率。

**识别方法（按优先级）：**
1. **站房名称推断（优先级1）**：从"冷站"sheet的"站房名称"字段提取城市关键词
2. **文件名推断（优先级2）**：从用户上传的**原始文件名**提取城市关键词
   - ✅ 现在会保留用户上传时的原始文件名（如"惠州光弘-调研表.xlsx"）
   - ✅ 即使文件被临时保存为 `tmp/upload_survey.xlsx`，原始文件名仍会用于地区推断
   - ✅ 原始文件名通过 session state 传递给 extract-and-check-data skill
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
| **原始文件名** | **"惠州光弘-调研表.xlsx"** | **华南** |
| **原始文件名** | **"石家庄仁和药业中央空调节能调研表.xlsx"** | **华北** |
| 项目总体情况 | 单元格包含"武汉市" | 华中 |

## 站房类型识别规则

系统支持三种站房类型，通过 AI 智能分析调研表内容自动识别：

### 支持的类型

1. **standard（标准站房）**
   - 特征：仅有一次冷冻泵，无二次泵分离
   - 使用模板：`00_sample/模板测算表/节能评估表-按冷站电量数据-标准版.xlsx`
   - 典型调研表特征：
     - "冷冻泵"字段只有一行数据
     - 无"一次泵"/"二次泵"分开描述

2. **secondary_pump（二次泵站房）**
   - 特征：冷冻系统包含一次泵和二次泵
   - 使用模板：`00_sample/模板测算表/节能评估表-按冷站电量数据-二次泵版.xlsx`
   - 典型调研表特征：
     - 冷冻泵分为"一次冷冻泵"和"二次冷冻泵"两个部分
     - 表格中有"一次泵"/"二次泵"标签

### 不支持的类型

**unsupported（特殊类型站房）**
- 包含以下任一特征：
  - 热水泵：调研表中有"热水泵"相关字段
  - 水蓄冷：调研表中有"蓄冷"/"蓄冰"相关字段
  - 中低温机组：调研表中有"中温"/"低温"机组描述
- **处理方式**：在数据提取阶段自动拦截，不进入计算流程
- **原因**：这些特殊类型的节能计算逻辑复杂，需要专门的评估方法

### 识别置信度

- **high**: 明确特征，如明确标注"一次泵"/"二次泵"或"热水泵"
- **medium**: 特征不明显，基于推断
- **low**: 无法判断，默认为 standard

### 流程拦截机制

系统在以下两个阶段检查站房类型：

1. **提取检查阶段**：
   - 识别到 `unsupported` 类型后立即中断流程
   - 展示识别依据和原因
   - 提供"返回重新上传"按钮

2. **计算阶段**（防御性检查）：
   - 再次检查 `station_type` 字段
   - 如果为 `unsupported` 则抛出 ValueError

详见：`config/template_config.py` 和 `.Codex/skills/extract-and-check-data/`

## 已修复的关键问题

### Excel计算失败导致前端显示mock默认值（已修复 - 2025-12-29）

**问题描述：**
1. Sheet1（上限）没有回填数据，也没有用来计算节能率上限值
2. 前端显示的是mock默认值（15%, 12%-18%），不是实际计算的节能率

**根本原因：**
- `config/cell_mapping.py:14` 中上限sheet名称配置有末尾空格
- 配置：`"【1】按冷站电量数据-上限 "` （有空格）
- 实际：`"【1】按冷站电量数据-上限"` （无空格）
- 导致 `openpyxl` 抛出 `KeyError`，计算失败降级到mock结果

**解决方案：**
- 移除 `SHEET_NAMES["upper"]` 末尾的空格
- 添加sheet名称验证测试
- 增强错误日志，方便未来调试

**验证：**
- ✅ 双sheet计算成功
- ✅ 前端显示真实计算的节能率范围
- ✅ 所有单元测试和集成测试通过

**相关 Commit:**
- `fix: remove trailing space from upper sheet name in cell_mapping`
- `test: add failing test for sheet name mismatch`
- `feat: add detailed error logging and sheet name validation`

### 月份列错位问题（已修复）

**问题描述：**
调研表的"用电情况统计"和"设备运行规律"两个部分的列结构不同：
- **设备运行规律**：有"备注"列（C列），月份从D列开始（D=1月, E=2月, ..., N=11月）
- **用电情况统计**：无备注列，月份从C列开始（C=1月, D=2月, ..., N=12月）

早期实现使用硬编码 `month_col_start = 3`（D列）处理所有字段，导致：
- ❌ 用电情况的1月数据（C列）被漏读
- ❌ 2月数据（D列）被错当成1月
- ❌ 后续所有月份向左错位一个月
- ❌ 12月数据可能超出范围

**解决方案：**
- 添加 `detect_month_column_start()` 函数，通过查找"1月"关键字动态检测每个部分的月份列起始位置
- 分别处理设备运行规律（equipment_col_start）和用电情况（energy_col_start）
- 根据字段类型使用正确的列偏移量

**验证：**
- 测试文件：`tests/unit/test_extract_column_offset.py`
- 验证脚本：`scripts/verify_column_offset_bug.py`

**相关 Commit:**
- `fix: correct column offset for energy vs equipment data`

## 相关文档

- **产品需求**：`02_prd/PRD-空调节能率智能测算工具.md`
- **技术方案**：`03_plan/技术方案详细设计-LLM混合架构.md`
- **实施总结**：`IMPLEMENTATION_SUMMARY.md`
- **部署指南**：`DEPLOYMENT.md`

## 项目依赖版本

见 `requirements.txt`：
- streamlit >= 1.28.0
- pandas >= 2.0.0
- openpyxl >= 3.1.0
- formulas >= 1.3.0（Excel 公式计算）
- plotly >= 5.0.0（用于可视化）
- pytest >= 7.0.0（测试）
- Codex-agent-sdk >= 0.1.0
