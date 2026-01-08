# 确认按钮后滚动到顶部实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 点击确认按钮后，页面自动滚动到顶部，提升用户体验

**Architecture:** 在确认按钮点击后添加 JavaScript 代码，使页面自动滚动到顶部

**Tech Stack:** Streamlit, Python, JavaScript

---

## Task 1: 在提取检查阶段添加滚动到顶部功能

**Files:**
- Modify: `app.py` (提取检查阶段的确认按钮逻辑)

**Step 1: 查找确认按钮代码**

使用 grep 查找：

```bash
grep -n "✅ 确认，进行下一步" app.py
```

预期找到第 408 行的确认按钮。

**Step 2: 读取确认按钮上下文**

读取确认按钮周围的代码，确认修改位置。

**Step 3: 添加滚动到顶部逻辑**

找到（约第 406-410 行）：
```python
    # 提供确认按钮进入下一阶段(仅当置信度不是 low 时)
    st.markdown("---")
    if st.button("✅ 确认，进行下一步", type="primary", use_container_width=True):
        st.session_state.stage = 'filling'
        st.rerun()
```

修改为：
```python
    # 提供确认按钮进入下一阶段(仅当置信度不是 low 时)
    st.markdown("---")
    if st.button("✅ 确认，进行下一步", type="primary", use_container_width=True):
        st.session_state.stage = 'filling'
        st.session_state.scroll_to_top = True  # 标记需要滚动到顶部
        st.rerun()
```

**Step 4: 在主流程中添加滚动到顶部的 JavaScript**

找到 `main()` 函数中的流程控制部分（约第 110-125 行），在渲染各个阶段之前添加滚动逻辑。

找到类似：
```python
def main():
    init_session_state()

    # 流程进度指示器
    stages = ['上传调研表', '数据提取+质量检查', '数据填充', '节能测算', '结果展示']
```

在 `init_session_state()` 后添加滚动逻辑：
```python
def main():
    init_session_state()

    # 检查是否需要滚动到顶部
    if st.session_state.get('scroll_to_top', False):
        st.markdown(
            """
            <script>
                window.scrollTo(0, 0);
            </script>
            """,
            unsafe_allow_html=True
        )
        st.session_state.scroll_to_top = False  # 重置标记

    # 流程进度指示器
    stages = ['上传调研表', '数据提取+质量检查', '数据填充', '节能测算', '结果展示']
```

**Step 5: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 6: 提交修改**

```bash
git add app.py
git commit -m "feat: scroll to top after clicking confirmation button

- Add scroll_to_top flag to session state
- Use JavaScript to scroll to page top after stage transition
- Improve user experience by showing new stage content from top"
```

---

## Task 2: 验证滚动功能

**Files:**
- Verify: `app.py`

**Step 1: 运行语法检查**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 2: 运行 Streamlit 检查**

尝试启动应用（不需要实际访问）：

```bash
timeout 5 streamlit run app.py --server.headless true 2>&1 | head -20
```

预期：看到 "You can now view your Streamlit app" 或类似成功消息

**Step 3: 查看提交历史**

```bash
git log --oneline -1
```

预期：看到 1 个新提交

**Step 4: 手动测试建议**

启动应用并测试：
```bash
streamlit run app.py
```

测试步骤：
1. 上传调研表
2. 等待数据提取完成
3. 滚动到页面底部
4. 点击"✅ 确认，进行下一步"按钮
5. 验证页面是否自动滚动到顶部

---

## 验证清单

- [ ] Task 1: 确认按钮添加滚动标记
- [ ] Task 1: main() 函数添加滚动 JavaScript
- [ ] Task 2: 语法检查通过
- [ ] Task 2: Streamlit 启动正常
- [ ] 所有修改已提交到 Git

---

## 预期修改总结

### 新增的 Session State 字段

| 字段名 | 用途 |
|--------|------|
| scroll_to_top | 标记是否需要在下次渲染时滚动到顶部 |

### 修改的位置

| 位置 | 修改内容 |
|------|----------|
| app.py:408-410 | 确认按钮点击时设置 scroll_to_top = True |
| app.py:110-125（main 函数开头） | 添加 JavaScript 滚动逻辑 |

---

## 注意事项

1. **JavaScript 执行**：使用 `st.markdown()` 的 `unsafe_allow_html=True` 参数来执行 JavaScript
2. **标记重置**：执行滚动后立即重置 `scroll_to_top` 标记，避免重复滚动
3. **用户体验**：滚动到顶部后，用户可以从页面开始查看新阶段的内容
4. **兼容性**：`window.scrollTo(0, 0)` 是标准的浏览器 API，兼容性好

---

## 潜在改进（未来迭代）

1. 添加平滑滚动效果（smooth scroll）
2. 考虑在其他阶段转换时也添加滚动功能
3. 评估是否需要滚动到特定元素而不是页面顶部
