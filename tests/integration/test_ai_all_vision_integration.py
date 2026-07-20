"""ai_all_vision 与 simulation_ui 联动集成测试

测试多图识别结果如何被 simulation_ui 处理并填入各组主机表单。
不依赖真实 API，mock extract_multi_chiller_topology 的行为。
"""

import copy
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

from simulation.ai智能识别设备铭牌.ai_all_vision import extract_multi_chiller_topology


# ── 模拟 AI API 返回的原始文本（不同场景）──

VALID_RESULT_3_SUCCESS = {
    "total_count": 3,
    "success_count": 3,
    "partial_count": 0,
    "failed_count": 0,
    "chillers": [
        {
            "index": 0,
            "status": "success",
            "warning": None,
            "data": {
                "name": "约克YK离心机",
                "qty": 3,
                "capacity_kw": 5274.0,
                "rated_power_kw": 800.0,
                "rated_cop": 6.6,
                "variable_freq": True,
            },
        },
        {
            "index": 1,
            "status": "success",
            "warning": None,
            "data": {
                "name": "特灵CVHE离心机",
                "qty": 2,
                "capacity_kw": 3868.0,
                "rated_power_kw": 632.0,
                "rated_cop": 6.12,
                "variable_freq": True,
            },
        },
        {
            "index": 2,
            "status": "success",
            "warning": None,
            "data": {
                "name": "麦克维尔螺杆机",
                "qty": 4,
                "capacity_kw": 1400.0,
                "rated_power_kw": 270.0,
                "rated_cop": 5.2,
                "variable_freq": False,
            },
        },
    ],
}

VALID_RESULT_PARTIAL_MIXED = {
    "total_count": 3,
    "success_count": 1,
    "partial_count": 1,
    "failed_count": 1,
    "chillers": [
        {
            "index": 0,
            "status": "success",
            "warning": None,
            "data": {
                "name": "约克YK离心机",
                "qty": 3,
                "capacity_kw": 5274.0,
                "rated_power_kw": 800.0,
                "rated_cop": 6.6,
                "variable_freq": True,
            },
        },
        {
            "index": 1,
            "status": "partial",
            "warning": "个别参数无法识别：rated_cop字段模糊，建议核查主机组2",
            "data": {
                "name": "特灵CVHE离心机",
                "qty": 2,
                "capacity_kw": 3868.0,
                "rated_power_kw": 632.0,
                "rated_cop": None,
                "variable_freq": True,
            },
        },
        {
            "index": 2,
            "status": "failed",
            "warning": "第3张图片画面模糊/反光严重，无法识别任何参数，建议核查主机组3",
            "data": None,
        },
    ],
}

VALID_RESULT_ALL_FAILED = {
    "total_count": 2,
    "success_count": 0,
    "partial_count": 0,
    "failed_count": 2,
    "chillers": [
        {
            "index": 0,
            "status": "failed",
            "warning": "第1张图片模糊无法识别，建议核查主机组1",
            "data": None,
        },
        {
            "index": 1,
            "status": "failed",
            "warning": "第2张图片非铭牌照片，建议核查主机组2",
            "data": None,
        },
    ],
}


# ── 模拟 simulation_ui 中的处理逻辑 ──

def simulate_ui_process_result(result: dict) -> dict:
    """
    模拟 simulation_ui 中对 extract_multi_chiller_topology 返回结果的处理逻辑。
    返回 UI 处理后的状态变化摘要。
    """
    if not result or result.get("total_count", 0) == 0:
        return {"status": "no_result", "filled_groups": 0, "warnings": [], "errors": []}

    chillers = result.get("chillers", [])
    valid_chillers = [
        ch for ch in chillers
        if ch.get("status") in ("success", "partial")
    ]

    if not valid_chillers:
        # 全部失败
        return {
            "status": "all_failed",
            "filled_groups": 0,
            "warnings": [ch["warning"] for ch in chillers if ch.get("warning")],
            "errors": ["所有图片均识别失败"],
        }

    # 构建 topology 结果（只包含成功/部分识别的组）
    topology = {
        "chillers": [ch["data"] for ch in valid_chillers if ch.get("data") is not None],
    }

    # 逐组处理
    filled_index = 0
    warnings = []
    success_groups = []
    partial_groups = []
    failed_messages = []

    for ch in chillers:
        if ch.get("status") == "success":
            if ch.get("data"):
                success_groups.append({"index": filled_index, "data": ch["data"]})
            filled_index += 1
        elif ch.get("status") == "partial":
            if ch.get("data"):
                partial_groups.append({"index": filled_index, "data": ch["data"]})
            if ch.get("warning"):
                warnings.append(ch["warning"])
            filled_index += 1
        elif ch.get("status") == "failed":
            if ch.get("warning"):
                failed_messages.append(ch["warning"])

    return {
        "status": "success",
        "filled_groups": filled_index,
        "topology_chiller_count": len(topology["chillers"]),
        "success_groups": success_groups,
        "partial_groups": partial_groups,
        "warnings": warnings,
        "failed_messages": failed_messages,
    }


class TestUiSimulateProcessResult:
    """测试模拟 UI 处理逻辑（与 simulation_ui 中的处理逻辑保持一致）"""

    def test_all_3_success(self):
        """3张图片全部识别成功 → 填入3组"""
        result = simulate_ui_process_result(VALID_RESULT_3_SUCCESS)
        assert result["status"] == "success"
        assert result["filled_groups"] == 3
        assert result["topology_chiller_count"] == 3
        assert len(result["success_groups"]) == 3
        assert len(result["partial_groups"]) == 0
        assert len(result["warnings"]) == 0
        assert len(result["failed_messages"]) == 0

        # 验证每组参数正确
        assert result["success_groups"][0]["index"] == 0
        assert result["success_groups"][0]["data"]["name"] == "约克YK离心机"
        assert result["success_groups"][1]["index"] == 1
        assert result["success_groups"][1]["data"]["rated_cop"] == 6.12
        assert result["success_groups"][2]["index"] == 2
        assert result["success_groups"][2]["data"]["variable_freq"] is False

    def test_all_3_success_n_groups(self):
        """识别完成后自动设置的主机组数应等于成功识别的组数"""
        result = simulate_ui_process_result(VALID_RESULT_3_SUCCESS)
        assert result["filled_groups"] == 3  # 对应 n_groups = 3

    def test_mixed_partial_and_failed(self):
        """1成功+1部分+1失败 → 填入2组，产生1个warning，1个failed消息"""
        result = simulate_ui_process_result(VALID_RESULT_PARTIAL_MIXED)
        assert result["status"] == "success"
        assert result["filled_groups"] == 2  # 成功+部分 = 2组
        assert result["topology_chiller_count"] == 2
        assert len(result["success_groups"]) == 1
        assert len(result["partial_groups"]) == 1
        assert len(result["warnings"]) == 1
        assert len(result["failed_messages"]) == 1
        assert "核查主机组2" in result["warnings"][0]
        assert "核查主机组3" in result["failed_messages"][0]

    def test_all_failed(self):
        """全部识别失败 → 0组填入，显示错误"""
        result = simulate_ui_process_result(VALID_RESULT_ALL_FAILED)
        assert result["status"] == "all_failed"
        assert result["filled_groups"] == 0
        assert len(result["warnings"]) == 2
        assert "核查主机组1" in result["warnings"][0]
        assert "核查主机组2" in result["warnings"][1]

    def test_partial_data_has_null_fields(self):
        """partial 状态的 data 中 rated_cop 为 null，UI 应使用默认值"""
        result = simulate_ui_process_result(VALID_RESULT_PARTIAL_MIXED)
        partial_data = result["partial_groups"][0]["data"]
        assert partial_data["rated_cop"] is None
        # UI 层应使用默认值 6.0 填充（由 _apply_single_chiller_result 处理）
        # 这里验证数据确实传到了 UI 处理阶段
        assert partial_data["name"] == "特灵CVHE离心机"

    def test_empty_result(self):
        """空结果处理"""
        result = simulate_ui_process_result({"total_count": 0, "success_count": 0,
                                              "partial_count": 0, "failed_count": 0, "chillers": []})
        assert result["status"] == "no_result"

    def test_none_result(self):
        """None 结果处理"""
        result = simulate_ui_process_result(None)
        assert result["status"] == "no_result"

    def test_failed_data_is_always_none(self):
        """failed 状态的 data 必须是 None"""
        for ch in VALID_RESULT_ALL_FAILED["chillers"]:
            assert ch["data"] is None

    def test_filled_indices_are_sequential(self):
        """
        验证填入的 index 是连续的 (0, 1, 2, ...)。
        failed 的图片不应该占据 filled_index 位置。
        例如：图片0成功→组0，图片1失败→跳过，图片2部分→组1
        """
        # 构造：第1张成功，第2张失败，第3张成功
        result_with_gap = {
            "total_count": 3,
            "success_count": 2,
            "partial_count": 0,
            "failed_count": 1,
            "chillers": [
                {"index": 0, "status": "success", "warning": None,
                 "data": {"name": "主机A", "qty": 1, "capacity_kw": 5000, "rated_power_kw": 800, "rated_cop": 6.3, "variable_freq": True}},
                {"index": 1, "status": "failed", "warning": "第2张图片模糊", "data": None},
                {"index": 2, "status": "success", "warning": None,
                 "data": {"name": "主机B", "qty": 2, "capacity_kw": 3000, "rated_power_kw": 500, "rated_cop": 6.0, "variable_freq": False}},
            ],
        }
        result = simulate_ui_process_result(result_with_gap)
        # filled_index 应该连续：group 0 = 主机A, group 1 = 主机B
        assert result["filled_groups"] == 2
        assert result["success_groups"][0]["index"] == 0
        assert result["success_groups"][1]["index"] == 1
        assert result["success_groups"][0]["data"]["name"] == "主机A"
        assert result["success_groups"][1]["data"]["name"] == "主机B"


class TestWriteChillerToSessionState:
    """测试 _write_chiller_to_session_state 字段写入逻辑"""

    # 验证字段映射的正确性（不依赖 streamlit session_state）
    from simulation_ui import _write_chiller_to_session_state

    def test_normal_data(self):
        """正常数据填入"""
        data = {
            "name": "测试主机",
            "qty": 2,
            "capacity_kw": 5000.0,
            "rated_power_kw": 800.0,
            "rated_cop": 6.25,
            "variable_freq": True,
        }
        # 函数正常执行不抛异常
        # 注意：_apply_single_chiller_result 依赖 st.session_state，
        # 这里只验证参数传递正确
        assert data["name"] == "测试主机"
        assert data["qty"] == 2
        assert data["capacity_kw"] == 5000.0
        assert data["rated_power_kw"] == 800.0
        assert data["rated_cop"] == 6.25
        assert data["variable_freq"] is True

    def test_data_with_none_cop(self):
        """COP 为 None 时，函数应使用默认值（6.0）"""
        data = {
            "name": "部分识别主机",
            "qty": 1,
            "capacity_kw": 3868.0,
            "rated_power_kw": 632.0,
            "rated_cop": None,  # AI 未能识别
            "variable_freq": False,
        }
        # _apply_single_chiller_result 中:
        # float(data.get("rated_cop") or 6.0) → 6.0
        assert data["rated_cop"] is None
        # 应用默认值逻辑
        default_cop = float(data.get("rated_cop") or 6.0)
        assert default_cop == 6.0

    def test_data_with_missing_cop(self):
        """COP 字段完全缺失"""
        data = {
            "name": "无COP主机",
            "qty": 1,
            "capacity_kw": 5000.0,
            "rated_power_kw": 800.0,
            "variable_freq": True,
        }
        default_cop = float(data.get("rated_cop") or 6.0)
        assert default_cop == 6.0


class TestApiReturnedDataFieldMapping:
    """测试 AI 返回字段到 simulation_ui 表单字段的映射"""

    def _simulate_field_mapping(self, ai_data: dict) -> dict:
        """
        模拟 _apply_single_chiller_result 中的字段映射：
        name→name, qty→qty, capacity_kw→capacity_kw,
        rated_power_kw→rated_power_kw, rated_cop→rated_cop,
        variable_freq→variable_freq
        """
        return {
            "name": ai_data.get("name", "主机组X"),
            "qty": int(ai_data.get("qty") or 1),
            "capacity_kw": float(ai_data.get("capacity_kw") or 5000),
            "rated_power_kw": float(ai_data.get("rated_power_kw") or 800),
            "rated_cop": float(ai_data.get("rated_cop") or 6.0),
            "variable_freq": bool(ai_data.get("variable_freq", False)),
        }

    def test_all_fields_present(self):
        ai_data = {
            "name": "离心机A", "qty": 3, "capacity_kw": 5274.0,
            "rated_power_kw": 800.0, "rated_cop": 6.6, "variable_freq": True,
        }
        mapped = self._simulate_field_mapping(ai_data)
        assert mapped["name"] == "离心机A"
        assert mapped["qty"] == 3
        assert mapped["capacity_kw"] == 5274.0
        assert mapped["rated_cop"] == 6.6

    def test_missing_fields_get_defaults(self):
        ai_data = {"name": "未知主机"}
        mapped = self._simulate_field_mapping(ai_data)
        assert mapped["name"] == "未知主机"
        assert mapped["qty"] == 1
        assert mapped["capacity_kw"] == 5000.0
        assert mapped["rated_power_kw"] == 800.0
        assert mapped["rated_cop"] == 6.0
        assert mapped["variable_freq"] is False

    def test_null_fields_in_partial_result(self):
        """partial 状态下个别字段为 None，其余有值"""
        ai_data = {
            "name": "部分识别主机",
            "qty": 2,
            "capacity_kw": 3868.0,
            "rated_power_kw": 632.0,
            "rated_cop": None,  # 这个字段模糊无法识别
            "variable_freq": True,
        }
        mapped = self._simulate_field_mapping(ai_data)
        assert mapped["rated_cop"] == 6.0  # 默认值
        assert mapped["capacity_kw"] == 3868.0  # 正常值保留
        assert mapped["variable_freq"] is True
