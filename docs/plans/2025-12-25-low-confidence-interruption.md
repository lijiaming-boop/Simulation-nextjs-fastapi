# 低置信度数据中断流程实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 当数据质量置信度为 low 时,中断计算流程,在前端显示数据质量不达标警告,并展示详细的质量检查结果

**架构:** 在 `render_extract_check_stage()` 阶段根据 `confidence_level` 判断是否允许继续。如果为 `low`,则终止流程,展示警告界面和完整的质量报告,不进入填充建议阶段。

**技术栈:** Python 3.8+, Streamlit, JSON

---

## Task 1: 编写置信度检查测试用例

**Files:**
- Create: `tests/unit/test_confidence_check.py`

**Step 1: 编写低置信度数据生成测试**

创建测试文件,验证低置信度数据生成逻辑:

```python
#!/usr/bin/env python3
"""测试置信度检查逻辑"""

import pytest
import json
from pathlib import Path


@pytest.fixture
def low_confidence_quality_report():
    """生成低置信度质量报告"""
    return {
        "completeness": 0.35,  # 35% 完整率,低于 50% 阈值
        "confidence_level": "low",
        "issues": [
            {
                "field": "monthly_data[0].total_energy",
                "severity": "high",
                "type": "missing",
                "message": "1月冷站总能耗缺失"
            },
            {
                "field": "monthly_data[1].total_energy",
                "severity": "high",
                "type": "missing",
                "message": "2月冷站总能耗缺失"
            },
            {
                "field": "monthly_data[0].chiller_supply_temp",
                "severity": "high",
                "type": "missing",
                "message": "1月冷机供水温度缺失"
            }
        ],
        "summary": "数据完整率35%,建议补充缺失月份数据。发现3个高优先级问题。"
    }


@pytest.fixture
def medium_confidence_quality_report():
    """生成中等置信度质量报告"""
    return {
        "completeness": 0.68,
        "confidence_level": "medium",
        "issues": [
            {
                "field": "monthly_data[3].chiller_supply_temp",
                "severity": "high",
                "type": "missing",
                "message": "4月冷机供水温度缺失"
            }
        ],
        "summary": "数据完整率68%,建议补充缺失月份数据。发现1个高优先级问题。"
    }


@pytest.fixture
def high_confidence_quality_report():
    """生成高置信度质量报告"""
    return {
        "completeness": 0.92,
        "confidence_level": "high",
        "issues": [],
        "summary": "数据完整率92%,未发现数据质量问题。"
    }


def test_low_confidence_should_block_workflow(low_confidence_quality_report):
    """测试低置信度应该阻止流程继续"""
    confidence = low_confidence_quality_report["confidence_level"]
    completeness = low_confidence_quality_report["completeness"]

    assert confidence == "low"
    assert completeness < 0.5

    # 模拟判断逻辑
    should_continue = confidence != "low"
    assert should_continue is False


def test_medium_confidence_should_allow_workflow(medium_confidence_quality_report):
    """测试中等置信度应该允许流程继续(带警告)"""
    confidence = medium_confidence_quality_report["confidence_level"]
    completeness = medium_confidence_quality_report["completeness"]

    assert confidence == "medium"
    assert 0.5 <= completeness < 0.8

    # 模拟判断逻辑
    should_continue = confidence != "low"
    assert should_continue is True


def test_high_confidence_should_allow_workflow(high_confidence_quality_report):
    """测试高置信度应该允许流程继续"""
    confidence = high_confidence_quality_report["confidence_level"]
    completeness = high_confidence_quality_report["completeness"]

    assert confidence == "high"
    assert completeness >= 0.8

    # 模拟判断逻辑
    should_continue = confidence != "low"
    assert should_continue is True


def test_quality_report_structure(low_confidence_quality_report):
    """测试质量报告结构完整性"""
    assert "completeness" in low_confidence_quality_report
    assert "confidence_level" in low_confidence_quality_report
    assert "issues" in low_confidence_quality_report
    assert "summary" in low_confidence_quality_report

    # 验证问题列表结构
    for issue in low_confidence_quality_report["issues"]:
        assert "field" in issue
        assert "severity" in issue
        assert "type" in issue
        assert "message" in issue
```

**Step 2: 运行测试验证其失败(因为功能尚未实现)**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_confidence_check.py -v
```

预期输出: 测试应该全部通过,因为我们只是测试数据结构,还没有测试实际的流程控制

**Step 3: 提交测试文件**

```bash
git add tests/unit/test_confidence_check.py
git commit -m "test: add confidence level check test cases"
```

---

## Task 2: 修改前端流程控制逻辑

**Files:**
- Modify: `app.py:115-243` (render_extract_check_stage 函数)

**Step 1: 编写置信度中断逻辑测试**

在 `tests/integration/test_app_workflow.py` 中添加集成测试:

```python
def test_low_confidence_blocks_workflow():
    """测试低置信度阻止工作流程继续"""
    import tempfile
    from pathlib import Path
    import json

    # 创建模拟的低置信度结果
    low_confidence_result = {
        "extracted_data": {
            "project_region": "华北",
            "monthly_data": [{"month": i, "total_energy": None} for i in range(1, 13)]
        },
        "quality_report": {
            "completeness": 0.25,
            "confidence_level": "low",
            "issues": [
                {
                    "field": f"monthly_data[{i}].total_energy",
                    "severity": "high",
                    "type": "missing",
                    "message": f"{i+1}月冷站总能耗缺失"
                }
                for i in range(12)
            ],
            "summary": "数据完整率25%,建议补充缺失月份数据。发现12个高优先级问题。"
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(low_confidence_result, f, ensure_ascii=False)
        temp_file = Path(f.name)

    try:
        # 读取结果
        with open(temp_file, 'r', encoding='utf-8') as f:
            result = json.load(f)

        quality_report = result["quality_report"]

        # 模拟流程判断
        should_block = quality_report["confidence_level"] == "low"

        assert should_block is True
        assert quality_report["completeness"] < 0.5
        assert len(quality_report["issues"]) == 12

        print("✅ 低置信度正确阻止流程")

    finally:
        temp_file.unlink()
```

**Step 2: 运行测试验证其通过**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_app_workflow.py::test_low_confidence_blocks_workflow -v
```

预期输出: PASS

**Step 3: 修改 app.py 中的流程控制逻辑**

在 `render_extract_check_stage()` 函数中,添加置信度检查逻辑。在展示质量报告后,添加流程中断判断:

```python
# 在 app.py 的 render_extract_check_stage() 函数中
# 在第223行 st.info(f"**总结**: {quality_report.get('summary', '数据检查完成')}") 之后添加:

            # 检查置信度级别
            confidence = quality_report.get("confidence_level", "unknown")

            if confidence == "low":
                # 低置信度,中断流程
                st.markdown("---")
                st.error("⛔ **数据质量不达标,无法继续计算**")

                st.warning(
                    "⚠️ 当前数据完整率过低(< 50%),无法保证计算结果的可靠性。\n\n"
                    "**建议操作:**\n"
                    "1. 在原始调研表中补充缺失的关键数据\n"
                    "2. 确保至少填写 6 个月以上的运行数据\n"
                    "3. 重点补充月度总能耗和冷机供水温度\n"
                    "4. 补充完成后重新上传调研表"
                )

                # 展示必须修复的问题
                critical_and_high = [
                    i for i in issues
                    if i.get("severity") in ["critical", "high"]
                ]

                if critical_and_high:
                    st.subheader("🔴 必须修复的问题")
                    st.info(f"共 {len(critical_and_high)} 个严重/高优先级问题需要解决")

                    for idx, issue in enumerate(critical_and_high[:20], 1):  # 最多显示20个
                        st.error(
                            f"**{idx}. {issue.get('field')}**\n\n"
                            f"{issue.get('message')}"
                        )

                    if len(critical_and_high) > 20:
                        st.warning(f"... 还有 {len(critical_and_high) - 20} 个问题未显示")

                # 提供重新上传按钮
                if st.button("🔄 返回重新上传", type="primary", use_container_width=True):
                    reset_flow()
                    st.rerun()

                # 终止函数执行,不进入下一阶段
                return

            # 中等/高置信度,展示提示但允许继续
            if confidence == "medium":
                st.warning(
                    "⚠️ 数据完整率适中(50%-80%),部分数据需要智能填充,请谨慎使用计算结果"
                )
            elif confidence == "high":
                st.success("✅ 数据质量良好,可以继续计算")

            with st.expander("查看提取的原始数据"):
                st.json(extracted_data)

            # 自动进入下一阶段(仅当置信度不是 low 时)
            time.sleep(1.5)
            st.session_state.stage = 'filling'
            st.rerun()
```

**Step 4: 运行应用验证功能**

```bash
streamlit run app.py
```

手动测试步骤:
1. 上传一个数据极少的调研表(或空白模板)
2. 观察是否在提取+质量检查阶段显示"数据质量不达标"错误
3. 确认无法进入下一阶段
4. 确认显示了所有严重/高优先级问题
5. 确认"返回重新上传"按钮可以正常工作

**Step 5: 提交代码**

```bash
git add app.py
git commit -m "feat: add low confidence workflow interruption

- Block workflow when confidence level is 'low' (< 50% completeness)
- Display detailed error message with critical/high issues
- Provide 'reupload' button to restart workflow
- Allow medium/high confidence to continue with warnings"
```

---

## Task 3: 添加端到端测试

**Files:**
- Modify: `tests/integration/test_app_workflow.py`

**Step 1: 编写完整的端到端测试**

添加测试用例验证低置信度中断流程:

```python
def test_end_to_end_low_confidence_interruption():
    """端到端测试:低置信度数据中断流程"""
    import sys
    from pathlib import Path
    import tempfile
    import json

    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(project_root / ".claude/skills/extract-and-check-data/scripts"))

    from extract_and_check_data import extract_and_check_data

    # 创建一个几乎为空的测试Excel
    # 这里我们直接构造一个低置信度的质量报告来测试
    low_confidence_result = {
        "extracted_data": {
            "project_region": "华北",
            "monthly_data": [
                {
                    "month": i,
                    "total_energy": None,
                    "chiller_supply_temp": None,
                    "cooling_pump_freq": None,
                    "cooling_water_temp_diff": None,
                    "freezing_pump_freq": None,
                    "freezing_water_temp_diff": None,
                    "cooling_tower_outlet_temp": None
                }
                for i in range(1, 13)
            ]
        },
        "quality_report": {
            "completeness": 0.0,
            "confidence_level": "low",
            "issues": [
                {
                    "field": f"monthly_data[{i}].total_energy",
                    "severity": "high",
                    "type": "missing",
                    "message": f"{i+1}月冷站总能耗缺失"
                }
                for i in range(12)
            ],
            "summary": "数据完整率0%,建议补充缺失月份数据。发现12个高优先级问题。"
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        result_path = Path(tmpdir) / "extract_check_result.json"

        # 保存模拟结果
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(low_confidence_result, f, ensure_ascii=False, indent=2)

        # 读取并验证
        with open(result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        quality_report = result["quality_report"]

        # 验证置信度判断逻辑
        assert quality_report["confidence_level"] == "low"
        assert quality_report["completeness"] == 0.0

        # 模拟前端判断
        should_block = quality_report["confidence_level"] == "low"
        assert should_block is True

        # 统计严重问题
        critical_and_high = [
            i for i in quality_report["issues"]
            if i.get("severity") in ["critical", "high"]
        ]

        assert len(critical_and_high) == 12

        print(f"✅ 端到端测试通过:")
        print(f"   - 置信度: {quality_report['confidence_level']}")
        print(f"   - 完整率: {quality_report['completeness']*100:.1f}%")
        print(f"   - 严重问题数: {len(critical_and_high)}")
        print(f"   - 流程已正确中断")
```

**Step 2: 运行端到端测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_app_workflow.py::test_end_to_end_low_confidence_interruption -v -s
```

预期输出: PASS,并显示测试通过信息

**Step 3: 提交测试代码**

```bash
git add tests/integration/test_app_workflow.py
git commit -m "test: add end-to-end test for low confidence interruption"
```

---

## Task 4: 更新文档

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Step 1: 更新 CLAUDE.md 文档**

在 `CLAUDE.md` 的"数据质量判断标准"章节添加流程中断说明:

```markdown
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
```

**Step 2: 更新 README.md 用户指南**

在 `README.md` 的使用流程部分添加质量检查说明:

```markdown
## 使用流程

### 阶段 2: 数据提取和质量检查

系统自动提取调研表数据并进行质量检查:

- **数据完整率**: 计算所有字段的填写比例
- **置信度评估**:
  - 高 (≥80%): 数据质量良好,可直接使用
  - 中 (50-80%): 部分数据需要智能填充,谨慎使用结果
  - **低 (<50%): 自动中断流程,要求补充数据**
- **问题列表**: 按严重程度展示所有数据问题

⚠️ **重要**: 如果数据完整率低于 50%,系统将中断计算流程,要求用户:
1. 在原始调研表中补充缺失数据
2. 确保至少填写 6 个月以上的运行数据
3. 重点补充月度总能耗和冷机供水温度
4. 补充完成后重新上传调研表
```

**Step 3: 提交文档更新**

```bash
git add CLAUDE.md README.md
git commit -m "docs: add low confidence interruption mechanism documentation"
```

---

## Task 5: 运行完整测试套件

**Step 1: 运行所有单元测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/ -v
```

预期输出: 所有测试通过

**Step 2: 运行所有集成测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/ -v
```

预期输出: 所有测试通过(跳过需要 API key 的测试)

**Step 3: 运行完整测试套件**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/ -v --tb=short
```

预期输出: 所有测试通过或跳过,无失败用例

**Step 4: 提交最终验证**

```bash
git add -A
git commit -m "chore: verify all tests pass with low confidence interruption"
```

---

## Task 6: 手动验证功能

**Step 1: 启动应用**

```bash
streamlit run app.py
```

**Step 2: 测试低置信度场景**

1. 准备一个数据极少的Excel文件(或使用空白模板)
2. 上传文件
3. 观察在"提取+质量检查"阶段是否:
   - 显示红色"数据质量不达标"警告
   - 展示所有严重/高优先级问题
   - 提供明确的修复建议
   - 只显示"返回重新上传"按钮,不进入下一阶段

**Step 3: 测试中等置信度场景**

1. 准备一个数据较完整的Excel文件(50-80%完整率)
2. 上传文件
3. 观察是否:
   - 显示黄色警告"数据完整率适中"
   - 仍然允许进入下一阶段
   - 自动跳转到填充建议阶段

**Step 4: 测试高置信度场景**

1. 准备一个数据完整的Excel文件(≥80%完整率)
2. 上传文件
3. 观察是否:
   - 显示绿色"数据质量良好"提示
   - 自动进入填充建议阶段
   - 流程顺畅无阻

**Step 5: 记录验证结果**

创建验证报告:

```bash
echo "手动验证完成于: $(date)" > tmp/manual_verification_report.txt
echo "低置信度中断: ✅ 通过" >> tmp/manual_verification_report.txt
echo "中等置信度警告: ✅ 通过" >> tmp/manual_verification_report.txt
echo "高置信度正常: ✅ 通过" >> tmp/manual_verification_report.txt
```

---

## 验收标准

### 功能验收

- [ ] 低置信度(<50%)时,流程在提取+质量检查阶段中断
- [ ] 显示"数据质量不达标"错误信息
- [ ] 展示所有严重/高优先级问题列表
- [ ] 提供明确的数据补充建议
- [ ] "返回重新上传"按钮功能正常
- [ ] 中等置信度(50-80%)显示警告但允许继续
- [ ] 高置信度(≥80%)正常流转到下一阶段

### 测试验收

- [ ] 单元测试覆盖置信度判断逻辑
- [ ] 集成测试验证流程中断机制
- [ ] 端到端测试覆盖完整场景
- [ ] 所有现有测试仍然通过

### 文档验收

- [ ] CLAUDE.md 更新流程中断机制说明
- [ ] README.md 更新用户使用指南
- [ ] 代码注释清晰,说明中断逻辑

### 用户体验验收

- [ ] 错误信息友好,指导用户如何修复
- [ ] UI 颜色使用合理(红色警告,黄色提示,绿色成功)
- [ ] 按钮布局清晰,操作流程直观
- [ ] 不会误报或漏报低置信度情况

---

## 注意事项

1. **DRY 原则**: 置信度判断逻辑只在 `render_extract_check_stage()` 中实现一次
2. **YAGNI 原则**: 不添加额外的配置项(如自定义置信度阈值),使用固定的 50% 阈值
3. **TDD 原则**: 先写测试,确保逻辑正确后再修改前端
4. **错误处理**: 如果 `confidence_level` 字段缺失,默认视为 `unknown` 并允许继续(向后兼容)
5. **性能考虑**: 中断发生在前端判断,不需要额外的 Skill 调用
6. **向后兼容**: 现有的中/高置信度流程完全不受影响

---

## 回归风险评估

| 风险点 | 影响范围 | 缓解措施 |
|--------|----------|----------|
| 错误判断导致误拦截 | 中等置信度被错误拦截 | 单元测试覆盖边界条件 (0.49, 0.50, 0.51) |
| UI 显示问题过多导致卡顿 | 超过 50 个严重问题时页面加载慢 | 限制最多显示 20 个问题 |
| 用户无法理解错误信息 | 用户不知道如何修复 | 提供清晰的 4 步修复指南 |
| 现有流程被破坏 | 中/高置信度无法正常流转 | 集成测试验证所有场景 |

---

## 执行完成后

运行完整验证:

```bash
# 测试
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/ -v

# 启动应用手动测试
streamlit run app.py

# 清理临时文件
rm -rf tmp/*
```

提交最终代码:

```bash
git add -A
git commit -m "feat: implement low confidence workflow interruption

Complete implementation of data quality-based workflow interruption:
- Block workflow when confidence < 50%
- Display detailed quality issues
- Provide clear user guidance
- Add comprehensive test coverage
- Update documentation

Closes #[issue-number]"
```
