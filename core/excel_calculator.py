"""Excel 计算引擎

使用 formulas 库执行 Excel 公式计算（纯 Python 实现，无需外部依赖）
"""
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from config.cell_mapping import CellMapping
from config.template_config import TemplateConfig


class ExcelCalculator:
    """Excel 计算引擎 - 数据回填和结果提取"""

    def __init__(self, template_path: Optional[str] = None):
        """初始化计算器

        Args:
            template_path: Excel 模板文件路径（可选，如果不提供则根据 station_type 动态选择）
        """
        self.template_path = template_path
        self.mapper = CellMapping()
        self.template_config = TemplateConfig()

    def calculate(
        self,
        filled_data_path: str,
        output_path: str
    ) -> str:
        """执行节能率计算

        Args:
            filled_data_path: 填充后的数据 JSON 路径
            output_path: 结果输出 JSON 路径

        Returns:
            结果文件路径

        Raises:
            ValueError: 站房类型为 unsupported
        """
        # 读取填充后的数据
        with open(filled_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 如果没有指定模板路径，根据 station_type 自动选择
        if self.template_path is None:
            station_type = data.get("station_type", "standard")

            # 检查是否为不支持的类型
            if station_type == "unsupported":
                raise ValueError(
                    "不支持的站房类型。该类型站房（如包含热水泵、水蓄冷、中低温机组）"
                    "不在自动节能评估范围内。"
                )

            # 动态获取模板路径
            template_path = self.template_config.get_template_path(station_type)
        else:
            template_path = self.template_path

        # 创建临时 Excel 文件
        temp_excel = Path(output_path).parent / "calculation_result.xlsx"
        shutil.copy(template_path, temp_excel)

        try:
            # 优先使用 formulas 库（纯 Python，无需外部依赖）
            result = self._calculate_with_formulas(data, temp_excel)
        except Exception as e:
            # 输出详细错误信息
            import traceback
            error_details = traceback.format_exc()
            print("=" * 80)
            print("❌ Excel计算失败，降级到mock结果")
            print("=" * 80)
            print(f"异常类型: {type(e).__name__}")
            print(f"异常信息: {str(e)}")
            print(f"\n完整堆栈跟踪:")
            print(error_details)
            print("=" * 80)
            result = self._mock_result(data)

        # 保存结果
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return str(output_path)

    def _calculate_with_formulas(
        self,
        data: Dict[str, Any],
        excel_path: Path
    ) -> Dict[str, Any]:
        """使用 formulas 库执行计算

        计算上限和下限两个sheet，返回节能率范围

        Args:
            data: 填充后的数据字典
            excel_path: Excel 文件路径

        Returns:
            计算结果字典（包含范围）
        """
        try:
            import formulas
            import openpyxl
        except ImportError as e:
            raise RuntimeError(f"Required library not installed: {e}")

        # 计算下限（保守估计）
        result_lower = self._calculate_single_sheet(data, excel_path, "lower")

        # 计算上限（理想情况）
        result_upper = self._calculate_single_sheet(data, excel_path, "upper")

        # 合并结果，构建范围
        result = {
            # 节能率范围
            "energy_saving_rate_min": result_lower["saving_rate"],
            "energy_saving_rate_max": result_upper["saving_rate"],
            "energy_saving_rate_range": (
                f"{result_lower['saving_rate']*100:.1f}% - "
                f"{result_upper['saving_rate']*100:.1f}%"
            ),

            # 向后兼容：保留原有单一值字段（使用下限）
            "energy_saving_rate": result_lower["saving_rate"],

            # 分项节能量范围
            "chiller_saving_min": result_lower["chiller_saving"],
            "chiller_saving_max": result_upper["chiller_saving"],
            "chiller_saving": result_lower["chiller_saving"],  # 向后兼容

            "pump_saving_min": result_lower["pump_saving"],
            "pump_saving_max": result_upper["pump_saving"],
            "pump_saving": result_lower["pump_saving"],  # 向后兼容

            "tower_saving_min": result_lower["tower_saving"],
            "tower_saving_max": result_upper["tower_saving"],
            "tower_saving": result_lower["tower_saving"],  # 向后兼容

            "total_saving_min": result_lower["total_saving"],
            "total_saving_max": result_upper["total_saving"],
            "total_saving": result_lower["total_saving"],  # 向后兼容

            # 元数据
            "completeness": data["_metadata"]["final_completeness"],
            "filled_count": data["_metadata"]["fill_count"],
            "calculation_timestamp": datetime.now().isoformat(),
            "calculation_method": "dual_sheet",  # 标记使用双sheet计算
        }

        return result

    def _calculate_single_sheet(
        self,
        data: Dict[str, Any],
        excel_path: Path,
        sheet_type: str
    ) -> Dict[str, Any]:
        """计算单个sheet（上限或下限）

        Args:
            data: 填充后的数据字典
            excel_path: Excel 文件路径
            sheet_type: sheet类型 ("upper"/"lower")

        Returns:
            单个sheet的计算结果
        """
        import formulas
        import openpyxl

        # 获取sheet名称
        sheet_name = self.mapper.get_sheet_name(sheet_type)

        # 阶段1: 使用 openpyxl 将数据写入 Excel 文件
        wb = openpyxl.load_workbook(excel_path)

        # 验证sheet是否存在（添加详细错误信息）
        if sheet_name not in wb.sheetnames:
            available_sheets = wb.sheetnames
            wb.close()
            raise ValueError(
                f"Sheet '{sheet_name}' 不存在于Excel模板中。\n"
                f"可用的sheet名称: {available_sheets}\n"
                f"提示: 检查sheet名称是否有多余空格或特殊字符\n"
                f"配置位置: config/cell_mapping.py:SHEET_NAMES['{sheet_type}']"
            )

        sheet = wb[sheet_name]

        # 1. 回填项目地区
        region_cell = self.mapper.get_basic_info_cell("project_region")
        sheet[region_cell] = data["project_region"]

        # 2. 回填月度数据
        for month_data in data["monthly_data"]:
            month_idx = month_data["month"] - 1

            for field in self.mapper.get_monthly_fields():
                value = month_data.get(field)
                if value is not None:
                    cell = self.mapper.get_cell("monthly_data", month_idx, field)
                    sheet[cell] = value

        # 3. 保存写入的数据
        wb.save(excel_path)
        wb.close()

        # 阶段2: 使用 formulas 库加载并计算
        xl_model = formulas.ExcelModel().loads(str(excel_path)).finish()
        book_name = list(xl_model.books.keys())[0]
        result_data = xl_model.calculate()

        # 阶段3: 提取计算结果
        def get_result_value(result_field: str) -> float:
            """提取结果单元格的值"""
            cell = self.mapper.get_result_cell(result_field)
            cell_id = f"'[{book_name.lower()}]{sheet_name}'!{cell}"

            if cell_id in result_data:
                value = result_data[cell_id]
                if hasattr(value, 'value'):
                    value = value.value[0][0]
                return float(value) if value is not None else 0.0
            else:
                return 0.0

        result = {
            "chiller_saving": get_result_value("chiller_saving_total"),
            "pump_saving": (
                get_result_value("cooling_pump_saving_total") +
                get_result_value("freezing_pump_saving_total")
            ),
            "tower_saving": get_result_value("tower_saving_total"),
            "total_saving": get_result_value("total_saving"),
            "saving_rate": get_result_value("saving_rate"),
        }

        return result

    def _mock_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """生成 mock 结果用于测试 (formulas 库不可用时)"""
        return {
            # 节能率范围
            "energy_saving_rate": 0.15,  # 向后兼容（下限值）
            "energy_saving_rate_min": 0.12,
            "energy_saving_rate_max": 0.18,
            "energy_saving_rate_range": "12.0% - 18.0%",

            # 分项节能量范围
            "chiller_saving": 12.5,
            "chiller_saving_min": 10.0,
            "chiller_saving_max": 15.0,

            "pump_saving": 3.2,
            "pump_saving_min": 2.5,
            "pump_saving_max": 4.0,

            "tower_saving": 1.8,
            "tower_saving_min": 1.5,
            "tower_saving_max": 2.2,

            "total_saving": 17.5,
            "total_saving_min": 14.0,
            "total_saving_max": 21.2,

            # 元数据
            "completeness": data["_metadata"]["final_completeness"],
            "filled_count": data["_metadata"]["fill_count"],
            "calculation_timestamp": datetime.now().isoformat(),
            "calculation_method": "dual_sheet",
            "mock": True  # 标记为 mock 数据
        }
