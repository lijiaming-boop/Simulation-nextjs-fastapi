# AI 分析日志流式侧边栏设计方案

## 目标

将现有的"查看AI分析过程"从折叠区域改为实时流式的侧边栏日志面板，提升用户体验。

## 设计决策总结

| 维度 | 选择 | 理由 |
|------|------|------|
| **布局** | 侧边栏 (st.sidebar) | 固定位置，不占用主界面空间 |
| **流式方式** | 回调函数 | 真正的实时流式显示 |
| **用户体验** | 完全阻塞 | 主界面显示 spinner，侧边栏实时更新，实现简单可靠 |
| **显示风格** | 日志流（带时间戳） | 简洁清晰，类似终端输出 |
| **消息粒度** | 仅 AI 文本回复 | 信息精炼，用户易读 |
| **完成后处理** | 保持显示 + 手动关闭 | 用户可以回看分析过程 |

---

## 架构设计

### 整体架构

```
用户点击按钮
    ↓
app.py 调用 SkillCaller.call_skill(callback=update_log)
    ↓
SkillCaller._call_skill_async() 执行异步查询
    ↓
每次收到 AssistantMessage
    → 调用 callback(timestamp, message)
    → callback 更新 st.session_state.ai_logs
    → callback 更新侧边栏 st.text_area
    ↓
分析完成，返回结果
    ↓
主界面跳转到下一阶段
侧边栏保持日志显示
```

### 关键技术约束

**Streamlit 的同步限制**：
- Streamlit 不支持真正的异步 UI 更新
- 在同一个请求周期内，UI 只会在脚本执行完后才重新渲染
- 解决方案：使用 `st.empty()` 容器 + `asyncio.sleep(0.01)` 给 Streamlit 重绘机会
- 实际效果：**分段更新**（每次 AssistantMessage 更新一次），而非逐字流式

---

## 实现细节

### 1. SkillCaller 增加回调支持

**文件**：`core/skill_caller.py`

**修改点 1：同步接口增加 callback 参数**

```python
def call_skill(
    self,
    skill_name: str,
    *args,
    check_output: bool = True,
    callback: Optional[Callable[[str, str], None]] = None  # 新增
) -> Dict[str, Any]:
    """调用 Claude Skill(同步包装器)

    Args:
        skill_name: Skill 名称
        *args: Skill 参数
        check_output: 是否检查输出文件
        callback: 回调函数 callback(timestamp, message)，每次 AI 回复时调用
    """
    # ...
    return loop.run_until_complete(
        self._call_skill_async(skill_name, *args, check_output=check_output, callback=callback)
    )
```

**修改点 2：异步实现调用回调函数**

```python
async def _call_skill_async(
    self,
    skill_name: str,
    *args,
    check_output: bool = True,
    callback: Optional[Callable[[str, str], None]] = None  # 新增
) -> Dict[str, Any]:
    """调用 Claude Skill(异步实现)

    Args:
        callback: 回调函数，每次收到 AI 回复时调用
    """
    all_messages = []
    ai_responses = []

    try:
        async with asyncio.timeout(self.timeout):
            async for message in query(prompt=prompt, options=options):
                all_messages.append(str(message))

                # 只提取 AssistantMessage 的文本内容
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            # 打印到 console
                            print(f"[AI Response] {block.text}")
                            ai_responses.append(block.text)

                            # 调用回调函数（新增）
                            if callback:
                                timestamp = datetime.now().strftime("%H:%M:%S")
                                callback(timestamp, block.text)

                            # 等待一小段时间让 Streamlit 有机会重绘
                            await asyncio.sleep(0.01)

    except asyncio.TimeoutError as e:
        # 错误时也调用回调
        if callback:
            timestamp = datetime.now().strftime("%H:%M:%S")
            callback(timestamp, f"❌ 执行超时（>{self.timeout}秒）")
        raise SkillError(...)

    except Exception as e:
        # 错误时也调用回调
        if callback:
            timestamp = datetime.now().strftime("%H:%M:%S")
            callback(timestamp, f"❌ 执行出错: {str(e)}")
        raise SkillError(...)

    # ... 后续代码不变
```

**需要导入的模块**：

```python
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable  # 新增 Callable
```

---

### 2. app.py 侧边栏日志面板

**修改点 1：初始化 session_state**

```python
def init_session_state():
    """初始化 session state"""
    if "stage" not in st.session_state:
        st.session_state.stage = "upload"
    # ... 其他初始化

    # 新增：AI 日志列表
    if "ai_logs" not in st.session_state:
        st.session_state.ai_logs = []
```

**修改点 2：侧边栏渲染函数**

```python
def render_sidebar():
    """渲染侧边栏的 AI 日志面板"""
    with st.sidebar:
        st.markdown("### 🤖 AI 分析日志")

        # 显示日志
        if st.session_state.ai_logs:
            log_text = "\n".join(st.session_state.ai_logs)

            st.text_area(
                label="",
                value=log_text,
                height=500,  # 固定高度，可滚动
                disabled=True,
                label_visibility="collapsed"
            )

            # 清空按钮
            if st.button("🗑️ 清空日志"):
                st.session_state.ai_logs = []
                st.rerun()
        else:
            st.info("暂无 AI 分析日志")
```

**修改点 3：日志更新辅助函数**

```python
def update_log(timestamp: str, message: str):
    """更新 AI 日志

    Args:
        timestamp: 时间戳 (HH:MM:SS)
        message: 日志消息
    """
    if 'ai_logs' not in st.session_state:
        st.session_state.ai_logs = []

    formatted_msg = f"[{timestamp}] {message}"
    st.session_state.ai_logs.append(formatted_msg)

    # 限制日志条数，防止内存溢出
    MAX_LOG_LINES = 500
    if len(st.session_state.ai_logs) > MAX_LOG_LINES:
        st.session_state.ai_logs = st.session_state.ai_logs[-MAX_LOG_LINES:]


def start_new_skill_log(skill_name: str):
    """开始新的 Skill 调用日志

    Args:
        skill_name: Skill 名称
    """
    if 'ai_logs' not in st.session_state:
        st.session_state.ai_logs = []

    # 添加分隔线
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.ai_logs.append("")
    st.session_state.ai_logs.append("=" * 50)
    st.session_state.ai_logs.append(f"[{timestamp}] 开始执行: {skill_name}")
    st.session_state.ai_logs.append("=" * 50)
```

**修改点 4：main() 函数调用侧边栏**

```python
def main():
    st.set_page_config(page_title="中央空调节能率智能测算", layout="wide")

    # 渲染侧边栏（在主界面之前）
    render_sidebar()

    # 初始化 session state
    init_session_state()

    # 渲染主界面
    # ...
```

**修改点 5：各阶段调用 Skill 时传入 callback**

**示例：提取+质量检查阶段**

```python
def render_stage_extract_check():
    # ...

    if st.button("🚀 开始提取", type="primary"):
        with st.spinner("正在分析调研表，请稍候..."):
            # 开始新的日志
            start_new_skill_log("extract-and-check-data")

            try:
                # 调用 skill，传入回调
                result = caller.call_skill(
                    "extract-and-check-data",
                    input_path,
                    output_path,
                    original_filename,
                    callback=update_log  # 传入回调函数
                )

                # 成功后记录
                update_log(
                    datetime.now().strftime("%H:%M:%S"),
                    "✅ 数据提取完成"
                )

                # 保存结果，跳转到下一阶段
                st.session_state.extract_result = result
                st.session_state.stage = "filling"
                st.rerun()

            except Exception as e:
                # 错误已在 callback 中记录
                update_log(
                    datetime.now().strftime("%H:%M:%S"),
                    f"❌ 执行失败: {str(e)}"
                )
                st.error(f"执行失败: {str(e)}")
```

**需要修改的所有 Skill 调用点**：
1. `render_stage_extract_check()` - extract-and-check-data
2. `render_stage_filling()` - suggest-data-filling

**需要导入的模块**：

```python
from datetime import datetime
```

---

### 3. 移除旧的 expander 显示方式

**需要删除的代码**（在 `render_stage_extract_check()` 和 `render_stage_filling()` 中）：

```python
# 删除这段代码
if skill_result.get("ai_responses"):
    with st.expander("🤖 查看 AI 分析过程", expanded=False):
        for idx, response in enumerate(skill_result["ai_responses"], 1):
            st.markdown(f"**步骤 {idx}:**")
            st.text(response)
            st.markdown("---")
```

**原因**：AI 分析过程已经通过侧边栏实时显示，不需要在主界面重复展示。

---

## 完整的交互流程

```
用户操作                 主界面                    侧边栏
─────────────────────────────────────────────────────────────────
点击"开始提取"  →   显示 spinner           [10:23:15] ================================
                  "正在分析调研表..."      [10:23:15] 开始执行: extract-and-check-data
                                          [10:23:15] ================================

                   spinner 旋转中...       [10:23:16] 正在读取调研表...
                                          [10:23:18] 已读取"冷站"sheet，发现2台冷机

                   spinner 旋转中...       [10:23:22] 提取到项目地区：华南
                                          [10:23:25] 月度数据完整率：75%

提取完成         →   跳转到"填充建议"       [10:23:28] ✅ 数据提取完成
                   阶段，spinner 消失
                   显示提取结果

用户查看结果          显示数据质量报告        （日志保持显示，可回看）

点击"清空日志"  →   （无变化）             （日志清空，显示"暂无 AI 分析日志"）

点击"生成建议"  →   显示 spinner           [10:24:01]
                                          [10:24:01] ================================
                                          [10:24:01] 开始执行: suggest-data-filling
                                          [10:24:01] ================================
                                          [10:24:02] 正在分析数据质量报告...
                                          ...（新的日志继续追加）
```

---

## 需要修改的文件清单

### 1. core/skill_caller.py
- ✅ `call_skill()` 增加 `callback` 参数
- ✅ `_call_skill_async()` 在收到 AssistantMessage 时调用 callback
- ✅ 异常处理时也调用 callback 记录错误
- ✅ 导入 `datetime` 和 `Callable`

### 2. app.py
- ✅ `init_session_state()` 初始化 `ai_logs = []`
- ✅ 新增 `render_sidebar()` 函数
- ✅ 新增 `update_log()` 函数
- ✅ 新增 `start_new_skill_log()` 函数
- ✅ `main()` 开头调用 `render_sidebar()`
- ✅ `render_stage_extract_check()` 修改 Skill 调用，传入 callback
- ✅ `render_stage_filling()` 修改 Skill 调用，传入 callback
- ✅ 删除旧的 expander 显示代码
- ✅ 导入 `datetime`

### 3. CLAUDE.md
- ✅ 更新架构说明，描述新的日志流显示机制

---

## 测试计划

### 单元测试
- `test_skill_caller_with_callback.py` - 测试 SkillCaller 的回调机制
  - 验证每次 AssistantMessage 都调用 callback
  - 验证 callback 参数正确（timestamp, message）
  - 验证异常时也调用 callback

### 集成测试
无需新增测试（Streamlit UI 测试通过手动测试验证）

### 手动测试清单
1. ✅ 上传调研表，点击"开始提取"
   - 验证侧边栏实时显示 AI 日志
   - 验证主界面显示 spinner
   - 验证完成后跳转到下一阶段，日志保持显示
2. ✅ 点击"生成填充建议"
   - 验证新的日志追加显示（有分隔线）
   - 验证日志可以滚动查看
3. ✅ 点击"清空日志"
   - 验证日志清空，显示"暂无日志"
4. ✅ 测试错误场景（如上传错误格式的文件）
   - 验证侧边栏显示错误消息（带 ❌）

---

## 未来优化方向

### 1. 日志导出功能
允许用户下载完整的 AI 分析日志（TXT 或 JSON 格式）

### 2. 日志过滤
按级别过滤（信息/成功/错误）

### 3. 真正的流式显示
探索使用 Streamlit Components 或 WebSocket 实现逐字流式显示

### 4. 日志持久化
将日志保存到 session 目录，允许用户查看历史分析记录

---

## 参考资料

- Streamlit 文档：https://docs.streamlit.io/
- Claude Agent SDK：https://github.com/anthropics/claude-agent-sdk
- Python asyncio：https://docs.python.org/3/library/asyncio.html
