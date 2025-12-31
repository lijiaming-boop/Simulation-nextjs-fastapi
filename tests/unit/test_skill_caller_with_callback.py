"""测试 SkillCaller 的回调机制"""
import pytest
import asyncio
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.skill_caller import SkillCaller, SkillError
from claude_agent_sdk import AssistantMessage, TextBlock


@pytest.mark.asyncio
async def test_callback_called_on_assistant_message():
    """测试每次收到 AssistantMessage 时都调用 callback"""
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        caller = SkillCaller(timeout=10)

        # 创建一个测试 skill
        skill_path = caller.skills_dir / "test-callback-skill"
        skill_path.mkdir(exist_ok=True)
        skill_md = skill_path / "SKILL.md"
        skill_md.write_text("# Test Skill\nTest callback")

        try:
            # 模拟多个 AssistantMessage
            async def mock_query(*args, **kwargs):
                # 第一条消息
                msg1 = MagicMock(spec=AssistantMessage)
                msg1.content = [TextBlock(text="第一步分析")]
                yield msg1

                # 第二条消息
                msg2 = MagicMock(spec=AssistantMessage)
                msg2.content = [TextBlock(text="第二步处理")]
                yield msg2

                # 第三条消息
                msg3 = MagicMock(spec=AssistantMessage)
                msg3.content = [TextBlock(text="完成")]
                yield msg3

            # 创建回调函数来记录调用
            callback_calls = []

            def test_callback(timestamp: str, message: str):
                callback_calls.append({"timestamp": timestamp, "message": message})

            with patch('core.skill_caller.query', side_effect=mock_query):
                result = await caller._call_skill_async(
                    "test-callback-skill",
                    "input.txt",
                    "output.txt",
                    check_output=False,
                    callback=test_callback
                )

                # 验证回调被调用了3次（对应3条 AssistantMessage）
                assert len(callback_calls) == 3

                # 验证每次调用的参数正确
                assert callback_calls[0]["message"] == "第一步分析"
                assert callback_calls[1]["message"] == "第二步处理"
                assert callback_calls[2]["message"] == "完成"

                # 验证时间戳格式正确（HH:MM:SS）
                for call in callback_calls:
                    timestamp = call["timestamp"]
                    assert len(timestamp.split(":")) == 3  # 格式：HH:MM:SS

                # 验证返回结果正确
                assert result["success"] is True
                assert len(result["ai_responses"]) == 3
                assert result["ai_responses"][0] == "第一步分析"
                assert result["ai_responses"][1] == "第二步处理"
                assert result["ai_responses"][2] == "完成"

        finally:
            # 清理测试文件
            skill_md.unlink(missing_ok=True)
            skill_path.rmdir()


@pytest.mark.asyncio
async def test_callback_on_timeout_error():
    """测试超时错误时也调用 callback"""
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        caller = SkillCaller(timeout=1)  # 1秒超时

        # 创建一个测试 skill
        skill_path = caller.skills_dir / "test-timeout-callback-skill"
        skill_path.mkdir(exist_ok=True)
        skill_md = skill_path / "SKILL.md"
        skill_md.write_text("# Test Skill\nTest timeout callback")

        try:
            # 模拟一个会超时的查询
            async def slow_query(*args, **kwargs):
                await asyncio.sleep(5)  # 超过1秒超时
                yield "Should not reach here"

            # 创建回调函数来记录调用
            callback_calls = []

            def test_callback(timestamp: str, message: str):
                callback_calls.append({"timestamp": timestamp, "message": message})

            with patch('core.skill_caller.query', side_effect=slow_query):
                with pytest.raises(SkillError) as exc_info:
                    await caller._call_skill_async(
                        "test-timeout-callback-skill",
                        "input.txt",
                        "output.txt",
                        check_output=False,
                        callback=test_callback
                    )

                # 验证抛出了超时错误
                assert "执行超时" in str(exc_info.value)

                # 验证回调被调用了，并记录了错误
                assert len(callback_calls) == 1
                assert "执行超时" in callback_calls[0]["message"]
                assert "❌" in callback_calls[0]["message"]

        finally:
            # 清理测试文件
            skill_md.unlink(missing_ok=True)
            skill_path.rmdir()


@pytest.mark.asyncio
async def test_callback_on_general_error():
    """测试一般错误时也调用 callback"""
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        caller = SkillCaller(timeout=10)

        # 创建一个测试 skill
        skill_path = caller.skills_dir / "test-error-callback-skill"
        skill_path.mkdir(exist_ok=True)
        skill_md = skill_path / "SKILL.md"
        skill_md.write_text("# Test Skill\nTest error callback")

        try:
            # 模拟一个会抛出异常的查询
            async def error_query(*args, **kwargs):
                raise ValueError("模拟的错误")
                yield  # 使其成为异步生成器

            # 创建回调函数来记录调用
            callback_calls = []

            def test_callback(timestamp: str, message: str):
                callback_calls.append({"timestamp": timestamp, "message": message})

            with patch('core.skill_caller.query', side_effect=error_query):
                with pytest.raises(SkillError) as exc_info:
                    await caller._call_skill_async(
                        "test-error-callback-skill",
                        "input.txt",
                        "output.txt",
                        check_output=False,
                        callback=test_callback
                    )

                # 验证抛出了错误
                assert "执行出错" in str(exc_info.value)

                # 验证回调被调用了，并记录了错误
                assert len(callback_calls) == 1
                assert "执行出错" in callback_calls[0]["message"]
                assert "❌" in callback_calls[0]["message"]

        finally:
            # 清理测试文件
            skill_md.unlink(missing_ok=True)
            skill_path.rmdir()


def test_call_skill_with_callback_sync():
    """测试同步接口也支持 callback"""
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        caller = SkillCaller(timeout=10)

        # 创建一个测试 skill
        skill_path = caller.skills_dir / "test-sync-callback-skill"
        skill_path.mkdir(exist_ok=True)
        skill_md = skill_path / "SKILL.md"
        skill_md.write_text("# Test Skill\nTest sync callback")

        try:
            # 模拟 AssistantMessage
            async def mock_query(*args, **kwargs):
                msg = MagicMock(spec=AssistantMessage)
                msg.content = [TextBlock(text="同步回调测试")]
                yield msg

            # 创建回调函数来记录调用
            callback_calls = []

            def test_callback(timestamp: str, message: str):
                callback_calls.append({"timestamp": timestamp, "message": message})

            with patch('core.skill_caller.query', side_effect=mock_query):
                result = caller.call_skill(
                    "test-sync-callback-skill",
                    "input.txt",
                    "output.txt",
                    check_output=False,
                    callback=test_callback
                )

                # 验证回调被调用了
                assert len(callback_calls) == 1
                assert callback_calls[0]["message"] == "同步回调测试"

                # 验证返回结果正确
                assert result["success"] is True
                assert len(result["ai_responses"]) == 1
                assert result["ai_responses"][0] == "同步回调测试"

        finally:
            # 清理测试文件
            skill_md.unlink(missing_ok=True)
            skill_path.rmdir()


@pytest.mark.asyncio
async def test_callback_without_callback_parameter():
    """测试不提供 callback 参数时正常工作"""
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        caller = SkillCaller(timeout=10)

        # 创建一个测试 skill
        skill_path = caller.skills_dir / "test-no-callback-skill"
        skill_path.mkdir(exist_ok=True)
        skill_md = skill_path / "SKILL.md"
        skill_md.write_text("# Test Skill\nTest no callback")

        try:
            # 模拟 AssistantMessage
            async def mock_query(*args, **kwargs):
                msg = MagicMock(spec=AssistantMessage)
                msg.content = [TextBlock(text="无回调测试")]
                yield msg

            with patch('core.skill_caller.query', side_effect=mock_query):
                # 不传入 callback 参数
                result = await caller._call_skill_async(
                    "test-no-callback-skill",
                    "input.txt",
                    "output.txt",
                    check_output=False
                    # callback=None  # 不传入 callback
                )

                # 验证正常执行
                assert result["success"] is True
                assert len(result["ai_responses"]) == 1
                assert result["ai_responses"][0] == "无回调测试"

        finally:
            # 清理测试文件
            skill_md.unlink(missing_ok=True)
            skill_path.rmdir()
