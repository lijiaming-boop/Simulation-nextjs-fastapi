"""测试数据提取中月份列对齐问题"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pathlib import Path
import pytest


def test_extract_january_data_alignment():
    """测试1月数据提取的正确性 - 验证用电情况和设备运行规律的月份对齐

    根本问题：
    - 设备运行规律：1月从D列开始（有备注列C）
    - 用电情况统计：1月从C列开始（无备注列）

    预期：
    - 1月冷站用电量应该是 26.16 万kWh（C44单元格）
    - 1月冷机供水温度应该是 8°C（D34单元格）
    """
    from pathlib import Path
    import sys

    # 导入提取函数
    skill_script_path = Path(__file__).parent.parent.parent / '.claude/skills/extract-and-check-data/scripts'
    sys.path.insert(0, str(skill_script_path))

    from extract_and_check_data import extract_data_from_excel

    # 使用齐全的示例调研表
    survey_path = '00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx'

    result = extract_data_from_excel(survey_path)

    # 验证没有错误
    assert 'error' not in result or not result['error'], f"提取失败: {result.get('message')}"

    monthly_data = result['monthly_data']
    assert len(monthly_data) == 12, "应该提取12个月的数据"

    # 验证1月数据
    jan_data = monthly_data[0]
    assert jan_data['month'] == 1

    # ✅ 核心验证：1月冷站用电量应该是 26.16（C44单元格）
    # 当前 bug 会读取到 19.94（2月的数据，D44单元格）
    assert jan_data['total_energy'] == pytest.approx(26.16, abs=0.01), \
        f"1月冷站用电量错误: 期望 26.16, 实际 {jan_data['total_energy']}"

    # ✅ 验证1月冷机供水温度应该是 8°C（D34单元格）
    assert jan_data['chiller_supply_temp'] == pytest.approx(8.0, abs=0.1), \
        f"1月冷机供水温度错误: 期望 8.0, 实际 {jan_data['chiller_supply_temp']}"

    # 验证2月数据（作为对照）
    feb_data = monthly_data[1]
    assert feb_data['month'] == 2

    # ✅ 2月冷站用电量应该是 19.94（D44单元格）
    assert feb_data['total_energy'] == pytest.approx(19.94, abs=0.01), \
        f"2月冷站用电量错误: 期望 19.94, 实际 {feb_data['total_energy']}"


def test_extract_december_data_presence():
    """测试12月数据提取 - 验证不会漏掉最后一个月

    由于错位问题：
    - 设备运行规律只有11个月（D-N列，1-11月，缺12月）
    - 用电情况统计有完整12个月（C-N列，1-12月）

    预期：
    - 12月应该有用电量数据 28.64 万kWh（N44单元格）
    - 12月的设备运行规律数据可能缺失（因为表格只到11月）
    """
    from pathlib import Path
    import sys

    skill_script_path = Path(__file__).parent.parent.parent / '.claude/skills/extract-and-check-data/scripts'
    sys.path.insert(0, str(skill_script_path))

    from extract_and_check_data import extract_data_from_excel

    survey_path = '00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx'

    result = extract_data_from_excel(survey_path)
    monthly_data = result['monthly_data']

    # 验证12月数据
    dec_data = monthly_data[11]
    assert dec_data['month'] == 12

    # ✅ 12月应该有用电量数据 28.64 万kWh（N44单元格）
    assert dec_data['total_energy'] == pytest.approx(28.64, abs=0.01), \
        f"12月冷站用电量错误: 期望 28.64, 实际 {dec_data['total_energy']}"
