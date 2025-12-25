#!/usr/bin/env python3
"""测试置信度检查逻辑"""

import pytest
import json
from pathlib import Path


@pytest.fixture
def low_confidence_quality_report():
    """生成低置信度质量报告"""
    return {
        "completeness": 0.35,  # 35% 完整率,低于 50% 阈值
        "confidence_level": "low",
        "issues": [
            {
                "field": "monthly_data[0].total_energy",
                "severity": "high",
                "type": "missing",
                "message": "1月冷站总能耗缺失"
            },
            {
                "field": "monthly_data[1].total_energy",
                "severity": "high",
                "type": "missing",
                "message": "2月冷站总能耗缺失"
            },
            {
                "field": "monthly_data[0].chiller_supply_temp",
                "severity": "high",
                "type": "missing",
                "message": "1月冷机供水温度缺失"
            }
        ],
        "summary": "数据完整率35%,建议补充缺失月份数据。发现3个高优先级问题。"
    }


@pytest.fixture
def medium_confidence_quality_report():
    """生成中等置信度质量报告"""
    return {
        "completeness": 0.68,
        "confidence_level": "medium",
        "issues": [
            {
                "field": "monthly_data[3].chiller_supply_temp",
                "severity": "high",
                "type": "missing",
                "message": "4月冷机供水温度缺失"
            }
        ],
        "summary": "数据完整率68%,建议补充缺失月份数据。发现1个高优先级问题。"
    }


@pytest.fixture
def high_confidence_quality_report():
    """生成高置信度质量报告"""
    return {
        "completeness": 0.92,
        "confidence_level": "high",
        "issues": [],
        "summary": "数据完整率92%,未发现数据质量问题。"
    }


def test_low_confidence_should_block_workflow(low_confidence_quality_report):
    """测试低置信度应该阻止流程继续"""
    confidence = low_confidence_quality_report["confidence_level"]
    completeness = low_confidence_quality_report["completeness"]

    assert confidence == "low"
    assert completeness < 0.5

    # 模拟判断逻辑
    should_continue = confidence != "low"
    assert should_continue is False


def test_medium_confidence_should_allow_workflow(medium_confidence_quality_report):
    """测试中等置信度应该允许流程继续(带警告)"""
    confidence = medium_confidence_quality_report["confidence_level"]
    completeness = medium_confidence_quality_report["completeness"]

    assert confidence == "medium"
    assert 0.5 <= completeness < 0.8

    # 模拟判断逻辑
    should_continue = confidence != "low"
    assert should_continue is True


def test_high_confidence_should_allow_workflow(high_confidence_quality_report):
    """测试高置信度应该允许流程继续"""
    confidence = high_confidence_quality_report["confidence_level"]
    completeness = high_confidence_quality_report["completeness"]

    assert confidence == "high"
    assert completeness >= 0.8

    # 模拟判断逻辑
    should_continue = confidence != "low"
    assert should_continue is True


def test_quality_report_structure(low_confidence_quality_report):
    """测试质量报告结构完整性"""
    assert "completeness" in low_confidence_quality_report
    assert "confidence_level" in low_confidence_quality_report
    assert "issues" in low_confidence_quality_report
    assert "summary" in low_confidence_quality_report

    # 验证问题列表结构
    for issue in low_confidence_quality_report["issues"]:
        assert "field" in issue
        assert "severity" in issue
        assert "type" in issue
        assert "message" in issue
