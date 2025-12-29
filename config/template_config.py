"""Excel 模板配置管理"""
from pathlib import Path
from typing import Dict


class TemplateConfig:
    """Excel 计算模板配置器"""

    # 模板目录
    TEMPLATE_DIR = Path("00_sample/模板测算表")

    # 站房类型 -> 模板文件映射
    TEMPLATES: Dict[str, str] = {
        "standard": "节能评估表-按冷站电量数据-标准版.xlsx",
        "secondary_pump": "节能评估表-按冷站电量数据-二次泵版.xlsx",
    }

    # 站房类型中文名称
    TYPE_NAMES: Dict[str, str] = {
        "standard": "标准站房",
        "secondary_pump": "二次泵站房",
        "unsupported": "不支持的特殊类型",
    }

    def get_template_path(self, station_type: str) -> str:
        """获取模板文件路径

        Args:
            station_type: 站房类型 (standard/secondary_pump)

        Returns:
            模板文件绝对路径

        Raises:
            ValueError: 不支持的站房类型
        """
        if station_type == "unsupported":
            raise ValueError(
                "不支持的站房类型。该类型站房（如包含热水泵、水蓄冷、中低温机组）"
                "不在自动节能评估范围内。"
            )

        if station_type not in self.TEMPLATES:
            raise ValueError(
                f"无效的站房类型: {station_type}。"
                f"支持的类型: {list(self.TEMPLATES.keys())}"
            )

        template_file = self.TEMPLATES[station_type]
        template_path = self.TEMPLATE_DIR / template_file

        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")

        return str(template_path)

    def get_type_name(self, station_type: str) -> str:
        """获取站房类型中文名称"""
        return self.TYPE_NAMES.get(station_type, station_type)
