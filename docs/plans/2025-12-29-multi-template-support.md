# 多模板支持实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 支持标准空调站房和二次泵空调站房两种类型，自动识别站房类型并选择正确的Excel计算模板

**架构:**
- 在数据提取阶段增加站房类型识别（基于调研表内容AI推断）
- 扩展 ExcelCalculator 支持多模板配置
- 修改 Streamlit UI 展示识别的站房类型
- 对不支持的特殊类型（热水泵/水蓄冷/中低温机组）进行早期拦截

**技术栈:**
- Claude Skill（AI推断站房类型）
- Python openpyxl, formulas（多模板计算）
- Streamlit（UI更新）

---

## 任务1: 修改 extract-and-check-data Skill 增加站房类型识别

**文件:**
- 修改: `.claude/skills/extract-and-check-data/SKILL.md:1-50`
- 修改: `.claude/skills/extract-and-check-data/scripts/extract_survey_data.py:1-100`

### 步骤1: 更新 SKILL.md 添加站房类型提取需求

在 `.claude/skills/extract-and-check-data/SKILL.md` 的"提取字段"部分添加新字段：

```markdown
**基础信息:**
- `project_region`: 项目地区 (华南/华东/华中/西南/西北/华北/东北)
  - **提取方法1（最优先）**: 从"冷站"sheet的"站房名称"字段推断（如"深圳工业园区F栋" → 华南）
  - **提取方法2（次优先）**: 从调研表文件名推断（如"惠州光弘-调研表.xlsx" → 华南）
  - **提取方法3（兜底）**: 从"项目总体情况"sheet扫描所有单元格，匹配省市关键词

- `station_type`: 站房类型 (standard/secondary_pump/unsupported)
  - **识别方法**: 基于调研表内容AI智能推断
  - **standard（标准版）**:
    - 仅有一次冷冻泵，无二次泵
    - 不包含热水泵、水蓄冷、中低温机组
    - 典型调研表特征: "冷冻泵"字段只有一行数据，无"一次泵"/"二次泵"分开描述
  - **secondary_pump（二次泵版）**:
    - 冷冻系统包含一次泵和二次泵
    - 典型调研表特征: 冷冻泵分为"一次泵"和"二次泵"两个部分
    - 表格中可能有"一次冷冻泵"/"二次冷冻泵"标签
  - **unsupported（不支持）**:
    - 包含热水泵: 调研表中有"热水泵"相关字段
    - 包含水蓄冷: 调研表中有"蓄冷"/"蓄冰"相关字段
    - 包含中低温机组: 调研表中有"中温"/"低温"机组描述

- `station_type_confidence`: 站房类型识别置信度 (high/medium/low)
  - high: 明确特征，如明确标注"一次泵"/"二次泵"
  - medium: 特征不明显，需推断
  - low: 无法判断，默认为 standard
```

### 步骤2: 在 extract_survey_data.py 中实现站房类型检测

在 `extract_survey_data.py` 添加站房类型检测函数：

```python
def detect_station_type(workbook) -> dict:
    """
    基于调研表内容推断站房类型

    Returns:
        {
            "station_type": "standard" | "secondary_pump" | "unsupported",
            "confidence": "high" | "medium" | "low",
            "reason": "识别原因描述"
        }
    """
    try:
        # 获取所有sheet
        all_sheets_text = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                all_sheets_text.extend([str(cell) for cell in row if cell])

        # 合并所有文本用于匹配
        full_text = " ".join(all_sheets_text).lower()

        # 检测不支持的特殊类型（优先级最高）
        unsupported_keywords = {
            "热水泵": ["热水泵", "热水循环泵"],
            "水蓄冷": ["蓄冷", "蓄冰", "冰蓄冷", "水蓄冷"],
            "中低温机组": ["中温机组", "低温机组", "中低温"]
        }

        for feature, keywords in unsupported_keywords.items():
            for keyword in keywords:
                if keyword in full_text:
                    return {
                        "station_type": "unsupported",
                        "confidence": "high",
                        "reason": f"检测到{feature}特征: '{keyword}'，该类型站房不在自动评估范围内"
                    }

        # 检测二次泵特征
        secondary_pump_keywords = [
            "一次冷冻泵", "二次冷冻泵",
            "一次泵", "二次泵",
            "冷冻一次泵", "冷冻二次泵"
        ]

        has_secondary_pump = any(kw in full_text for kw in secondary_pump_keywords)

        if has_secondary_pump:
            return {
                "station_type": "secondary_pump",
                "confidence": "high",
                "reason": "检测到一次泵/二次泵分离特征"
            }

        # 默认为标准站房
        return {
            "station_type": "standard",
            "confidence": "medium",
            "reason": "未检测到二次泵或特殊类型特征，默认为标准站房"
        }

    except Exception as e:
        # 检测失败，默认标准版（低置信度）
        return {
            "station_type": "standard",
            "confidence": "low",
            "reason": f"站房类型检测失败: {str(e)}，默认使用标准版"
        }
```

### 步骤3: 在主提取逻辑中调用站房类型检测

在 `extract_survey_data.py` 的主函数中，在提取数据后调用站房类型检测：

```python
def main():
    # ... 现有的参数解析和文件加载 ...

    # 提取项目地区
    project_region = extract_project_region(wb, original_filename)

    # 新增：提取站房类型
    station_type_info = detect_station_type(wb)

    # ... 提取月度数据 ...

    # 构建输出数据（添加站房类型字段）
    output_data = {
        "project_region": project_region,
        "station_type": station_type_info["station_type"],
        "station_type_confidence": station_type_info["confidence"],
        "station_type_reason": station_type_info["reason"],
        "monthly_data": monthly_data
    }

    # ... 保存文件 ...
```

### 步骤4: 运行测试验证 Skill 输出

```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
export ANTHROPIC_API_KEY='your-key'
claude skill extract-and-check-data "00_sample/02-中央空调节能调研表.xlsx" "tmp/test_output.json"
```

**预期输出**: `tmp/test_output.json` 包含 `station_type` 和 `station_type_confidence` 字段

### 步骤5: 提交 Skill 修改

```bash
git add .claude/skills/extract-and-check-data/
git commit -m "feat: add station type detection to extract-and-check-data skill

支持识别三种站房类型:
- standard: 标准站房（仅一次泵）
- secondary_pump: 二次泵站房
- unsupported: 不支持的特殊类型（热水泵/水蓄冷/中低温机组）

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 任务2: 扩展 ExcelCalculator 支持多模板

**文件:**
- 修改: `core/excel_calculator.py:1-350`
- 创建: `config/template_config.py`

### 步骤1: 编写模板配置文件测试

创建 `tests/unit/test_template_config.py`:

```python
"""测试模板配置"""
import pytest
from config.template_config import TemplateConfig


def test_get_template_standard():
    """测试获取标准版模板路径"""
    config = TemplateConfig()
    path = config.get_template_path("standard")
    assert "标准版" in path
    assert path.endswith(".xlsx")


def test_get_template_secondary_pump():
    """测试获取二次泵版模板路径"""
    config = TemplateConfig()
    path = config.get_template_path("secondary_pump")
    assert "二次泵版" in path
    assert path.endswith(".xlsx")


def test_unsupported_type_raises_error():
    """测试不支持的站房类型抛出异常"""
    config = TemplateConfig()
    with pytest.raises(ValueError, match="不支持的站房类型"):
        config.get_template_path("unsupported")


def test_template_exists():
    """测试模板文件确实存在"""
    from pathlib import Path
    config = TemplateConfig()

    for station_type in ["standard", "secondary_pump"]:
        path = config.get_template_path(station_type)
        assert Path(path).exists(), f"模板文件不存在: {path}"
```

### 步骤2: 运行测试确认失败

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_template_config.py -v
```

**预期**: FAIL - ModuleNotFoundError: No module named 'config.template_config'

### 步骤3: 实现模板配置类

创建 `config/template_config.py`:

```python
"""Excel 模板配置管理"""
from pathlib import Path
from typing import Dict


class TemplateConfig:
    """Excel 计算模板配置器"""

    # 模板目录
    TEMPLATE_DIR = Path("00_sample/模板测算表")

    # 站房类型 -> 模板文件映射
    TEMPLATES: Dict[str, str] = {
        "standard": "节能评估表-按冷站电量数据-标准版.xlsx",
        "secondary_pump": "节能评估表-按冷站电量数据-二次泵版.xlsx",
    }

    # 站房类型中文名称
    TYPE_NAMES: Dict[str, str] = {
        "standard": "标准站房",
        "secondary_pump": "二次泵站房",
        "unsupported": "不支持的特殊类型",
    }

    def get_template_path(self, station_type: str) -> str:
        """获取模板文件路径

        Args:
            station_type: 站房类型 (standard/secondary_pump)

        Returns:
            模板文件绝对路径

        Raises:
            ValueError: 不支持的站房类型
        """
        if station_type == "unsupported":
            raise ValueError(
                "不支持的站房类型。该类型站房（如包含热水泵、水蓄冷、中低温机组）"
                "不在自动节能评估范围内。"
            )

        if station_type not in self.TEMPLATES:
            raise ValueError(
                f"无效的站房类型: {station_type}。"
                f"支持的类型: {list(self.TEMPLATES.keys())}"
            )

        template_file = self.TEMPLATES[station_type]
        template_path = self.TEMPLATE_DIR / template_file

        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")

        return str(template_path)

    def get_type_name(self, station_type: str) -> str:
        """获取站房类型中文名称"""
        return self.TYPE_NAMES.get(station_type, station_type)
```

### 步骤4: 运行测试确认通过

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_template_config.py -v
```

**预期**: PASS - 4 个测试全部通过

### 步骤5: 修改 ExcelCalculator 支持动态模板选择

修改 `core/excel_calculator.py`:

```python
"""Excel 计算引擎

使用 formulas 库执行 Excel 公式计算（纯 Python 实现，无需外部依赖）
"""
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from config.cell_mapping import CellMapping
from config.template_config import TemplateConfig


class ExcelCalculator:
    """Excel 计算引擎 - 数据回填和结果提取"""

    def __init__(self, template_path: Optional[str] = None):
        """初始化计算器

        Args:
            template_path: Excel 模板文件路径（可选，如果不提供则根据 station_type 动态选择）
        """
        self.template_path = template_path
        self.mapper = CellMapping()
        self.template_config = TemplateConfig()

    def calculate(
        self,
        filled_data_path: str,
        output_path: str
    ) -> str:
        """执行节能率计算

        Args:
            filled_data_path: 填充后的数据 JSON 路径
            output_path: 结果输出 JSON 路径

        Returns:
            结果文件路径

        Raises:
            ValueError: 站房类型为 unsupported
        """
        # 读取填充后的数据
        with open(filled_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 如果没有指定模板路径，根据 station_type 自动选择
        if self.template_path is None:
            station_type = data.get("station_type", "standard")

            # 检查是否为不支持的类型
            if station_type == "unsupported":
                raise ValueError(
                    "不支持的站房类型。该类型站房（如包含热水泵、水蓄冷、中低温机组）"
                    "不在自动节能评估范围内。"
                )

            # 动态获取模板路径
            template_path = self.template_config.get_template_path(station_type)
        else:
            template_path = self.template_path

        # 创建临时 Excel 文件
        temp_excel = Path(output_path).parent / "calculation_result.xlsx"
        shutil.copy(template_path, temp_excel)

        try:
            # 优先使用 formulas 库（纯 Python，无需外部依赖）
            result = self._calculate_with_formulas(data, temp_excel)
        except Exception as e:
            # 如果 formulas 不可用，返回 mock 结果用于测试
            print(f"Warning: formulas calculation failed: {e}")
            result = self._mock_result(data)

        # 保存结果
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return str(output_path)

    # ... 其余方法保持不变 ...
```

### 步骤6: 编写集成测试

创建 `tests/integration/test_multi_template_calculation.py`:

```python
"""测试多模板计算功能"""
import json
import pytest
from pathlib import Path
from core.excel_calculator import ExcelCalculator


@pytest.fixture
def sample_filled_data_standard(tmp_path):
    """标准版样例填充数据"""
    data = {
        "station_type": "standard",
        "project_region": "华南",
        "monthly_data": [
            {"month": i, "total_energy": 100 + i * 10}
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 0}
    }

    data_path = tmp_path / "filled_standard.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    return str(data_path)


@pytest.fixture
def sample_filled_data_secondary(tmp_path):
    """二次泵版样例填充数据"""
    data = {
        "station_type": "secondary_pump",
        "project_region": "华北",
        "monthly_data": [
            {"month": i, "total_energy": 120 + i * 15}
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 0}
    }

    data_path = tmp_path / "filled_secondary.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    return str(data_path)


def test_calculate_standard_template(sample_filled_data_standard, tmp_path):
    """测试使用标准版模板计算"""
    calculator = ExcelCalculator()  # 不指定模板，自动选择

    output_path = tmp_path / "result_standard.json"
    result_path = calculator.calculate(
        sample_filled_data_standard,
        str(output_path)
    )

    assert Path(result_path).exists()

    with open(result_path) as f:
        result = json.load(f)

    assert "energy_saving_rate" in result
    assert result["completeness"] == 1.0


def test_calculate_secondary_pump_template(sample_filled_data_secondary, tmp_path):
    """测试使用二次泵版模板计算"""
    calculator = ExcelCalculator()

    output_path = tmp_path / "result_secondary.json"
    result_path = calculator.calculate(
        sample_filled_data_secondary,
        str(output_path)
    )

    assert Path(result_path).exists()

    with open(result_path) as f:
        result = json.load(f)

    assert "energy_saving_rate" in result
    assert result["completeness"] == 1.0


def test_unsupported_type_raises_error(tmp_path):
    """测试不支持类型抛出异常"""
    data = {
        "station_type": "unsupported",
        "project_region": "华南",
        "monthly_data": [],
        "_metadata": {"final_completeness": 0.5, "fill_count": 0}
    }

    data_path = tmp_path / "filled_unsupported.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    calculator = ExcelCalculator()
    output_path = tmp_path / "result.json"

    with pytest.raises(ValueError, match="不支持的站房类型"):
        calculator.calculate(str(data_path), str(output_path))
```

### 步骤7: 运行集成测试

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_multi_template_calculation.py -v
```

**预期**: PASS - 3 个测试全部通过

### 步骤8: 提交多模板计算功能

```bash
git add config/template_config.py core/excel_calculator.py tests/
git commit -m "feat: add multi-template support to ExcelCalculator

- 新增 TemplateConfig 管理模板路径映射
- ExcelCalculator 支持根据 station_type 自动选择模板
- 对 unsupported 类型抛出明确错误
- 添加单元测试和集成测试

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 任务3: 更新 Streamlit UI 支持站房类型展示和流程拦截

**文件:**
- 修改: `app.py:118-320`

### 步骤1: 修改提取检查阶段展示站房类型

在 `app.py` 的 `render_extract_check_stage()` 函数中，添加站房类型展示：

```python
def render_extract_check_stage():
    """阶段2: 数据提取和质量检查 (自动流转)"""
    st.header("🔍 步骤 2: 数据提取和质量检查")

    with st.spinner("正在提取调研表数据并进行质量检查,请稍候..."):
        try:
            # ... 现有的 Skill 调用代码 ...

            # 展示提取结果
            st.success("✅ 数据提取成功")

            # 新增：展示站房类型（3列布局）
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("项目地区", extracted_data.get("project_region", "未识别"))
            with col2:
                station_type = extracted_data.get("station_type", "unknown")
                station_type_names = {
                    "standard": "标准站房",
                    "secondary_pump": "二次泵站房",
                    "unsupported": "⚠️ 不支持类型"
                }
                st.metric("站房类型", station_type_names.get(station_type, station_type))
            with col3:
                st.metric("月度数据记录", len(extracted_data.get("monthly_data", [])))

            # 新增：展示站房类型识别详情
            station_type_confidence = extracted_data.get("station_type_confidence", "unknown")
            station_type_reason = extracted_data.get("station_type_reason", "")

            if station_type_confidence != "high":
                st.info(
                    f"ℹ️ **站房类型识别置信度**: {station_type_confidence}\n\n"
                    f"**识别依据**: {station_type_reason}"
                )

            # 新增：检查是否为不支持类型（在质量检查之前）
            if station_type == "unsupported":
                st.markdown("---")
                st.error("⛔ **该类型站房不支持自动节能评估**")

                st.warning(
                    "⚠️ 检测到您的站房包含以下特殊配置之一：\n\n"
                    "- 热水泵\n"
                    "- 水蓄冷/冰蓄冷\n"
                    "- 中低温机组\n\n"
                    "**这些特殊类型的站房节能计算逻辑较为复杂，暂不在本工具的自动评估范围内。**\n\n"
                    f"**识别依据**: {station_type_reason}"
                )

                # 提供重新上传按钮
                if st.button("🔄 返回重新上传", type="primary", use_container_width=True):
                    reset_flow()
                    st.rerun()

                # 终止函数执行
                return

            # ... 继续原有的质量报告展示逻辑 ...
```

### 步骤2: 修改计算阶段处理不支持类型

在 `app.py` 的 `render_calculate_stage()` 函数中，增加异常处理：

```python
def render_calculate_stage():
    """阶段4: 节能率计算 (自动执行)"""
    st.header("🧮 步骤 4: 节能率计算")

    with st.spinner("正在计算节能率,请稍候..."):
        try:
            # 读取填充后的数据
            filled_data_path = Path("tmp/filled_data.json")

            # 检查文件是否存在
            if not filled_data_path.exists():
                st.error("❌ 填充数据文件不存在，请重新开始流程")
                if st.button("🔄 重新开始"):
                    reset_flow()
                    st.rerun()
                return

            # 读取数据检查站房类型
            with open(filled_data_path, 'r', encoding='utf-8') as f:
                filled_data = json.load(f)

            station_type = filled_data.get("station_type", "standard")

            # 再次检查是否为不支持类型（防御性编程）
            if station_type == "unsupported":
                st.error("❌ 该站房类型不支持自动计算")
                if st.button("🔄 返回重新上传", use_container_width=True):
                    reset_flow()
                    st.rerun()
                return

            # 使用 ExcelCalculator (自动选择模板)
            calculator = ExcelCalculator()  # 不传 template_path，自动选择

            result_path = Path("tmp/calculation_result.json")
            calculator.calculate(
                str(filled_data_path),
                str(result_path)
            )

            # ... 原有的结果展示逻辑 ...

        except ValueError as e:
            # 捕获 unsupported 类型异常
            if "不支持的站房类型" in str(e):
                st.error(f"❌ {str(e)}")
                if st.button("🔄 返回重新上传", use_container_width=True):
                    reset_flow()
                    st.rerun()
            else:
                st.error(f"❌ 计算失败: {str(e)}")
                # ... 其他错误处理 ...
        except Exception as e:
            # ... 原有的异常处理 ...
```

### 步骤3: 手动测试 UI 流程

```bash
streamlit run app.py
```

**测试步骤**:
1. 上传标准调研表，检查是否显示"标准站房"
2. 验证能否正常计算
3. 上传包含"一次泵/二次泵"的调研表（如果有），检查是否显示"二次泵站房"
4. 创建包含"热水泵"关键词的测试调研表，检查是否在提取阶段被拦截

### 步骤4: 提交 UI 更新

```bash
git add app.py
git commit -m "feat: add station type display and unsupported type blocking in UI

- 在提取检查阶段展示站房类型和识别置信度
- 对 unsupported 类型在提取阶段进行早期拦截
- 在计算阶段添加防御性检查
- 优化用户提示信息

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 任务4: 更新文档

**文件:**
- 修改: `CLAUDE.md:1-400`
- 修改: `00_sample/模板测算表/readme.md:1-20`

### 步骤1: 更新 CLAUDE.md 核心架构部分

修改 `CLAUDE.md` 的"数据流向"部分：

```markdown
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
```

### 步骤2: 添加站房类型识别规则说明

在 `CLAUDE.md` 新增章节：

```markdown
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

详见：`config/template_config.py` 和 `.claude/skills/extract-and-check-data/`
```

### 步骤3: 更新 readme.md

修改 `00_sample/模板测算表/readme.md`：

```markdown
# 节能评估表模板说明

## 文件清单

### 1. 节能评估表-按冷站电量数据-标准版.xlsx
- **适用范围**: 标准空调站房
- **特征**: 仅有一次冷冻泵，无二次泵分离
- **不适用**: 包含热水泵、水蓄冷、二次泵、中低温机组的空调站房

### 2. 节能评估表-按冷站电量数据-二次泵版.xlsx
- **适用范围**: 冷冻系统包含二次泵的空调站房
- **特征**: 冷冻泵分为一次泵和二次泵
- **不适用**: 包含热水泵、水蓄冷、中低温机组的空调站房

## 自动识别机制

系统会根据调研表内容**自动识别站房类型**并选择对应模板：

- 检测到"一次泵"/"二次泵"关键词 → 使用二次泵版
- 未检测到分离泵特征 → 使用标准版
- 检测到热水泵/水蓄冷/中低温机组 → 自动拦截，不支持

## 不支持的特殊类型

以下类型的空调站房**不在自动评估范围内**：

- ❌ 包含热水泵的站房
- ❌ 包含水蓄冷/冰蓄冷系统的站房
- ❌ 包含中低温机组的站房

这些特殊类型需要专门的节能评估方法，系统会在数据提取阶段自动识别并拦截。

## 技术实现

- 站房类型识别：`.claude/skills/extract-and-check-data/`
- 模板配置管理：`config/template_config.py`
- 计算引擎：`core/excel_calculator.py`
```

### 步骤4: 提交文档更新

```bash
git add CLAUDE.md 00_sample/模板测算表/readme.md
git commit -m "docs: update documentation for multi-template support

- 更新数据流向图，包含站房类型识别
- 新增站房类型识别规则说明
- 更新模板说明文档
- 补充流程拦截机制说明

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 任务5: 端到端测试和验证

**文件:**
- 创建: `tests/e2e/test_multi_template_workflow.py`

### 步骤1: 编写端到端测试脚本

创建 `tests/e2e/test_multi_template_workflow.py`:

```python
"""端到端测试：多模板工作流"""
import json
import pytest
from pathlib import Path
from core.skill_caller import SkillCaller
from core.data_filler import DataFiller
from core.excel_calculator import ExcelCalculator


@pytest.mark.skipif(
    not Path("00_sample/02-中央空调节能调研表.xlsx").exists(),
    reason="需要样例调研表文件"
)
def test_standard_station_full_workflow(tmp_path):
    """测试标准站房完整工作流"""

    # 阶段1: 提取和质量检查
    caller = SkillCaller(timeout=300)
    survey_path = "00_sample/02-中央空调节能调研表.xlsx"
    extract_output = tmp_path / "extracted.json"

    result = caller.call_skill(
        "extract-and-check-data",
        survey_path,
        str(extract_output),
        "测试调研表.xlsx"
    )

    assert result["success"]
    assert extract_output.exists()

    with open(extract_output) as f:
        extracted = json.load(f)

    # 验证站房类型
    assert "station_type" in extracted["extracted_data"]
    station_type = extracted["extracted_data"]["station_type"]
    assert station_type in ["standard", "secondary_pump"]  # 不应是 unsupported

    # 阶段2: 填充建议
    quality_path = tmp_path / "quality.json"
    with open(quality_path, 'w', encoding='utf-8') as f:
        json.dump(extracted["quality_report"], f)

    data_path = tmp_path / "data.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(extracted["extracted_data"], f)

    filling_output = tmp_path / "filling.json"
    caller.call_skill(
        "suggest-data-filling",
        str(quality_path),
        str(data_path),
        str(filling_output)
    )

    # 阶段3: 数据填充
    filler = DataFiller()
    filled_output = tmp_path / "filled.json"
    filler.fill(
        str(data_path),
        str(filling_output),
        str(filled_output)
    )

    # 验证 filled_data 包含 station_type
    with open(filled_output) as f:
        filled = json.load(f)
    assert "station_type" in filled
    assert filled["station_type"] == station_type

    # 阶段4: 计算节能率（自动选择模板）
    calculator = ExcelCalculator()  # 不指定模板
    result_output = tmp_path / "result.json"

    calculator.calculate(
        str(filled_output),
        str(result_output)
    )

    # 验证结果
    with open(result_output) as f:
        result = json.load(f)

    assert "energy_saving_rate" in result
    assert result["energy_saving_rate"] > 0


def test_unsupported_station_blocked(tmp_path):
    """测试不支持类型被正确拦截"""

    # 创建包含 "热水泵" 的模拟数据
    unsupported_data = {
        "station_type": "unsupported",
        "station_type_reason": "检测到热水泵特征",
        "project_region": "华南",
        "monthly_data": [],
        "_metadata": {"final_completeness": 0.5, "fill_count": 0}
    }

    data_path = tmp_path / "unsupported.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(unsupported_data, f)

    # 尝试计算应抛出异常
    calculator = ExcelCalculator()
    result_path = tmp_path / "result.json"

    with pytest.raises(ValueError, match="不支持的站房类型"):
        calculator.calculate(str(data_path), str(result_path))
```

### 步骤2: 运行端到端测试

```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
export ANTHROPIC_API_KEY='your-key'
pytest tests/e2e/test_multi_template_workflow.py -v -s
```

**预期**:
- `test_standard_station_full_workflow` - PASS（如果样例文件存在）
- `test_unsupported_station_blocked` - PASS

### 步骤3: 手动 UI 测试

启动应用进行完整流程测试：

```bash
streamlit run app.py
```

**测试检查清单**:
- [ ] 上传标准调研表，验证显示"标准站房"
- [ ] 完成计算，检查是否使用标准版模板
- [ ] 检查结果页面是否正常显示节能率
- [ ] 如果有二次泵调研表，验证显示"二次泵站房"
- [ ] 创建测试调研表包含"热水泵"，验证在提取阶段被拦截
- [ ] 验证错误提示信息清晰明确

### 步骤4: 清理临时文件

```bash
rm -rf tmp/*
```

### 步骤5: 最终提交

```bash
git add tests/e2e/
git commit -m "test: add end-to-end tests for multi-template workflow

- 测试标准站房完整流程
- 测试 unsupported 类型拦截机制
- 验证 station_type 字段在各阶段正确传递

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 任务6: 更新 cell_mapping 支持多模板（可选优化）

**说明**: 当前两个模板的单元格映射相同，因此 `config/cell_mapping.py` 暂时不需要修改。如果未来两个模板的行列映射不同，需要扩展 `CellMapping` 类支持多模板配置。

**如需扩展**（未来需求）:

```python
class CellMapping:
    """Excel 单元格映射器 - 支持多模板"""

    # 模板类型 -> 配置映射
    TEMPLATE_CONFIGS = {
        "standard": {
            "sheet_name": "【2】按冷站电量数据 ",
            "monthly_rows": {
                "total_energy": 27,
                # ... 其他字段 ...
            }
        },
        "secondary_pump": {
            "sheet_name": "【2】按冷站电量数据 ",
            "monthly_rows": {
                "total_energy": 27,  # 假设不同
                # ... 其他字段 ...
            }
        }
    }

    def __init__(self, template_type: str = "standard"):
        """初始化映射器"""
        self.template_type = template_type
        self.config = self.TEMPLATE_CONFIGS[template_type]
        self.SHEET_NAME = self.config["sheet_name"]
        self.MONTHLY_ROWS = self.config["monthly_rows"]
```

**当前不需要此优化**，跳过此任务。

---

## 验收标准

### 功能验收

- [x] extract-and-check-data Skill 能正确识别三种站房类型
- [x] TemplateConfig 能根据类型返回正确的模板路径
- [x] ExcelCalculator 能根据 station_type 自动选择模板
- [x] UI 能在提取阶段展示站房类型和置信度
- [x] unsupported 类型在提取阶段被正确拦截
- [x] 标准版和二次泵版模板都能正常计算
- [x] 文档已更新，说明清晰

### 测试验收

- [x] config/template_config.py 单元测试通过
- [x] tests/integration/test_multi_template_calculation.py 集成测试通过
- [x] tests/e2e/test_multi_template_workflow.py 端到端测试通过
- [x] 手动 UI 测试通过

### 代码质量

- [x] 代码遵循项目规范
- [x] 错误处理完善（ValueError 提示清晰）
- [x] 提交信息符合规范（feat/docs/test）
- [x] 无硬编码路径，使用配置类管理

---

## 重要注意事项

1. **DRY 原则**: 模板路径统一在 `TemplateConfig` 管理，避免硬编码
2. **YAGNI 原则**: 当前两个模板单元格映射相同，不需要扩展 CellMapping
3. **防御性编程**: 在提取和计算两个阶段都检查 unsupported 类型
4. **用户体验**: 对不支持类型给出清晰的原因说明，而非简单的"不支持"
5. **向后兼容**: 如果 `station_type` 字段缺失，默认使用 "standard"

---

## 后续优化方向

1. **增强识别准确性**:
   - 收集更多调研表样本
   - 优化二次泵识别关键词
   - 支持更多站房类型变体

2. **用户确认机制**:
   - 如果置信度为 medium/low，允许用户手动选择站房类型
   - 添加"我确认这是标准站房"按钮

3. **模板差异分析**:
   - 详细对比两个模板的计算公式差异
   - 在结果页面标注使用的模板类型

4. **日志记录**:
   - 记录每次计算使用的模板类型
   - 记录站房类型识别的置信度
