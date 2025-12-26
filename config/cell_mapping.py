"""Excel 单元格映射配置

映射 JSON 数据字段到 Excel 模板单元格位置
基于模板: 00_sample/机房智能化节能评估表-按冷站电量数据.xlsx
"""
from typing import Dict, List


class CellMapping:
    """Excel 单元格映射器"""

    # 工作表名称
    SHEET_NAME = "【2】按冷站电量数据 "  # 注意末尾空格

    # 列号映射: 月份(0-11) -> Excel列(D-O)
    MONTH_COLS = ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O']

    # 月度数据字段 -> 行号映射 (Sheet1)
    MONTHLY_ROWS = {
        "total_energy": 27,              # 冷站月度总能耗
        "chiller_supply_temp": 9,        # 冷机供水温度
        "cooling_pump_freq": 13,         # 冷却泵运行频率
        "cooling_water_temp_diff": 14,   # 冷却侧供回水温差
        "freezing_pump_freq": 18,        # 冷冻泵运行频率
        "freezing_water_temp_diff": 19,  # 冷冻侧供回水温差
        "cooling_tower_outlet_temp": 23, # 冷却塔出水温度
    }

    # 基础信息字段 -> 单元格映射 (Sheet2)
    BASIC_INFO_CELLS = {
        "project_region": "H4",  # 项目地区
    }

    # 结果提取位置 (Sheet2)
    RESULT_CELLS = {
        "chiller_saving_total": "P11",
        "cooling_pump_saving_total": "P16",
        "freezing_pump_saving_total": "P21",
        "tower_saving_total": "P25",
        "total_saving": "P28",
        "saving_rate": "O30",  # 修正：实际位置是 O30 而非 P29
    }

    def get_cell(self, data_type: str, month_index: int, field: str) -> str:
        """获取单元格位置

        Args:
            data_type: 数据类型 ("monthly_data")
            month_index: 月份索引 (0-11)
            field: 字段名

        Returns:
            Excel单元格位置,如 "D27"
        """
        if data_type != "monthly_data":
            raise ValueError(f"Unsupported data_type: {data_type}")

        if month_index < 0 or month_index > 11:
            raise ValueError(f"Invalid month_index: {month_index}")

        if field not in self.MONTHLY_ROWS:
            raise ValueError(f"Unknown field: {field}")

        col = self.MONTH_COLS[month_index]
        row = self.MONTHLY_ROWS[field]
        return f"{col}{row}"

    def get_basic_info_cell(self, field: str) -> str:
        """获取基础信息单元格位置"""
        if field not in self.BASIC_INFO_CELLS:
            raise ValueError(f"Unknown basic info field: {field}")
        return self.BASIC_INFO_CELLS[field]

    def get_result_cell(self, field: str) -> str:
        """获取结果单元格位置"""
        if field not in self.RESULT_CELLS:
            raise ValueError(f"Unknown result field: {field}")
        return self.RESULT_CELLS[field]

    def get_monthly_fields(self) -> List[str]:
        """获取所有月度数据字段列表"""
        return list(self.MONTHLY_ROWS.keys())
