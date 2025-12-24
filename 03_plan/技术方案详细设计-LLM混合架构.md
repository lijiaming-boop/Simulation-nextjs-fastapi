# 空调节能率智能测算工具 - 技术方案详细设计

> 基于 LLM + Excel 计算引擎的混合架构

**设计日期**: 2025-12-17
**版本**: v1.0
**设计目标**: 使用 LLM Skills 处理数据提取、质量检查和填充决策,使用 Excel 公式引擎保证计算精度

---

## 一、整体架构

### 系统分层

```
┌─────────────────────────────────────┐
│      Streamlit UI Layer             │
│  (app.py - 用户交互界面)             │
└──────────────┬──────────────────────┘
               │
    ┌──────────┴──────────────────┐
    │                             │
┌───▼─────────┐          ┌────────▼─────────┐
│ LLM Skills  │          │ Excel Engine     │
│   Layer     │          │  (excel_calc.py) │
│             │          │                  │
│ skill 1-3   │          │ 1. 数据回填      │
└──────┬──────┘          │ 2. 触发计算      │
       │                 │ 3. 提取结果      │
       │                 └──────────────────┘
┌──────▼────────────────────────────┐
│   File System                     │
│  tmp/                             │
│  - extracted_data.json            │
│  - quality_report.json            │
│  - filling_suggestions.json       │
│  - filled_data.json               │
│  - calculation_result.xlsx        │
│  - result_data.json               │
└───────────────────────────────────┘
```

### 技术栈

- **Frontend**: Streamlit 1.28+
- **LLM Skills**: 自定义 .md 文件,通过 subprocess 调用 Claude CLI
- **Excel 引擎**: xlwings (可调用 Excel/LibreOffice 计算引擎)
- **数据交换**: JSON 文件 (存放在 `./tmp/` 目录)

### 核心设计决策

1. **步骤(1)(2)(3)使用 LLM Skills 实现**,利用 LLM 的理解和推理能力
2. **步骤(4)使用代码实现**,直接使用 Excel 模板公式保证精度
3. Skills 通过文件路径传递数据,输出结构化 JSON
4. 不重新实现计算逻辑,数据回填到 Excel 模板后触发计算

---

## 二、详细数据流程

### 完整流程

```
1. 用户上传调研表.xlsx
   ↓
2. Streamlit 保存到 tmp/upload_survey.xlsx
   ↓
3. 调用 Skill 1: /extract-survey-data tmp/upload_survey.xlsx
   → 输出: tmp/extracted_data.json
   {
     "project_region": "华北",
     "monthly_data": [
       {"month": 1, "total_energy": 20.0, "chiller_supply_temp": 7.0, ...},
       ...
     ]
   }
   ↓
4. 调用 Skill 2: /check-data-quality tmp/extracted_data.json
   → 输出: tmp/quality_report.json
   {
     "completeness": 0.75,
     "confidence_level": "medium",
     "issues": [
       {"field": "monthly_data[3].chiller_supply_temp", "severity": "high", ...},
     ],
     "risks": ["数据完整率75%,建议补充缺失月份"]
   }
   UI 展示质量报告,自动流转(不需要用户确认)
   ↓
5. 调用 Skill 3: /suggest-data-filling tmp/extracted_data.json tmp/quality_report.json
   → 输出: tmp/filling_suggestions.json
   {
     "can_proceed": true,
     "unfillable_fields": [],
     "fillable_suggestions": [
       {
         "field": "monthly_data[3].chiller_supply_temp",
         "suggested_value": 8.2,
         "method": "linear_interpolation",
         "confidence": "high",
         "reasoning": "基于2月(7.5)和5月(8.9)线性插值"
       }
     ]
   }
   ↓
6. UI 展示填充建议:
   - 如果有 unfillable 项 → 显示错误,提示用户必须补充关键数据,中断流程
   - 否则 → 展示填充列表,等待用户一次性确认
   ↓
7. 用户确认后,Python 执行填充
   → 输出: tmp/filled_data.json
   ↓
8. Excel 计算引擎:
   - 复制模板到 tmp/calculation_result.xlsx
   - 回填数据到对应单元格
   - 调用 xlwings 触发 Excel 计算
   - 提取结果数据
   → 输出: tmp/result_data.json
   ↓
9. UI 展示结果:
   - 预估节能率: x% ~ x%
   - 分项明细
   - 管理员密码验证后可下载完整计算表格
```

---

## 三、LLM Skills 详细设计

### 文件位置
`.claude/skills/`

### Skill 1: extract-survey-data.md

**功能**: 从调研表 Excel 中提取空调系统月度运行数据

**输入**: 调研表 Excel 文件路径

**输出**: `tmp/extracted_data.json`

**提取字段**:
1. **项目地区**: 华南/华东/华中/西南/西北/华北 (如调研表没有,标记为 null)
2. **月度运行数据**(1-12月):
   - 冷站月度总能耗/万kWh (调研表行47)
   - 冷机供水温度/°C (行38)
   - 冷却泵运行频率/Hz (行39)
   - 冷却侧供回水温差/℃ (行40)
   - 冷冻泵运行频率/Hz (行41)
   - 冷冻侧供回水温差/℃ (行42)
   - 冷却塔出水温度/℃ (行44)

**处理要点**:
- 依赖 LLM 理解能力识别数据,不硬编码 Sheet 名称
- 频率和温差字段可能是文本描述(如"工频50HZ"、"3-5℃/4℃"),需解析出数值
- 空白单元格标记为 null
- 如果找不到足够必需数据,返回错误标记

**输出结构**:
```json
{
  "project_region": "华北",
  "monthly_data": [
    {
      "month": 1,
      "total_energy": 20.7948,
      "chiller_supply_temp": 7.0,
      "cooling_pump_freq": 45,
      "cooling_water_temp_diff": 4.5,
      "freezing_pump_freq": 50,
      "freezing_water_temp_diff": 4.5,
      "cooling_tower_outlet_temp": 22
    },
    // ... 12个月
  ]
}
```

### Skill 2: check-data-quality.md

**功能**: 检查提取数据的完整性和合理性

**输入**: `tmp/extracted_data.json`

**输出**: `tmp/quality_report.json`

**检查项**:
1. 必填字段缺失: project_region, 各月 total_energy 等
2. 数值异常: 温度/频率超出合理范围
3. 逻辑错误: 供回水温差为负、频率>50Hz等
4. 完整率计算: 有效数据点 / 总数据点

**输出结构**:
```json
{
  "completeness": 0.75,
  "confidence_level": "medium",
  "issues": [
    {
      "field": "project_region",
      "severity": "critical",
      "type": "missing",
      "message": "项目地区缺失,无法匹配气象数据"
    },
    {
      "field": "monthly_data[3].chiller_supply_temp",
      "severity": "high",
      "type": "missing",
      "message": "4月冷机供水温度缺失"
    }
  ],
  "summary": "数据完整率75%,建议补充缺失月份数据"
}
```

### Skill 3: suggest-data-filling.md

**功能**: 为缺失数据提供智能填充建议

**输入**:
- `tmp/extracted_data.json`
- `tmp/quality_report.json`

**输出**: `tmp/filling_suggestions.json`

**填充策略依赖 LLM 推理**:

**场景1: 部分月份有数据,推测全年**
```
输入: 只有6-9月(夏季)的冷冻水出水温度
LLM推理:
  - 分析夏季温度特征: 26-30℃
  - 理解环境气温曲线规律(冬冷夏热)
  - 推测春秋: 18-22℃
  - 推测冬季: 12-16℃
输出: 12个月的填充值,置信度根据距离已知数据的远近标记
```

**场景2: 稀疏数据,同季节插值**
```
输入: 只有1月、4月、7月、10月的数据(每季度一个点)
LLM推理:
  - 识别季节模式: 冬(1月) → 春(4月) → 夏(7月) → 秋(10月)
  - 2-3月用1月和4月插值(同属冬春过渡)
  - 5-6月用4月和7月插值(同属春夏过渡)
输出: 使用相邻季节数据的加权插值
```

**场景3: 完全缺失某参数**
```
输入: 所有月份的冷却塔出水温度都缺失
LLM推理:
  - 检查是否有其他相关参数(如冷却侧温度)
  - 如果有关联参数,基于热力学关系推测
  - 如果无关联参数,使用行业默认值(低置信度)
  - 如果是关键参数且无法合理推测,标记为 unfillable
```

**输出结构**:
```json
{
  "can_proceed": false,
  "unfillable_fields": [
    {
      "field": "project_region",
      "reason": "项目地区是必填项,无法通过算法推断,必须用户补充"
    }
  ],
  "fillable_suggestions": [
    {
      "field": "monthly_data[3].chiller_supply_temp",
      "original_value": null,
      "suggested_value": 8.2,
      "method": "linear_interpolation",
      "confidence": "high",
      "reasoning": "基于3月(7.5℃)和5月(8.9℃)的线性插值"
    }
  ]
}
```

**注意**: 填充方法的具体策略待后续设计确认,当前标记为待定

---

## 四、数据填充执行模块

### 架构澄清

- **Skill 3 (LLM)**: 负责智能推理和决策填充策略
- **data_filler.py (代码)**: 只负责机械执行 LLM 的决策结果

### data_filler.py 实现

```python
class DataFiller:
    """
    纯执行模块,不做任何智能决策
    """
    def fill_data(self, extracted_data_path: str,
                  filling_suggestions_path: str,
                  output_path: str) -> str:
        """
        1. 读取 tmp/extracted_data.json
        2. 读取 tmp/filling_suggestions.json (LLM已决策好的)
        3. 机械地将 suggested_value 填入对应字段
        4. 添加 _filled_fields 标记
        5. 输出到 tmp/filled_data.json

        不做任何判断、推理、验证 - 完全信任 LLM 的决策
        """
```

### filled_data.json 结构

```json
{
  "project_region": "华北",
  "monthly_data": [
    {
      "month": 1,
      "total_energy": 20.7948,
      "chiller_supply_temp": 7.0,
      "_filled_fields": []
    },
    {
      "month": 4,
      "total_energy": 18.5,
      "chiller_supply_temp": 8.2,
      "_filled_fields": ["chiller_supply_temp"]
    }
  ],
  "_metadata": {
    "fill_timestamp": "2025-12-17T10:30:00",
    "fill_count": 5,
    "original_completeness": 0.75,
    "final_completeness": 1.0
  }
}
```

---

## 五、Excel 计算引擎实现

### excel_calculator.py 实现

```python
class ExcelCalculator:
    def __init__(self, template_path: str):
        """
        template_path: 00_sample/机房智能化节能评估表-按冷站电量数据.xlsx
        """
        self.template = template_path

    def calculate(self, filled_data_path: str, output_path: str) -> str:
        """
        输入: tmp/filled_data.json
        输出: tmp/result_data.json

        步骤:
        1. 读取 filled_data.json
        2. 复制模板到 tmp/calculation_result.xlsx
        3. 将数据回填到对应单元格
        4. 触发 Excel 重新计算 (使用 xlwings)
        5. 提取结果数据,保存到 result_data.json
        6. 返回结果文件路径
        """
```

### 数据回填映射表 (config/cell_mapping.py)

```python
CELL_MAPPING = {
    # 基础信息
    "basic_info.city": "Sheet2!B5",
    "basic_info.building_area": "Sheet2!B6",

    # 月度数据 (行号动态计算)
    "monthly_data[{i}].total_energy": "Sheet1!{col}27",  # col: D-O
    "monthly_data[{i}].chiller_supply_temp": "Sheet1!{col}9",
    "monthly_data[{i}].cooling_pump_freq": "Sheet1!{col}13",
    "monthly_data[{i}].cooling_water_temp_diff": "Sheet1!{col}14",
    "monthly_data[{i}].freezing_pump_freq": "Sheet1!{col}18",
    "monthly_data[{i}].freezing_water_temp_diff": "Sheet1!{col}19",
    "monthly_data[{i}].cooling_tower_outlet_temp": "Sheet1!{col}23",
}

# 结果提取位置
RESULT_EXTRACT_MAPPING = {
    "chiller_saving_total": "Sheet2!P11",
    "cooling_pump_saving_total": "Sheet2!P16",
    "freezing_pump_saving_total": "Sheet2!P21",
    "tower_saving_total": "Sheet2!P25",
    "total_saving": "Sheet2!P28",
    "saving_rate": "Sheet2!P29",
}
```

### Excel 计算引擎选择

**方案 A: xlwings** (推荐)
- 需要本地安装 Excel/LibreOffice
- 支持完整公式计算
- 公式已验证,完全兼容

### 结果提取

从计算后的 Excel 中提取并保存到 `result_data.json`:
```json
{
  "energy_saving_rate": 0.1523,
  "energy_saving_rate_min": 0.1218,
  "energy_saving_rate_max": 0.1828,
  "chiller_saving": 12.5,
  "pump_saving": 3.2,
  "tower_saving": 1.8,
  "total_saving": 17.5,
  "monthly_breakdown": [...],
  "completeness": 0.95,
  "filled_count": 5
}
```

---

## 六、Streamlit UI 流程设计

### 主应用结构

```python
# app.py
import streamlit as st

# 页面配置
st.set_page_config(page_title="空调节能率智能测算工具", layout="wide")

# 流程状态管理
if 'stage' not in st.session_state:
    st.session_state.stage = 'upload'
    # upload -> extract -> quality -> filling -> calculate -> result
```

### UI 流程分阶段

**阶段1: 上传调研表**
- 文件上传组件
- 保存到 `tmp/upload_survey.xlsx`
- 点击"开始分析"按钮 → 转到阶段2

**阶段2: 数据提取** (自动流转)
- 调用 Skill 1
- 展示提取结果 JSON
- 自动转到阶段3

**阶段3: 质量检查** (仅展示,自动流转)
- 调用 Skill 2
- 展示:
  - 数据完整率指标卡
  - 置信水平指标卡
  - 问题列表(severity + message)
- 自动转到阶段4

**阶段4: 填充建议** (需要用户确认)
- 调用 Skill 3
- 如果 `can_proceed = false`:
  - 显示错误,列出 unfillable_fields
  - 提示"必须补充关键数据,中断流程"
  - 提供"重新上传"按钮
- 否则:
  - 表格展示所有 fillable_suggestions
  - "✅ 确认所有填充建议,开始计算"按钮
  - "❌ 取消,重新上传"按钮

**阶段5: 执行填充和计算** (自动执行)
- 调用 data_filler.py
- 调用 excel_calculator.py
- 显示进度提示
- 自动转到阶段6

**阶段6: 结果展示**
- 核心指标:
  ```python
  st.metric("预估节能率", f"{result['energy_saving_rate_min']*100:.2f}% ~ {result['energy_saving_rate_max']*100:.2f}%")
  ```
- 分项节能量明细表格
- 置信度说明
- 下载完整计算表格:
  - 输入管理员密码
  - 验证通过后提供下载按钮
  - 验证失败显示错误
- "🔄 开始新的测算"按钮

### 状态管理

使用 `st.session_state.stage` 管理流程:
- 阶段2、3自动流转
- 阶段4需要用户确认
- 阶段5、6自动执行

---

## 七、错误处理和边界情况

### Skill 调用失败处理

```python
def call_skill_safely(skill_name: str, *args, timeout: int = 300):
    """
    安全调用 Skill,带超时和错误处理
    """
    try:
        result = subprocess.run(
            ['claude', 'skill', skill_name, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True
        )
        return result.stdout

    except subprocess.TimeoutExpired:
        st.error(f"⏱️ {skill_name} 执行超时(>{timeout}秒),请重试或联系管理员")
        st.stop()
    except Exception as e:
        st.error(f"❌ {skill_name} 执行出错: {str(e)}")
        st.stop()
```

### 关键错误场景

**场景1: 上传的不是标准调研表**
- Skill 1 利用 LLM 理解能力尝试识别
- 如果找不到必需数据,返回 error 标记
- UI 显示: "未能识别调研表中的月度运行数据,请确认上传了正确的文件"

**场景2: 数据完全缺失**
- Skill 2 检测完整率 < 30%
- 质量报告标记"数据不足,无法测算"
- UI 拒绝继续

**场景3: xlwings 环境异常**
- 启动时检测 xlwings 可用性
- 计算失败时保存中间文件到 `tmp/error_calc.xlsx`
- 提示: "Excel 计算失败,中间文件已保存便于调试"

### 错误处理原则

- 所有外部调用(subprocess、文件IO、Excel操作)都要 try-catch
- 错误信息对用户友好,提供解决建议
- 保存中间结果便于调试
- 在 UI 层统一处理错误,避免页面崩溃

---

## 八、项目目录结构

```
conditioner_saving/
├── .streamlit/
│   ├── config.toml           # Streamlit 远程访问配置
│   └── secrets.toml          # 管理员密码(不提交git)
├── .claude/
│   └── skills/               # 自定义 Skills
│       ├── extract-survey-data.md
│       ├── check-data-quality.md
│       └── suggest-data-filling.md
├── 00_sample/                # 示例文件
│   ├── 机房智能化节能评估表-按冷站电量数据.xlsx
│   └── 02-中央空调节能调研表.xlsx
├── 01_idea/
├── 02_prd/
├── 03_plan/
│   └── 技术方案详细设计-LLM混合架构.md
├── docs/
├── tmp/                      # 临时文件目录(git忽略)
│   ├── upload_survey.xlsx
│   ├── extracted_data.json
│   ├── quality_report.json
│   ├── filling_suggestions.json
│   ├── filled_data.json
│   ├── calculation_result.xlsx
│   └── result_data.json
├── core/                     # 核心业务逻辑
│   ├── __init__.py
│   ├── data_filler.py       # 数据填充执行器
│   ├── excel_calculator.py  # Excel 计算引擎
│   └── skill_caller.py      # Skill 调用封装
├── config/
│   ├── __init__.py
│   └── cell_mapping.py      # Excel 单元格映射关系
├── tests/                    # 测试文件
│   ├── fixtures/            # 测试数据
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── app.py                    # Streamlit 主应用
├── requirements.txt
├── .gitignore
└── README.md
```

**注意**: 目录结构后续可能调整

---

## 九、部署和运行要求

### 环境依赖

**系统依赖**:
```bash
# Linux 服务器: 安装 LibreOffice
sudo apt-get update
sudo apt-get install libreoffice  # Ubuntu/Debian
```

**Python 依赖**:
```txt
streamlit>=1.28.0
pandas>=2.0.0
openpyxl>=3.1.0
xlwings>=0.30.0
```

### 服务器配置

**1. Streamlit 远程访问配置**

`.streamlit/config.toml`:
```toml
[server]
port = 8501
address = "0.0.0.0"  # 允许所有IP访问
headless = true      # 服务器模式
enableCORS = false
enableXsrfProtection = true
```

**2. 管理员密码配置**

`.streamlit/secrets.toml`:
```toml
admin_password = "your_secure_password"
```

**3. 防火墙开放端口**:
```bash
sudo ufw allow 8501/tcp
```

### 启动应用

**后台运行**:
```bash
nohup streamlit run app.py > logs/streamlit.log 2>&1 &
```

**systemd 服务** (推荐):
```ini
[Unit]
Description=Air Conditioner Energy Saving Calculator
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/conditioner_saving
ExecStart=/usr/bin/streamlit run app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### 访问地址

```
http://服务器IP:8501
```

### 性能预期

- 单次测算耗时: 约 30-60 秒
- 支持多用户并发访问
- 每个用户独立 session

---

## 十、开发策略

### 开发阶段

**阶段1: 基础设施** (1-2天)
- 项目目录结构
- Streamlit 环境配置
- tmp/ 目录管理

**阶段2: Skills 开发** (3-5天)
- Skill 1: extract-survey-data
- Skill 2: check-data-quality
- Skill 3: suggest-data-filling (填充策略暂时占位)
- 用真实数据测试优化

**阶段3: Excel 计算引擎** (2-3天)
- cell_mapping.py
- excel_calculator.py
- 验证计算精度 ≤2%

**阶段4: 数据填充模块** (1天)
- data_filler.py
- 单元测试

**阶段5: UI 集成** (3-4天)
- 实现 6 个阶段的 UI
- 流程状态管理
- 端到端打通

**阶段6: 错误处理和完善** (2-3天)
- 统一错误处理
- 边界情况
- 用户体验优化

**阶段7: 部署上线** (1-2天)
- 服务器环境配置
- 真实数据验收测试

**总计**: 15-20 个工作日

### 开发优先级原则

1. **核心链路优先**: 先打通最简流程
2. **Skills 独立验证**: 每个 Skill 单独测试通过才集成
3. **计算精度优先**: Excel 计算精度是核心指标
4. **UI 最后集成**: 核心模块稳定后再集成

### 关键风险

**风险1: Skill 提取准确率不足**
- 应对: 准备多份真实调研表测试,迭代优化 prompt
- 后备: 降级为手工映射规则

**风险2: xlwings 在 Linux 兼容性问题**
- 应对: 提前在目标服务器验证环境
- 后备: 考虑 Docker 容器

**风险3: Skill 3 填充策略难以实现**
- 应对: 先用简单规则占位,单独排期优化
- 后备: 编写规则引擎

---

## 十一、测试策略

### 测试层次

```
端到端测试 (E2E)
    ↑
集成测试 (Integration)
    ↑
单元测试 (Unit)
```

### 关键测试点

**单元测试**:
1. **data_filler.py**
   - 填充不覆盖已有数据
   - 正确标记 `_filled_fields`
   - 元数据记录准确

2. **excel_calculator.py**
   - 计算精度偏差 ≤2%
   - 单元格映射位置正确
   - 地区气象数据匹配正确

3. **cell_mapping.py**
   - 映射表包含所有必需字段

**集成测试**:
1. **Skills Pipeline**
   - Skill 1 → Skill 2 → Skill 3 数据流转正确
   - unfillable 字段正确标记并中断流程
   - 完整流程: 上传 → 计算 → 结果(节能率在 5%-35% 合理范围)

2. **UI Workflow**
   - 文件上传成功保存到 tmp/
   - 质量报告正确展示
   - 管理员密码验证有效

**端到端测试**:
1. **完整数据场景**: 无需填充,直接计算成功
2. **部分缺失场景**: 填充建议合理,用户确认后计算成功
3. **关键缺失场景**: 返回 can_proceed=false,UI 中断流程
4. **错误格式场景**: Skill 1 识别错误,友好提示
5. **多用户并发**: session 隔离,无数据混淆

### 测试数据准备

```
tests/fixtures/
├── complete_survey.xlsx          # 完整数据
├── partial_survey.xlsx           # 部分缺失
├── critical_missing_survey.xlsx  # 关键字段缺失
└── expected_result.json          # 预期计算结果(手工Excel计算)
```

### 性能基准

- 单次完整流程: < 60秒
- 支持 5 用户并发访问
- tmp/ 目录自动清理旧文件

### 覆盖率目标

- 单元测试覆盖率: ≥80%
- 关键模块(data_filler, excel_calculator): 100%

---

## 附录: 待定事项

1. **Skill 3 填充策略**: 具体的 LLM 推理规则需要后续设计确认
2. **项目目录结构**: 后续可能调整
3. **tmp/ 文件清理策略**: 需要确定清理时机和规则
4. **日志记录**: 需要设计日志格式和存储策略

---

**设计完成日期**: 2025-12-17
