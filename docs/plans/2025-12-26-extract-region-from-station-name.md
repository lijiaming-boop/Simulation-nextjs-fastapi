# 从站房名称和文件名推断项目地区 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 增强数据提取功能，使用三级优先级策略从调研表推断项目地区：站房名称 > 文件名 > 项目总体情况表

**Architecture:**
- 修改 extract-and-check-data skill 的 `extract_and_check_data.py` 脚本
- 添加 `extract_station_name()` 函数从"冷站"sheet第1行提取站房名称
- 添加 `extract_region_from_filename()` 函数从文件名提取地区关键词
- 添加 `infer_region_from_text()` 函数根据城市关键词推断地区（统一供站房名称和文件名使用）
- 调整提取优先级：站房名称 > 文件名 > 项目总体情况表扫描

**Tech Stack:** Python 3.8+, pandas, pytest

---

## Task 1: 添加通用地区推断和站房名称提取功能

**Files:**
- Modify: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py:63-84`
- Test: `tests/unit/test_region_inference.py` (新建)

**Step 1: Write the failing test**

创建测试文件 `tests/unit/test_region_inference.py`:

```python
#!/usr/bin/env python3
"""测试地区推断和站房名称提取功能"""

import pytest
import pandas as pd
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / '.claude/skills/extract-and-check-data/scripts'))

from extract_and_check_data import extract_station_name, infer_region_from_text


class TestExtractStationName:
    """测试站房名称提取"""

    def test_extract_station_name_from_df(self):
        """测试从 DataFrame 提取站房名称"""
        # 模拟冷站 sheet 的前几行
        data = {
            0: [None, None, None],
            1: [None, '站房名称', None],
            2: [None, None, None],
            3: [None, 'F栋制冷站', None]
        }
        df = pd.DataFrame(data)

        result = extract_station_name(df)
        assert result == 'F栋制冷站'

    def test_extract_station_name_not_found(self):
        """测试站房名称字段不存在"""
        df = pd.DataFrame({
            0: [None, None],
            1: ['其他', '内容']
        })

        result = extract_station_name(df)
        assert result is None

    def test_extract_station_name_empty_value(self):
        """测试站房名称值为空"""
        data = {
            0: [None, None],
            1: [None, '站房名称'],
            2: [None, None],
            3: [None, None]
        }
        df = pd.DataFrame(data)

        result = extract_station_name(df)
        assert result is None


class TestInferRegionFromText:
    """测试从文本推断地区"""

    @pytest.mark.parametrize("text,expected_region", [
        # 站房名称示例
        ('北京总部冷站', '华北'),
        ('上海分公司机房', '华东'),
        ('深圳工业园区站房', '华南'),
        ('杭州研发中心空调机房', '华东'),
        ('武汉生产基地冷站', '华中'),
        ('成都办公楼制冷站', '西南'),
        ('西安厂区空调站', '西北'),
        ('沈阳冷站', '东北'),
        ('广州天河冷站', '华南'),
        ('石家庄仁和药业', '华北'),
        ('惠州光弘', '华南'),
        # 文件名示例
        ('【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx', '华南'),
        ('【缺冬季】10.4%石家庄仁和药业中央空调节能调研表.xlsx', '华北'),
        ('【仅有夏季】6.5%和光同程-机房智能化调研表2023年5月版.xlsx', None),  # 无地区关键词
        ('上海和元-机房智能化调研表模板.xlsx', '华东'),
        ('北京某公司调研表.xlsx', '华北'),
    ])
    def test_infer_region_with_city_keywords(self, text, expected_region):
        """测试包含城市关键词的文本"""
        result = infer_region_from_text(text)
        assert result == expected_region

    @pytest.mark.parametrize("text", [
        'F栋制冷站',
        '1号冷站',
        '中央空调机房',
        '某公司调研表.xlsx',
        None,
        '',
    ])
    def test_infer_region_no_keywords(self, text):
        """测试不包含地区关键词的文本"""
        result = infer_region_from_text(text)
        assert result is None
```

**Step 2: Run test to verify it fails**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/test_region_inference.py -v
```

预期输出: FAIL - "ImportError: cannot import name 'extract_station_name'"

**Step 3: Write minimal implementation**

在 `extract_and_check_data.py` 的 `extract_region()` 函数后添加新函数（约63行之后）:

```python
def extract_station_name(df):
    """从冷站工作表中提取站房名称

    Args:
        df: 冷站工作表的 DataFrame

    Returns:
        站房名称字符串，如果未找到则返回 None
    """
    # 在前10行查找"站房名称"字段
    for idx in range(min(10, len(df))):
        row = df.iloc[idx]
        for col_idx, val in enumerate(row):
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if '站房名称' in val_str:
                # 站房名称的值通常在右侧第2列（跳过1列）
                if col_idx + 2 < len(row):
                    station_name = df.iloc[idx, col_idx + 2]
                    if pd.notna(station_name):
                        return str(station_name).strip()
                return None
    return None


def infer_region_from_text(text):
    """从文本（站房名称或文件名）推断项目地区

    Args:
        text: 文本字符串（站房名称、文件名等）

    Returns:
        地区字符串（华南/华东/华中/西南/西北/华北/东北），如果无法推断则返回 None
    """
    if not text or pd.isna(text):
        return None

    text_str = str(text)

    # 地区关键词映射（扩展了城市列表以提高识别率）
    regions = {
        '华南': ['广东', '广西', '海南', '福建', '深圳', '广州', '厦门', '珠海', '东莞', '佛山', '惠州', '中山', '江门', '湛江', '汕头'],
        '华东': ['上海', '江苏', '浙江', '安徽', '江西', '南京', '杭州', '苏州', '无锡', '宁波', '合肥', '南昌', '温州', '常州', '徐州'],
        '华中': ['湖北', '湖南', '河南', '武汉', '长沙', '郑州', '洛阳', '株洲', '岳阳'],
        '西南': ['四川', '重庆', '贵州', '云南', '西藏', '成都', '贵阳', '昆明', '拉萨'],
        '西北': ['陕西', '甘肃', '青海', '宁夏', '新疆', '西安', '兰州', '银川', '乌鲁木齐', '西宁'],
        '华北': ['北京', '天津', '河北', '山西', '内蒙古', '石家庄', '太原', '呼和浩特', '唐山', '保定', '廊坊'],
        '东北': ['辽宁', '吉林', '黑龙江', '沈阳', '大连', '长春', '哈尔滨', '鞍山', '抚顺']
    }

    # 查找匹配的地区
    for region, keywords in regions.items():
        if any(keyword in text_str for keyword in keywords):
            return region

    return None
```

**Step 4: Run test to verify it passes**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/test_region_inference.py -v
```

预期输出: 全部 PASS

**Step 5: Commit**

```bash
git add tests/unit/test_region_inference.py .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py
git commit -m "feat: add station name extraction and region inference

添加 extract_station_name() 从冷站sheet提取站房名称
添加 infer_region_from_text() 从文本推断地区（支持站房名称和文件名）

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: 添加从文件名提取地区功能

**Files:**
- Modify: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py` (添加新函数)
- Test: `tests/unit/test_region_inference.py` (扩展)

**Step 1: Write the failing test**

在 `tests/unit/test_region_inference.py` 添加测试类:

```python
class TestExtractRegionFromFilename:
    """测试从文件名提取地区"""

    @pytest.mark.parametrize("filename,expected_region", [
        ('【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx', '华南'),
        ('【缺冬季】10.4%石家庄仁和药业中央空调节能调研表.xlsx', '华北'),
        ('【仅有夏季】6.5%和光同程-机房智能化调研表2023年5月版.xlsx', None),
        ('【缺夏季】12.1%上海和元-机房智能化调研表模板（深度调研）.xlsx', '华东'),
        ('/path/to/北京某公司调研表.xlsx', '华北'),
        ('/path/to/深圳工业园区/调研表.xlsx', '华南'),
        ('test.xlsx', None),
    ])
    def test_extract_region_from_filename(self, filename, expected_region):
        """测试从文件名提取地区"""
        from extract_and_check_data import extract_region_from_filename
        result = extract_region_from_filename(filename)
        assert result == expected_region
```

**Step 2: Run test to verify it fails**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/test_region_inference.py::TestExtractRegionFromFilename -v
```

预期输出: FAIL - "ImportError: cannot import name 'extract_region_from_filename'"

**Step 3: Write minimal implementation**

在 `extract_and_check_data.py` 添加函数（在 `infer_region_from_text()` 之后）:

```python
def extract_region_from_filename(filepath):
    """从文件名提取项目地区

    Args:
        filepath: 文件路径字符串

    Returns:
        地区字符串（华南/华东/华中/西南/西北/华北/东北），如果无法推断则返回 None
    """
    if not filepath:
        return None

    # 从完整路径中提取文件名（包括目录名，因为目录名可能也包含地区信息）
    return infer_region_from_text(filepath)
```

**Step 4: Run test to verify it passes**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/test_region_inference.py::TestExtractRegionFromFilename -v
```

预期输出: 全部 PASS

**Step 5: Commit**

```bash
git add tests/unit/test_region_inference.py .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py
git commit -m "feat: add extract_region_from_filename function

支持从调研表文件名或路径提取地区信息

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: 修改地区提取逻辑使用三级优先级

**Files:**
- Modify: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py:103-112`
- Test: `tests/unit/test_region_inference.py` (扩展集成测试)

**Step 1: Write the failing test**

在 `tests/unit/test_region_inference.py` 添加集成测试:

```python
class TestExtractDataWithPriorityLogic:
    """测试完整的地区提取流程（三级优先级）"""

    def test_priority_1_station_name(self, tmp_path):
        """优先级1: 从站房名称提取地区"""
        import openpyxl

        wb = openpyxl.Workbook()

        # 创建"项目总体情况"sheet（不包含地区）
        ws_overview = wb.active
        ws_overview.title = '项目总体情况'
        ws_overview['A1'] = '项目名称'
        ws_overview['B1'] = '某公司冷站项目'

        # 创建"冷站"sheet（站房名称包含地区）
        ws_station = wb.create_sheet('冷站')
        ws_station['B2'] = '站房名称'
        ws_station['D2'] = '深圳工业园区F栋制冷站'

        # 添加月份行和能耗数据
        ws_station['D35'] = '1月'
        ws_station['E35'] = '2月'
        ws_station['F35'] = '3月'
        ws_station['D47'] = 10.5
        ws_station['E47'] = 12.3
        ws_station['F47'] = 15.8

        # 保存测试文件（文件名也不包含地区）
        test_file = tmp_path / 'test.xlsx'
        wb.save(test_file)

        # 执行提取
        from extract_and_check_data import extract_data_from_excel
        result = extract_data_from_excel(str(test_file))

        # 断言地区从站房名称提取成功
        assert result['project_region'] == '华南'

    def test_priority_2_filename(self, tmp_path):
        """优先级2: 站房名称失败，从文件名提取地区"""
        import openpyxl

        wb = openpyxl.Workbook()

        # 创建"项目总体情况"sheet（不包含地区）
        ws_overview = wb.active
        ws_overview.title = '项目总体情况'
        ws_overview['A1'] = '项目名称'
        ws_overview['B1'] = '某公司冷站项目'

        # 创建"冷站"sheet（站房名称不包含地区）
        ws_station = wb.create_sheet('冷站')
        ws_station['B2'] = '站房名称'
        ws_station['D2'] = 'F栋制冷站'

        # 添加月份行和能耗数据
        ws_station['D35'] = '1月'
        ws_station['E35'] = '2月'
        ws_station['F35'] = '3月'
        ws_station['D47'] = 10.5
        ws_station['E47'] = 12.3
        ws_station['F47'] = 15.8

        # 保存测试文件（文件名包含地区）
        test_file = tmp_path / '北京某公司调研表.xlsx'
        wb.save(test_file)

        # 执行提取
        from extract_and_check_data import extract_data_from_excel
        result = extract_data_from_excel(str(test_file))

        # 断言地区从文件名提取成功
        assert result['project_region'] == '华北'

    def test_priority_3_overview_sheet(self, tmp_path):
        """优先级3: 站房名称和文件名都失败，从项目总体情况提取"""
        import openpyxl

        wb = openpyxl.Workbook()

        # 创建"项目总体情况"sheet（包含地区）
        ws_overview = wb.active
        ws_overview.title = '项目总体情况'
        ws_overview['A1'] = '项目名称'
        ws_overview['B1'] = '武汉市某公司冷站项目'

        # 创建"冷站"sheet（站房名称不包含地区）
        ws_station = wb.create_sheet('冷站')
        ws_station['B2'] = '站房名称'
        ws_station['D2'] = 'F栋制冷站'

        # 添加月份行和能耗数据
        ws_station['D35'] = '1月'
        ws_station['E35'] = '2月'
        ws_station['F35'] = '3月'
        ws_station['D47'] = 10.5
        ws_station['E47'] = 12.3
        ws_station['F47'] = 15.8

        # 保存测试文件（文件名不包含地区）
        test_file = tmp_path / 'test.xlsx'
        wb.save(test_file)

        # 执行提取
        from extract_and_check_data import extract_data_from_excel
        result = extract_data_from_excel(str(test_file))

        # 断言地区从项目总体情况提取成功
        assert result['project_region'] == '华中'
```

**Step 2: Run test to verify it fails**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/test_region_inference.py::TestExtractDataWithPriorityLogic -v
```

预期输出: FAIL - 地区提取逻辑尚未调整，测试失败

**Step 3: Modify extraction logic**

修改 `extract_data_from_excel()` 函数中的地区提取部分（约103-112行）:

```python
def extract_data_from_excel(survey_excel_path: str) -> Dict[str, Any]:
    """从 Excel 文件提取数据"""
    xls = pd.ExcelFile(survey_excel_path)

    # 读取冷站数据
    if '冷站' not in xls.sheet_names:
        return {
            "error": True,
            "message": "找不到'冷站'工作表,请确认上传了正确的文件"
        }

    df = pd.read_excel(xls, sheet_name='冷站', header=None)

    # 提取项目地区（三级优先级）
    project_region = None

    # 优先级1: 从站房名称推断地区
    station_name = extract_station_name(df)
    if station_name:
        project_region = infer_region_from_text(station_name)

    # 优先级2: 如果优先级1失败，从文件名推断地区
    if not project_region:
        project_region = extract_region_from_filename(survey_excel_path)

    # 优先级3: 如果优先级1和2都失败，从项目总体情况表提取
    if not project_region and '项目总体情况' in xls.sheet_names:
        df_overview = pd.read_excel(xls, sheet_name='项目总体情况', header=None)
        project_region = extract_region(df_overview)

    # 查找关键行
    # ... 后续代码保持不变 ...
```

**Step 4: Run test to verify it passes**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/test_region_inference.py::TestExtractDataWithPriorityLogic -v
```

预期输出: 全部 PASS

**Step 5: Commit**

```bash
git add .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py tests/unit/test_region_inference.py
git commit -m "refactor: implement 3-tier region extraction priority

优先级: 站房名称 > 文件名 > 项目总体情况表
大幅提高地区识别成功率

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: 更新 Skill 文档说明

**Files:**
- Modify: `.claude/skills/extract-and-check-data/SKILL.md:19-40`

**Step 1: Update documentation**

修改 SKILL.md 的"提取字段"和"数据处理要点"部分:

**在第19行"提取字段"部分添加说明:**

```markdown
## 提取字段

**基础信息:**
- `project_region`: 项目地区 (华南/华东/华中/西南/西北/华北/东北)
  - **提取方法1（最优先）**: 从"冷站"sheet的"站房名称"字段推断（如"深圳工业园区F栋" → 华南）
  - **提取方法2（次优先）**: 从调研表文件名推断（如"惠州光弘-调研表.xlsx" → 华南）
  - **提取方法3（兜底）**: 从"项目总体情况"sheet扫描所有单元格，匹配省市关键词

**月度运行数据** (1-12月):
...
```

**在第32行"数据处理要点"部分更新第1条:**

```markdown
## 数据处理要点

1. **智能识别**:
   - 不要硬编码 Sheet 名称，利用 LLM 理解能力识别包含月度数据的工作表
   - **项目地区三级优先级提取**：
     1. **优先级1**: 从"冷站"sheet的"站房名称"字段推断（如"深圳工业园区F栋" → 华南）
     2. **优先级2**: 从调研表文件名推断（如"惠州光弘-调研表.xlsx" → 华南）
     3. **优先级3**: 从"项目总体情况"sheet扫描所有单元格匹配省市关键词
   - 支持识别全国主要城市：北上广深、省会城市、计划单列市等
2. **文本解析**:
   ...
```

**Step 2: Verify documentation clarity**

检查文档是否清晰说明了：
- ✅ 提取方法的三级优先级
- ✅ 站房名称字段的位置和格式
- ✅ 文件名提取机制
- ✅ 兜底机制

**Step 3: Commit**

```bash
git add .claude/skills/extract-and-check-data/SKILL.md
git commit -m "docs: update skill documentation with 3-tier extraction

说明项目地区三级优先级提取逻辑：站房名称 > 文件名 > 项目总体情况

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: 端到端测试验证

**Files:**
- Test: `tests/integration/test_sample_surveys_e2e.py` (已存在)
- Create: `tests/integration/test_region_extraction_e2e.py` (新建专项测试)

**Step 1: Write end-to-end test**

创建 `tests/integration/test_region_extraction_e2e.py`:

```python
#!/usr/bin/env python3
"""端到端测试：验证从真实调研表提取项目地区"""

import pytest
import json
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / '.claude/skills/extract-and-check-data/scripts'))

from extract_and_check_data import extract_and_check_data


class TestRegionExtractionE2E:
    """测试真实调研表的地区提取"""

    @pytest.mark.parametrize("survey_file,expected_region,extraction_source", [
        ('00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx', '华南', 'filename'),
        ('00_sample/示例调研表/【缺冬季】10.4%石家庄仁和药业中央空调节能调研表.xlsx', '华北', 'filename'),
        ('00_sample/示例调研表/【缺夏季】12.1%上海和元-机房智能化调研表模板（深度调研）.xlsx', '华东', 'filename'),
    ])
    def test_extract_region_from_real_surveys(self, survey_file, expected_region, extraction_source, tmp_path):
        """测试从真实调研表提取地区"""
        survey_path = project_root / survey_file
        if not survey_path.exists():
            pytest.skip(f"测试文件不存在: {survey_file}")

        output_path = tmp_path / 'result.json'

        # 执行提取
        extract_and_check_data(str(survey_path), str(output_path))

        # 验证输出
        with open(output_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        assert 'extracted_data' in result
        assert result['extracted_data']['project_region'] == expected_region, \
            f"预期从{extraction_source}提取到{expected_region},实际为{result['extracted_data']['project_region']}"

    def test_region_extraction_coverage(self, tmp_path):
        """统计所有示例调研表的地区提取成功率"""
        sample_dir = project_root / '00_sample/示例调研表'
        if not sample_dir.exists():
            pytest.skip("示例调研表目录不存在")

        survey_files = list(sample_dir.glob('*.xlsx'))
        if not survey_files:
            pytest.skip("未找到示例调研表文件")

        success_count = 0
        total_count = len(survey_files)
        results = []

        for survey_file in survey_files:
            output_path = tmp_path / f'{survey_file.stem}_result.json'

            try:
                extract_and_check_data(str(survey_file), str(output_path))

                with open(output_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)

                project_region = result.get('extracted_data', {}).get('project_region')
                if project_region:
                    success_count += 1
                    results.append(f'✅ {survey_file.name}: {project_region}')
                else:
                    results.append(f'❌ {survey_file.name}: 地区提取失败')
            except Exception as e:
                results.append(f'❌ {survey_file.name}: 异常 - {str(e)}')

        # 打印统计结果
        print('\n地区提取测试结果:')
        print('=' * 60)
        for result in results:
            print(result)
        print('=' * 60)
        print(f'成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)')

        # 期望至少95%的调研表能成功提取地区（三级优先级应该能大幅提高成功率）
        assert success_count / total_count >= 0.95, f'地区提取成功率过低: {success_count}/{total_count}'
```

**Step 2: Run test to verify current coverage**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/integration/test_region_extraction_e2e.py -v -s
```

预期输出: 显示各调研表的地区提取结果，成功率 ≥ 95%

**Step 3: Fix any failures**

如果有调研表提取失败，分析原因：
- 站房名称、文件名、项目总体情况都无地区关键词？→ 可接受的失败
- 关键词列表不完整？→ 补充城市关键词

**Step 4: Commit**

```bash
git add tests/integration/test_region_extraction_e2e.py
git commit -m "test: add comprehensive e2e tests for region extraction

验证三级优先级提取逻辑，期望成功率 ≥ 95%

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: 更新项目文档

**Files:**
- Modify: `CLAUDE.md:60-80`

**Step 1: Update CLAUDE.md**

在 "Claude Skills（AI辅助层）" 部分更新 extract-and-check-data 的说明（约60-80行）:

```markdown
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
```

**Step 2: Add region keyword reference**

在 CLAUDE.md 末尾"相关文档"部分之前，添加"项目地区识别规则"小节:

```markdown
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
...
```

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with 3-tier region extraction

添加项目地区识别规则说明,详细描述三级优先级提取机制和支持的城市列表

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: 运行完整测试套件

**Files:**
- Test: All test files

**Step 1: Run unit tests**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/ -v
```

预期输出: 所有单元测试 PASS

**Step 2: Run integration tests**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/integration/ -v -s
```

预期输出: 所有集成测试 PASS

**Step 3: Run region extraction coverage test**

运行:
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/integration/test_region_extraction_e2e.py::TestRegionExtractionE2E::test_region_extraction_coverage -v -s
```

预期输出: 显示各调研表的地区提取结果，成功率 ≥ 95%

**Step 4: Commit if all pass**

```bash
git add -A
git commit -m "test: verify all tests pass after 3-tier region extraction

确认所有单元测试和集成测试通过，地区提取成功率达标

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: 手动验证真实调研表

**Files:**
- Manual test with sample surveys

**Step 1: Test priority 1 (station name)**

创建测试用例验证优先级1（站房名称包含地区信息的调研表）:

运行:
```bash
python .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py \
  "00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx" \
  tmp/test_priority1.json

cat tmp/test_priority1.json | grep -A 1 '"project_region"'
```

预期输出包含: `"project_region": "华南"`

**Step 2: Test priority 2 (filename)**

运行:
```bash
python .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py \
  "00_sample/示例调研表/【缺冬季】10.4%石家庄仁和药业中央空调节能调研表.xlsx" \
  tmp/test_priority2.json

cat tmp/test_priority2.json | grep -A 1 '"project_region"'
```

预期输出包含: `"project_region": "华北"`

**Step 3: Test priority 3 (overview sheet)**

如果有调研表站房名称和文件名都不包含地区，验证从项目总体情况提取

**Step 4: Clean up temp files**

运行:
```bash
rm -f tmp/test_*.json
```

**Step 5: Document test results**

在终端输出测试结果摘要:
```
手动验证完成：
✅ 优先级1（站房名称）: 惠州光弘调研表 → 华南
✅ 优先级2（文件名）: 石家庄仁和药业调研表 → 华北
✅ 优先级3（项目总体情况）: [如有测试案例] → [地区]

三级优先级提取功能正常工作
```

---

## Verification Checklist

完成所有任务后，验证以下检查项：

- [ ] ✅ `extract_station_name()` 函数正确提取站房名称
- [ ] ✅ `infer_region_from_text()` 函数正确从文本推断地区
- [ ] ✅ `extract_region_from_filename()` 函数正确从文件名提取地区
- [ ] ✅ 地区提取三级优先级正确实现：站房名称 > 文件名 > 项目总体情况
- [ ] ✅ 单元测试覆盖核心函数（提取、推断、优先级）
- [ ] ✅ 集成测试验证真实调研表提取成功率 ≥ 95%
- [ ] ✅ SKILL.md 文档更新，说明三级优先级机制
- [ ] ✅ CLAUDE.md 文档更新，添加地区识别规则和示例
- [ ] ✅ 所有测试通过
- [ ] ✅ 手动验证示例调研表，各优先级都正常工作

---

## 技术要点

### DRY (Don't Repeat Yourself)
- `infer_region_from_text()` 统一处理站房名称和文件名的地区推断，避免重复逻辑
- 复用现有的 `extract_region()` 函数作为优先级3的兜底机制
- 统一的地区关键词映射表，在一处维护

### YAGNI (You Aren't Gonna Need It)
- 仅实现三级优先级提取，不添加额外的配置选项或复杂规则
- 简单的关键词匹配，不引入NLP或机器学习
- 文件名提取直接复用文本推断函数，保持简洁

### TDD (Test-Driven Development)
- 每个新函数先写测试，看到失败，再写实现
- 集成测试验证端到端流程和优先级逻辑
- 覆盖率测试验证真实调研表的提取成功率

### 频繁提交
- 每完成一个小功能就提交（函数实现、优先级逻辑、文档更新）
- 提交信息清晰说明改动内容和价值
- 每个任务独立提交，便于代码审查和回滚
