# Read Energy Survey Skill

## 目的

读取"标准能管项目调研表.xlsx"，将其中 9 大板块的项目事实提取为结构化 JSON。

## 输入

调研表 xlsx 文件路径。调研表 9 大板块：
1. 项目基础信息 (rows 7-13)
2. 既有表计/设备接入 (rows 18-25)
3. 新增电表 (rows 29-34)
4. 新增水表 (rows 39-44)
5. 新增流量计/冷热量表 (rows 49-54)
6. 新增蒸汽/天然气 (rows 59-62)
7. 第三方系统接入 (rows 67-72)
8. 可选软件 (rows 77-84, 88-93)
9. 项目需求补充 (rows 98-100)

## 输出

输出 project.json，格式必须严格如下：

```json
{
  "client_name": "string",
  "project_name": "string",
  "project_location": "string",
  "deployment_mode": "cloud|private_our|private_client",
  "existing_meters": {
    "electric_accessible": 0,
    "electric_need_retrofit": 0,
    "water_accessible": 0,
    "water_need_retrofit": 0
  },
  "new_meters": {
    "electric": [{"location": "string", "quantity": 0, "ct_current": 0, "ct_type": "穿缆圆孔式|母排方孔式", "site_condition": "string"}],
    "water": [{"location": "string", "dn": "DN50", "quantity": 0, "need_install": true, "site_condition": "string"}],
    "flow_meters": [{"medium": "string", "dn": "string", "quantity": 0, "install_type": "string", "site_condition": "string"}],
    "steam_gas": [{"medium": "蒸汽|天然气", "dn": "string", "quantity": 0}]
  },
  "third_party_systems": [{"name": "string", "type": "MES|ERP|PLC|...", "direction": "单向读取|双向交互/写回|控制/启停", "description": "string"}],
  "optional_modules": {
    "batch_energy_analysis": false,
    "mobile_app": false,
    "extra_dashboards": 0,
    "extra_topology": 0,
    "extra_reports": 0
  },
  "project_notes": {
    "current_status": "string",
    "problems": "string",
    "goals": "string"
  }
}
```

## 单元格映射

### 板块一：项目基础信息
- C7 = client_name
- C8 = project_name
- C9 = project_location
- D12 = deployment_mode（"云端部署"→cloud, "私有部署（我方）"→private_our, "私有部署（客户）"→private_client）
- D13 = 能源管理方式（保留原文）

### 板块二：既有表计
- row 18: 电表 → C18=可接入, D18=需改造
- row 19: 水表 → C19=可接入, D19=需改造
- 如果有数据（非空非0）就填入 existing_meters

### 板块三：新增电表 (rows 29-34)
- 每行：B=位置, C=数量, D=CT电流(A), E=CT形式, F=现场条件
- 只读取 C 列（数量）不为空的行

### 板块四：新增水表 (rows 39-44)
- 每行：B=位置, C=管径DN, D=数量, E=是否安装, F=现场条件
- E列"是"→need_install=true

### 板块五-六：流量计/蒸汽天然气(rows 49-62)
- 类似逻辑，只取有数据的行

### 板块七：第三方系统 (rows 67-72)
- B=系统名, C=系统类型, D=接口方向

### 板块八：可选软件 (rows 77-84)
- 行77=单位能耗(not used), 行78=批次能耗, 行82=移动端
- C列"选用"→true

### 板块八-附加：额外大屏/组态/报表 (rows 88-93)
- B=类型, C=新增数量

### 板块九：项目需求 (rows 98-100)
- C98=项目现状, C100=特殊要求

## 执行步骤

1. 用 openpyxl 读取调研表，打印所有非空单元格的值
2. 按上述映射规则提取为 JSON
3. 将 JSON 写入输出文件
4. 打印摘要信息确认

## 注意事项

- deployment_mode 必须映射为英文字符串
- 数量字段必须是数字类型，不是字符串
- 空的行不纳入 new_meters 数组
- CT 电流规格是数字（150, 200, 250...），不是字符串
- 部署方式从 D12 的下拉选项值中识别
