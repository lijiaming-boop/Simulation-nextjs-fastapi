"""测试 AI 服务模块 - ai_service.py"""
import pytest
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.ai_service import (
    ai_extract_plant_topology,
    ai_generate_simulation_report,
    _get_client,
    _get_model,
)


class TestGetClient:
    """测试 _get_client 函数"""

    def test_get_client_with_valid_key(self):
        """测试有有效 API 密钥时能创建客户端"""
        with patch.dict(os.environ, {
            'ANTHROPIC_API_KEY': 'test-key-123',
            'ANTHROPIC_BASE_URL': ''
        }):
            # Mock anthropic.Anthropic
            with patch('simulation.ai_service.anthropic') as mock_anthropic:
                mock_client = Mock()
                mock_anthropic.Anthropic.return_value = mock_client

                client = _get_client()

                # 验证调用了 Anthropic 构造函数
                mock_anthropic.Anthropic.assert_called_once_with(
                    api_key='test-key-123',
                    base_url=None
                )
                assert client == mock_client

    def test_get_client_with_base_url(self):
        """测试带自定义 base_url"""
        with patch.dict(os.environ, {
            'ANTHROPIC_API_KEY': 'test-key-123',
            'ANTHROPIC_BASE_URL': 'http://custom-api.com'
        }):
            with patch('simulation.ai_service.anthropic') as mock_anthropic:
                mock_client = Mock()
                mock_anthropic.Anthropic.return_value = mock_client

                client = _get_client()

                mock_anthropic.Anthropic.assert_called_once_with(
                    api_key='test-key-123',
                    base_url='http://custom-api.com'
                )

    def test_get_client_without_api_key_raises_error(self):
        """测试没有 API 密钥时抛出异常"""
        with patch.dict(os.environ, {
            'ANTHROPIC_API_KEY': '',
            'ANTHROPIC_BASE_URL': ''
        }):
            with patch('simulation.ai_service.anthropic') as mock_anthropic:
                mock_client = Mock()
                mock_anthropic.Anthropic.return_value = mock_client

                # 应该抛出 RuntimeError
                with pytest.raises(RuntimeError, match="未配置 ANTHROPIC_API_KEY"):
                    _get_client()


class TestGetModel:
    """测试 _get_model 函数"""

    def test_get_model_from_env(self):
        """测试从环境变量获取模型名称"""
        with patch.dict(os.environ, {'ANTHROPIC_MODEL': 'claude-3-opus-20240229'}):
            model = _get_model()
            assert model == 'claude-3-opus-20240229'

    def test_get_model_default(self):
        """测试默认模型名称"""
        with patch.dict(os.environ, {}, clear=True):
            model = _get_model()
            assert model == 'claude-sonnet-4-20250514'


class TestAIExtractPlantTopology:
    """测试 ai_extract_plant_topology 函数"""

    @patch('simulation.ai_service._get_client')
    def test_extract_from_text_success(self, mock_get_client):
        """测试从文本成功提取设备拓扑"""
        # Mock AI 响应
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "chillers": [
                {"name": "变频离心机", "qty": 2, "capacity_kw": 5000,
                 "rated_power_kw": 800, "rated_cop": 6.0, "variable_freq": True}
            ],
            "chw_pumps": [
                {"name": "冷冻泵", "qty": 2, "power_kw": 132,
                 "flow_m3h": 920, "variable_freq": True}
            ],
            "cw_pumps": [
                {"name": "冷却泵", "qty": 2, "power_kw": 132,
                 "flow_m3h": 1300, "variable_freq": False}
            ],
            "towers": [
                {"name": "冷却塔", "qty": 4, "fan_power_kw": 22,
                 "fans_per_tower": 2, "variable_freq": True}
            ],
            "monthly_chiller_count": [1, 1, 1, 2, 2, 2, 2, 2, 2, 1, 1, 1],
            "base_load_ratio": 0.7,
            "region": "华东"
        }))]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        # 输入文本
        text_content = """
        2台变频离心机，单台制冷量5000kW，额定功率800kW，COP 6.0
        2台冷冻泵132kW变频，流量920m³/h
        2台冷却泵132kW工频，流量1300m³/h
        4台冷却塔22kW变频，每塔2风机
        夏季开2台主机，冬季开1台
        """

        # 执行
        result = ai_extract_plant_topology(content=text_content, content_type="text")

        # 验证
        assert result is not None
        assert len(result['chillers']) == 1
        assert result['chillers'][0]['qty'] == 2
        assert result['chillers'][0]['capacity_kw'] == 5000
        assert result['chw_pumps'][0]['variable_freq'] == True
        assert result['cw_pumps'][0]['variable_freq'] == False
        assert result['towers'][0]['qty'] == 4
        assert result['region'] == '华东'

        # 验证调用了 API
        mock_client.messages.create.assert_called_once()

    @patch('simulation.ai_service._get_client')
    def test_extract_from_image_success(self, mock_get_client):
        """测试从图片成功提取设备拓扑"""
        # Mock AI 响应（与上面相同）
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps({
            "chillers": [{"name": "主机", "qty": 3, "capacity_kw": 3000,
                          "rated_power_kw": 500, "rated_cop": 5.5, "variable_freq": False}],
            "chw_pumps": [],
            "cw_pumps": [],
            "towers": [],
            "monthly_chiller_count": [1] * 12,
            "base_load_ratio": 0.7,
            "region": "华南"
        }))]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        # 模拟图片数据
        image_data = b"fake-image-data"

        # 执行
        result = ai_extract_plant_topology(
            content="[已上传1张设备图片]",
            content_type="image",
            image_data=image_data,
            media_type="image/jpeg"
        )

        # 验证
        assert result is not None
        assert result['chillers'][0]['qty'] == 3

        # 验证传入了图片数据
        call_args = mock_client.messages.create.call_args
        messages = call_args[1]['messages'][0]['content']
        assert any(msg['type'] == 'image' for msg in messages)

    @patch('simulation.ai_service._get_client')
    def test_extract_invalid_json_returns_none(self, mock_get_client):
        """测试无效 JSON 返回 None"""
        # Mock AI 返回非 JSON 文本
        mock_response = Mock()
        mock_response.content = [Mock(text="这不是有效的JSON格式")]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        # 执行
        result = ai_extract_plant_topology(content="一些文本", content_type="text")

        # 验证
        assert result is None

    @patch('simulation.ai_service._get_client')
    def test_extract_api_error_returns_none(self, mock_get_client):
        """测试 API 调用失败返回 None"""
        mock_get_client.side_effect = Exception("API 连接失败")

        # 执行
        result = ai_extract_plant_topology(content="测试", content_type="text")

        # 验证
        assert result is None

    @patch('simulation.ai_service._get_client')
    def test_extract_empty_content(self, mock_get_client):
        """测试空内容"""
        mock_response = Mock()
        mock_response.content = [Mock(text="{}")]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        # 执行
        result = ai_extract_plant_topology(content="", content_type="text")

        # 验证
        assert result == {}


class TestAIGenerateSimulationReport:
    """测试 ai_generate_simulation_report 函数"""

    @patch('simulation.ai_service._get_client')
    def test_generate_report_success(self, mock_get_client):
        """测试成功生成报告"""
        # Mock AI 响应
        mock_response = Mock()
        mock_response.content = [Mock(text="""# 冷站优化控制策略仿真报告

## 核心结果

| 指标 | 基线 | 优化后 | 变化 |
|------|------|--------|------|
| 年加权系统COP | 5.23 | 6.15 | +17.6% |

## 优化策略

1. **冷冻泵温差控制**: 目标供回水温差5°C
2. **冷却塔优化变频**: 根据环温智能调节

---
*仿真方法: 全年8760小时逐时计算*
""")]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        # 输入数据
        summary = {
            "baseline_cop": 5.23,
            "optimized_cop": 6.15,
            "saving_kwh": 1250000,
            "saving_pct": 15.2,
            "baseline_power_kwh": 8200000,
            "optimized_power_kwh": 6950000,
            "saving_cost_yuan": 625000,
            "baseline_chiller_kwh": 6800000,
            "optimized_chiller_kwh": 5900000,
            "baseline_chw_pump_kwh": 1250000,
            "optimized_chw_pump_kwh": 850000,
            "baseline_cw_pump_kwh": 1450000,
            "optimized_cw_pump_kwh": 1450000,
            "baseline_tower_kwh": 450000,
            "optimized_tower_kwh": 280000,
            "summer_base_cop": 5.80,
            "summer_opt_cop": 6.45,
            "winter_base_cop": 4.03,
            "winter_opt_cop": 5.20,
        }

        config_desc = "2台5000kW变频离心机，COP=6.0"

        # 执行
        report = ai_generate_simulation_report(summary, config_desc)

        # 验证
        assert report is not None
        assert "# 冷站优化控制策略仿真报告" in report
        assert "5.23" in report
        assert "6.15" in report
        assert "+17.6%" in report

        # 验证调用了 API
        mock_client.messages.create.assert_called_once()

        # 验证 prompt 中包含 summary 数据
        call_args = mock_client.messages.create.call_args
        prompt = call_args[1]['messages'][0]['content'][-1]['text']
        assert "5.23" in prompt
        assert "6.15" in prompt

    @patch('simulation.ai_service._get_client')
    def test_generate_report_without_config_desc(self, mock_get_client):
        """测试不带设备描述生成报告"""
        mock_response = Mock()
        mock_response.content = [Mock(text="# 报告内容")]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        summary = {"baseline_cop": 5.0, "optimized_cop": 5.5}

        # 执行
        report = ai_generate_simulation_report(summary)

        # 验证
        assert report is not None

        # 验证 prompt 中不包含设备描述部分
        call_args = mock_client.messages.create.call_args
        prompt = call_args[1]['messages'][0]['content'][-1]['text']
        assert "## 设备描述" not in prompt

    @patch('simulation.ai_service._get_client')
    def test_generate_report_api_error_returns_none(self, mock_get_client):
        """测试 API 调用失败返回 None"""
        mock_get_client.side_effect = Exception("网络错误")

        summary = {"baseline_cop": 5.0}

        # 执行
        report = ai_generate_simulation_report(summary)

        # 验证
        assert report is None

    @patch('simulation.ai_service._get_client')
    def test_generate_report_empty_summary(self, mock_get_client):
        """测试空 summary"""
        mock_response = Mock()
        mock_response.content = [Mock(text="# 空报告")]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        # 执行
        report = ai_generate_simulation_report({})

        # 验证
        assert report is not None


class TestEnvFileLoading:
    """测试 .env 文件加载"""

    def test_env_file_loaded_on_import(self):
        """测试导入模块时自动加载 .env 文件"""
        # 这个测试验证模块导入时会读取 .env 文件
        # 由于已经在模块级别执行了加载逻辑，这里只需验证环境变量存在

        # 检查是否从 .env 加载了变量
        # 注意：这取决于测试环境，可能需要清理环境变量
        pass  # 实际项目中需要更复杂的测试设置


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
#python tests/unit/test_a_api_connection.py --chat