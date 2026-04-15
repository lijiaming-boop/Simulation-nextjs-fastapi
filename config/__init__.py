import json
from pathlib import Path
from typing import Dict, Optional

class WeatherService:
    """气象数据查询服务"""
    
    def __init__(self, weather_data_file: str = None):
        """初始化气象服务
        
        Args:
            weather_data_file: 气象数据JSON文件路径（默认使用config/weather_data.json）
        """
        config_dir = Path(__file__).parent
        
        if weather_data_file is None:
            weather_data_file = config_dir / "weather_data.json"
        
        with open(weather_data_file, 'r', encoding='utf-8') as f:
            self.weather_data: Dict = json.load(f)
    
    def get_cooling_tower_temp(self, region: str, month: int) -> float:
        """获取指定地区和月份的冷却塔出水温度
        
        Args:
            region: 地区名称
            month: 月份 (1-12)
            
        Returns:
            冷却塔出水温度，如果未找到则返回默认值21
        """
        # 将中文地区名转换为对应的英文键
        region_mapping = {
            "华南": "china_guangzhou",
            "华东": "china_shanghai",
            "华中": "china_wuhan",
            "西南": "china_chengdu",
            "西北": "china_xian",
            "华北": "china_jinan",
            "东南亚": "malaysia_kuala_lumpur",
            "马来西亚": "malaysia_kuala_lumpur",
            "泰国": "thailand_bangkok",
            "越南": "vietnam_ho_chi_minh_city",
            "新加坡": "singapore",
            "菲律宾": "philippines_manila",
            "吉隆坡": "malaysia_kuala_lumpur",
            "曼谷": "thailand_bangkok",
            "胡志明市": "vietnam_ho_chi_minh_city"
        }
        
        # 如果区域名称直接存在于数据中，直接使用
        if region in self.weather_data:
            city_key = region
        else:
            # 尝试使用映射
            city_key = region_mapping.get(region)
        
        if city_key and city_key in self.weather_data:
            city_data = self.weather_data[city_key]
            month_names = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 
                          'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
            if 1 <= month <= 12:
                month_key = month_names[month - 1]
                wet_bulb_temp = city_data.get(month_key, 21.0)
                # 公式：冷却塔出水温度 = 湿球温度 + 4.5℃（最低21℃）
                cooling_tower_temp = wet_bulb_temp + 4.5
                # 应用最低21℃的限制
                return max(cooling_tower_temp, 21.0)
        
        # 默认返回21度
        return 21.0
    
    def get_city_name(self, region: str) -> str:
        """获取地区的参考城市名称
        
        Args:
            region: 地区名称
            
        Returns:
            参考城市名称
        """
        region_mapping = {
            "华南": "china_guangzhou",
            "华东": "china_shanghai",
            "华中": "china_wuhan",
            "西南": "china_chengdu",
            "西北": "china_xian",
            "华北": "china_jinan",
            "东南亚": "malaysia_kuala_lumpur",
            "马来西亚": "malaysia_kuala_lumpur",
            "泰国": "thailand_bangkok",
            "越南": "vietnam_ho_chi_minh_city",
            "新加坡": "singapore",
            "菲律宾": "philippines_manila",
            "吉隆坡": "malaysia_kuala_lumpur",
            "曼谷": "thailand_bangkok",
            "胡志明市": "vietnam_ho_chi_minh_city"
        }
        
        # 如果区域名称直接存在于数据中，直接使用
        if region in self.weather_data:
            city_key = region
        else:
            # 尝试使用映射
            city_key = region_mapping.get(region)
        
        if city_key and city_key in self.weather_data:
            return self.weather_data[city_key]["city"]
        
        return "未知城市"
"""配置文件模块

包括:
- CellMapping: Excel 单元格映射配置
"""