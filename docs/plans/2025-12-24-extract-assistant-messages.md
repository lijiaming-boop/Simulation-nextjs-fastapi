# 提取和展示 AI 助手响应内容 - 实施计划

**创建时间：** 2025-12-24
**需求来源：** 用户反馈 - 需要在 Streamlit 前端展示 Skill 调用过程中 AI 的响应内容

---

## 需求概述

### 当前问题
- `skill_caller.py` 使用 Claude Agent SDK 调用 skills
- 目前只是简单地用 `str(message)` 转换所有消息
- 前端看不到 AI 的实际响应内容，用户体验差

### 目标
1. 从 Agent SDK 的消息流中提取 `AssistantMessage` 的 content 文本
2. 忽略 `UserMessage` 的 content（因为是系统生成的）
3. 在 Streamlit 前端以友好的方式展示这些 AI 响应

---

## 技术方案

### Agent SDK Message 结构

根据官方文档，消息类型结构如下：

```python
# AssistantMessage 结构
AssistantMessage(
    content=[
        TextBlock(text="这是 AI 的回复文本"),
        ToolUseBlock(...),  # 工具调用
        ...
    ],
    model="claude-sonnet-4",
    parent_tool_use_id=None,
    error=None
)

# UserMessage 结构
UserMessage(
    content="用户消息或系统消息",
    parent_tool_use_id=None
)
```

### 提取逻辑

```python
from claude_agent_sdk import AssistantMessage, TextBlock

ai_responses = []
async for message in query(prompt=prompt, options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                ai_responses.append(block.text)
```

---

## 实施方案

### 方案选择：扩展返回值类型

**决定：** 修改 `call_skill` 返回值为字典，包含详细信息

**理由：**
- 清晰明确，不依赖隐藏状态
- 易于在前端使用
- 未来可扩展（如添加工具调用信息）

**返回值结构：**
```python
{
    "success": True,
    "ai_responses": ["AI回复1", "AI回复2", ...],  # 只包含 AssistantMessage 的 TextBlock
    "all_messages": ["消息1", "消息2", ...],      # 所有消息的字符串表示（调试用）
    "result_text": "合并的所有消息"                # 向后兼容字段
}
```

---

## 文件修改清单

### 1. `core/skill_caller.py`

**修改点1：导入必要类型**
```python
# 在文件顶部添加
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock
```

**修改点2：修改 `_call_skill_async` 方法（line 90-158）**

当前代码（line 131-148）：
```python
# 调用 Agent SDK（添加超时控制）
result_messages = []
try:
    async with asyncio.timeout(self.timeout):  # 添加超时控制
        async for message in query(prompt=prompt, options=options):
            result_messages.append(str(message))
            print(f"Type: {type(message)}")
            print(f"Message: {message}")
            print(f"Dir: {dir(message)}")  # 查看所有属性
            print("---")
except asyncio.TimeoutError as e:
    raise SkillError(
        f"Skill '{skill_name}' 执行超时(>{self.timeout}秒)"
    ) from e
except Exception as e:
    raise SkillError(f"Skill '{skill_name}' 执行出错: {str(e)}") from e

# 合并结果
result_text = "\n".join(result_messages)
```

修改为：
```python
# 调用 Agent SDK（添加超时控制）
all_messages = []
ai_responses = []
try:
    async with asyncio.timeout(self.timeout):  # 添加超时控制
        async for message in query(prompt=prompt, options=options):
            # 收集所有消息的字符串表示
            all_messages.append(str(message))

            # 只提取 AssistantMessage 的文本内容
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        ai_responses.append(block.text)

except asyncio.TimeoutError as e:
    raise SkillError(
        f"Skill '{skill_name}' 执行超时(>{self.timeout}秒)"
    ) from e
except Exception as e:
    raise SkillError(f"Skill '{skill_name}' 执行出错: {str(e)}") from e

# 合并结果文本
result_text = "\n".join(all_messages)
```

**修改点3：修改返回值结构**

当前返回（line 148-158）：
```python
# 合并结果
result_text = "\n".join(result_messages)

# 检查输出文件（如果需要）
if check_output and len(args) >= 2:
    output_file = Path(args[-1])
    if not output_file.exists():
        raise SkillError(
            f"Skill 执行完成，但未生成预期的输出文件: {output_file}"
        )

return result_text
```

修改为：
```python
# 检查输出文件（如果需要）
if check_output and len(args) >= 2:
    output_file = Path(args[-1])
    if not output_file.exists():
        raise SkillError(
            f"Skill 执行完成，但未生成预期的输出文件: {output_file}"
        )

# 返回详细结果
return {
    "success": True,
    "ai_responses": ai_responses,
    "all_messages": all_messages,
    "result_text": result_text
}
```

**修改点4：更新 `call_skill` 返回类型注解**

当前（line 60-88）：
```python
def call_skill(
    self,
    skill_name: str,
    *args,
    check_output: bool = True
) -> Optional[str]:
```

修改为：
```python
def call_skill(
    self,
    skill_name: str,
    *args,
    check_output: bool = True
) -> Dict[str, Any]:
```

**修改点5：更新 `_call_skill_async` 返回类型注解**

当前（line 90-107）：
```python
async def _call_skill_async(
    self,
    skill_name: str,
    *args,
    check_output: bool = True
) -> Optional[str]:
```

修改为：
```python
async def _call_skill_async(
    self,
    skill_name: str,
    *args,
    check_output: bool = True
) -> Dict[str, Any]:
```

---

### 2. `app.py`

需要修改三个调用 `call_skill` 的地方：

#### 修改点1：`render_extract_check_stage()` - line 115-234

**当前代码（line 120-131）：**
```python
caller = SkillCaller(timeout=300)

upload_path = Path("tmp/upload_survey.xlsx")
output_path = Path("tmp/extract_check_result.json")

# 调用合并的 Skill: 提取和质量检查
caller.call_skill(
    "extract-and-check-data",
    str(upload_path),
    str(output_path)
)
```

**修改为：**
```python
caller = SkillCaller(timeout=300)

upload_path = Path("tmp/upload_survey.xlsx")
output_path = Path("tmp/extract_check_result.json")

# 调用合并的 Skill: 提取和质量检查
skill_result = caller.call_skill(
    "extract-and-check-data",
    str(upload_path),
    str(output_path)
)

# 展示 AI 响应过程
if skill_result.get("ai_responses"):
    with st.expander("🤖 查看 AI 分析过程", expanded=False):
        for idx, response in enumerate(skill_result["ai_responses"], 1):
            st.markdown(f"**步骤 {idx}:**")
            st.text(response)
            st.markdown("---")
```

#### 修改点2：`render_filling_stage()` - line 237-344

**当前代码（line 244-257）：**
```python
caller = SkillCaller(timeout=300)

extracted_path = Path("tmp/extracted_data.json")
quality_path = Path("tmp/quality_report.json")
output_path = Path("tmp/filling_suggestions.json")

# 调用 Skill 3: 填充建议
caller.call_skill(
    "suggest-data-filling",
    str(extracted_path),
    str(quality_path),
    str(output_path)
)
```

**修改为：**
```python
caller = SkillCaller(timeout=300)

extracted_path = Path("tmp/extracted_data.json")
quality_path = Path("tmp/quality_report.json")
output_path = Path("tmp/filling_suggestions.json")

# 调用 Skill 3: 填充建议
skill_result = caller.call_skill(
    "suggest-data-filling",
    str(extracted_path),
    str(quality_path),
    str(output_path)
)

# 展示 AI 响应过程（在生成填充建议后）
if skill_result.get("ai_responses"):
    with st.expander("🤖 查看 AI 推理过程", expanded=False):
        for idx, response in enumerate(skill_result["ai_responses"], 1):
            st.markdown(f"**步骤 {idx}:**")
            st.text(response)
            st.markdown("---")
```

---

### 3. `CLAUDE.md`

在 "Skill 调用" 部分更新返回值说明：

**当前内容（line 584-606）：**
```markdown
**在 Python 代码中调用（推荐）：**
```python
from core.skill_caller import SkillCaller

caller = SkillCaller(timeout=300)
result = caller.call_skill(
    "extract-survey-data",
    "input.xlsx",
    "output.json"
)
```

**特性：**
- 使用 Claude Agent SDK 进行异步调用
- 自动发现 `.claude/skills/` 目录下的 skills
- 支持超时控制和错误处理
- 保持向后兼容的同步接口
```

**修改为：**
```markdown
**在 Python 代码中调用（推荐）：**
```python
from core.skill_caller import SkillCaller

caller = SkillCaller(timeout=300)
result = caller.call_skill(
    "extract-survey-data",
    "input.xlsx",
    "output.json"
)

# 访问 AI 响应内容
ai_responses = result["ai_responses"]  # AI 助手的文本回复列表
all_messages = result["all_messages"]  # 所有消息（调试用）
result_text = result["result_text"]    # 合并的文本（向后兼容）
```

**返回值结构：**
```python
{
    "success": True,
    "ai_responses": ["AI回复1", "AI回复2", ...],  # AssistantMessage 的文本内容
    "all_messages": ["消息1", "消息2", ...],      # 所有消息的字符串表示
    "result_text": "合并的所有消息文本"            # 向后兼容字段
}
```

**特性：**
- 使用 Claude Agent SDK 进行异步调用
- 自动发现 `.claude/skills/` 目录下的 skills
- 支持超时控制和错误处理
- 提取 AssistantMessage 的文本内容供前端展示
- 保持向后兼容的同步接口
```

---

## 测试计划

### 单元测试修改

**文件：** `tests/unit/test_skill_caller.py`

需要更新测试以验证新的返回值结构：

```python
def test_call_skill_return_structure():
    """测试 call_skill 返回值结构"""
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        caller = SkillCaller()

        # Mock Agent SDK
        with patch('core.skill_caller.query') as mock_query:
            # 模拟 AssistantMessage 和 TextBlock
            mock_message = MagicMock()
            mock_message.__class__.__name__ = 'AssistantMessage'

            mock_block = MagicMock()
            mock_block.__class__.__name__ = 'TextBlock'
            mock_block.text = "AI 的回复"

            mock_message.content = [mock_block]

            async def mock_async_iter():
                yield mock_message

            mock_query.return_value = mock_async_iter()

            # 调用并验证
            result = caller.call_skill("test-skill", "arg1", "arg2", check_output=False)

            assert isinstance(result, dict)
            assert "success" in result
            assert "ai_responses" in result
            assert "all_messages" in result
            assert "result_text" in result
            assert result["success"] is True
            assert len(result["ai_responses"]) > 0
```

### 集成测试

**文件：** `tests/integration/test_skill_integration.py`

更新现有测试以验证新返回值：

```python
def test_extract_survey_data_skill_return_structure(self, skill_caller, tmp_output_dir):
    """测试 extract-survey-data skill 返回值结构"""
    survey_file = "00_sample/02-中央空调节能调研表.xlsx"
    output_file = tmp_output_dir / "extracted_data.json"

    if not Path(survey_file).exists():
        pytest.skip(f"样例文件不存在: {survey_file}")

    # 调用 skill
    result = skill_caller.call_skill(
        "extract-survey-data",
        str(survey_file),
        str(output_file)
    )

    # 验证返回值结构
    assert isinstance(result, dict)
    assert result["success"] is True
    assert "ai_responses" in result
    assert isinstance(result["ai_responses"], list)

    # 验证 AI 响应内容
    assert len(result["ai_responses"]) > 0
    for response in result["ai_responses"]:
        assert isinstance(response, str)
        assert len(response) > 0
```

---

## 实施步骤

### Step 1: 修改 `core/skill_caller.py`
- [ ] 导入 `AssistantMessage` 和 `TextBlock`
- [ ] 修改 `_call_skill_async` 方法提取 AI 响应
- [ ] 修改返回值结构为字典
- [ ] 更新类型注解

### Step 2: 修改 `app.py`
- [ ] 更新 `render_extract_check_stage()` 展示 AI 响应
- [ ] 更新 `render_filling_stage()` 展示 AI 响应
- [ ] 测试 UI 展示效果

### Step 3: 更新测试
- [ ] 修改单元测试验证新返回值结构
- [ ] 修改集成测试验证 AI 响应提取
- [ ] 运行所有测试确保通过

### Step 4: 更新文档
- [ ] 更新 `CLAUDE.md` 的 Skill 调用说明
- [ ] 添加返回值结构说明
- [ ] 添加使用示例

### Step 5: 验证和测试
- [ ] 运行单元测试
- [ ] 运行集成测试（需要 API key）
- [ ] 启动 Streamlit 应用进行端到端测试
- [ ] 验证 AI 响应在前端正确展示

---

## 验收标准

1. **功能完整性：**
   - ✅ `call_skill` 返回包含 `ai_responses` 的字典
   - ✅ 只提取 `AssistantMessage` 的 `TextBlock` 内容
   - ✅ Streamlit 前端能展示 AI 响应内容

2. **代码质量：**
   - ✅ 所有单元测试通过
   - ✅ 类型注解正确
   - ✅ 代码可读性良好

3. **用户体验：**
   - ✅ AI 响应以折叠面板形式展示
   - ✅ 不影响原有功能流程
   - ✅ 提供"查看 AI 分析过程"入口

4. **文档完整性：**
   - ✅ CLAUDE.md 更新了返回值说明
   - ✅ 提供了使用示例

---

## 注意事项

1. **类型导入：** 确保从 `claude_agent_sdk` 正确导入 `AssistantMessage` 和 `TextBlock`

2. **错误处理：** 如果 message 类型不是预期的，应有合理的降级处理

3. **性能：** AI 响应可能较长，使用折叠面板避免占用过多屏幕空间

4. **调试信息：** 保留 `all_messages` 字段用于调试，但不在前端默认展示

---

## 回滚计划

如果出现问题，可以快速回滚：

```bash
# 查看最近的提交
git log --oneline -5

# 回滚到修改前
git revert <commit-hash>
```

或者保留旧版本作为备份：
```bash
cp core/skill_caller.py core/skill_caller.backup.py
```

---

**预计实施时间：** 1-2 小时
**风险等级：** 低（主要是展示逻辑修改，核心功能不变）
