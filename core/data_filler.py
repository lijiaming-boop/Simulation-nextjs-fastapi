"""数据填充执行器

纯机械执行模块,不做智能决策,完全信任 LLM Skill 的填充建议
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


class DataFiller:
    """数据填充器 - 执行 LLM 决策的填充操作"""

    def fill_data(
        self,
        extracted_data_path: str,
        filling_suggestions_path: str,
        output_path: str
    ) -> str:
        """执行数据填充

        Args:
            extracted_data_path: 提取的原始数据 JSON 路径
            filling_suggestions_path: LLM 生成的填充建议 JSON 路径
            output_path: 填充后数据输出路径

        Returns:
            输出文件路径
        """
        # 读取数据
        with open(extracted_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        with open(filling_suggestions_path, 'r', encoding='utf-8') as f:
            suggestions = json.load(f)

        # 为每个月度数据初始化 _filled_fields
        for month_data in data["monthly_data"]:
            month_data["_filled_fields"] = []

        # 计算原始完整率
        total_fields = len(data["monthly_data"]) * 7  # 12个月 × 7个字段
        filled_count = 0

        # 执行填充
        for suggestion in suggestions.get("fillable_suggestions", []):
            field_path = suggestion["field"]
            suggested_value = suggestion["suggested_value"]

            # 解析字段路径: "monthly_data[1].chiller_supply_temp"
            if field_path.startswith("monthly_data["):
                month_idx = int(field_path.split('[')[1].split(']')[0])
                field_name = field_path.split('.')[1]

                month_data = data["monthly_data"][month_idx]

                # 只填充 null 值,不覆盖已有数据
                if month_data.get(field_name) is None:
                    month_data[field_name] = suggested_value
                    month_data["_filled_fields"].append(field_name)
                    filled_count += 1

        # 计算最终完整率
        null_count = sum(
            1 for month in data["monthly_data"]
            for field in ["total_energy", "chiller_supply_temp",
                         "cooling_pump_freq", "cooling_water_temp_diff",
                         "freezing_pump_freq", "freezing_water_temp_diff",
                         "cooling_tower_outlet_temp"]
            if month.get(field) is None
        )

        original_completeness = 1 - (null_count + filled_count) / total_fields
        final_completeness = 1 - null_count / total_fields

        # 添加元数据
        data["_metadata"] = {
            "fill_timestamp": datetime.now().isoformat(),
            "fill_count": filled_count,
            "original_completeness": round(original_completeness, 2),
            "final_completeness": round(final_completeness, 2)
        }

        # 输出结果
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return str(output_path)
