---
name: plant-simulation
description: 冷站性能仿真技能。根据收集到的站房拓扑、COP性能曲线和工况需求数据，动态生成Python仿真脚本并执行，输出8760小时逐时仿真结果、分析图表和报告。支持新站房（需求冷量+COP计算）和旧站房（基准+优化对比节能率）两种模式。
---

# Plant Simulation Skill - 冷站性能仿真

## 任务

根据用户提供的站房设备拓扑、COP性能曲线和月度运行工况数据，生成完整的Python仿真脚本并执行，输出全年8760小时逐时仿真结果。

## 工作模式

本技能根据第3个参数（task_type）区分不同任务：

### 1. extract_topology - 从调研表提取拓扑
- 输入: 调研表Excel路径, 输出JSON路径
- 任务: 用 openpyxl 读取 Excel，重点定位“冷站” sheet 中的设备规格表

**解析要点**：
1. 找到设备规格表：表头行包含列名如“类型、品牌、型号、台数、制冷量/kW、功率/kW、COP、变频/工频”
2. 只提取真正的设备数据行（有具体品牌名+型号+数值型制冷量/功率数据）
3. 必须跳过：表头行、说明性文字（“例如：”“示例：”）、调研问题文本（“现场是否有...”）、月度运行数据
4. 设备分类：冷机、冷却泵、冷冻泵、冷却塔
5. 同类设备合并台数

**输出 JSON 格式**（必须用英文键名）：
```json
{
  "project_name": "项目名称",
  "chillers": [{"brand": "约克", "model": "YZ-3000RT", "type": "变频", "count": 2, "capacity_kw": 3516, "power_kw": 680, "rated_cop": 5.17, "vfd": true}],
  "cooling_pumps": [{"power_kw": 90, "count": 4, "vfd": true}],
  "chilled_pumps": [{"power_kw": 75, "count": 3, "vfd": true}],
  "towers": [{"fan_power_kw": 45, "count": 12, "vfd": true, "type": "闭式"}],
  "special": {"type": "none"}
}
```
- capacity_kw/power_kw/rated_cop/fan_power_kw 必须是数字，不能是 null
- 不要包含调研表的问题文本和说明性文字

### 2. parse_topology - 解析用户文本输入
- 输入: 用户输入文本文件路径, 输出JSON路径
- 任务: 将自然语言描述的设备信息解析为结构化JSON
- 输出: 结构化拓扑JSON

### 3. parse_cop_curve - 识别性能曲线图片
- 输入: 性能曲线图片路径, 输出JSON路径
- 任务: 从COP性能曲线图片中提取二维COP数据表
- 输出: COP查找表JSON

### 4. generate_operating - 生成月度运行组合
- 输入: 数据文件路径(或文本), 输出JSON路径
- 任务: 整理月度冷机运行组合、负载率、冷量需求
- 输出: 月度运行组合JSON

### 5. new_station - 新站房仿真（完整仿真）
- 输入: 汇总数据JSON路径, 输出目录
- 任务: 生成并执行完整仿真脚本
- 输出: 8760h结果 + 图表 + 报告

### 6. old_station - 旧站房仿真（基准+优化对比）
- 输入: 汇总数据JSON路径, 输出目录
- 任务: 生成并执行基准仿真和优化仿真，计算节能率
- 输出: 8760h结果 + 对比图表 + 报告 + 节能率

## 输入数据格式

### 汇总输入 JSON (sim_input_all.json)

```json
{
  "project_name": "项目名称",
  "sim_mode": "new_station | old_station",
  "topology": {
    "chillers": [
      {"brand": "约克", "model": "YZ-3000RT", "type": "中温变频", "count": 2, "capacity_kw": 10551, "power_kw": 750, "rated_cop": 6.5}
    ],
    "cooling_pumps": [{"power_kw": 90, "count": 4, "vfd": true}],
    "chilled_pumps": [{"power_kw": 75, "count": 3, "vfd": true}],
    "towers": [{"fan_power_kw": 45, "count": 12, "vfd": true, "type": "闭式"}],
    "special": {"type": "none|storage|ice|heat_recovery", "capacity": 0}
  },
  "cop_data": {
    "约克 YZ-3000RT (中温变频)": {
      "cw_temps": [18, 19, ..., 33],
      "load_ratios": [1.0, 0.9, ..., 0.2],
      "cop_table": [[...], ...]
    }
  },
  "operating_conditions": {
    "months": [1, 2, ..., 12],
    "chiller_combination": ["2×3000RT", ...],
    "load_ratio": [0.6, ...],
    "cooling_demand_kwh": [100000, ...],
    "chw_supply_temp": [7, ...],
    "cw_temp": [28, ...],
    "notes": ["冬季", ...],
    "region": "华南",
    "electricity_price": 0.65
  },
  "target_energy_saving_rate": 0.065,
  "project_name": "XX工厂中央空调冷站"
}
```

## 仿真代码生成规范

### 代码结构（必须包含）

```python
"""
{project_name} 冷站性能仿真
仿真模式: {new_station/old_station}
生成时间: {timestamp}
"""

# 第一部分: 设备参数与COP数据
# - 从输入JSON加载设备参数
# - 构建二维COP插值器 (RegularGridInterpolator)
# - 冷却水温度 × 负荷率 → COP

# 第二部分: 气象与负荷模型
# - 月度冷却水温度（基于项目地区）
# - 24小时负荷曲线（工业/商业）
# - 月度冷量需求分配

# 第三部分: 加减机策略
# - 根据冷量需求自动分配各机组负荷
# - 优先高效机组，保持PLR在最优区间

# 第四部分: 逐时仿真循环 (8760h)
# - 每小时: 查COP → 算主机功耗 → 算辅机功耗 → 记录
# - 辅机: 变频泵三次方律 P = P_rated × (f/50)^3

# 第五部分: 结果输出
# - 8760h逐时CSV
# - 月度汇总Excel
# - 分析图表 (matplotlib)
# - Markdown报告
```

### 物理约束（必须遵守）

1. **COP卡诺极限**: COP ≤ T_cold / (T_hot - T_cold)，其中温度为绝对温标(K)
2. **变频泵三次方律**: P_actual = P_rated × (freq/50)^3，最低频率限制25Hz
3. **冷却塔逼近度**: 冷却水出水温度 ≥ 湿球温度 + 3°C
4. **负荷率范围**: 离心机最低负荷率20%，低于则停机
5. **能量守恒**: 供冷量 = 主机功耗 × COP
6. **默认开机顺序**: 若运行组合只指定开机台数 N 而未指定具体主机，默认按 topology.chillers 数组顺序开前 N 台（优先开大机制冷量主机）
7. **月度冷量计算**: cooling_demand_kw = 开机台数 × 单机容量 × 负载率，工作日/休息日加权平均

### 新站房仿真要点

- 无历史基准，直接基于需求冷量和控制策略计算
- 输出: 全年COP、月度能耗、设备运行时间
- 图表: COP专项分析、设备运行分析、综合性能分析

### 旧站房仿真要点

- **基准仿真**: 使用调研表实际运行参数（固定频率、固定台数）
- **优化仿真**: 应用控制策略（温差控制、变频联动、群控优化）
- **节能率计算**: (基准能耗 - 优化能耗) / 基准能耗 × 100%
- **关键约束**: 节能率需与空调节能率模块计算结果误差 < 1%

### 优化控制策略（旧站房）

| 设备 | 基准控制 | 优化策略 |
|------|---------|---------|
| 冷冻泵 | 固定频率 | 供回水温差PID控制(目标4-5°C) |
| 冷却泵 | 固定频率 | 压差控制+台数联动 |
| 冷却塔 | 固定频率 | 出水温度逼近度控制 |
| 冷机 | 人工启停 | AI群控+负荷优化分配 |

## 输出要求

### 文件输出（到指定输出目录）

1. **8760h逐时CSV**: `{project}_8760h_results.csv`
   - 列: month, hour, cooling_kw, chiller_power_kw, pump_power_kw, tower_power_kw, total_power_kw, cop, chiller_on, plr

2. **月度汇总Excel**: `{project}_monthly_summary.xlsx`
   - Sheet1: 月度能耗汇总
   - Sheet2: 设备运行统计

3. **分析图表** (matplotlib, 英文标签):
   - `{project}_cop_analysis.png`: Monthly COP trend, load-COP relationship
   - `{project}_equipment_operation.png`: Equipment energy breakdown, runtime
   - `{project}_overall_performance.png`: Energy structure, seasonal comparison

4. **Markdown报告**: `{project_name}_COP性能仿真分析报告.md`
   - **标题格式**: `# {项目名称}中央空调冷站 控制策略优化仿真报告`
   - **报告结构**（必须包含以下章节）：
     - 一、项目概况（表格：项目名称、地址、系统类型、总装机制冷量、仿真时长）
     - 二、设备现状（设备配置表、调研表实际月度运行参数表、关键问题识别）
     - 三、优化控制策略（可优化设备表、冷冻泵温差控制逻辑、冷却塔优化逻辑）
     - 四、仿真结果（年度核心指标对比表、分项能耗对比表、月度详细对比表）
     - 五、节能分析（节能贡献分解表、经济效益表、仿真保守因素说明）
     - 六、图表引用（嵌入生成的 PNG 图表）
     - 七、实施建议（分阶段措施、注意事项）
   - **报告由 AI 根据仿真数据动态生成**，不要使用硬编码文本

### 节能率校验（旧站房必须遵守）

- 输入 JSON 中 `target_energy_saving_rate` 字段为空调节能率模块的计算结果
- 仿真计算出的节能率必须与 target 误差 < 1%
- 若仿真节能率偏差过大，调整优化参数（如冷冻泵最低频率、目标温差）直到对齐
- 在报告中标注：`仿真节能率 X.X%，评估模块节能率 Y.Y%，误差 Z.Z%`

5. **汇总JSON**: `{project}_summary.json`
   ```json
   {
     "annual_cop": 5.5,
     "annual_power_mwh": 1000,
     "annual_cooling_mwh": 5500,
     "energy_saving_rate": 0.12,
     "annual_saving_yuan": 500000
   }
   ```

### 图表规范

- 使用 matplotlib，**全部使用英文标签**（避免中文字体缺失导致方块）
- 分辨率: dpi=150, figsize=(14, 8)
- 配色: 使用专业配色方案 (如 plt.cm.Set2 或 tab10)
- 必须包含: 标题、坐标轴标签、图例、网格线

**标题/轴标签规范（必须英文）：**

| 图表 | 标题 | X轴 | Y轴 |
|------|------|-----|-----|
| COP专项分析 | COP Analysis | Load Ratio (%) | COP |
| 设备运行分析 | Equipment Operation | Month | Energy (kWh) |
| 综合性能分析 | Overall Performance | Month | COP / Energy |

**示例：**
```python
plt.title('Monthly COP Trend', fontsize=14)
plt.xlabel('Month', fontsize=12)
plt.ylabel('System COP', fontsize=12)
plt.legend(['Chiller COP', 'System COP'], loc='best')
```

## 执行方式

生成仿真脚本后，通过以下命令执行：
```bash
python {output_dir}/simulate_{project_name}.py
```

确保脚本可以独立运行，所有数据从输入JSON文件读取。

## 代码质量要求（必须遵守）

### 字符串与报告写入
- **多行文本必须使用三引号** `"""..."""`，禁止在单引号字符串中嵌入未转义的换行
- **报告内容用列表拼接**，最后用 `'\n'.join(lines)` 合并，禁止在单引号中直接写换行
- **文件写入示例**：
  ```python
  # 正确
  lines = []
  lines.append('# 仿真报告')
  lines.append(f'年度COP: {annual_cop:.2f}')
  Path(report_path).write_text('\n'.join(lines), encoding='utf-8')
  
  # 错误
  Path(report_path).write_text('第一行
第二行', encoding='utf-8')  # 未终止字符串
  ```

### 脚本结构规范
- 所有 import 放在文件顶部
- 主函数用 `def main():` 包裹，末尾 `if __name__ == '__main__': main()`
- 使用 `try/except` 捕获异常并打印有意义的错误信息
- matplotlib 图表必须 `plt.close()` 释放内存

### 执行前自检
- 生成脚本后，先执行 `python -c "import ast; ast.parse(open('{script}').read())"` 验证语法
- 语法检查通过后再执行脚本
- 执行后检查所有输出文件是否生成成功

## 依赖库

仿真脚本仅使用以下标准科学计算库：
- numpy: 数值计算
- scipy.interpolate: COP二维插值
- pandas: 数据处理
- openpyxl: Excel输出
- matplotlib: 图表生成
- json, os, pathlib: 文件操作

### 依赖可用性检查（必须实现）

脚本顶部必须用 try/except 检查可选依赖，确保部分库缺失时仍能生成核心文件：
```python
try:
    import matplotlib
    matplotlib.use('Agg')  # 无 GUI 后端
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    import scipy.interpolate as si
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
```

生成图表前检查：
```python
if HAS_MATPLOTLIB:
    # 生成图表
    plt.savefig(...)
    plt.close()
else:
    print('⚠️ matplotlib 未安装，跳过图表生成')
```

COP 插值时检查：
```python
if HAS_SCIPY:
    from scipy.interpolate import RegularGridInterpolator
    cop_func = RegularGridInterpolator(...)
else:
    # 降级为双线性插值或最近邻
    cop_func = _simple_bilinear_interp(cop_table, cw_temps, load_ratios)
```
