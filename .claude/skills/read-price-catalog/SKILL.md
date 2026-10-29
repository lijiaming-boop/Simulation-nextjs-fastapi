# Read Price Catalog Skill

## 目的

读取云智控报价体系 Excel 文件，解析全部 sheet 的产品和价格，输出结构化 `price_catalog.json`。

## 输入

报价体系 Excel 文件路径（如 `templates/2025年云智控报价体系-全产品线11.xlsx`）。

## 输出

`outputs/price_catalog.json`，结构如下：

```json
{
  "software": {
    "<key>": {
      "name": "产品名称",
      "brand": "品牌",
      "model": "型号",
      "description": "功能描述",
      "standard_price": 数值或null,
      "channel_price": 数值或null,
      "conflict_note": "冲突说明（可选）"
    }
  },
  "hardware": {
    "<key>": {
      "name": "产品名称",
      "brand": "品牌",
      "model": "型号",
      "standard_price": 数值,
      "channel_price": 数值
    }
  },
  "ct_mapping": [
    {
      "current": 电流规格数字,
      "type": "穿缆圆孔式|母排方孔式",
      "aperture": "口径描述",
      "brand": "安科瑞",
      "model": "型号全称",
      "standard_price": 数值,
      "channel_price": 数值
    }
  ],
  "water_meters": {
    "<DN>": {
      "brand": "品牌",
      "model": "型号",
      "standard_price": 数值,
      "channel_price": 数值,
      "install_price": 数值
    }
  },
  "construction": {
    "<key>": {
      "name": "服务名称",
      "standard_price": 数值,
      "channel_price": 数值
    }
  },
  "tax_info": {
    "software_hardware_rate": 税率,
    "construction_rate": 税率,
    "template_note": "报价模板中的税费原文"
  }
}
```

## 执行步骤

1. 用 openpyxl 打开报价体系 Excel
2. 遍历全部 sheet，识别每个 sheet 的列结构：
   - `【软件】平台`：产品名、描述、品牌、型号、标准价、渠道价
   - `【三方硬件】能管`：产品/服务、描述、品牌、型号、渠道销售底价、市场指导价格
   - `【一方硬件】`：一方硬件产品价格
   - `【施工调试】`：服务名、施工单价
   - `报价模板`：提取 row27 备注中的税费原文
3. 解析半结构化产品描述文本（如 "150A/5A&口径K-φ24mm&AKH-0.66K"），拆分为结构化字段（电流、形式、口径、型号）
4. 处理合并单元格：用 openpyxl 读取时取左上角单元格的值
5. 判断价格列：根据表头文字语义识别标准价和渠道价列，不按固定列号
6. 输出 JSON 到 `outputs/price_catalog.json`

## 锚点校验

生成后必须自动校验以下锚点价格（硬编码对照）：

| 产品 | 标准价 | 渠道价 |
|------|--------|--------|
| ADL400 三相电表 | 305 | 245 |
| DN50 水表（捷先） | 1,080 | 860 |
| 系统基础平台 | 60,000 | 42,000 |

锚点不匹配 → 报警提示人工复核，不静默覆盖。

## 缓存策略

`price_catalog.json` 作为缓存文件，只在以下情况重新生成：
- 报价体系 Excel 文件修改时间晚于 price_catalog.json 的修改时间
- 用户明确要求重新生成

日常运行时直接加载缓存 JSON，不重复调用 AI。

## 注意事项

- 价格数字类型为数字（非字符串），null 表示无价格
- 多品牌产品（如水表有捷先RS485、捷先NB、青岛积成NB三线）全部提取，不筛选
- 施工表中不存在标准价/渠道价区分的，两列填相同值
- 税率信息从报价模板备注原文提取，不做语义判断
