# 打印提示简化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 简化结果页打印功能，使用浏览器原生打印，提示用户使用右上角打印

**Architecture:** 修改 `app.py` 结果展示阶段的打印相关代码

**Tech Stack:** Streamlit, Python

---

## Task 1: 删除自定义打印按钮

**Files:**
- Modify: `app.py` (结果展示阶段，删除打印按钮相关代码)

**Step 1: 查找打印按钮代码**

使用 grep 查找：

```bash
grep -n "打印本页" app.py
```

预期找到打印按钮和相关提示的位置。

**Step 2: 读取打印按钮代码上下文**

读取打印按钮周围的代码，确认需要删除的完整代码块。

**Step 3: 删除打印按钮和旧提示**

删除以下代码块（约在第 891-917 行）：

```python
    # 打印功能
    st.markdown("---")
    st.info("📋 **呼叫SR前请打印本页**")

    # 使用 JavaScript 实现打印功能
    print_button_html = """
<script>
function printPage() {
    window.print();
}
</script>
<button onclick="printPage()" style="
    background-color: #0066cc;
    color: white;
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    font-size: 1rem;
    width: 100%;
">
    🖨️ 打印本页
</button>
"""
    st.markdown(print_button_html, unsafe_allow_html=True)

    st.markdown("---")
```

保留"重新开始"按钮之前的分隔线。

**Step 4: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 5: 提交修改**

```bash
git add app.py
git commit -m "refactor: remove custom print button

- Remove JavaScript print button implementation
- Prepare for simplified browser-native print reminder"
```

---

## Task 2: 添加新的打印提示到标题上方

**Files:**
- Modify: `app.py` (结果展示阶段开头)

**Step 1: 查找结果展示标题**

使用 grep 查找：

```bash
grep -n "📈 测算结果" app.py
```

预期找到结果展示阶段的标题（约第 629 行）。

**Step 2: 读取标题上下文**

读取标题周围的代码，确认插入位置。

**Step 3: 在标题上方添加打印提示**

找到（约第 629 行）：
```python
def render_result_stage():
    """阶段5: 结果展示"""
    st.header("📈 测算结果")
```

修改为：
```python
def render_result_stage():
    """阶段5: 结果展示"""

    # 打印提示
    st.info("📋 **呼叫SR前，请点击右上角打印本页**")

    st.header("📈 测算结果")
```

**Step 4: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 5: 提交修改**

```bash
git add app.py
git commit -m "feat: add simplified print reminder at top of results

- Add reminder to use browser's native print (top-right corner)
- Place reminder above results header for better visibility
- Use st.info() for consistent styling"
```

---

## Task 3: 验证所有修改

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
git log --oneline -2
```

预期：看到 2 个新提交

---

## 验证清单

- [ ] Task 1: 自定义打印按钮已删除
- [ ] Task 2: 新的打印提示已添加到标题上方
- [ ] Task 3: 语法检查通过
- [ ] Task 3: Streamlit 启动正常
- [ ] 所有修改已提交到 Git

---

## 预期修改总结

### 删除的内容

| 位置 | 删除内容 |
|------|----------|
| 结果页底部（原第 891-917 行） | 自定义打印按钮 + JavaScript + 旧提示 |

### 新增的内容

| 位置 | 新增内容 |
|------|----------|
| 结果页顶部（标题上方） | st.info("📋 **呼叫SR前，请点击右上角打印本页**") |

---

## 注意事项

1. **简化方案**：使用浏览器原生打印功能，无需自定义 JavaScript
2. **位置优化**：提示放在页面顶部更显眼
3. **用户体验**：明确指引用户点击"右上角"打印
4. **保持一致**：使用 st.info() 与其他提示保持样式一致

---

## 潜在改进（未来迭代）

1. 添加浏览器快捷键提示（Ctrl+P / Cmd+P）
2. 考虑添加 CSS 媒体查询优化打印样式
3. 评估是否需要"打印预览"功能
