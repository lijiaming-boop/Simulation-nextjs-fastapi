# 保留上传文件原始文件名实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 在整个数据流中保留用户上传文件的原始文件名,以便在项目地区识别中作为第二优先级的推断来源

**架构:** 将原始文件名通过 session state 传递到提取流程,并在调用 extract-and-check-data skill 时作为参数传入,使文件名推断功能能够正常工作

**技术栈:** Streamlit session state, Python subprocess, Claude Agent SDK

---

## 背景说明

当前问题:
- 用户上传调研表时,文件被保存为固定名称 `tmp/upload_survey.xlsx`,丢失了原始文件名
- `extract-and-check-data` skill 的优先级2（从文件名推断地区）无法工作
- 调研表文件名如 "惠州光弘-调研表.xlsx"、"石家庄仁和药业.xlsx" 包含重要的地理位置信息

解决方案:
- 在 session state 中保存原始文件名
- 将原始文件名作为参数传递给 extract-and-check-data skill
- 更新 skill 脚本以接收并使用原始文件名进行地区推断

---

## Task 1: 在 app.py 中保存原始文件名

**Files:**
- Modify: `app.py:96-112`

**Step 1: 在 init_session_state 中添加 original_filename 字段**

在 `app.py` 的 `init_session_state()` 函数中添加新字段:

```python
def init_session_state():
    """初始化 session state"""
    if 'stage' not in st.session_state:
        st.session_state.stage = 'upload'
        st.session_state.uploaded_file = None
        st.session_state.original_filename = None  # 新增: 保存原始文件名
        st.session_state.extracted_data = None
        st.session_state.quality_report = None
        st.session_state.filling_suggestions = None
        st.session_state.result = None
```

**Step 2: 在 reset_flow 中清空 original_filename**

在 `reset_flow()` 函数中添加对应的清空逻辑:

```python
def reset_flow():
    """重置流程"""
    st.session_state.stage = 'upload'
    st.session_state.uploaded_file = None
    st.session_state.original_filename = None  # 新增
    st.session_state.extracted_data = None
    st.session_state.quality_report = None
    st.session_state.filling_suggestions = None
    st.session_state.result = None
```

**Step 3: 在上传阶段保存原始文件名**

在 `render_upload_stage()` 函数中,上传文件时保存原始文件名:

```python
    if uploaded_file:
        st.session_state.uploaded_file = uploaded_file
        st.session_state.original_filename = uploaded_file.name  # 新增: 保存原始文件名

        # 保存到临时目录
        tmp_dir = Path("tmp")
        tmp_dir.mkdir(exist_ok=True)

        upload_path = tmp_dir / "upload_survey.xlsx"
        with open(upload_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.success(f"✅ 文件已上传: {uploaded_file.name}")
        st.info(f"文件大小: {uploaded_file.size / 1024:.2f} KB")
```

**Step 4: 验证修改**

运行应用并检查上传后 session state 是否保存了原始文件名:

```bash
# 运行应用
streamlit run app.py
```

预期: 在浏览器开发者工具中可以看到 `st.session_state.original_filename` 保存了上传文件的原始名称

---

## Task 2: 更新 Skill 调用以传递原始文件名

**Files:**
- Modify: `app.py:115-132`
- Modify: `core/skill_caller.py:45-78`

**Step 1: 修改 app.py 中的 skill 调用**

在 `render_extract_check_stage()` 函数中,传递原始文件名:

```python
    with st.spinner("正在提取调研表数据并进行质量检查,请稍候..."):
        try:
            caller = SkillCaller(timeout=300)

            upload_path = Path("tmp/upload_survey.xlsx")
            output_path = Path("tmp/extract_check_result.json")

            # 获取原始文件名
            original_filename = st.session_state.get('original_filename', 'unknown.xlsx')

            # 调用合并的 Skill: 提取和质量检查,传递原始文件名
            skill_result = caller.call_skill(
                "extract-and-check-data",
                str(upload_path),
                str(output_path),
                original_filename  # 新增: 传递原始文件名
            )
```

**Step 2: 更新 SkillCaller.call_skill 方法签名**

修改 `core/skill_caller.py` 的 `call_skill` 方法以支持可变参数:

```python
    def call_skill(self, skill_name: str, *args) -> Dict[str, Any]:
        """调用指定的 Claude Skill

        Args:
            skill_name: Skill 名称
            *args: 传递给 skill 的位置参数

        Returns:
            包含 AI 响应的字典
        """
        # 构建命令
        cmd = ["claude", "skill", skill_name] + list(args)

        # ... 其余代码不变
```

**Step 3: 验证参数传递**

添加调试日志确认参数正确传递:

```python
    def call_skill(self, skill_name: str, *args) -> Dict[str, Any]:
        """调用指定的 Claude Skill"""
        # 构建命令
        cmd = ["claude", "skill", skill_name] + list(args)

        # 调试日志
        print(f"[DEBUG] 调用 skill: {skill_name}")
        print(f"[DEBUG] 参数: {args}")

        # ... 其余代码不变
```

运行测试:

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_skill_caller.py -v -s
```

预期: 测试通过,日志显示参数正确传递

---

## Task 3: 更新 Skill 脚本以接收原始文件名参数

**Files:**
- Modify: `.claude/skills/extract-and-check-data/SKILL.md:12-16`
- Modify: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py:721-728`

**Step 1: 更新 SKILL.md 文档**

修改输入参数说明:

```markdown
## 输入参数

1. `survey_excel_path`: 调研表 Excel 文件路径
2. `output_json_path`: 输出 JSON 文件路径
3. `original_filename` (可选): 原始上传文件名,用于地区推断优先级2
```

**Step 2: 更新脚本 main() 函数**

修改 `extract_and_check_data.py` 的命令行参数处理:

```python
def main():
    """命令行入口"""
    if len(sys.argv) < 3:
        print('用法: python extract_and_check_data.py <调研表Excel路径> <输出JSON路径> [原始文件名]')
        sys.exit(1)

    survey_excel_path = sys.argv[1]
    output_json_path = sys.argv[2]
    original_filename = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        extract_and_check_data(survey_excel_path, output_json_path, original_filename)
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
```

**Step 3: 更新 extract_and_check_data() 函数签名**

```python
def extract_and_check_data(survey_excel_path: str, output_json_path: str, original_filename: Optional[str] = None):
    """提取数据并进行质量检查

    Args:
        survey_excel_path: 调研表路径
        output_json_path: 输出路径
        original_filename: 原始文件名(用于地区推断)
    """

    # 步骤 1: 提取数据,传递原始文件名
    extracted_data = extract_data_from_excel(survey_excel_path, original_filename)

    # ... 其余代码不变
```

**Step 4: 更新 extract_data_from_excel() 函数**

```python
def extract_data_from_excel(survey_excel_path: str, original_filename: Optional[str] = None) -> Dict[str, Any]:
    """从 Excel 文件提取数据

    Args:
        survey_excel_path: Excel 文件路径
        original_filename: 原始文件名(优先用于地区推断)
    """
    xls = pd.ExcelFile(survey_excel_path)

    # 查找冷站工作表
    cold_station_sheet = find_cold_station_sheet(xls)
    if not cold_station_sheet:
        return {
            "error": True,
            "message": "找不到包含冷站数据的工作表,请确认上传了正确的文件"
        }

    df = pd.read_excel(xls, sheet_name=cold_station_sheet, header=None)

    # 提取项目地区（三级优先级）
    project_region = None

    # 优先级1: 从站房名称推断地区
    station_name = extract_station_name(df)
    if station_name:
        project_region = infer_region_from_text(station_name)

    # 优先级2: 从原始文件名推断地区 (使用传入的 original_filename)
    if not project_region and original_filename:
        project_region = extract_region_from_filename(original_filename)

    # 优先级2备选: 如果没有提供 original_filename,使用当前文件路径
    if not project_region:
        project_region = extract_region_from_filename(survey_excel_path)

    # 优先级3: 从项目总体情况表提取
    if not project_region and '项目总体情况' in xls.sheet_names:
        df_overview = pd.read_excel(xls, sheet_name='项目总体情况', header=None)
        project_region = extract_region(df_overview)

    # ... 其余代码不变
```

**Step 5: 运行单元测试验证**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/ -k "test_extract" -v
```

预期: 所有提取相关的测试通过

---

## Task 4: 编写测试验证原始文件名功能

**Files:**
- Create: `tests/unit/test_original_filename.py`

**Step 1: 编写测试文件**

```python
"""测试原始文件名保留和地区推断功能"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.skill_caller import SkillCaller


class TestOriginalFilenamePreservation:
    """测试原始文件名保留功能"""

    def test_skill_caller_accepts_variable_args(self):
        """测试 SkillCaller 支持可变参数"""
        caller = SkillCaller(timeout=30)

        # 模拟调用 skill 传递3个参数
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps({
                "messages": [
                    {"role": "assistant", "content": "测试"}
                ]
            })

            result = caller.call_skill(
                "extract-and-check-data",
                "input.xlsx",
                "output.json",
                "惠州光弘-调研表.xlsx"
            )

            # 验证调用参数
            called_cmd = mock_run.call_args[0][0]
            assert called_cmd[0] == "claude"
            assert called_cmd[1] == "skill"
            assert called_cmd[2] == "extract-and-check-data"
            assert called_cmd[3] == "input.xlsx"
            assert called_cmd[4] == "output.json"
            assert called_cmd[5] == "惠州光弘-调研表.xlsx"

    def test_region_inference_from_filename_priority_2(self, tmp_path):
        """测试优先级2: 从原始文件名推断地区"""
        from .claude.skills.extract_and_check_data.scripts.extract_and_check_data import (
            extract_region_from_filename,
            infer_region_from_text
        )

        # 测试各种文件名格式
        test_cases = [
            ("惠州光弘-调研表.xlsx", "华南"),
            ("石家庄仁和药业中央空调节能调研表.xlsx", "华北"),
            ("深圳工业园-2024年调研.xlsx", "华南"),
            ("北京总部-节能调研表.xlsx", "华北"),
            ("/tmp/upload/武汉分公司-调研表.xlsx", "华中"),
        ]

        for filename, expected_region in test_cases:
            result = extract_region_from_filename(filename)
            assert result == expected_region, f"文件名 '{filename}' 应推断为 {expected_region}, 实际为 {result}"
```

**Step 2: 运行测试验证**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_original_filename.py -v
```

预期: 所有测试通过

**Step 3: Commit 测试文件**

```bash
git add tests/unit/test_original_filename.py
git commit -m "test: add original filename preservation tests

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: 更新文档说明功能变更

**Files:**
- Modify: `CLAUDE.md:180-230`

**Step 1: 更新项目地区识别规则章节**

在 `CLAUDE.md` 的"项目地区识别规则"章节中更新文件名推断说明:

```markdown
## 项目地区识别规则

系统支持从调研表自动识别项目所属地区,用于匹配气象数据。采用**三级优先级**提取策略,大幅提高识别成功率。

**识别方法（按优先级）：**
1. **站房名称推断（优先级1）**：从"冷站"sheet的"站房名称"字段提取城市关键词
2. **文件名推断（优先级2）**：从用户上传的**原始文件名**提取城市关键词
   - ✅ 现在会保留用户上传时的原始文件名（如"惠州光弘-调研表.xlsx"）
   - ✅ 即使文件被临时保存为 `tmp/upload_survey.xlsx`,原始文件名仍会用于地区推断
3. **项目总体情况扫描（优先级3，兜底）**：从"项目总体情况"sheet扫描所有单元格匹配省市关键词

**提取示例：**

| 提取源 | 示例 | 推断地区 |
|--------|------|----------|
| 站房名称 | "深圳工业园区F栋制冷站" | 华南 |
| 站房名称 | "北京总部冷站" | 华北 |
| **原始文件名** | **"惠州光弘-调研表.xlsx"** | **华南** |
| **原始文件名** | **"石家庄仁和药业中央空调节能调研表.xlsx"** | **华北** |
| 项目总体情况 | 单元格包含"武汉市" | 华中 |
```

**Step 2: 添加数据流说明**

在文档开头的"数据流向"章节中添加说明:

```markdown
### 数据流向
```
用户上传调研表Excel (保留原始文件名)
        ↓
extract-and-check-data Skill (使用原始文件名进行地区推断)
        ↓
JSON数据 + 质量报告
        ↓
suggest-data-filling Skill
        ↓
DataFiller
        ↓
ExcelCalculator
        ↓
节能率结果
```
```

**Step 3: Commit 文档更新**

```bash
git add CLAUDE.md
git commit -m "docs: update region inference to mention original filename preservation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: 端到端测试验证完整流程

**Files:**
- Create: `tests/integration/test_original_filename_e2e.py`

**Step 1: 编写端到端测试**

```python
"""端到端测试: 验证原始文件名在整个流程中正确传递"""

import json
import pytest
from pathlib import Path
import shutil

# 测试文件路径
SAMPLE_DIR = Path("00_sample/示例调研表")
惠州_SURVEY = SAMPLE_DIR / "惠州光弘-调研表-齐全数据.xlsx"


@pytest.mark.integration
@pytest.mark.skipif(not惠州_SURVEY.exists(), reason="示例文件不存在")
class TestOriginalFilenameE2E:
    """测试原始文件名的端到端流程"""

    def test_extract_with_original_filename(self, tmp_path):
        """测试提取数据时使用原始文件名推断地区"""
        from core.skill_caller import SkillCaller

        # 复制示例文件到临时目录(模拟上传)
        temp_upload = tmp_path / "upload_survey.xlsx"
        shutil.copy(惠州_SURVEY, temp_upload)

        # 保存原始文件名
        original_filename =惠州_SURVEY.name  # "惠州光弘-调研表-齐全数据.xlsx"

        # 调用 skill,传递原始文件名
        output_path = tmp_path / "extract_check_result.json"
        caller = SkillCaller(timeout=300)

        result = caller.call_skill(
            "extract-and-check-data",
            str(temp_upload),
            str(output_path),
            original_filename
        )

        # 验证结果
        assert result["success"], "Skill 调用应该成功"

        # 读取输出 JSON
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 验证地区识别
        extracted_data = data.get("extracted_data", {})
        project_region = extracted_data.get("project_region")

        # 惠州属于华南地区
        assert project_region == "华南", f"应从文件名'惠州光弘'推断为华南,实际为: {project_region}"

    def test_full_pipeline_preserves_filename(self, tmp_path):
        """测试完整流程保留原始文件名"""
        # 这个测试需要启动 Streamlit 应用,暂时跳过
        # 可以通过手动测试验证
        pytest.skip("需要手动测试 Streamlit 应用")
```

**Step 2: 运行集成测试**

```bash
export ANTHROPIC_API_KEY='your-api-key'
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_original_filename_e2e.py -v -s
```

预期: 测试通过,原始文件名被正确用于地区推断

**Step 3: Commit 集成测试**

```bash
git add tests/integration/test_original_filename_e2e.py
git commit -m "test: add e2e test for original filename preservation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: 手动测试验证用户体验

**Step 1: 启动应用进行手动测试**

```bash
streamlit run app.py
```

**Step 2: 测试场景**

上传示例文件并验证:

1. **上传"惠州光弘-调研表-齐全数据.xlsx"**
   - 检查 session state 是否保存了原始文件名
   - 验证提取结果中 project_region 是否为"华南"
   - 检查 AI 分析过程中是否提到使用了文件名推断

2. **上传"石家庄XX-调研表.xlsx"（如果有）**
   - 验证是否识别为"华北"

**Step 3: 检查日志输出**

在终端查看调试日志:

```
[DEBUG] 调用 skill: extract-and-check-data
[DEBUG] 参数: ('tmp/upload_survey.xlsx', 'tmp/extract_check_result.json', '惠州光弘-调研表-齐全数据.xlsx')
```

预期: 日志显示原始文件名正确传递

**Step 4: 验证降级兼容性**

测试没有站房名称和原始文件名的情况:
- 上传匿名文件（如 "test.xlsx"）
- 验证系统是否回退到优先级3（项目总体情况扫描）

---

## Task 8: 清理和最终提交

**Step 1: 移除调试日志**

从 `core/skill_caller.py` 中移除调试 print 语句:

```python
    def call_skill(self, skill_name: str, *args) -> Dict[str, Any]:
        """调用指定的 Claude Skill"""
        # 构建命令
        cmd = ["claude", "skill", skill_name] + list(args)

        # 移除这两行调试日志
        # print(f"[DEBUG] 调用 skill: {skill_name}")
        # print(f"[DEBUG] 参数: {args}")

        # ... 其余代码
```

**Step 2: 运行完整测试套件**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/ -v
```

预期: 所有测试通过

**Step 3: 最终提交**

```bash
git add .
git commit -m "feat: preserve uploaded filename for region inference

- Store original filename in session state
- Pass original filename to extract-and-check-data skill
- Update skill script to use original filename as priority 2
- Add tests for filename preservation
- Update documentation

This enables the region inference priority 2 (filename-based inference)
to work correctly with user-uploaded files.

Example: '惠州光弘-调研表.xlsx' → inferred region: 华南

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 验收标准

功能完成的验收标准:

1. ✅ **原始文件名保留**: 上传文件后,session state 保存了 `original_filename`
2. ✅ **参数正确传递**: SkillCaller 将原始文件名传递给 skill 脚本
3. ✅ **地区推断工作**: 上传"惠州XX.xlsx"文件,能识别为"华南"地区
4. ✅ **降级兼容**: 没有原始文件名时,系统仍能通过其他方式推断地区
5. ✅ **测试通过**: 所有单元测试和集成测试通过
6. ✅ **文档更新**: CLAUDE.md 准确描述了原始文件名保留机制

---

## 注意事项

1. **向后兼容**: 原始文件名参数是可选的,不会破坏现有的命令行调用
2. **优先级顺序**: 文件名推断仍然是第二优先级,只在站房名称推断失败时才使用
3. **测试数据**: 使用现有的示例调研表进行测试,无需创建新的测试数据
4. **错误处理**: 如果原始文件名为空或无法推断地区,系统应优雅降级到优先级3

---

## 相关技术细节

### Session State 数据流

```
用户上传文件 (uploaded_file.name)
    ↓
st.session_state.original_filename = "惠州光弘-调研表.xlsx"
    ↓
caller.call_skill("extract-and-check-data", upload_path, output_path, original_filename)
    ↓
claude skill extract-and-check-data <path> <output> "惠州光弘-调研表.xlsx"
    ↓
extract_data_from_excel(..., original_filename="惠州光弘-调研表.xlsx")
    ↓
extract_region_from_filename("惠州光弘-调研表.xlsx") → "华南"
```

### 地区关键词映射

当前支持的城市关键词（位于 `infer_region_from_text` 函数）:
- 华南: 惠州、深圳、广州、东莞、佛山等
- 华北: 石家庄、北京、天津、唐山、保定等
- 其他地区: 见代码中的 `regions` 字典
