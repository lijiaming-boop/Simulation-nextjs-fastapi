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
  "cooling_pumps": [{"brand": "南方泵业", "model": "CDMF32-4", "power_kw": 90, "count": 4, "vfd": true, "flow_rate_m3h": 200, "head_m": 32}],
  "chilled_pumps": [{"brand": "南方泵业", "model": "CDMF25-3", "power_kw": 75, "count": 3, "vfd": true, "flow_rate_m3h": 150, "head_m": 25}],
  "towers": [{"brand": "元亨", "fan_power_kw": 45, "count": 12, "vfd": true, "type": "闭式", "flow_rate_m3h": 300}],
  "special": {"type": "none"}
}
```
- capacity_kw/power_kw/rated_cop/fan_power_kw 必须是数字，不能是 null
- 不要包含调研表的问题文本和说明性文字
- **special.type 只能取以下 5 个值之一**: `none`(无)、`storage`(水蓄冷)、`ice`(冰蓄冷)、`heat_recovery`(热回收)、`storage_and_heat_recovery`(蓄冷+热回收)。严禁使用其他值（如 water_thermal_storage、水蓄冷 等均不允许）

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
    "cooling_pumps": [{"brand": "南方泵业", "model": "CDMF32-4", "power_kw": 90, "count": 4, "vfd": true, "flow_rate_m3h": 200, "head_m": 32}],
    "chilled_pumps": [{"brand": "南方泵业", "model": "CDMF25-3", "power_kw": 75, "count": 3, "vfd": true, "flow_rate_m3h": 150, "head_m": 25}],
    "towers": [{"brand": "元亨", "fan_power_kw": 45, "count": 12, "vfd": true, "type": "闭式", "flow_rate_m3h": 300}],
    "special": {"type": "none|storage|ice|heat_recovery|storage_and_heat_recovery", "capacity": 0}
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
  "baseline_power_kwh": 4835800,
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
2. **变频泵三次方律**: P_actual = P_rated × (freq/50)^3，最低频率限制30Hz（水泵和冷却塔均适用）
   - **优先取调研表频率范围**: 若 monthly_data 中有 `cooling_pump_freq`/`freezing_pump_freq` 字段，取其最小值作为对应水泵的频率下限（而非硬编码30Hz）
   - 例: 调研表冷冻泵频率范围为35~49Hz → 频率下限=35Hz，上限=50Hz
   - 若调研表无频率数据或为新站房，频率下限默认30Hz
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

| 设备 | 基准控制 | 优化策略 | 控制逻辑 |
|------|---------|---------|----------|
| 冷机 | 人工启停 | **群控加减机** | 根据负载率自动加/减机，保持每台机在最佳负荷区(60-80%) |
| 冷冻泵 | 固定频率 | **温差变频控制** | 供回水温差PID控制，目标温差5°C，最低频率30Hz |
| 冷却泵 | 固定频率 | **压差+变频** | 供回水压差控制或温差控制，最低频率30Hz |
| 冷却塔 | 固定频率 | **逼近度控制** | 出水温度逼近湿球温度控制，冬季降频，最低频率30Hz |
| 冷冻出水温度 | 固定设定 | **供水温度重设** | 根据环境温度动态调整供水温度设定值 |

### 策略详细逻辑

#### 1. 主机群控加减机策略

```
目标: 保持每台运行主机在最佳负荷区间(60-80%)

加机条件:
  - 当前所有主机平均负荷率 > 85% 持续 15分钟
  - 或单台主机负荷率 > 90% 持续 10分钟

减机条件:
  - 当前所有主机平均负荷率 < 50% 持续 20分钟
  - 且当前开机台数 > 1

加减机顺序:
  - 加机: 先开大容量机，后开小容量机
  - 减机: 先停小容量机，后停大容量机
  - 避免频繁启停: 同一台机启停间隔 ≥ 30分钟

每台机负载分配:
  - 均分负载: 每台机 load_ratio = 总负荷 / 开机台数 / 单机容量
  - 确保每台机 load_ratio ≥ 20% (离心机最低负荷率)
```

#### 2. 冷冻水供水温度重设策略

```
目标: 根据环境温度和负荷动态调整供水温度，提高主机COP

规则:
  - 夏季满负荷: 供水温度 = 7°C (基准)
  - 过渡季低负荷: 供水温度可提高到 8-9°C
  - 冬季低负荷: 供水温度可提高到 10-12°C

逻辑:
  if 月平均环境温度 > 28°C:
      供水温度 = 7°C
  elif 月平均环境温度 > 20°C:
      供水温度 = 8°C
  elif 月平均环境温度 > 10°C:
      供水温度 = 9°C
  else:
      供水温度 = 10°C

约束:
  - 供水温度 ≥ 5°C (防止冷冻水结冰风险)
  - 供水温度 ≤ 12°C (保证末端除湿能力)
```

#### 3. 水泵温差变频调节策略

```
目标: 根据实际冷量和温差调节水泵频率，减少泵耗

★ 频率范围确定规则（优先调研表）:
  - 若 monthly_data 中有 freezing_pump_freq → 冷冻泵频率下限 = min(freezing_pump_freq)，上限 = max(freezing_pump_freq) 或 50Hz
  - 若 monthly_data 中有 cooling_pump_freq → 冷却泵频率下限 = min(cooling_pump_freq)，上限 = max(cooling_pump_freq) 或 50Hz
  - 冷却塔风机: 若调研表无风机频率数据，频率下限默认30Hz
  - 若调研表无频率数据或新站房，所有设备频率下限默认30Hz

冷冻泵控制:
  目标温差 = 5°C
  所需流量(kg/s) = 当前冷量(kW) / (4.186 × 目标温差)
  泵频率(Hz) = 所需流量 / 额定流量 × 50
  
  频率下限 = 调研表min(freezing_pump_freq) 或 30Hz
  频率上限 = 50Hz
  实际功率 = 理论功率 × (频率/50)^3 / 0.92 (变频器效率)

冷却泵控制 (仅变频泵):
  目标温差 = 5°C (或根据冷却塔散热能力调整)
  控制逻辑同冷冻泵，频率下限 = 调研表min(cooling_pump_freq) 或 30Hz
  需保证冷却塔最低流量

冷却塔控制 (仅变频风机):
  目标: 出水温度逼近湿球温度 + 3°C
  风机频率根据逼近度PID调节
  频率下限 = 调研表风机频率min 或 30Hz
  频率上限 = 50Hz
  冬季低温时可降至频率下限运行

变频器效率损失: 约8% (含变频器自身损耗+管网特性偏差)

★ 水泵联动台数控制（关键约束）:
  - 运行水泵台数 = 当前运行冷机台数（一机一泵对应）
  - 不能只开1台冷机却跑全部水泵
  - 示例: 3台冷却泵+3台冷冻泵配置
    - 1台冷机运行 → 只开1台冷却泵 + 1台冷冻泵
    - 2台冷机运行 → 只开2台冷却泵 + 2台冷冻泵
  - 工频泵: 运行台数 × 额定功率
  - 变频泵: 运行台数 × 额定功率 × (频率/50)³ / 0.92
  - 冷却塔同理: 运行塔数 = 当前冷机台数
```

### 新站房优化策略

新站房无历史基准，优化策略为设计推荐方案：
- 主机群控: 同上逻辑
- 供水温度: 根据设计工况设定
- 水泵变频: 同上逻辑，但无工频泵限制

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
   - **报告语言: 必须全部使用中文（正文、表格内容、章节标题全部中文，图表除外）**
   - **标题格式**: `# {项目名称}中央空调冷站 控制策略优化仿真报告`
   - **报告结构**（必须包含以下章节）：
     - 一、项目概况（表格：项目名称、地址、系统类型、总装机制冷量、仿真时长）
     - 二、设备现状（设备配置表、调研表实际月度运行参数表、关键问题识别）
     - 三、优化控制策略（可优化设备表、冷冻泵温差控制逻辑、冷却塔优化逻辑）
     - 四、仿真结果（年度核心指标对比表、分项能耗对比表、月度详细对比表）
     - 五、节能分析（节能贡献分解表、仿真保守因素说明；不要包含节能收益/经济效益测算）
   - **报告不要包含节能收益（电费节省金额等经济测算）和实施建议章节**
   - **报告由 AI 根据仿真数据动态生成**，不要使用硬编码文本

### 节能率与基准耗电量校验（旧站房必须遵守）

- 输入 JSON 中 `target_energy_saving_rate` 字段为空调节能率模块的计算结果
- 仿真计算出的节能率必须与 target 误差 < 1%
- 若仿真节能率偏差过大，调整优化参数（如冷冻泵最低频率、目标温差）直到对齐
- 在报告中标注：`仿真节能率 X.X%，评估模块节能率 Y.Y%，误差 Z.Z%`
- **基准年耗电对齐**：若输入 JSON 存在 `baseline_power_kwh`（来自调研表逐月电量求和或用户修正，单位 **kWh**）：
  - 基准仿真的年总耗电量必须与该值对齐（误差 < 2%）
  - 对齐方法：先按 topology + operating_conditions 正常仿真得到原始基准年耗电，再用 `scale_factor = baseline_power_kwh / 原始基准年耗电(kWh)` 统一缩放基准与优化工况的逐时功率（保持节能率不变）
  - 在报告中标注：`基准年耗电（用户/调研表）X kWh，仿真基准年耗电 Y kWh，缩放系数 Z`
- 若未提供 `baseline_power_kwh`，基准耗电由仿真自行计算，不做缩放

5. **汇总JSON（必须生成）**: `{project}_summary.json`
   > **⚠️ 重要：此文件必须生成！若缺失，前端结果页将无法显示节能率和耗电量指标。**
   ```json
   {
     "project_name": "项目名称",
     "sim_mode": "old_station",
     "baseline_power_kwh_input": 11271700,
     "baseline_power_kwh_simulated": 11271700,
     "optimized_power_kwh_simulated": 10630313,
     "target_energy_saving_rate": 0.0569,
     "actual_energy_saving_rate": 0.0569,
     "energy_saving_kwh": 641387,
     "raw_baseline_total_kwh": 27252532,
     "raw_optimized_total_kwh": 20509916,
     "baseline_scale_factor": 0.4136,
     "hours": 8760,
     "csv_file": "8760h_results.csv",
     "excel_file": "monthly_summary.xlsx",
     "plot_files": ["monthly_energy_comparison.png", "monthly_saving_rate.png", "operating_conditions_overview.png"],
     "report_file": "COP性能仿真分析报告.md"
   }
   ```
   **必填字段**: `baseline_power_kwh_simulated`, `optimized_power_kwh_simulated`, `actual_energy_saving_rate`, `energy_saving_kwh`

### 图表规范

- 使用 matplotlib，**图表标题、坐标轴、图例必须全部使用英文标签**
- **⚠️ 严禁在图表中使用任何中文！服务器未安装中文字体，会导致乱码方块或崩溃**
- **注意: 只有图表用英文，报告正文/表格/标题必须用中文**
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
