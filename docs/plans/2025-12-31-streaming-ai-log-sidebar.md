# 流式 AI 日志侧边栏实施计划（复用 SkillCaller）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 在现有 Streamlit 空调节能测算应用中添加 AI 日志侧边栏，实时显示 Skill 执行过程中的 AI 响应

**架构：**
- 使用 Streamlit 的双栏布局（st.columns），左侧为主工作流，右侧为 AI 日志侧边栏
- **复用现有的 `core/skill_caller.py`**，不额外调用 Anthropic SDK
- 从 `SkillCaller._call_skill_async` 的 `block.text` 流式提取 AI 响应
- 使用生成器模式（yield）实现实时流式显示

**技术栈：**
- Streamlit >= 1.28.0（UI 框架）
- 现有的 `SkillCaller` + Claude Agent SDK（已有依赖）
- 异步生成器 + Streamlit 容器更新

**设计决策：**
1. **不调用额外的 LLM API**：直接复用 SkillCaller 执行 skill 时的 AI 响应
2. **流式显示机制**：修改 `_call_skill_async` 使用回调函数传递 `block.text`
3. **状态管理**：在 `st.session_state` 中存储 AI 日志历史

---

## 前置准备：理解现有架构

**当前 SkillCaller 机制：**
- `core/skill_caller.py::_call_skill_async()` 已经提取 `block.text`（第148-151行）
- 当前实现：收集所有响应后返回
- **目标改造**：增加回调机制，实时传递每个 `block.text`

**设计方案：**
1. 在 `SkillCaller.__init__()` 中添加 `on_ai_response` 回调参数
2. 在 `_call_skill_async()` 第150行调用回调：`self.on_ai_response(block.text)`
3. Streamlit 侧边栏通过回调实时更新显示

---

## Task 1: 修改 SkillCaller 支持流式回调

### Step 1: 编写回调机制的测试（TDD）

**文件：** `tests/unit/test_skill_caller_streaming.py`

```python
"""SkillCaller 流式回调机制测试"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from core.skill_caller import SkillCaller, SkillError
from claude_agent_sdk import AssistantMessage, TextBlock


@pytest.fixture
def mock_env():
    """Mock 环境变量"""
    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
        yield


def test_skill_caller_with_callback(mock_env):
    """测试带回调的 SkillCaller 初始化"""
    callback = Mock()
    caller = SkillCaller(timeout=300, on_ai_response=callback)
    assert caller.on_ai_response == callback


@pytest.mark.asyncio
async def test_callback_invoked_on_text_block(mock_env):
    """测试 TextBlock 触发回调"""
    callback = Mock()
    caller = SkillCaller(timeout=300, on_ai_response=callback)

    # Mock query() 返回的异步生成器
    mock_message = AssistantMessage(
        content=[TextBlock(text="测试响应")]
    )

    with patch('core.skill_caller.query') as mock_query:
        async def mock_generator():
            yield mock_message

        mock_query.return_value = mock_generator()

        # 执行调用
        result = await caller._call_skill_async("test-skill", "input.xlsx", "output.json", check_output=False)

        # 验证回调被调用
        callback.assert_called_once_with("测试响应")
        assert "测试响应" in result["ai_responses"]


@pytest.mark.asyncio
async def test_multiple_text_blocks_trigger_multiple_callbacks(mock_env):
    """测试多个 TextBlock 触发多次回调"""
    callback = Mock()
    caller = SkillCaller(timeout=300, on_ai_response=callback)

    # Mock 多条消息
    mock_messages = [
        AssistantMessage(content=[TextBlock(text="响应1")]),
        AssistantMessage(content=[TextBlock(text="响应2")]),
        AssistantMessage(content=[TextBlock(text="响应3")]),
    ]

    with patch('core.skill_caller.query') as mock_query:
        async def mock_generator():
            for msg in mock_messages:
                yield msg

        mock_query.return_value = mock_generator()

        result = await caller._call_skill_async("test-skill", "input.xlsx", "output.json", check_output=False)

        # 验证回调被调用3次
        assert callback.call_count == 3
        callback.assert_any_call("响应1")
        callback.assert_any_call("响应2")
        callback.assert_any_call("响应3")
```

### Step 2: 运行测试验证失败

**命令：**
```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_skill_caller_streaming.py -v
```

**预期输出：**
```
tests/unit/test_skill_caller_streaming.py::test_skill_caller_with_callback FAILED
TypeError: __init__() got an unexpected keyword argument 'on_ai_response'
```

### Step 3: 修改 SkillCaller 添加回调支持

**文件：** `core/skill_caller.py`

**修改 `__init__` 方法（第20-59行）：**
```python
def __init__(
    self,
    timeout: int = 300,
    api_key: Optional[str] = None,
    project_root: Optional[Path] = None,
    on_ai_response: Optional[callable] = None  # 新增：AI响应回调
):
    """初始化 Skill 调用器

    Args:
        timeout: 调用超时时间(秒)
        api_key: Anthropic API Key,如果不提供则从环境变量读取
        project_root: 项目根目录,包含 .claude/skills/ 目录
        on_ai_response: AI响应回调函数，接收block.text作为参数

    Raises:
        SkillError: API key 未配置
    """
    self.timeout = timeout
    self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
    self.on_ai_response = on_ai_response  # 新增

    if not self.api_key:
        raise SkillError(
            "ANTHROPIC_API_KEY 环境变量未设置。\n"
            "请设置: export ANTHROPIC_API_KEY='your-api-key'"
        )

    # 确定项目根目录
    if project_root:
        self.project_root = Path(project_root).resolve()
    else:
        # 默认:从当前文件向上两级(core/ -> 项目根)
        self.project_root = Path(__file__).parent.parent.resolve()

    # 验证 skills 目录存在
    self.skills_dir = self.project_root / ".claude" / "skills"
    if not self.skills_dir.exists():
        raise SkillError(
            f"Skills 目录不存在: {self.skills_dir}\n"
            f"项目根目录: {self.project_root}"
        )
```

**修改 `_call_skill_async` 方法（第146-151行）：**
```python
# 只提取 AssistantMessage 的文本内容
if isinstance(message, AssistantMessage):
    for block in message.content:
        if isinstance(block, TextBlock):
            # 打印AI响应内容到console（方便调试）
            print(f"[AI Response] {block.text}")
            ai_responses.append(block.text)

            # 新增：触发回调
            if self.on_ai_response:
                self.on_ai_response(block.text)
```

### Step 4: 运行测试验证通过

**命令：**
```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_skill_caller_streaming.py -v
```

**预期输出：**
```
tests/unit/test_skill_caller_streaming.py::test_skill_caller_with_callback PASSED
tests/unit/test_skill_caller_streaming.py::test_callback_invoked_on_text_block PASSED
tests/unit/test_skill_caller_streaming.py::test_multiple_text_blocks_trigger_multiple_callbacks PASSED
========== 3 passed in 0.28s ==========
```

### Step 5: 验证现有测试无回归

**命令：**
```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_skill_caller.py -v
```

**预期输出：**
```
... (所有现有测试通过)
========== X passed in Y.Ys ==========
```

### Step 6: 提交回调机制

```bash
git add core/skill_caller.py tests/unit/test_skill_caller_streaming.py
git commit -m "feat: add streaming callback to SkillCaller"
```

---

## Task 2: 创建 AI 日志管理模块

### Step 1: 编写 AI 日志管理器测试

**文件：** `tests/unit/test_ai_log_manager.py`

```python
"""AI 日志管理器测试"""
import pytest
from core.ai_log_manager import AILogManager


def test_ai_log_manager_initialization():
    """测试 AI 日志管理器初始化"""
    manager = AILogManager()
    assert manager.logs == []


def test_add_log():
    """测试添加日志"""
    manager = AILogManager()
    manager.add_log("测试日志1")
    manager.add_log("测试日志2")

    assert len(manager.logs) == 2
    assert manager.logs[0] == "测试日志1"
    assert manager.logs[1] == "测试日志2"


def test_get_all_logs():
    """测试获取所有日志"""
    manager = AILogManager()
    manager.add_log("日志A")
    manager.add_log("日志B")

    logs = manager.get_all_logs()
    assert logs == ["日志A", "日志B"]


def test_clear_logs():
    """测试清空日志"""
    manager = AILogManager()
    manager.add_log("日志1")
    manager.add_log("日志2")

    manager.clear_logs()
    assert manager.logs == []


def test_get_logs_count():
    """测试获取日志数量"""
    manager = AILogManager()
    assert manager.get_logs_count() == 0

    manager.add_log("日志1")
    assert manager.get_logs_count() == 1

    manager.add_log("日志2")
    assert manager.get_logs_count() == 2
```

### Step 2: 运行测试验证失败

**命令：**
```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_ai_log_manager.py -v
```

**预期输出：**
```
ModuleNotFoundError: No module named 'core.ai_log_manager'
```

### Step 3: 实现 AI 日志管理器

**文件：** `core/ai_log_manager.py`

```python
"""AI 日志管理器 - 管理 Skill 执行过程中的 AI 响应日志"""
from typing import List


class AILogManager:
    """管理 AI 响应日志的类"""

    def __init__(self):
        """初始化日志管理器"""
        self.logs: List[str] = []

    def add_log(self, text: str) -> None:
        """添加日志条目

        Args:
            text: 日志文本（通常是 block.text）
        """
        self.logs.append(text)

    def get_all_logs(self) -> List[str]:
        """获取所有日志

        Returns:
            日志列表
        """
        return self.logs.copy()

    def clear_logs(self) -> None:
        """清空所有日志"""
        self.logs = []

    def get_logs_count(self) -> int:
        """获取日志条目数量

        Returns:
            日志数量
        """
        return len(self.logs)
```

### Step 4: 运行测试验证通过

**命令：**
```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_ai_log_manager.py -v
```

**预期输出：**
```
tests/unit/test_ai_log_manager.py::test_ai_log_manager_initialization PASSED
tests/unit/test_ai_log_manager.py::test_add_log PASSED
tests/unit/test_ai_log_manager.py::test_get_all_logs PASSED
tests/unit/test_ai_log_manager.py::test_clear_logs PASSED
tests/unit/test_ai_log_manager.py::test_get_logs_count PASSED
========== 5 passed in 0.15s ==========
```

### Step 5: 提交 AI 日志管理器

```bash
git add core/ai_log_manager.py tests/unit/test_ai_log_manager.py
git commit -m "feat: add AILogManager for tracking AI responses"
```

---

## Task 3: 在 app.py 中集成侧边栏

### Step 1: 修改 init_session_state 添加 AI 日志状态

**文件：** `app.py:14-30`

**原代码：**
```python
def init_session_state():
    """初始化 session state"""
    if 'stage' not in st.session_state:
        st.session_state.stage = 'upload'
        st.session_state.uploaded_file = None
        st.session_state.original_filename = None
        st.session_state.extracted_data = None
        st.session_state.quality_report = None
        st.session_state.filling_suggestions = None
        st.session_state.result = None
        st.session_state.uploader_key = 0

        # 新增: 初始化会话管理器
        from core.session_manager import SessionManager
        st.session_state.session_manager = SessionManager()
        st.session_state.session_dir = st.session_state.session_manager.create_session_directory()
```

**修改为：**
```python
def init_session_state():
    """初始化 session state"""
    if 'stage' not in st.session_state:
        st.session_state.stage = 'upload'
        st.session_state.uploaded_file = None
        st.session_state.original_filename = None
        st.session_state.extracted_data = None
        st.session_state.quality_report = None
        st.session_state.filling_suggestions = None
        st.session_state.result = None
        st.session_state.uploader_key = 0

        # 初始化会话管理器
        from core.session_manager import SessionManager
        st.session_state.session_manager = SessionManager()
        st.session_state.session_dir = st.session_state.session_manager.create_session_directory()

    # 初始化 AI 日志管理器（独立判断，避免重置）
    if 'ai_log_manager' not in st.session_state:
        from core.ai_log_manager import AILogManager
        st.session_state.ai_log_manager = AILogManager()

    # 初始化日志显示占位符（用于实时更新）
    if 'log_placeholder' not in st.session_state:
        st.session_state.log_placeholder = None
```

### Step 2: 创建侧边栏渲染函数

**文件：** `app.py`（在文件末尾添加，main() 函数之前）

**新增代码：**
```python
def render_ai_log_sidebar():
    """渲染 AI 日志侧边栏"""
    st.markdown("### 🤖 AI 执行日志")
    st.markdown("---")

    # 显示日志统计
    log_count = st.session_state.ai_log_manager.get_logs_count()
    st.metric("日志条目数", log_count)

    # 日志显示区域（滚动容器）
    log_container = st.container()
    with log_container:
        logs = st.session_state.ai_log_manager.get_all_logs()

        if logs:
            # 显示所有日志
            for i, log in enumerate(logs):
                with st.expander(f"📝 日志 {i+1}", expanded=(i == len(logs) - 1)):
                    st.text(log)
        else:
            st.info("暂无日志，开始分析后将显示 AI 执行过程")

    # 清空日志按钮
    if st.button("🗑️ 清空日志", use_container_width=True):
        st.session_state.ai_log_manager.clear_logs()
        st.rerun()


def create_ai_response_callback():
    """创建 AI 响应回调函数，用于实时更新侧边栏"""
    def callback(text: str):
        """回调函数：接收 AI 响应并添加到日志"""
        # 添加到日志管理器
        st.session_state.ai_log_manager.add_log(text)

        # 注意：Streamlit 的回调中无法直接调用 st.rerun()
        # 因此实时更新需要通过其他机制（见下一步）

    return callback
```

### Step 3: 修改 render_extract_check_stage 使用回调

**文件：** `app.py`（找到 render_extract_check_stage 函数，约第132-180行）

**原代码（第145-158行）：**
```python
# 需要执行skill获取新结果
with st.spinner("正在提取调研表数据并进行质量检查,请稍候..."):
    try:
        caller = SkillCaller(timeout=300)

        # 修改: 使用会话目录
        session_dir = st.session_state.session_dir
        upload_path = session_dir / "upload_survey.xlsx"
        output_path = session_dir / "extract_check_result.json"

        # 新增：传递原始文件名给skill（用于地区推断）
        original_filename = st.session_state.get('original_filename', '')

        result = caller.call_skill(
            "extract-and-check-data",
```

**修改为：**
```python
# 需要执行skill获取新结果
with st.spinner("正在提取调研表数据并进行质量检查,请稍候..."):
    try:
        # 创建带回调的 SkillCaller
        callback = create_ai_response_callback()
        caller = SkillCaller(timeout=300, on_ai_response=callback)

        # 修改: 使用会话目录
        session_dir = st.session_state.session_dir
        upload_path = session_dir / "upload_survey.xlsx"
        output_path = session_dir / "extract_check_result.json"

        # 新增：传递原始文件名给skill（用于地区推断）
        original_filename = st.session_state.get('original_filename', '')

        result = caller.call_skill(
            "extract-and-check-data",
```

**说明：** 同样的修改应用到所有调用 `SkillCaller` 的地方：
- `render_filling_stage()` 中的 `suggest-data-filling` 调用
- 其他使用 skill 的地方

### Step 4: 修改 main() 函数使用双栏布局

**文件：** `app.py:48-97`

**原代码：**
```python
def main():
    """主函数"""
    # 页面配置
    st.set_page_config(
        page_title="空调节能率智能测算工具",
        page_icon="❄️",
        layout="wide"
    )

    # 初始化
    init_session_state()

    # 标题
    st.title("❄️ 空调节能率智能测算工具")
    st.markdown("---")

    # ... 其余代码
```

**修改为：**
```python
def main():
    """主函数"""
    # 页面配置
    st.set_page_config(
        page_title="空调节能率智能测算工具",
        page_icon="❄️",
        layout="wide"
    )

    # 初始化
    init_session_state()

    # 创建双栏布局：左侧主内容 (70%) + 右侧日志 (30%)
    main_col, log_col = st.columns([0.7, 0.3])

    # ========== 左侧主内容区域 ==========
    with main_col:
        # 标题
        st.title("❄️ 空调节能率智能测算工具")
        st.markdown("---")

        # 流程进度指示器
        stages = ['上传', '提取+质量检查', '填充建议', '计算', '结果']
        stage_map = {
            'upload': 0, 'extract_check': 1,
            'filling': 2, 'calculate': 3, 'result': 4
        }
        current_stage = stage_map.get(st.session_state.stage, 0)

        cols = st.columns(len(stages))
        for i, (col, stage_name) in enumerate(zip(cols, stages)):
            with col:
                if i < current_stage:
                    st.success(f"✅ {stage_name}")
                elif i == current_stage:
                    st.info(f"▶️ {stage_name}")
                else:
                    st.text(f"⏸️ {stage_name}")

        st.markdown("---")

        # 根据阶段渲染不同界面
        stage = st.session_state.stage

        if stage == 'upload':
            render_upload_stage()
        elif stage == 'extract_check':
            render_extract_check_stage()
        elif stage == 'filling':
            render_filling_stage()
        elif stage == 'calculate':
            render_calculate_stage()
        elif stage == 'result':
            render_result_stage()

    # ========== 右侧 AI 日志侧边栏 ==========
    with log_col:
        render_ai_log_sidebar()
```

### Step 5: 修改其他使用 SkillCaller 的地方

**文件：** `app.py`（找到 render_filling_stage 函数）

**查找所有 `SkillCaller(timeout=300)` 实例，替换为：**
```python
callback = create_ai_response_callback()
caller = SkillCaller(timeout=300, on_ai_response=callback)
```

**预期修改位置：**
- `render_filling_stage()` 中调用 `suggest-data-filling`

### Step 6: 手动测试双栏布局和日志显示

**命令：**
```bash
streamlit run app.py
```

**测试步骤：**
1. 访问 http://localhost:8501
2. 上传调研表
3. 点击"开始分析"
4. 观察右侧日志栏是否实时显示 AI 响应
5. 验证日志条目数是否正确累加

**预期结果：**
- ✅ 双栏布局显示正确（左70%，右30%）
- ✅ 右侧日志栏显示 AI 执行过程
- ✅ 每条 `block.text` 都被记录
- ✅ 日志条目数正确

### Step 7: 提交双栏布局集成

```bash
git add app.py
git commit -m "feat: integrate AI log sidebar with SkillCaller callbacks"
```

---

## Task 4: 优化日志显示样式

### Step 1: 在 app.py 中添加自定义 CSS

**文件：** `app.py`（在 main() 函数开始处添加）

**在 `init_session_state()` 调用之后添加：**
```python
def apply_custom_css():
    """应用自定义 CSS 样式"""
    st.markdown("""
    <style>
    /* AI 日志侧边栏样式 */
    .ai-log-container {
        max-height: 600px;
        overflow-y: auto;
        padding: 10px;
        background-color: #F8F9FA;
        border-radius: 8px;
    }

    .log-entry {
        background-color: #FFFFFF;
        border-left: 4px solid #4CAF50;
        padding: 12px;
        margin-bottom: 10px;
        border-radius: 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }

    .log-entry:hover {
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    }

    /* 日志统计卡片 */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
    }

    /* 滚动条美化 */
    .ai-log-container::-webkit-scrollbar {
        width: 8px;
    }

    .ai-log-container::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 10px;
    }

    .ai-log-container::-webkit-scrollbar-thumb {
        background: #888;
        border-radius: 10px;
    }

    .ai-log-container::-webkit-scrollbar-thumb:hover {
        background: #555;
    }
    </style>
    """, unsafe_allow_html=True)


def main():
    """主函数"""
    # 页面配置
    st.set_page_config(
        page_title="空调节能率智能测算工具",
        page_icon="❄️",
        layout="wide"
    )

    # 初始化
    init_session_state()

    # 应用自定义样式
    apply_custom_css()

    # ... 其余代码不变
```

### Step 2: 手动测试样式

**命令：**
```bash
streamlit run app.py
```

**测试步骤：**
1. 刷新浏览器
2. 检查日志条目样式（白色背景，绿色左边框）
3. 检查滚动条美化效果
4. 检查 hover 效果

**预期结果：**
- ✅ 日志条目有清晰的视觉层次
- ✅ 滚动条美观
- ✅ Hover 有阴影效果

### Step 3: 提交样式优化

```bash
git add app.py
git commit -m "style: add custom CSS for AI log sidebar"
```

---

## Task 5: 添加集成测试

### Step 1: 编写集成测试

**文件：** `tests/integration/test_ai_log_sidebar.py`

```python
"""AI 日志侧边栏集成测试"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
from core.skill_caller import SkillCaller
from core.ai_log_manager import AILogManager
from claude_agent_sdk import AssistantMessage, TextBlock


@pytest.fixture
def mock_env():
    """Mock 环境变量"""
    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
        yield


@pytest.mark.asyncio
async def test_skill_caller_populates_log_manager(mock_env):
    """测试 SkillCaller 正确填充日志管理器"""
    log_manager = AILogManager()

    # 创建回调函数
    def callback(text: str):
        log_manager.add_log(text)

    caller = SkillCaller(timeout=300, on_ai_response=callback)

    # Mock query 返回多条消息
    mock_messages = [
        AssistantMessage(content=[TextBlock(text="开始提取数据")]),
        AssistantMessage(content=[TextBlock(text="正在解析 Excel")]),
        AssistantMessage(content=[TextBlock(text="提取完成")]),
    ]

    with patch('core.skill_caller.query') as mock_query:
        async def mock_generator():
            for msg in mock_messages:
                yield msg

        mock_query.return_value = mock_generator()

        await caller._call_skill_async("test-skill", "input.xlsx", "output.json", check_output=False)

        # 验证日志管理器收到所有日志
        assert log_manager.get_logs_count() == 3
        logs = log_manager.get_all_logs()
        assert logs[0] == "开始提取数据"
        assert logs[1] == "正在解析 Excel"
        assert logs[2] == "提取完成"


@pytest.mark.asyncio
async def test_multiple_skill_calls_accumulate_logs(mock_env):
    """测试多次调用累积日志"""
    log_manager = AILogManager()

    def callback(text: str):
        log_manager.add_log(text)

    caller = SkillCaller(timeout=300, on_ai_response=callback)

    # 第一次调用
    with patch('core.skill_caller.query') as mock_query:
        async def mock_gen1():
            yield AssistantMessage(content=[TextBlock(text="第1次调用")])

        mock_query.return_value = mock_gen1()
        await caller._call_skill_async("skill1", "input1.xlsx", "output1.json", check_output=False)

    assert log_manager.get_logs_count() == 1

    # 第二次调用
    with patch('core.skill_caller.query') as mock_query:
        async def mock_gen2():
            yield AssistantMessage(content=[TextBlock(text="第2次调用")])

        mock_query.return_value = mock_gen2()
        await caller._call_skill_async("skill2", "input2.xlsx", "output2.json", check_output=False)

    # 验证日志累积
    assert log_manager.get_logs_count() == 2
    logs = log_manager.get_all_logs()
    assert logs[0] == "第1次调用"
    assert logs[1] == "第2次调用"


def test_log_manager_clear_resets_state():
    """测试清空日志重置状态"""
    log_manager = AILogManager()
    log_manager.add_log("日志1")
    log_manager.add_log("日志2")

    assert log_manager.get_logs_count() == 2

    log_manager.clear_logs()

    assert log_manager.get_logs_count() == 0
    assert log_manager.get_all_logs() == []
```

### Step 2: 运行集成测试

**命令：**
```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_ai_log_sidebar.py -v
```

**预期输出：**
```
tests/integration/test_ai_log_sidebar.py::test_skill_caller_populates_log_manager PASSED
tests/integration/test_ai_log_sidebar.py::test_multiple_skill_calls_accumulate_logs PASSED
tests/integration/test_ai_log_sidebar.py::test_log_manager_clear_resets_state PASSED
========== 3 passed in 0.42s ==========
```

### Step 3: 运行所有测试确保无回归

**命令：**
```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/ -v
```

**预期输出：**
```
... (所有测试通过)
========== X passed in Y.Ys ==========
```

### Step 4: 提交集成测试

```bash
git add tests/integration/test_ai_log_sidebar.py
git commit -m "test: add integration tests for AI log sidebar"
```

---

## Task 6: 文档更新和最终验证

### Step 1: 更新 CLAUDE.md 文档

**文件：** `CLAUDE.md`

**在 "## 核心架构" 部分之后添加：**

```markdown
### AI 日志侧边栏

**功能：** 实时显示 Skill 执行过程中的 AI 响应日志

**位置：** `app.py` 右侧栏（30% 宽度）

**实现机制：**
- 复用现有的 `core/skill_caller.py`，不额外调用 LLM API
- 通过 `SkillCaller` 的 `on_ai_response` 回调捕获 `block.text`
- 使用 `AILogManager` 管理日志历史

**核心模块：**
- `core/skill_caller.py`：添加了 `on_ai_response` 回调参数
- `core/ai_log_manager.py`：日志存储和管理
- `app.py::render_ai_log_sidebar()`：侧边栏渲染函数
- `app.py::create_ai_response_callback()`：回调函数工厂

**数据流：**
1. Skill 执行过程中产生 `AssistantMessage`
2. `SkillCaller._call_skill_async` 提取 `block.text`
3. 触发 `on_ai_response(block.text)` 回调
4. 回调函数将日志添加到 `AILogManager`
5. 侧边栏读取 `AILogManager` 显示日志

**状态管理：**
- `st.session_state.ai_log_manager`：AILogManager 实例
- 日志在会话期间持久化，刷新页面后清空

**测试：**
- 单元测试：`tests/unit/test_skill_caller_streaming.py`、`tests/unit/test_ai_log_manager.py`
- 集成测试：`tests/integration/test_ai_log_sidebar.py`
```

### Step 2: 手动端到端验证

**启动应用：**
```bash
streamlit run app.py
```

**验证清单：**
- [ ] 双栏布局正确显示（左70%，右30%）
- [ ] 左侧工作流正常运行（5个阶段）
- [ ] 上传调研表后点击"开始分析"
- [ ] 右侧日志栏实时显示 AI 响应（每条 block.text）
- [ ] 日志条目数与实际 AI 响应数量一致
- [ ] 日志样式美观（绿色边框，白色背景）
- [ ] "清空日志"按钮工作正常
- [ ] 刷新页面后日志清空（符合预期）
- [ ] 无布局错乱或性能问题

### Step 3: 提交文档更新

```bash
git add CLAUDE.md
git commit -m "docs: add AI log sidebar documentation"
```

---

## Task 7: 最终整合和清理

### Step 1: 验证所有测试通过

**命令：**
```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/ -v --tb=short
```

**预期输出：**
```
========== X passed in Y.Ys ==========
```

### Step 2: 检查代码质量（可选）

**如果使用 linter：**
```bash
flake8 core/skill_caller.py core/ai_log_manager.py app.py --max-line-length=100
```

### Step 3: 创建功能演示脚本（可选）

**文件：** `scripts/demo_ai_log.py`

```python
"""AI 日志功能演示脚本"""
import asyncio
from core.skill_caller import SkillCaller
from core.ai_log_manager import AILogManager
import os


async def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ 请设置 ANTHROPIC_API_KEY 环境变量")
        return

    log_manager = AILogManager()

    def callback(text: str):
        print(f"[实时日志] {text}")
        log_manager.add_log(text)

    caller = SkillCaller(timeout=300, on_ai_response=callback)

    print("🤖 开始调用 skill，实时显示 AI 响应...")
    print("=" * 60)

    # 这里可以调用实际的 skill 进行演示
    # result = await caller._call_skill_async("extract-survey-data", "input.xlsx", "output.json")

    print("=" * 60)
    print(f"✅ 完成！共收集 {log_manager.get_logs_count()} 条日志")


if __name__ == "__main__":
    asyncio.run(main())
```

### Step 4: 最终提交

```bash
git add scripts/demo_ai_log.py
git commit -m "chore: add AI log demo script"
```

---

## 完成检查清单

在宣布任务完成前，确保：

- [ ] 所有单元测试通过
  - [ ] `test_skill_caller_streaming.py`
  - [ ] `test_ai_log_manager.py`
- [ ] 所有集成测试通过
  - [ ] `test_ai_log_sidebar.py`
- [ ] 所有现有测试无回归
- [ ] 手动测试验证：
  - [ ] 双栏布局正确
  - [ ] AI 日志实时显示
  - [ ] 日志条目数准确
  - [ ] 清空功能工作
  - [ ] 样式美观
- [ ] 文档更新完成（CLAUDE.md）
- [ ] 代码已提交到 Git
- [ ] 代码符合项目规范（DRY、YAGNI）

---

## 潜在扩展（未来迭代）

1. **日志持久化**：将日志保存到会话目录（`session_dir/ai_logs.json`）
2. **日志分类**：区分不同 skill 的日志（用颜色或图标标记）
3. **日志搜索**：添加搜索框过滤日志
4. **日志导出**：允许用户下载日志为文本文件
5. **实时流式显示**：使用 `st.empty()` 实现逐字显示（需要异步机制）
6. **日志统计**：显示每个 skill 的执行时间和日志数量

---

**计划修改完成！** 📋

保存位置：`docs/plans/2025-12-31-streaming-ai-log-sidebar.md`
