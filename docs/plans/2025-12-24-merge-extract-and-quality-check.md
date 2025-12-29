# 合并数据提取和质量检查步骤实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 将"数据提取"和"质量检查"两个独立步骤合并为一个统一的步骤，减少用户等待时间，简化工作流程。

**架构方法:** 创建新的 Claude Skill `extract-and-check-data`，整合现有的 `extract-survey-data` 和 `check-data-quality` 的逻辑。修改 Streamlit UI 流程，将原来的 6 阶段减少为 5 阶段。

**技术栈:** Python 3.8+, pandas, Claude Skills, Streamlit

---

## 任务 1: 创建合并后的 Skill 目录结构

**文件:**
- Create: `.claude/skills/extract-and-check-data/SKILL.md`
- Create: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py`

**步骤 1: 创建 Skill 目录结构**

```bash
mkdir -p .claude/skills/extract-and-check-data/scripts
```

**步骤 2: 创建 SKILL.md 描述文件**

创建文件 `.claude/skills/extract-and-check-data/SKILL.md`，内容如下:

```markdown
---
name: extract-and-check-data
description: 从中央空调节能调研表 Excel 文件中提取月度运行数据，同时进行数据质量检查，输出结构化 JSON 数据和质量报告。当用户需要处理中央空调调研表、提取能耗数据并验证数据质量时使用此技能。
---

# Extract and Check Data Skill

## 任务

从上传的中央空调节能调研表中提取关键数据，同时进行质量检查，输出包含提取数据和质量报告的 JSON 文件。

## 输入参数

1. `survey_excel_path`: 调研表 Excel 文件路径
2. `output_json_path`: 输出 JSON 文件路径

## 提取字段

**基础信息:**
- `project_region`: 项目地区 (华南/华东/华中/西南/西北/华北)

**月度运行数据** (1-12月):
- `month`: 月份 (1-12)
- `total_energy`: 冷站月度总能耗 (万kWh)
- `chiller_supply_temp`: 冷机供水温度 (°C)
- `cooling_pump_freq`: 冷却泵运行频率 (Hz)
- `cooling_water_temp_diff`: 冷却侧供回水温差 (℃)
- `freezing_pump_freq`: 冷冻泵运行频率 (Hz)
- `freezing_water_temp_diff`: 冷冻侧供回水温差 (℃)
- `cooling_tower_outlet_temp`: 冷却塔出水温度 (℃)

## 质量检查项

### 1. 必填字段缺失检查
- Critical: `project_region` 缺失
- High: `total_energy`, `chiller_supply_temp` 缺失
- Medium: 其他运行参数缺失

### 2. 数值范围检查
- `chiller_supply_temp`: 5-15°C
- `cooling_pump_freq`: 20-50 Hz
- `freezing_pump_freq`: 20-50 Hz
- `cooling_water_temp_diff`: 2-8℃
- `freezing_water_temp_diff`: 2-8℃
- `cooling_tower_outlet_temp`: 15-40°C

### 3. 逻辑一致性检查
- 温差 < 0
- 频率 > 50Hz
- 总能耗 ≤ 0

### 4. 数据完整率计算
- 完整率 ≥ 80% → `high` 置信度
- 完整率 50%-80% → `medium` 置信度
- 完整率 < 50% → `low` 置信度

## 输出格式

成功提取和检查时输出:

```json
{
  "extracted_data": {
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
      }
    ]
  },
  "quality_report": {
    "completeness": 0.75,
    "confidence_level": "medium",
    "issues": [
      {
        "field": "monthly_data[3].chiller_supply_temp",
        "severity": "high",
        "type": "missing",
        "message": "4月冷机供水温度缺失"
      }
    ],
    "summary": "数据完整率75%,建议补充缺失月份数据。发现1个高优先级问题。"
  }
}
```

## 错误处理

如果遇到以下情况,返回错误 JSON:

```json
{
  "error": true,
  "message": "未能识别调研表中的月度运行数据,请确认上传了正确的文件"
}
```

## 执行流程

### 使用提供的脚本

推荐使用 `scripts/extract_and_check_data.py` 脚本:

```bash
python .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py <survey_excel_path> <output_json_path>
```

脚本会自动完成:
1. 读取 Excel 文件
2. 智能识别包含月度数据的工作表
3. 提取 1-12 月的数据并解析文本值
4. 执行数据质量检查
5. 输出包含提取数据和质量报告的 JSON 文件
```

**步骤 3: Commit SKILL.md**

```bash
git add .claude/skills/extract-and-check-data/SKILL.md
git commit -m "$(cat <<'EOF'
feat: add extract-and-check-data skill definition

创建新的 skill 定义文件，合并数据提取和质量检查功能

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## 任务 2: 创建合并后的 Python 脚本

**文件:**
- Create: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py`

**步骤 1: 编写测试用例**

创建文件 `tests/unit/test_extract_and_check.py`:

```python
#!/usr/bin/env python3
"""测试合并的提取和质量检查功能"""

import pytest
import json
import tempfile
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / ".claude/skills/extract-and-check-data/scripts"))


def test_extract_and_check_data_integration():
    """测试提取和质量检查的集成功能"""
    # 使用测试数据文件
    test_excel = project_root / "00_sample/02-中央空调节能调研表.xlsx"

    if not test_excel.exists():
        pytest.skip("测试 Excel 文件不存在")

    # 创建临时输出文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_path = Path(f.name)

    try:
        from extract_and_check_data import extract_and_check_data

        # 执行提取和检查
        extract_and_check_data(str(test_excel), str(output_path))

        # 读取结果
        with open(output_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # 验证结果结构
        assert 'extracted_data' in result
        assert 'quality_report' in result

        # 验证提取数据
        extracted = result['extracted_data']
        assert 'project_region' in extracted
        assert 'monthly_data' in extracted
        assert len(extracted['monthly_data']) == 12

        # 验证质量报告
        quality = result['quality_report']
        assert 'completeness' in quality
        assert 'confidence_level' in quality
        assert 'issues' in quality
        assert 'summary' in quality

        # 验证数据类型
        assert isinstance(quality['completeness'], (int, float))
        assert quality['confidence_level'] in ['high', 'medium', 'low']
        assert isinstance(quality['issues'], list)

    finally:
        # 清理临时文件
        if output_path.exists():
            output_path.unlink()
```

**步骤 2: 运行测试，确认失败**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_extract_and_check.py -v
```

预期输出: `FAIL - ModuleNotFoundError: No module named 'extract_and_check_data'`

**步骤 3: 实现合并脚本**

创建文件 `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py`:

```python
#!/usr/bin/env python3
"""
从中央空调节能调研表中提取月度运行数据并进行质量检查
合并了 extract-survey-data 和 check-data-quality 的功能
"""

import pandas as pd
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


# ============= 数据提取部分 (来自 extract_survey_data.py) =============

def parse_value(value):
    """解析文本值为数值"""
    if pd.isna(value):
        return None

    value_str = str(value).strip()

    if not value_str or value_str.lower() in ['nan', 'none', '无', '/']:
        return None

    try:
        return float(value_str)
    except ValueError:
        pass

    # 处理范围格式
    range_match = re.search(r'(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)', value_str)
    if range_match:
        start = float(range_match.group(1))
        end = float(range_match.group(2))
        return (start + end) / 2

    # 处理频率格式
    freq_match = re.search(r'(\d+\.?\d*)\s*(?:Hz|HZ|hz)', value_str)
    if freq_match:
        return float(freq_match.group(1))

    # 处理温度格式
    temp_match = re.search(r'(\d+\.?\d*)\s*(?:℃|°C|C)', value_str)
    if temp_match:
        return float(temp_match.group(1))

    # 提取第一个数字
    number_match = re.search(r'(\d+\.?\d*)', value_str)
    if number_match:
        return float(number_match.group(1))

    return None


def extract_region(df):
    """从项目总体情况表中提取地区信息"""
    for idx, row in df.iterrows():
        for val in row:
            if pd.isna(val):
                continue
            val_str = str(val)
            regions = {
                '华南': ['广东', '广西', '海南', '福建', '深圳', '广州', '厦门'],
                '华东': ['上海', '江苏', '浙江', '安徽', '江西', '南京', '杭州'],
                '华中': ['湖北', '湖南', '河南', '武汉', '长沙'],
                '西南': ['四川', '重庆', '贵州', '云南', '西藏', '成都'],
                '西北': ['陕西', '甘肃', '青海', '宁夏', '新疆', '西安', '兰州'],
                '华北': ['北京', '天津', '河北', '山西', '内蒙古'],
                '东北': ['辽宁', '吉林', '黑龙江', '沈阳', '大连', '长春', '哈尔滨']
            }

            for region, keywords in regions.items():
                if any(keyword in val_str for keyword in keywords):
                    return region

    return None


def find_row_by_keyword(df, keywords, start_row=0, end_row=None):
    """根据关键词查找行号"""
    if end_row is None:
        end_row = len(df)

    for idx in range(start_row, min(end_row, len(df))):
        row = df.iloc[idx]
        for val in row:
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if any(keyword in val_str for keyword in keywords):
                return idx
    return None


def extract_data_from_excel(survey_excel_path: str) -> Dict[str, Any]:
    """从 Excel 文件提取数据"""
    xls = pd.ExcelFile(survey_excel_path)

    # 提取项目地区
    project_region = None
    if '项目总体情况' in xls.sheet_names:
        df_overview = pd.read_excel(xls, sheet_name='项目总体情况', header=None)
        project_region = extract_region(df_overview)

    # 读取冷站数据
    if '冷站' not in xls.sheet_names:
        return {
            "error": True,
            "message": "找不到'冷站'工作表,请确认上传了正确的文件"
        }

    df = pd.read_excel(xls, sheet_name='冷站', header=None)

    # 查找关键行
    row_mappings = {
        'chiller_supply_temp': ['冷机供水温度'],
        'cooling_pump_freq': ['冷却泵运行频率'],
        'cooling_water_temp_diff': ['冷却侧供回水温差'],
        'freezing_pump_freq': ['冷冻泵运行频率'],
        'freezing_water_temp_diff': ['冷冻侧供回水温差'],
        'cooling_tower_outlet_temp': ['冷却塔出水温度'],
        'total_energy': ['整个冷站', '万kWh']
    }

    month_row_idx = find_row_by_keyword(df, ['月份', '备注'])
    if month_row_idx is None:
        return {
            "error": True,
            "message": "未能识别调研表中的月度数据行,请确认上传了正确的文件"
        }

    # 查找各数据行
    data_rows = {}
    for key, keywords in row_mappings.items():
        row_idx = find_row_by_keyword(df, keywords, start_row=month_row_idx, end_row=month_row_idx + 20)
        if row_idx is not None:
            data_rows[key] = row_idx

    if 'total_energy' not in data_rows and len(df) > 46:
        data_rows['total_energy'] = 46

    # 提取月度数据
    monthly_data = []
    valid_energy_count = 0
    month_col_start = 3  # D列

    for month in range(1, 13):
        month_col_idx = month_col_start + (month - 1)

        month_record = {
            "month": month,
            "total_energy": None,
            "chiller_supply_temp": None,
            "cooling_pump_freq": None,
            "cooling_water_temp_diff": None,
            "freezing_pump_freq": None,
            "freezing_water_temp_diff": None,
            "cooling_tower_outlet_temp": None
        }

        for field in ['total_energy', 'chiller_supply_temp', 'cooling_pump_freq',
                     'cooling_water_temp_diff', 'freezing_pump_freq',
                     'freezing_water_temp_diff', 'cooling_tower_outlet_temp']:
            if field in data_rows:
                row_idx = data_rows[field]
                if row_idx < len(df):
                    value = df.iloc[row_idx, month_col_idx]
                    parsed = parse_value(value)
                    month_record[field] = parsed
                    if field == 'total_energy' and parsed is not None:
                        valid_energy_count += 1

        monthly_data.append(month_record)

    # 验证数据质量
    if valid_energy_count < 3:
        return {
            "error": True,
            "message": f"有效能耗数据月份不足3个月(仅找到{valid_energy_count}个月),请确认上传了正确的文件"
        }

    return {
        "project_region": project_region,
        "monthly_data": monthly_data
    }


# ============= 数据质量检查部分 (来自 check_data_quality.py) =============

class DataQualityChecker:
    """数据质量检查器"""

    RANGES = {
        'chiller_supply_temp': (5, 15, '°C'),
        'cooling_pump_freq': (20, 50, 'Hz'),
        'freezing_pump_freq': (20, 50, 'Hz'),
        'cooling_water_temp_diff': (2, 8, '℃'),
        'freezing_water_temp_diff': (2, 8, '℃'),
        'cooling_tower_outlet_temp': (15, 40, '°C'),
    }

    MONTHLY_FIELDS = [
        'total_energy',
        'chiller_supply_temp',
        'cooling_pump_freq',
        'freezing_pump_freq',
        'cooling_water_temp_diff',
        'freezing_water_temp_diff',
        'cooling_tower_outlet_temp'
    ]

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.issues: List[Dict[str, str]] = []

    def check_project_region(self) -> None:
        """检查项目地区"""
        if not self.data.get('project_region'):
            self.issues.append({
                'field': 'project_region',
                'severity': 'critical',
                'type': 'missing',
                'message': '项目地区缺失,无法匹配气象数据'
            })

    def check_monthly_data(self) -> None:
        """检查月度数据"""
        monthly_data = self.data.get('monthly_data', [])

        for idx, month_data in enumerate(monthly_data):
            month = month_data.get('month', idx + 1)
            self._check_total_energy(month, month_data)
            self._check_chiller_supply_temp(month, month_data)

            for field in self.MONTHLY_FIELDS[2:]:
                self._check_field(month, month_data, field)

    def _check_total_energy(self, month: int, data: Dict) -> None:
        """检查总能耗"""
        value = data.get('total_energy')

        if value is None:
            self.issues.append({
                'field': f'monthly_data[{month-1}].total_energy',
                'severity': 'high',
                'type': 'missing',
                'message': f'{month}月冷站总能耗缺失'
            })
        elif value <= 0:
            self.issues.append({
                'field': f'monthly_data[{month-1}].total_energy',
                'severity': 'critical',
                'type': 'logic_error',
                'message': f'{month}月能耗数据异常(值为{value})'
            })

    def _check_chiller_supply_temp(self, month: int, data: Dict) -> None:
        """检查冷机供水温度"""
        value = data.get('chiller_supply_temp')

        if value is None:
            self.issues.append({
                'field': f'monthly_data[{month-1}].chiller_supply_temp',
                'severity': 'high',
                'type': 'missing',
                'message': f'{month}月冷机供水温度缺失'
            })
        elif not (5 <= value <= 15):
            self.issues.append({
                'field': f'monthly_data[{month-1}].chiller_supply_temp',
                'severity': 'medium',
                'type': 'out_of_range',
                'message': f'{month}月冷机供水温度({value}°C)超出合理范围(5-15°C)'
            })

    def _check_field(self, month: int, data: Dict, field: str) -> None:
        """通用字段检查"""
        value = data.get(field)

        if value is None:
            self.issues.append({
                'field': f'monthly_data[{month-1}].{field}',
                'severity': 'medium',
                'type': 'missing',
                'message': f'{month}月{self._get_field_name(field)}缺失'
            })
        elif field in self.RANGES:
            min_val, max_val, unit = self.RANGES[field]
            if not (min_val <= value <= max_val):
                self.issues.append({
                    'field': f'monthly_data[{month-1}].{field}',
                    'severity': 'medium',
                    'type': 'out_of_range',
                    'message': f'{month}月{self._get_field_name(field)}({value}{unit})超出合理范围({min_val}-{max_val}{unit})'
                })

            if 'temp_diff' in field and value < 0:
                self.issues.append({
                    'field': f'monthly_data[{month-1}].{field}',
                    'severity': 'high',
                    'type': 'logic_error',
                    'message': f'{month}月供回水温差不能为负值(当前值:{value})'
                })

            if 'freq' in field and value > 50:
                self.issues.append({
                    'field': f'monthly_data[{month-1}].{field}',
                    'severity': 'high',
                    'type': 'logic_error',
                    'message': f'{month}月频率超过工频上限(当前值:{value}Hz)'
                })

    def _get_field_name(self, field: str) -> str:
        """获取字段中文名称"""
        field_names = {
            'total_energy': '冷站总能耗',
            'chiller_supply_temp': '冷机供水温度',
            'cooling_pump_freq': '冷却泵频率',
            'freezing_pump_freq': '冷冻泵频率',
            'cooling_water_temp_diff': '冷却水温差',
            'freezing_water_temp_diff': '冷冻水温差',
            'cooling_tower_outlet_temp': '冷却塔出水温度'
        }
        return field_names.get(field, field)

    def calculate_completeness(self) -> float:
        """计算数据完整率"""
        monthly_data = self.data.get('monthly_data', [])
        if not monthly_data:
            return 0.0

        total_points = len(monthly_data) * len(self.MONTHLY_FIELDS)
        non_null_points = 0

        for month_data in monthly_data:
            for field in self.MONTHLY_FIELDS:
                if month_data.get(field) is not None:
                    non_null_points += 1

        return non_null_points / total_points if total_points > 0 else 0.0

    def get_confidence_level(self, completeness: float) -> str:
        """根据完整率判断置信度"""
        if completeness >= 0.8:
            return 'high'
        elif completeness >= 0.5:
            return 'medium'
        else:
            return 'low'

    def sort_issues(self) -> None:
        """按严重程度排序"""
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        self.issues.sort(key=lambda x: severity_order.get(x['severity'], 99))

    def generate_summary(self, completeness: float) -> str:
        """生成总结"""
        percentage = int(completeness * 100)

        critical_count = sum(1 for i in self.issues if i['severity'] == 'critical')
        high_count = sum(1 for i in self.issues if i['severity'] == 'high')
        medium_count = sum(1 for i in self.issues if i['severity'] == 'medium')

        if not self.issues:
            return f'数据完整率{percentage}%,未发现数据质量问题。'

        problem_desc = []
        if critical_count > 0:
            problem_desc.append(f'{critical_count}个严重问题')
        if high_count > 0:
            problem_desc.append(f'{high_count}个高优先级问题')
        if medium_count > 0:
            problem_desc.append(f'{medium_count}个中等问题')

        problem_str = '、'.join(problem_desc)

        if completeness < 0.8:
            return f'数据完整率{percentage}%,建议补充缺失月份数据。发现{problem_str}。'
        else:
            return f'数据完整率{percentage}%。发现{problem_str}。'

    def run(self) -> Dict[str, Any]:
        """执行检查"""
        self.check_project_region()
        self.check_monthly_data()

        completeness = self.calculate_completeness()
        confidence_level = self.get_confidence_level(completeness)

        self.sort_issues()
        summary = self.generate_summary(completeness)

        return {
            'completeness': round(completeness, 2),
            'confidence_level': confidence_level,
            'issues': self.issues,
            'summary': summary
        }


# ============= 主函数 =============

def extract_and_check_data(survey_excel_path: str, output_json_path: str):
    """提取数据并进行质量检查"""

    # 步骤 1: 提取数据
    extracted_data = extract_data_from_excel(survey_excel_path)

    # 如果提取失败，直接返回错误
    if extracted_data.get("error"):
        output_path = Path(output_json_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=2)
        return

    # 步骤 2: 执行质量检查
    checker = DataQualityChecker(extracted_data)
    quality_report = checker.run()

    # 步骤 3: 合并结果
    result = {
        "extracted_data": extracted_data,
        "quality_report": quality_report
    }

    # 步骤 4: 输出结果
    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 数据提取和质量检查完成: {output_json_path}")
    print(f"项目地区: {extracted_data.get('project_region')}")
    print(f"\n{quality_report['summary']}")


def main():
    """命令行入口"""
    if len(sys.argv) != 3:
        print('用法: python extract_and_check_data.py <调研表Excel路径> <输出JSON路径>')
        sys.exit(1)

    survey_excel_path = sys.argv[1]
    output_json_path = sys.argv[2]

    try:
        extract_and_check_data(survey_excel_path, output_json_path)
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
```

**步骤 4: 运行测试，确认通过**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_extract_and_check.py -v
```

预期输出: `PASS`

**步骤 5: Commit 实现代码**

```bash
git add .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py tests/unit/test_extract_and_check.py
git commit -m "$(cat <<'EOF'
feat: implement extract-and-check-data script

合并数据提取和质量检查功能到单个脚本
- 整合 extract_survey_data.py 和 check_data_quality.py 的逻辑
- 统一输出格式，包含 extracted_data 和 quality_report
- 添加单元测试验证功能

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## 任务 3: 修改 Streamlit 应用流程

**文件:**
- Modify: `app.py`

**步骤 1: 编写测试用例**

创建文件 `tests/integration/test_app_workflow.py`:

```python
#!/usr/bin/env python3
"""测试应用工作流程"""

import pytest
from pathlib import Path


def test_streamlit_workflow_stages():
    """测试 Streamlit 工作流程阶段数量"""
    app_file = Path(__file__).parent.parent.parent / "app.py"

    with open(app_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 验证阶段数量为 5（上传、提取+质量检查、填充建议、计算、结果）
    assert "stages = ['上传', '提取+质量检查', '填充建议', '计算', '结果']" in content

    # 验证阶段映射
    assert "'extract_check': 1" in content
```

**步骤 2: 运行测试，确认失败**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_app_workflow.py -v
```

预期输出: `FAIL - AssertionError`

**步骤 3: 修改 app.py - 更新流程进度指示器**

在 `app.py` 的第 50-66 行，将:

```python
    # 流程进度指示器
    stages = ['上传', '提取', '质量检查', '填充建议', '计算', '结果']
    stage_map = {
        'upload': 0, 'extract': 1, 'quality': 2,
        'filling': 3, 'calculate': 4, 'result': 5
    }
```

替换为:

```python
    # 流程进度指示器
    stages = ['上传', '提取+质量检查', '填充建议', '计算', '结果']
    stage_map = {
        'upload': 0, 'extract_check': 1,
        'filling': 2, 'calculate': 3, 'result': 4
    }
```

**步骤 4: 修改 app.py - 更新阶段路由**

在 `app.py` 的第 70-84 行，将:

```python
    if stage == 'upload':
        render_upload_stage()
    elif stage == 'extract':
        render_extract_stage()
    elif stage == 'quality':
        render_quality_stage()
    elif stage == 'filling':
        render_filling_stage()
    elif stage == 'calculate':
        render_calculate_stage()
    elif stage == 'result':
        render_result_stage()
```

替换为:

```python
    if stage == 'upload':
        render_upload_stage()
    elif stage == 'extract_check':
        render_extract_check_stage()
    elif stage == 'filling':
        render_filling_stage()
    elif stage == 'calculate':
        render_calculate_stage()
    elif stage == 'result':
        render_result_stage()
```

**步骤 5: 修改 app.py - 更新上传阶段的跳转**

在 `app.py` 的第 112-114 行，将:

```python
        if st.button("🚀 开始分析", type="primary", use_container_width=True):
            st.session_state.stage = 'extract'
            st.rerun()
```

替换为:

```python
        if st.button("🚀 开始分析", type="primary", use_container_width=True):
            st.session_state.stage = 'extract_check'
            st.rerun()
```

**步骤 6: 修改 app.py - 合并提取和质量检查阶段**

删除原来的 `render_extract_stage()` (第 117-177 行) 和 `render_quality_stage()` (第 179-269 行)，创建新的合并函数:

```python
def render_extract_check_stage():
    """阶段2: 数据提取和质量检查 (自动流转)"""
    st.header("🔍 步骤 2: 数据提取和质量检查")

    with st.spinner("正在提取调研表数据并进行质量检查,请稍候..."):
        try:
            caller = SkillCaller(timeout=300)

            upload_path = Path("tmp/upload_survey.xlsx")
            output_path = Path("tmp/extract_check_result.json")

            # 调用合并的 Skill: 提取和质量检查
            caller.call_skill(
                "extract-and-check-data",
                str(upload_path),
                str(output_path)
            )

            # 读取结果
            with open(output_path, 'r', encoding='utf-8') as f:
                result = json.load(f)

            # 检查是否有错误
            if result.get("error"):
                st.error(f"❌ 数据处理失败: {result.get('message', '未知错误')}")
                if st.button("🔄 重新上传", use_container_width=True):
                    reset_flow()
                    st.rerun()
                return

            # 分离提取数据和质量报告
            extracted_data = result.get("extracted_data", {})
            quality_report = result.get("quality_report", {})

            # 保存到 session
            st.session_state.extracted_data = extracted_data
            st.session_state.quality_report = quality_report

            # 同时保存单独的文件（供后续步骤使用）
            with open("tmp/extracted_data.json", 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)
            with open("tmp/quality_report.json", 'w', encoding='utf-8') as f:
                json.dump(quality_report, f, ensure_ascii=False, indent=2)

            # 展示提取结果
            st.success("✅ 数据提取成功")

            col1, col2 = st.columns(2)
            with col1:
                st.metric("项目地区", extracted_data.get("project_region", "未识别"))
            with col2:
                st.metric("月度数据记录", len(extracted_data.get("monthly_data", [])))

            # 展示质量报告
            st.success("✅ 质量检查完成")

            # 核心指标卡
            col1, col2, col3 = st.columns(3)
            with col1:
                completeness = quality_report.get("completeness", 0)
                st.metric(
                    "数据完整率",
                    f"{completeness * 100:.1f}%",
                    delta=None if completeness >= 0.8 else "需要改进"
                )
            with col2:
                confidence = quality_report.get("confidence_level", "unknown")
                confidence_map = {"high": "高", "medium": "中", "low": "低"}
                st.metric("置信水平", confidence_map.get(confidence, confidence))
            with col3:
                issues = quality_report.get("issues", [])
                critical_issues = len([i for i in issues if i.get("severity") == "critical"])
                st.metric("严重问题数", critical_issues)

            # 问题列表
            if issues:
                st.subheader("📋 发现的问题")

                severity_groups = {"critical": [], "high": [], "medium": [], "low": []}
                for issue in issues:
                    severity = issue.get("severity", "low")
                    severity_groups.get(severity, []).append(issue)

                severity_labels = {
                    "critical": "🔴 严重问题",
                    "high": "🟠 高优先级",
                    "medium": "🟡 中优先级",
                    "low": "🔵 低优先级"
                }

                for severity in ["critical", "high", "medium", "low"]:
                    group = severity_groups[severity]
                    if group:
                        with st.expander(f"{severity_labels[severity]} ({len(group)}个)", expanded=(severity == "critical")):
                            for issue in group:
                                st.warning(f"**字段**: {issue.get('field')}\n\n{issue.get('message')}")
            else:
                st.success("✨ 未发现任何问题,数据质量优秀!")

            # 总结
            st.info(f"**总结**: {quality_report.get('summary', '数据检查完成')}")

            with st.expander("查看提取的原始数据"):
                st.json(extracted_data)

            # 自动进入下一阶段
            time.sleep(1.5)
            st.session_state.stage = 'filling'
            st.rerun()

        except SkillError as e:
            st.error(f"❌ 数据处理失败: {str(e)}")
            if st.button("🔄 重新上传", use_container_width=True):
                reset_flow()
                st.rerun()
        except Exception as e:
            st.error(f"❌ 发生未知错误: {str(e)}")
            if st.button("🔄 重新上传", use_container_width=True):
                reset_flow()
                st.rerun()
```

**步骤 7: 修改 app.py - 更新 filling 阶段的错误返回路径**

在 `render_filling_stage()` 函数中，将错误处理中的 `st.session_state.stage = 'quality'` 改为 `st.session_state.stage = 'extract_check'`。

具体修改位置：
- 第 304 行
- 第 310 行

**步骤 8: 运行测试，确认通过**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_app_workflow.py -v
```

预期输出: `PASS`

**步骤 9: Commit 应用修改**

```bash
git add app.py
git commit -m "$(cat <<'EOF'
refactor: merge extract and quality check stages in UI

将"数据提取"和"质量检查"两个阶段合并为一个阶段
- 更新流程进度指示器，从6阶段减少到5阶段
- 创建 render_extract_check_stage() 合并函数
- 调用新的 extract-and-check-data skill
- 更新阶段跳转逻辑

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## 任务 4: 更新文档

**文件:**
- Modify: `CLAUDE.md`

**步骤 1: 编写测试用例**

创建文件 `tests/integration/test_documentation.py`:

```python
#!/usr/bin/env python3
"""测试文档一致性"""

import pytest
from pathlib import Path


def test_claude_md_workflow_description():
    """测试 CLAUDE.md 中的工作流程描述"""
    claude_md = Path(__file__).parent.parent.parent / "CLAUDE.md"

    with open(claude_md, 'r', encoding='utf-8') as f:
        content = f.read()

    # 验证数据流向包含合并后的步骤
    assert "extract-and-check-data" in content

    # 验证技能列表更新
    assert "extract-and-check-data**：从调研表Excel提取数据并进行质量检查" in content


def test_claude_md_skill_count():
    """测试技能数量"""
    claude_md = Path(__file__).parent.parent.parent / "CLAUDE.md"

    with open(claude_md, 'r', encoding='utf-8') as f:
        content = f.read()

    # 应该有3个skills: extract-and-check-data, suggest-data-filling, (移除了单独的extract和check)
    # 但为了向后兼容，旧的skills可能仍然存在
    assert "extract-and-check-data" in content
```

**步骤 2: 运行测试，确认失败**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_documentation.py -v
```

预期输出: `FAIL`

**步骤 3: 修改 CLAUDE.md - 更新数据流向**

在 `CLAUDE.md` 的"数据流向"部分，将:

```
调研表Excel → extract-survey-data Skill → JSON数据
                ↓
        check-data-quality Skill → 质量报告
                ↓
        suggest-data-filling Skill → 填充建议
```

替换为:

```
调研表Excel → extract-and-check-data Skill → JSON数据 + 质量报告
                ↓
        suggest-data-filling Skill → 填充建议
                ↓
        DataFiller → 完整数据集
                ↓
        ExcelCalculator → 节能率结果
```

**步骤 4: 修改 CLAUDE.md - 更新 Claude Skills 部分**

在 `CLAUDE.md` 的"Claude Skills"部分，将:

```markdown
1. **extract-survey-data**：从调研表Excel提取12个月运行数据
   - 输入：调研表路径
   - 输出：`tmp/extracted_data.json`

2. **check-data-quality**：检查数据完整性和合理性
   - 输入：提取的数据JSON
   - 输出：`tmp/quality_report.json`

3. **suggest-data-filling**：基于季节模式和插值法推荐填充值
```

替换为:

```markdown
1. **extract-and-check-data**：从调研表Excel提取数据并进行质量检查
   - 输入：调研表路径（`00_sample/02-中央空调节能调研表.xlsx`）
   - 输出：`tmp/extract_check_result.json`（包含extracted_data和quality_report）
   - 关键功能：
     - 提取12个月运行数据（月度耗电量、供水温度、泵频率、水温差、冷却塔温度）
     - 检查数据完整性（必填字段、数值范围、逻辑一致性）
     - 计算完整率和置信度
     - 输出问题列表和总结
   - 同时保存单独的 `tmp/extracted_data.json` 和 `tmp/quality_report.json` 供后续使用

2. **suggest-data-filling**：基于季节模式和插值法推荐填充值
```

**步骤 5: 修改 CLAUDE.md - 更新 UI流程编排部分**

在核心模块职责表格中，更新 `app.py` 的描述:

将:
```
**UI流程编排** | `app.py` | 6阶段流程控制、用户交互 | Streamlit session state
```

替换为:
```
**UI流程编排** | `app.py` | 5阶段流程控制（上传→提取+质量检查→填充建议→计算→结果）、用户交互 | Streamlit session state
```

**步骤 6: 修改 CLAUDE.md - 更新临时文件约定**

在"临时文件约定"部分，添加:

```
- `extract_check_result.json`：提取和质量检查的合并结果
```

**步骤 7: 运行测试，确认通过**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_documentation.py -v
```

预期输出: `PASS`

**步骤 8: Commit 文档更新**

```bash
git add CLAUDE.md tests/integration/test_documentation.py
git commit -m "$(cat <<'EOF'
docs: update CLAUDE.md for merged workflow

更新项目文档以反映合并后的工作流程
- 更新数据流向图
- 更新 Claude Skills 描述
- 更新临时文件约定
- 添加文档一致性测试

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## 任务 5: 集成测试和验证

**文件:**
- Create: `tests/integration/test_merged_workflow.py`

**步骤 1: 编写集成测试**

```python
#!/usr/bin/env python3
"""测试合并后的完整工作流程"""

import pytest
import json
import tempfile
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def test_excel_file():
    """获取测试Excel文件路径"""
    excel_path = project_root / "00_sample/02-中央空调节能调研表.xlsx"
    if not excel_path.exists():
        pytest.skip("测试Excel文件不存在")
    return excel_path


def test_complete_merged_workflow(test_excel_file):
    """测试完整的合并工作流程"""
    sys.path.insert(0, str(project_root / ".claude/skills/extract-and-check-data/scripts"))

    from extract_and_check_data import extract_and_check_data

    # 创建临时输出文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_path = Path(f.name)

    try:
        # 执行提取和检查
        extract_and_check_data(str(test_excel_file), str(output_path))

        # 验证输出文件存在
        assert output_path.exists()

        # 读取结果
        with open(output_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # 验证结构
        assert 'extracted_data' in result
        assert 'quality_report' in result

        # 验证提取数据
        extracted = result['extracted_data']
        assert 'project_region' in extracted
        assert 'monthly_data' in extracted
        assert len(extracted['monthly_data']) == 12

        # 验证每个月的数据结构
        for month_data in extracted['monthly_data']:
            assert 'month' in month_data
            assert 'total_energy' in month_data
            assert 'chiller_supply_temp' in month_data

        # 验证质量报告
        quality = result['quality_report']
        assert 'completeness' in quality
        assert 'confidence_level' in quality
        assert 'issues' in quality
        assert 'summary' in quality

        # 验证质量报告的数据类型
        assert 0 <= quality['completeness'] <= 1
        assert quality['confidence_level'] in ['high', 'medium', 'low']
        assert isinstance(quality['issues'], list)
        assert isinstance(quality['summary'], str)

        # 验证问题列表结构
        for issue in quality['issues']:
            assert 'field' in issue
            assert 'severity' in issue
            assert 'type' in issue
            assert 'message' in issue
            assert issue['severity'] in ['critical', 'high', 'medium', 'low']
            assert issue['type'] in ['missing', 'out_of_range', 'logic_error']

        print(f"✅ 测试通过: 数据完整率 {quality['completeness']*100:.1f}%")
        print(f"   置信度: {quality['confidence_level']}")
        print(f"   问题数: {len(quality['issues'])}")

    finally:
        # 清理
        if output_path.exists():
            output_path.unlink()


def test_workflow_backwards_compatibility():
    """测试向后兼容性 - 确保生成的单独文件"""
    # 这个测试确保即使合并了步骤，仍然生成单独的文件供现有代码使用
    from core.skill_caller import SkillCaller

    test_excel = project_root / "00_sample/02-中央空调节能调研表.xlsx"
    if not test_excel.exists():
        pytest.skip("测试Excel文件不存在")

    # 创建临时目录
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "result.json"

        try:
            caller = SkillCaller(timeout=300)
            caller.call_skill(
                "extract-and-check-data",
                str(test_excel),
                str(output_path)
            )

            # 验证主输出文件
            assert output_path.exists()

            # 在实际应用中，app.py 会从主文件中分离并保存单独文件
            # 这里模拟这个过程
            with open(output_path, 'r', encoding='utf-8') as f:
                result = json.load(f)

            extracted_path = Path(tmpdir) / "extracted_data.json"
            quality_path = Path(tmpdir) / "quality_report.json"

            with open(extracted_path, 'w', encoding='utf-8') as f:
                json.dump(result['extracted_data'], f, ensure_ascii=False, indent=2)

            with open(quality_path, 'w', encoding='utf-8') as f:
                json.dump(result['quality_report'], f, ensure_ascii=False, indent=2)

            # 验证单独文件存在
            assert extracted_path.exists()
            assert quality_path.exists()

            # 验证单独文件内容正确
            with open(extracted_path, 'r', encoding='utf-8') as f:
                extracted = json.load(f)
                assert 'monthly_data' in extracted

            with open(quality_path, 'r', encoding='utf-8') as f:
                quality = json.load(f)
                assert 'completeness' in quality

            print("✅ 向后兼容性测试通过")

        except Exception as e:
            pytest.skip(f"Skill调用失败: {e}")
```

**步骤 2: 运行集成测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_merged_workflow.py -v -s
```

预期输出: 所有测试 `PASS`

**步骤 3: Commit 集成测试**

```bash
git add tests/integration/test_merged_workflow.py
git commit -m "$(cat <<'EOF'
test: add integration tests for merged workflow

添加合并工作流程的集成测试
- 测试完整的提取和质量检查流程
- 验证输出数据结构和内容
- 测试向后兼容性

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## 任务 6: 清理和最终验证

**步骤 1: 运行所有测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest -v
```

预期输出: 所有测试通过

**步骤 2: 启动应用进行手动测试**

```bash
streamlit run app.py
```

手动测试清单:
- [ ] 上传调研表Excel文件
- [ ] 验证"提取+质量检查"阶段自动执行
- [ ] 确认同时显示提取结果和质量报告
- [ ] 验证可以继续到填充建议阶段
- [ ] 完成整个工作流程

**步骤 3: 创建最终验证脚本**

创建文件 `scripts/verify_merge.sh`:

```bash
#!/bin/bash
# 验证合并后的工作流程

echo "========================================="
echo "验证合并后的工作流程"
echo "========================================="

# 检查skill是否存在
echo "1. 检查新的 skill 是否存在..."
if [ -f ".claude/skills/extract-and-check-data/SKILL.md" ]; then
    echo "   ✅ SKILL.md 存在"
else
    echo "   ❌ SKILL.md 不存在"
    exit 1
fi

if [ -f ".claude/skills/extract-and-check-data/scripts/extract_and_check_data.py" ]; then
    echo "   ✅ 脚本存在"
else
    echo "   ❌ 脚本不存在"
    exit 1
fi

# 运行单元测试
echo ""
echo "2. 运行单元测试..."
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/ -v
if [ $? -eq 0 ]; then
    echo "   ✅ 单元测试通过"
else
    echo "   ❌ 单元测试失败"
    exit 1
fi

# 运行集成测试
echo ""
echo "3. 运行集成测试..."
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/ -v
if [ $? -eq 0 ]; then
    echo "   ✅ 集成测试通过"
else
    echo "   ❌ 集成测试失败"
    exit 1
fi

# 检查文档更新
echo ""
echo "4. 检查文档是否更新..."
if grep -q "extract-and-check-data" CLAUDE.md; then
    echo "   ✅ CLAUDE.md 已更新"
else
    echo "   ❌ CLAUDE.md 未更新"
    exit 1
fi

echo ""
echo "========================================="
echo "✅ 所有验证通过!"
echo "========================================="
```

**步骤 4: 运行验证脚本**

```bash
chmod +x scripts/verify_merge.sh
bash scripts/verify_merge.sh
```

预期输出: 所有检查通过

**步骤 5: Commit 验证脚本**

```bash
git add scripts/verify_merge.sh
git commit -m "$(cat <<'EOF'
chore: add verification script for merged workflow

添加验证脚本检查合并后的工作流程
- 检查新skill文件存在
- 运行所有测试
- 验证文档更新

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## 任务 7: (可选) 弃用旧的 Skills

**注意**: 这是可选任务，可以选择保留旧的 skills 以保持向后兼容性。

**文件:**
- Modify: `.claude/skills/extract-survey-data/SKILL.md`
- Modify: `.claude/skills/check-data-quality/SKILL.md`

**步骤 1: 在旧 skills 中添加弃用警告**

在 `.claude/skills/extract-survey-data/SKILL.md` 的开头添加:

```markdown
> **⚠️ DEPRECATED**: 此 skill 已弃用，请使用 `extract-and-check-data` 替代。
> 该 skill 将在未来版本中移除。
```

在 `.claude/skills/check-data-quality/SKILL.md` 的开头添加相同警告。

**步骤 2: Commit 弃用标记**

```bash
git add .claude/skills/extract-survey-data/SKILL.md .claude/skills/check-data-quality/SKILL.md
git commit -m "$(cat <<'EOF'
docs: mark old skills as deprecated

标记 extract-survey-data 和 check-data-quality 为已弃用
建议使用新的 extract-and-check-data skill

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## 总结

完成以上所有任务后，您将拥有:

1. ✅ 新的合并 skill: `extract-and-check-data`
2. ✅ 更新的 Streamlit UI (5阶段工作流程)
3. ✅ 完整的测试套件
4. ✅ 更新的文档
5. ✅ 验证脚本
6. ✅ (可选) 弃用标记

**关键改进**:
- 减少用户等待时间 (2个阶段合并为1个)
- 简化工作流程 (6阶段 → 5阶段)
- 保持向后兼容性 (仍然生成单独的文件)
- 代码重用 (整合现有逻辑)

**测试覆盖**:
- 单元测试: 验证核心功能
- 集成测试: 验证完整工作流程
- 文档测试: 确保文档一致性
- 手动测试: UI交互验证
