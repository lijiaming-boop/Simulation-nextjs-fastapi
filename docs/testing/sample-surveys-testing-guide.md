# 示例调研表测试指南

## 概述

本测试套件使用6份不同质量等级的示例调研表，全面测试中央空调节能率智能测算系统的核心功能。

## 测试覆盖

### 测试场景

| 场景 | 文件 | 完整率 | 置信度 | 预期节能率 | 测试目的 |
|------|------|--------|--------|------------|----------|
| 齐全 | 【齐全】15.2%惠州光弘 | ≥80% | high | 15.2% | 验证完整数据流程 |
| 仅有夏季 | 【仅有夏季】6.5%和光同程 | 50-80% | medium | 6.5% | 验证季节性缺失填充 |
| 缺冬季 | 【缺冬季】10.4%石家庄仁和 | 50-80% | medium | 10.4% | 验证冬季数据填充 |
| 缺夏季 | 【缺夏季】12.1%上海和元 | 50-80% | medium | 12.1% | 验证夏季数据填充 |
| 参差不齐 | 【参差不齐】11.9% | 50-80% | medium | 11.9% | 验证插值填充策略 |
| 数据缺失过多 | 【数据缺失过多】工业板块 | <50% | low | N/A | 验证流程中断机制 |

### 功能覆盖

- ✅ 数据提取（extract-and-check-data skill）
- ✅ 质量检测（完整率、置信度、问题检测）
- ✅ 数据填充（suggest-data-filling skill + DataFiller）
- ✅ 节能率计算（ExcelCalculator）
- ✅ 流程中断（低置信度阻止）

## 运行测试

### 前置要求

```bash
# 设置 PYTHONPATH
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH

# 设置 API Key（用于调用 Claude Skills）
export ANTHROPIC_API_KEY='your-api-key'
```

### 运行单个场景测试

```bash
# 测试齐全数据
pytest tests/integration/test_sample_surveys_e2e.py::TestCompleteSurvey -v -s

# 测试仅有夏季
pytest tests/integration/test_sample_surveys_e2e.py::TestSummerOnlySurvey -v -s

# 测试数据缺失过多
pytest tests/integration/test_sample_surveys_e2e.py::TestInsufficientSurvey -v -s
```

### 运行所有场景测试

```bash
# 运行全部测试
pytest tests/integration/test_sample_surveys_e2e.py -v -s

# 仅运行批量测试和报告
pytest tests/integration/test_sample_surveys_e2e.py::TestAllSurveysBatch -v -s
```

## 测试输出

### 临时文件

测试过程中会在 `tmp/` 目录生成：
- `extract_check_result.json` - 提取和质量检查结果
- `extracted_data.json` - 提取的原始数据
- `quality_report.json` - 质量报告
- `filling_suggestions.json` - 填充建议
- `filled_data.json` - 填充后的数据
- `result_*.xlsx` - 节能率计算结果Excel文件

### 测试报告

批量测试会生成 `tmp/test_summary_report.json`，包含：
- 每份调研表的测试状态
- 完整率和置信度
- 节能率实际值与期望值
- 误差统计

## 验证标准

### 节能率容差

允许 ±0.5% 的计算误差，考虑到：
- Excel引擎差异（xlwings vs openpyxl）
- 浮点数精度
- 填充策略的近似性

### 置信度判断

- **高置信度 (high)**：完整率 ≥ 80%，可直接计算
- **中等置信度 (medium)**：完整率 50-80%，需填充后计算
- **低置信度 (low)**：完整率 < 50%，阻止计算流程

## 故障排查

### 常见问题

1. **Skill调用超时**
   - 增加timeout参数：`SkillCaller(timeout=600)`
   - 检查ANTHROPIC_API_KEY是否设置

2. **Excel计算失败**
   - 确保模板文件存在：`00_sample/机房智能化节能评估表-按冷站电量数据.xlsx`
   - 检查xlwings/openpyxl是否正确安装

3. **节能率偏差过大**
   - 检查填充策略是否正确应用
   - 对比 `filled_data.json` 和预期值
   - 检查Excel模板公式是否被修改

## 扩展测试

### 添加新的测试场景

1. 在 `tests/fixtures/sample_surveys.py` 中添加配置
2. 放置调研表文件到 `00_sample/示例调研表/`
3. 创建对应的测试类

### 自定义验证逻辑

修改 `TestHelper` 类中的验证方法：
- `validate_extracted_data()` - 数据结构验证
- `validate_quality_report()` - 质量报告验证
- `validate_filling_suggestions()` - 填充建议验证
