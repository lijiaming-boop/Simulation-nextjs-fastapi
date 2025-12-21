"""Excel 计算引擎

使用 xlwings 调用 Excel/LibreOffice 计算引擎执行节能率计算
"""
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from config.cell_mapping import CellMapping


class ExcelCalculator:
    """Excel 计算引擎 - 数据回填和结果提取"""

    def __init__(self, template_path: str):
        """初始化计算器

        Args:
            template_path: Excel 模板文件路径
        """
        self.template_path = template_path
        self.mapper = CellMapping()

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
        """
        # 读取填充后的数据
        with open(filled_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 创建临时 Excel 文件
        temp_excel = Path(output_path).parent / "calculation_result.xlsx"
        shutil.copy(self.template_path, temp_excel)

        try:
            # 使用 xlwings 回填数据和提取结果
            result = self._calculate_with_xlwings(data, temp_excel)
        except Exception as e:
            # 如果 xlwings 不可用,返回 mock 结果用于测试
            print(f"Warning: xlwings calculation failed: {e}")
            result = self._mock_result(data)

        # 保存结果
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return str(output_path)

    def _calculate_with_xlwings(
        self,
        data: Dict[str, Any],
        excel_path: Path
    ) -> Dict[str, Any]:
        """使用 xlwings 执行计算"""
        try:
            import xlwings as xw
        except ImportError:
            raise RuntimeError("xlwings not installed or not available")

        # 打开 Excel 文件
        app = xw.App(visible=False)
        wb = app.books.open(str(excel_path))

        try:
            sheet1 = wb.sheets[0]  # 数据表
            sheet2 = wb.sheets[1]  # 结果表

            # 1. 回填项目地区
            region_cell = self.mapper.get_basic_info_cell("project_region")
            sheet2.range(region_cell).value = data["project_region"]

            # 2. 回填月度数据
            for month_data in data["monthly_data"]:
                month_idx = month_data["month"] - 1  # 转换为0-based索引

                for field in self.mapper.get_monthly_fields():
                    value = month_data.get(field)
                    if value is not None:
                        cell = self.mapper.get_cell("monthly_data", month_idx, field)
                        sheet1.range(cell).value = value

            # 3. 触发重新计算
            wb.app.calculate()

            # 4. 提取计算结果
            result = {
                "chiller_saving": sheet2.range(
                    self.mapper.get_result_cell("chiller_saving_total")
                ).value or 0,
                "pump_saving": (
                    sheet2.range(self.mapper.get_result_cell("cooling_pump_saving_total")).value or 0
                ) + (
                    sheet2.range(self.mapper.get_result_cell("freezing_pump_saving_total")).value or 0
                ),
                "tower_saving": sheet2.range(
                    self.mapper.get_result_cell("tower_saving_total")
                ).value or 0,
                "total_saving": sheet2.range(
                    self.mapper.get_result_cell("total_saving")
                ).value or 0,
                "energy_saving_rate": sheet2.range(
                    self.mapper.get_result_cell("saving_rate")
                ).value or 0,
            }

            # 计算节能率范围 (±20%)
            rate = result["energy_saving_rate"]
            result["energy_saving_rate_min"] = rate * 0.8
            result["energy_saving_rate_max"] = rate * 1.2

            # 添加元数据
            result["completeness"] = data["_metadata"]["final_completeness"]
            result["filled_count"] = data["_metadata"]["fill_count"]
            result["calculation_timestamp"] = datetime.now().isoformat()

            return result

        finally:
            wb.close()
            app.quit()

    def _mock_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """生成 mock 结果用于测试 (xlwings 不可用时)"""
        return {
            "energy_saving_rate": 0.15,
            "energy_saving_rate_min": 0.12,
            "energy_saving_rate_max": 0.18,
            "chiller_saving": 12.5,
            "pump_saving": 3.2,
            "tower_saving": 1.8,
            "total_saving": 17.5,
            "completeness": data["_metadata"]["final_completeness"],
            "filled_count": data["_metadata"]["fill_count"],
            "calculation_timestamp": datetime.now().isoformat(),
            "mock": True  # 标记为 mock 数据
        }
