# 基于会话的临时目录管理实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为每次上传任务创建独立的临时目录，避免文件覆盖和混乱

**Architecture:**
- 在 Streamlit session_state 中维护会话目录路径
- 使用 `session_YYYYMMDD_HHMMSS` 格式命名目录
- 所有临时文件（上传、提取、填充、计算结果）存放在会话目录中
- 重置流程时创建新会话目录

**Tech Stack:** Python 3.8+, Streamlit, pathlib, datetime

---

## Task 1: 创建会话目录管理器

**Files:**
- Create: `core/session_manager.py`
- Test: `tests/unit/test_session_manager.py`

**Step 1: 编写失败测试**

创建 `tests/unit/test_session_manager.py`:

```python
"""测试会话目录管理器"""
import pytest
from pathlib import Path
from datetime import datetime
from core.session_manager import SessionManager


def test_create_session_directory():
    """测试创建会话目录"""
    manager = SessionManager()
    session_dir = manager.create_session_directory()

    # 验证目录格式: session_YYYYMMDD_HHMMSS
    assert session_dir.name.startswith("session_")
    assert len(session_dir.name) == len("session_20251230_153045")

    # 验证目录已创建
    assert session_dir.exists()
    assert session_dir.is_dir()

    # 清理
    session_dir.rmdir()


def test_get_file_path():
    """测试获取会话目录中的文件路径"""
    manager = SessionManager()
    session_dir = manager.create_session_directory()

    # 获取文件路径
    upload_path = manager.get_file_path("upload_survey.xlsx")

    # 验证路径正确
    assert upload_path.parent == session_dir
    assert upload_path.name == "upload_survey.xlsx"

    # 清理
    session_dir.rmdir()


def test_list_all_sessions():
    """测试列出所有会话目录"""
    manager = SessionManager()

    # 创建多个会话
    session1 = manager.create_session_directory()
    session2 = manager.create_session_directory()

    # 列出所有会话
    all_sessions = manager.list_all_sessions()

    # 验证至少包含刚创建的两个
    assert session1 in all_sessions
    assert session2 in all_sessions

    # 清理
    session1.rmdir()
    session2.rmdir()


def test_cleanup_old_sessions():
    """测试清理旧会话目录（可选功能）"""
    manager = SessionManager()

    # 创建会话目录
    session_dir = manager.create_session_directory()

    # 创建一些文件
    test_file = session_dir / "test.txt"
    test_file.write_text("test")

    # 清理会话
    manager.cleanup_session(session_dir)

    # 验证目录和文件都被删除
    assert not session_dir.exists()


def test_get_current_session_directory():
    """测试获取当前会话目录"""
    manager = SessionManager()

    # 首次调用应返回 None（未初始化）
    assert manager.get_current_session_directory() is None

    # 创建会话后应返回该目录
    session_dir = manager.create_session_directory()
    assert manager.get_current_session_directory() == session_dir

    # 清理
    session_dir.rmdir()
```

**Step 2: 运行测试验证失败**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_session_manager.py -v
```

Expected: FAIL - `ModuleNotFoundError: No module named 'core.session_manager'`

**Step 3: 实现会话管理器**

创建 `core/session_manager.py`:

```python
"""会话目录管理器

为每次上传任务创建独立的临时目录，避免文件覆盖
"""
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import shutil


class SessionManager:
    """会话目录管理器"""

    def __init__(self, base_dir: Optional[Path] = None):
        """初始化会话管理器

        Args:
            base_dir: 基础目录，默认为项目根目录下的 tmp
        """
        if base_dir is None:
            # 默认使用项目根目录下的 tmp 目录
            self.base_dir = Path(__file__).parent.parent / "tmp"
        else:
            self.base_dir = Path(base_dir)

        # 确保基础目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 当前会话目录
        self._current_session_dir: Optional[Path] = None

    def create_session_directory(self) -> Path:
        """创建新的会话目录

        Returns:
            会话目录路径
        """
        # 生成目录名: session_YYYYMMDD_HHMMSS
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dir_name = f"session_{timestamp}"

        # 创建目录
        session_dir = self.base_dir / dir_name
        session_dir.mkdir(parents=True, exist_ok=True)

        # 更新当前会话目录
        self._current_session_dir = session_dir

        return session_dir

    def get_current_session_directory(self) -> Optional[Path]:
        """获取当前会话目录

        Returns:
            当前会话目录路径，如果未创建则返回 None
        """
        return self._current_session_dir

    def get_file_path(self, filename: str) -> Path:
        """获取会话目录中的文件路径

        Args:
            filename: 文件名

        Returns:
            完整文件路径

        Raises:
            RuntimeError: 如果当前会话目录未创建
        """
        if self._current_session_dir is None:
            raise RuntimeError("会话目录未创建，请先调用 create_session_directory()")

        return self._current_session_dir / filename

    def list_all_sessions(self) -> List[Path]:
        """列出所有会话目录

        Returns:
            会话目录路径列表，按时间倒序排列
        """
        # 查找所有 session_* 目录
        session_dirs = [
            d for d in self.base_dir.iterdir()
            if d.is_dir() and d.name.startswith("session_")
        ]

        # 按修改时间倒序排列（最新的在前）
        session_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

        return session_dirs

    def cleanup_session(self, session_dir: Path) -> None:
        """清理指定的会话目录

        Args:
            session_dir: 要清理的会话目录
        """
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def cleanup_old_sessions(self, keep_count: int = 10) -> int:
        """清理旧的会话目录，保留最近的 N 个

        Args:
            keep_count: 保留的会话数量

        Returns:
            清理的会话数量
        """
        all_sessions = self.list_all_sessions()

        # 保留最近的 N 个，删除其余的
        sessions_to_delete = all_sessions[keep_count:]

        for session_dir in sessions_to_delete:
            self.cleanup_session(session_dir)

        return len(sessions_to_delete)
```

**Step 4: 运行测试验证通过**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_session_manager.py -v
```

Expected: PASS (all 5 tests)

**Step 5: 提交**

```bash
git add core/session_manager.py tests/unit/test_session_manager.py
git commit -m "feat: add session directory manager

- 创建 SessionManager 类管理会话目录
- 使用 session_YYYYMMDD_HHMMSS 格式命名
- 支持获取文件路径、列出会话、清理旧会话
- 完整的单元测试覆盖

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: 集成会话管理器到 app.py

**Files:**
- Modify: `app.py:14-24` (init_session_state)
- Modify: `app.py:27-37` (reset_flow)
- Modify: `app.py:104-121` (render_upload_stage)

**Step 1: 编写集成测试（失败）**

创建 `tests/integration/test_session_based_temp_dir.py`:

```python
"""测试基于会话的临时目录集成"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import streamlit as st


def test_session_directory_creation_on_upload():
    """测试上传时创建会话目录"""
    # 模拟 Streamlit session state
    with patch('streamlit.session_state') as mock_state:
        # 初始化 session state
        from app import init_session_state
        init_session_state()

        # 验证会话管理器已初始化
        assert hasattr(mock_state, 'session_manager')
        assert hasattr(mock_state, 'session_dir')


def test_reset_flow_creates_new_session():
    """测试重置流程时创建新会话目录"""
    with patch('streamlit.session_state') as mock_state:
        from app import reset_flow

        # 第一次重置
        reset_flow()
        first_session_dir = mock_state.session_dir

        # 第二次重置应创建不同的目录
        reset_flow()
        second_session_dir = mock_state.session_dir

        assert first_session_dir != second_session_dir


def test_uploaded_file_saved_to_session_directory():
    """测试上传文件保存到会话目录"""
    with patch('streamlit.file_uploader') as mock_uploader:
        # 模拟上传文件
        mock_file = MagicMock()
        mock_file.name = "test.xlsx"
        mock_file.getbuffer.return_value = b"test data"
        mock_uploader.return_value = mock_file

        from app import render_upload_stage
        render_upload_stage()

        # 验证文件保存到会话目录
        # (具体验证逻辑需要根据实际实现调整)
```

**Step 2: 运行集成测试验证失败**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_session_based_temp_dir.py -v
```

Expected: FAIL - 会话管理器未集成

**Step 3: 修改 app.py - init_session_state**

在 `app.py` 中修改 `init_session_state()` 函数（第14-24行）:

```python
def init_session_state():
    """初始化 session state"""
    if 'stage' not in st.session_state:
        st.session_state.stage = 'upload'
        st.session_state.uploaded_file = None
        st.session_state.original_filename = None  # 新增: 保存原始文件名
        st.session_state.extracted_data = None
        st.session_state.quality_report = None
        st.session_state.filling_suggestions = None
        st.session_state.result = None
        st.session_state.uploader_key = 0  # 新增: file_uploader的key计数器

        # 新增: 初始化会话管理器
        from core.session_manager import SessionManager
        st.session_state.session_manager = SessionManager()
        st.session_state.session_dir = st.session_state.session_manager.create_session_directory()
```

**Step 4: 修改 app.py - reset_flow**

在 `app.py` 中修改 `reset_flow()` 函数（第27-37行）:

```python
def reset_flow():
    """重置流程"""
    st.session_state.stage = 'upload'
    st.session_state.uploaded_file = None
    st.session_state.original_filename = None  # 新增
    st.session_state.extracted_data = None
    st.session_state.quality_report = None
    st.session_state.filling_suggestions = None
    st.session_state.result = None
    # 重要：增加uploader_key强制清空file_uploader缓存
    st.session_state.uploader_key = st.session_state.get('uploader_key', 0) + 1

    # 新增: 创建新的会话目录
    st.session_state.session_dir = st.session_state.session_manager.create_session_directory()
```

**Step 5: 修改 app.py - render_upload_stage**

在 `app.py` 中修改 `render_upload_stage()` 函数（第104-121行）:

```python
    if uploaded_file:
        st.session_state.uploaded_file = uploaded_file
        st.session_state.original_filename = uploaded_file.name  # 新增: 保存原始文件名

        # 修改: 保存到会话目录（不再使用硬编码的 tmp 目录）
        session_dir = st.session_state.session_dir
        upload_path = session_dir / "upload_survey.xlsx"

        with open(upload_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.success(f"✅ 文件已上传: {uploaded_file.name}")
        st.info(f"文件大小: {uploaded_file.size / 1024:.2f} KB")
        st.info(f"📂 会话目录: {session_dir.name}")  # 新增: 显示会话目录名

        if st.button("🚀 开始分析", type="primary", use_container_width=True):
            st.session_state.stage = 'extract_check'
            st.rerun()
```

**Step 6: 运行测试验证通过**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_session_manager.py -v
```

Expected: PASS (基础单元测试)

**Step 7: 提交**

```bash
git add app.py
git commit -m "feat: integrate session manager into app.py upload stage

- 在 init_session_state 中初始化会话管理器
- 在 reset_flow 中创建新会话目录
- 上传文件保存到会话目录而非固定 tmp 目录
- 显示会话目录名称供用户识别

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: 更新 render_extract_check_stage 使用会话目录

**Files:**
- Modify: `app.py:124-195` (render_extract_check_stage)

**Step 1: 修改提取检查阶段的路径**

在 `app.py` 中修改 `render_extract_check_stage()` 函数（第138-195行）:

```python
        # 需要执行skill获取新结果
        with st.spinner("正在提取调研表数据并进行质量检查,请稍候..."):
            try:
                caller = SkillCaller(timeout=300)

                # 修改: 使用会话目录
                session_dir = st.session_state.session_dir
                upload_path = session_dir / "upload_survey.xlsx"
                output_path = session_dir / "extract_check_result.json"

                # 获取原始文件名
                original_filename = st.session_state.get('original_filename', 'unknown.xlsx')

                # 调用合并的 Skill: 提取和质量检查,传递原始文件名
                skill_result = caller.call_skill(
                    "extract-and-check-data",
                    str(upload_path),
                    str(output_path),
                    original_filename  # 新增: 传递原始文件名
                )

                # ... 其余代码保持不变 ...

                # 同时保存单独的文件（供后续步骤使用）
                # 修改: 保存到会话目录
                with open(session_dir / "extracted_data.json", 'w', encoding='utf-8') as f:
                    json.dump(extracted_data, f, ensure_ascii=False, indent=2)
                with open(session_dir / "quality_report.json", 'w', encoding='utf-8') as f:
                    json.dump(quality_report, f, ensure_ascii=False, indent=2)
```

**Step 2: 手动测试**

```bash
streamlit run app.py
```

操作步骤:
1. 上传调研表文件
2. 点击"开始分析"
3. 验证提取检查成功
4. 检查会话目录是否包含文件

Expected:
- 会话目录包含 `upload_survey.xlsx`, `extract_check_result.json`, `extracted_data.json`, `quality_report.json`
- 不会覆盖 `tmp/` 目录下的旧文件

**Step 3: 提交**

```bash
git add app.py
git commit -m "feat: use session directory in extract_check_stage

- 修改提取检查阶段使用会话目录路径
- 所有中间文件保存到会话目录
- 避免覆盖全局 tmp 目录文件

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: 更新 render_filling_stage 使用会话目录

**Files:**
- Modify: `app.py:367-415` (render_filling_stage)

**Step 1: 修改填充建议阶段的路径**

在 `app.py` 中修改 `render_filling_stage()` 函数（第374-386行）:

```python
        with st.spinner("正在生成智能填充建议..."):
            try:
                caller = SkillCaller(timeout=300)

                # 修改: 使用会话目录
                session_dir = st.session_state.session_dir
                extracted_path = session_dir / "extracted_data.json"
                quality_path = session_dir / "quality_report.json"
                output_path = session_dir / "filling_suggestions.json"

                # 调用 Skill 3: 填充建议
                skill_result = caller.call_skill(
                    "suggest-data-filling",
                    str(extracted_path),
                    str(quality_path),
                    str(output_path)
                )
```

**Step 2: 手动测试**

```bash
streamlit run app.py
```

操作步骤:
1. 上传调研表文件
2. 等待提取检查完成（自动流转）
3. 查看填充建议页面
4. 检查会话目录

Expected:
- 会话目录包含 `filling_suggestions.json`
- 填充建议正确显示

**Step 3: 提交**

```bash
git add app.py
git commit -m "feat: use session directory in filling_stage

- 修改填充建议阶段使用会话目录路径
- 保持数据隔离，避免跨会话污染

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: 更新 render_calculate_stage 使用会话目录

**Files:**
- Modify: `app.py:485-566` (render_calculate_stage)

**Step 1: 修改计算阶段的路径**

在 `app.py` 中修改 `render_calculate_stage()` 函数（第494-532行）:

```python
    try:
        # 修改: 使用会话目录
        session_dir = st.session_state.session_dir

        # 步骤0: 执行数据填充（每次都重新生成，避免使用旧数据）
        status_text.text("正在填充数据...")
        progress_bar.progress(10)

        filler = DataFiller()
        filled_path = filler.fill_data(
            str(session_dir / "extracted_data.json"),
            str(session_dir / "filling_suggestions.json"),
            str(session_dir / "filled_data.json")
        )
        progress_bar.progress(20)

        # ... 检查站房类型 ...

        # 步骤2: Excel计算
        status_text.text("正在调用Excel计算引擎...")
        progress_bar.progress(60)

        calculator = ExcelCalculator()  # 不传 template_path，自动根据 station_type 选择

        result_path = calculator.calculate(
            filled_path,
            str(session_dir / "result_data.json")
        )

        progress_bar.progress(80)
```

**Step 2: 手动测试**

```bash
streamlit run app.py
```

操作步骤:
1. 完整流程：上传 → 提取 → 填充 → 计算
2. 检查会话目录

Expected:
- 会话目录包含 `filled_data.json`, `result_data.json`, `calculation_result.xlsx`
- 计算结果正确

**Step 3: 提交**

```bash
git add app.py
git commit -m "feat: use session directory in calculate_stage

- 修改计算阶段使用会话目录路径
- DataFiller 和 ExcelCalculator 都使用会话目录
- 所有计算结果隔离在各自的会话目录中

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: 更新 render_result_stage 使用会话目录

**Files:**
- Modify: `app.py:569-834` (render_result_stage)

**Step 1: 修改结果展示阶段的下载路径**

在 `app.py` 中修改 `render_result_stage()` 函数（第806-820行）:

```python
    if password:
        admin_password = st.secrets.get("admin_password", "admin123")
        if password == admin_password:
            st.success("✅ 密码验证通过")

            # 修改: 从会话目录读取计算结果Excel
            session_dir = st.session_state.session_dir
            excel_path = session_dir / "calculation_result.xlsx"

            if excel_path.exists():
                with open(excel_path, "rb") as f:
                    excel_data = f.read()

                st.download_button(
                    label="📥 下载 Excel 计算表",
                    data=excel_data,
                    file_name=f"节能率计算结果_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.warning("⚠️ Excel文件未找到")
```

**Step 2: 手动测试**

```bash
streamlit run app.py
```

操作步骤:
1. 完整流程到结果页面
2. 输入管理员密码下载文件
3. 验证下载的 Excel 文件正确

Expected:
- 下载功能正常
- 文件来自正确的会话目录

**Step 3: 提交**

```bash
git add app.py
git commit -m "feat: use session directory in result_stage download

- 修改结果下载功能使用会话目录路径
- 确保下载的是当前会话的计算结果

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: 更新 CLAUDE.md 文档

**Files:**
- Modify: `CLAUDE.md`

**Step 1: 更新临时文件管理部分**

在 `CLAUDE.md` 中找到"临时文件约定"章节，更新为:

```markdown
### 临时文件约定

**会话目录结构**：
- 每次上传任务创建独立的会话目录
- 目录命名格式：`tmp/session_YYYYMMDD_HHMMSS/`
- 会话目录由 `core.session_manager.SessionManager` 管理

**会话目录中的文件**：
- `upload_survey.xlsx`：用户上传的调研表
- `extract_check_result.json`：提取和质量检查的合并结果
- `extracted_data.json`：提取的原始数据
- `quality_report.json`：质量检查报告
- `filling_suggestions.json`：填充建议
- `filled_data.json`：填充后的完整数据
- `result_data.json`：计算结果JSON
- `calculation_result.xlsx`：计算结果Excel（供下载）

**优势**：
- ✅ 多用户同时使用时数据隔离
- ✅ 可以保留历史会话记录
- ✅ 避免文件覆盖和混乱
- ✅ 方便调试和问题追溯

**清理策略**（可选）：
- 自动保留最近 10 个会话
- 可通过 `SessionManager.cleanup_old_sessions()` 手动清理
- 建议定期清理避免磁盘占用过多

**向后兼容**：
- `tmp/.gitkeep` 保留以维护 Git 目录结构
- 旧代码中的硬编码 `tmp/` 路径已全部迁移到会话目录
```

**Step 2: 更新常用命令部分**

在 `CLAUDE.md` 的"常用命令"章节添加:

```markdown
### 会话管理

```bash
# 列出所有会话目录（按时间倒序）
ls -lt tmp/session_*/

# 查看特定会话的内容
ls -lh tmp/session_20251230_153045/

# 手动清理旧会话（保留最近10个）
python -c "from core.session_manager import SessionManager; SessionManager().cleanup_old_sessions(keep_count=10)"

# 删除特定会话
rm -rf tmp/session_20251230_153045/
```
```

**Step 3: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for session-based temp directory

- 更新临时文件约定，说明会话目录机制
- 添加会话管理命令示例
- 文档化清理策略和向后兼容性

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: 端到端测试

**Files:**
- Create: `tests/integration/test_session_directory_e2e.py`

**Step 1: 编写端到端测试**

创建 `tests/integration/test_session_directory_e2e.py`:

```python
"""端到端测试：会话目录隔离"""
import pytest
from pathlib import Path
from core.session_manager import SessionManager


def test_multiple_sessions_isolated():
    """测试多个会话完全隔离"""
    manager = SessionManager()

    # 会话1
    session1 = manager.create_session_directory()
    file1 = session1 / "test.txt"
    file1.write_text("session 1 data")

    # 会话2
    session2 = manager.create_session_directory()
    file2 = session2 / "test.txt"
    file2.write_text("session 2 data")

    # 验证隔离
    assert file1.read_text() == "session 1 data"
    assert file2.read_text() == "session 2 data"
    assert session1 != session2

    # 清理
    manager.cleanup_session(session1)
    manager.cleanup_session(session2)


def test_session_directory_lifecycle():
    """测试会话目录完整生命周期"""
    manager = SessionManager()

    # 创建会话
    session_dir = manager.create_session_directory()
    assert session_dir.exists()

    # 创建文件
    test_files = [
        "upload_survey.xlsx",
        "extract_check_result.json",
        "extracted_data.json",
        "quality_report.json",
        "filling_suggestions.json",
        "filled_data.json",
        "result_data.json",
        "calculation_result.xlsx"
    ]

    for filename in test_files:
        filepath = session_dir / filename
        filepath.write_text(f"test data for {filename}")

    # 验证所有文件存在
    for filename in test_files:
        assert (session_dir / filename).exists()

    # 清理会话
    manager.cleanup_session(session_dir)

    # 验证目录和所有文件都被删除
    assert not session_dir.exists()
    for filename in test_files:
        assert not (session_dir / filename).exists()


def test_cleanup_old_sessions_preserves_recent():
    """测试清理旧会话时保留最近的"""
    manager = SessionManager()

    # 创建15个会话
    sessions = []
    for i in range(15):
        session = manager.create_session_directory()
        (session / f"file_{i}.txt").write_text(f"session {i}")
        sessions.append(session)
        # 确保时间戳不同
        import time
        time.sleep(0.1)

    # 清理，保留最近10个
    deleted_count = manager.cleanup_old_sessions(keep_count=10)

    # 验证删除了5个
    assert deleted_count == 5

    # 验证最近10个还在
    remaining_sessions = manager.list_all_sessions()
    assert len(remaining_sessions) >= 10

    # 验证最早的5个被删除（sessions[0:5]）
    for session in sessions[:5]:
        assert not session.exists()

    # 验证最近的10个还在（sessions[5:15]）
    for session in sessions[5:15]:
        assert session.exists()

    # 清理剩余会话
    for session in sessions[5:15]:
        if session.exists():
            manager.cleanup_session(session)
```

**Step 2: 运行端到端测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_session_directory_e2e.py -v -s
```

Expected: PASS (all 3 tests)

**Step 3: 提交**

```bash
git add tests/integration/test_session_directory_e2e.py
git commit -m "test: add e2e tests for session directory isolation

- 测试多会话隔离
- 测试会话完整生命周期
- 测试清理旧会话功能

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 9: 手动全流程测试

**Files:**
- Create: `docs/testing/session-directory-manual-test.md`

**Step 1: 编写手动测试指南**

创建 `docs/testing/session-directory-manual-test.md`:

```markdown
# 会话目录手动测试指南

## 测试目标
验证每次上传任务都创建独立的会话目录，不会覆盖之前的数据。

## 测试步骤

### 测试1: 基础会话隔离

1. **启动应用**
   ```bash
   streamlit run app.py
   ```

2. **第一次上传**
   - 上传调研表文件1（如：`惠州光弘-调研表.xlsx`）
   - 记录会话目录名称（显示在上传成功后）
   - 完成全流程（提取 → 填充 → 计算 → 结果）
   - 检查 `tmp/session_YYYYMMDD_HHMMSS/` 目录是否包含所有文件

3. **第二次上传（不点击"开始新的测算"）**
   - 点击浏览器刷新按钮（或打开新标签页）
   - 上传调研表文件2（如：`石家庄仁和药业-调研表.xlsx`）
   - 记录新的会话目录名称
   - 完成全流程

4. **验证隔离**
   - 检查 `tmp/` 目录，应该有两个 `session_*` 目录
   - 第一个会话目录的文件名应该是 `惠州光弘-调研表.xlsx`
   - 第二个会话目录的文件名应该是 `石家庄仁和药业-调研表.xlsx`
   - 两个目录的计算结果应该不同

**预期结果**: ✅ 两个会话完全独立，数据不冲突

---

### 测试2: 重置流程创建新会话

1. **启动应用并完成一次流程**
   - 上传调研表文件
   - 完成全流程到结果页面
   - 记录会话目录名称（session_A）

2. **点击"开始新的测算"**
   - 在结果页面点击"🔄 开始新的测算"按钮
   - 系统应返回上传页面

3. **第二次上传**
   - 上传相同或不同的调研表文件
   - 完成全流程
   - 记录新的会话目录名称（session_B）

4. **验证**
   - session_A 和 session_B 目录名不同
   - 两个目录都存在且内容独立

**预期结果**: ✅ 重置流程创建新会话，旧会话数据保留

---

### 测试3: 会话目录内容完整性

1. **完成一次完整流程**

2. **检查会话目录内容**
   ```bash
   ls -lh tmp/session_YYYYMMDD_HHMMSS/
   ```

3. **验证文件列表**
   应包含以下文件:
   - `upload_survey.xlsx` - 上传的调研表
   - `extract_check_result.json` - 提取+检查结果
   - `extracted_data.json` - 提取的数据
   - `quality_report.json` - 质量报告
   - `filling_suggestions.json` - 填充建议
   - `filled_data.json` - 填充后的数据
   - `result_data.json` - 计算结果JSON
   - `calculation_result.xlsx` - 计算结果Excel

**预期结果**: ✅ 所有中间文件和结果文件都在会话目录中

---

### 测试4: 下载功能验证

1. **完成一次完整流程**
2. **在结果页面输入管理员密码**
3. **点击下载 Excel 计算表**
4. **打开下载的文件**
5. **对比会话目录中的 `calculation_result.xlsx`**

**预期结果**: ✅ 下载的文件与会话目录中的文件一致

---

### 测试5: 清理旧会话

1. **创建多个会话**
   - 重复上传不同文件15次
   - 应生成15个 `session_*` 目录

2. **手动清理旧会话**
   ```bash
   python -c "from core.session_manager import SessionManager; print(f'删除了 {SessionManager().cleanup_old_sessions(keep_count=10)} 个旧会话')"
   ```

3. **验证**
   ```bash
   ls -lt tmp/session_*/
   ```

**预期结果**: ✅ 只保留最近10个会话，旧的5个被删除

---

## 已知问题

无

## 测试人员

- 姓名: ___________
- 日期: ___________
- 测试结果: ⬜ 全部通过  ⬜ 部分失败  ⬜ 全部失败

## 备注

___________________________________________
```

**Step 2: 执行手动测试**

按照测试指南完成测试。

**Step 3: 提交测试文档**

```bash
git add docs/testing/session-directory-manual-test.md
git commit -m "docs: add manual test guide for session directory

- 详细的手动测试步骤
- 覆盖会话隔离、重置、清理等场景
- 包含验证检查清单

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 10: 更新 .gitignore（可选）

**Files:**
- Modify: `.gitignore`

**Step 1: 检查当前 .gitignore**

当前 `.gitignore` 已包含:
```
# Temporary files
tmp/
```

这已经覆盖了 `tmp/session_*/` 目录，无需修改。

**Step 2: 确认验证**

```bash
git status
```

验证 `tmp/session_*` 目录不会被 Git 追踪。

Expected: `tmp/` 目录下的所有会话目录都被忽略

---

## 验证清单

完成所有任务后，验证以下内容:

- [ ] `core/session_manager.py` 创建并测试通过
- [ ] `app.py` 所有阶段都使用会话目录
- [ ] 多次上传创建不同的会话目录
- [ ] 会话目录命名格式正确: `session_YYYYMMDD_HHMMSS`
- [ ] 所有中间文件保存在会话目录中
- [ ] 下载功能使用会话目录中的文件
- [ ] 重置流程创建新会话
- [ ] 旧会话数据不会被覆盖
- [ ] `CLAUDE.md` 文档已更新
- [ ] 手动测试全部通过
- [ ] 所有单元测试和集成测试通过

---

## 回归测试

在完成所有修改后，运行完整的测试套件:

```bash
# 单元测试
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/ -v

# 集成测试
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/ -v

# 特定的会话目录测试
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_session_manager.py tests/integration/test_session_directory_e2e.py -v
```

Expected: 所有测试通过，无回归问题

---

## 部署注意事项

1. **磁盘空间监控**
   - 每个会话约占用 5-10 MB（包含 Excel 文件）
   - 建议定期清理旧会话或增加自动清理策略

2. **并发用户**
   - Streamlit 的 session_state 是隔离的
   - 每个用户自动获得独立的会话目录
   - 无需额外配置

3. **向后兼容**
   - 保留 `tmp/.gitkeep` 文件
   - 旧的硬编码 `tmp/` 路径已全部移除

---

## 后续优化建议

1. **自动清理策略**
   - 在 `init_session_state()` 中自动清理旧会话
   - 或使用定时任务（cron job）定期清理

2. **会话恢复功能**
   - 允许用户查看历史会话记录
   - 从旧会话目录恢复数据

3. **会话导出功能**
   - 打包整个会话目录为 ZIP 文件供下载
   - 方便用户保存完整的计算记录

---

**计划创建完成！准备执行。**
