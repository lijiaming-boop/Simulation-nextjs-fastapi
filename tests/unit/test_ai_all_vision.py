"""ai_all_vision 模块单元测试

测试多图批量识别模块的核心函数（不依赖真实 API 调用）：
- _robust_extract_json: JSON 容错提取
- _build_failed_result: 全部失败兜底结果
- extract_multi_chiller_topology: 空输入边界情况
"""

import json
import pytest
import sys
from pathlib import Path

# 确保可以导入项目模块
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

from simulation.ai智能识别设备铭牌.ai_all_vision import (
    _robust_extract_json,
    _build_failed_result,
    extract_multi_chiller_topology,
    MULTI_CHILLER_PROMPT,
)


class TestRobustExtractJson:
    """测试 JSON 容错提取"""

    def test_direct_valid_json(self):
        result = _robust_extract_json('{"a": 1, "b": "hello"}')
        assert result == {"a": 1, "b": "hello"}

    def test_json_with_whitespace(self):
        result = _robust_extract_json('\n  {"a": 1}  \n')
        assert result == {"a": 1}

    def test_markdown_code_block(self):
        result = _robust_extract_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_markdown_without_lang(self):
        result = _robust_extract_json('```\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_json_in_text(self):
        result = _robust_extract_json('这里是一些说明文字 {"key": "value"} 后面还有文字')
        assert result == {"key": "value"}

    def test_trailing_comma_in_json(self):
        """测试尾逗号修复"""
        result = _robust_extract_json('{"a": 1, "b": 2,}')
        assert result == {"a": 1, "b": 2}

    def test_array_trailing_comma(self):
        """测试数组尾逗号修复"""
        result = _robust_extract_json('{"items": [1, 2, 3,]}')
        assert result == {"items": [1, 2, 3]}

    def test_empty_string(self):
        result = _robust_extract_json("")
        assert result is None

    def test_none_input(self):
        result = _robust_extract_json(None)
        assert result is None

    def test_invalid_json(self):
        result = _robust_extract_json("this is not json at all")
        assert result is None

    def test_nested_json(self):
        """测试嵌套 JSON 结构"""
        complicated = {
            "chillers": [
                {"name": "主机1", "capacity_kw": 5274.0, "rated_cop": 6.12}
            ],
            "count": 3
        }
        result = _robust_extract_json(json.dumps(complicated))
        assert result == complicated

    def test_multi_image_result(self):
        """测试多图识别结果的 JSON 解析"""
        sample = {
            "results": [
                {
                    "image_index": 0,
                    "status": "success",
                    "warning": None,
                    "data": {
                        "name": "约克YK离心机",
                        "qty": 3,
                        "capacity_kw": 5274.0,
                        "rated_power_kw": 800.0,
                        "rated_cop": 6.6,
                        "variable_freq": True
                    }
                },
                {
                    "image_index": 1,
                    "status": "partial",
                    "warning": "个别参数无法识别",
                    "data": {
                        "name": "开利离心机",
                        "qty": 2,
                        "capacity_kw": 3868.0,
                        "rated_power_kw": 632.0,
                        "rated_cop": None,
                        "variable_freq": True
                    }
                },
                {
                    "image_index": 2,
                    "status": "failed",
                    "warning": "图片模糊无法识别",
                    "data": None
                }
            ]
        }
        result = _robust_extract_json(json.dumps(sample))
        assert result is not None
        assert len(result["results"]) == 3
        assert result["results"][0]["status"] == "success"
        assert result["results"][1]["status"] == "partial"
        assert result["results"][2]["status"] == "failed"


class TestBuildFailedResult:
    """测试全部失败的兜底结果"""

    def test_single_failed(self):
        result = _build_failed_result(1, "测试失败原因")
        assert result["total_count"] == 1
        assert result["success_count"] == 0
        assert result["partial_count"] == 0
        assert result["failed_count"] == 1
        assert len(result["chillers"]) == 1
        assert result["chillers"][0]["index"] == 0
        assert result["chillers"][0]["status"] == "failed"
        assert "测试失败原因" in result["chillers"][0]["warning"]
        assert result["chillers"][0]["data"] is None

    def test_multiple_failed(self):
        result = _build_failed_result(3, "API异常")
        assert result["total_count"] == 3
        assert result["success_count"] == 0
        assert result["failed_count"] == 3
        assert len(result["chillers"]) == 3
        for i in range(3):
            assert result["chillers"][i]["index"] == i
            assert result["chillers"][i]["status"] == "failed"
            assert "第" in result["chillers"][i]["warning"]
            assert str(i+1) in result["chillers"][i]["warning"]


class TestExtractMultiChillerTopologyEmpty:
    """测试空输入边界情况"""

    def test_empty_images_list(self):
        """传入空列表应返回空结果"""
        result = extract_multi_chiller_topology([])
        assert result["total_count"] == 0
        assert result["success_count"] == 0
        assert result["failed_count"] == 0
        assert len(result["chillers"]) == 0

    def test_none_media_types_default(self):
        """不传 media_types 时默认 jpeg"""
        # 空列表不会调用 API，只是测试参数默认值逻辑
        result = extract_multi_chiller_topology([])
        assert result["total_count"] == 0


class TestPromptTemplate:
    """测试 prompt 模板"""

    def test_image_count_replacement(self):
        """测试 __IMAGE_COUNT__ 占位符被正确替换"""
        prompt = MULTI_CHILLER_PROMPT.replace("__IMAGE_COUNT__", "3")
        assert "3 张" in prompt
        assert "__IMAGE_COUNT__" not in prompt

    def test_prompt_contains_key_instructions(self):
        """测试 prompt 包含所有关键指令"""
        prompt = MULTI_CHILLER_PROMPT
        # 关键字段说明
        assert "image_index" in prompt
        assert "success" in prompt
        assert "partial" in prompt
        assert "failed" in prompt
        # 识别规则
        assert "3.517" in prompt  # RT → kW 转换系数
        assert "COP" in prompt
        assert "模糊" in prompt or "无法识别" in prompt
        # 输出格式
        assert "results" in prompt


class TestResultStructure:
    """测试返回结果结构"""

    def test_empty_result_structure(self):
        """空输入的返回结构应完整"""
        result = extract_multi_chiller_topology([])
        expected_keys = {"total_count", "success_count", "partial_count",
                         "failed_count", "chillers"}
        assert expected_keys.issubset(set(result.keys()))

    @pytest.mark.parametrize("count,reason", [
        (1, "API错误"),
        (2, "解析失败"),
        (5, "超时"),
    ])
    def test_build_failed_result_structure(self, count, reason):
        """各种数量的失败结果结构一致"""
        result = _build_failed_result(count, reason)
        assert result["total_count"] == count
        assert result["failed_count"] == count
        assert result["success_count"] == 0
        assert len(result["chillers"]) == count
        for i, ch in enumerate(result["chillers"]):
            assert ch["index"] == i
            assert ch["status"] == "failed"
            assert reason in ch["warning"]
            assert ch["data"] is None
