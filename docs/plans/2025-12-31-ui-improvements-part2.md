# UI 改进第二部分实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 进一步优化用户界面交互体验，提升专业性和用户控制

**Architecture:** 修改 `app.py` 的 UI 组件配置和流程控制逻辑

**Tech Stack:** Streamlit, Python

---

## Task 1: 默认展开"查看计算元数据"

**Files:**
- Modify: `app.py` (结果展示阶段的 expander)

**Step 1: 查找计算元数据 expander**

使用 grep 查找：

```bash
grep -n "查看计算元数据" app.py
```

预期找到结果展示阶段的 expander。

**Step 2: 修改 expanded 参数**

找到类似（位置待确认）：
```python
with st.expander("🔍 查看计算元数据"):
```

或：
```python
with st.expander("🔍 查看计算元数据", expanded=False):
```

修改为：
```python
with st.expander("🔍 查看计算元数据", expanded=True):
```

**Step 3: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 4: 提交修改**

```bash
git add app.py
git commit -m "feat: expand calculation metadata by default

- Set expanded=True for metadata expander
- Improve visibility of calculation details"
```

---

## Task 2: 更新 AI 分析过程标题

**Files:**
- Modify: `app.py` (2处 AI 分析/推理过程的 expander 标题)

**Step 1: 查找 AI 分析/推理过程标题**

使用 grep 查找：

```bash
grep -n "查看 AI" app.py
```

预期找到 2 处：
- 提取检查阶段："🤖 查看 AI 分析过程"
- 填充建议阶段："🤖 查看 AI 推理过程"

**Step 2: 修改提取检查阶段标题**

找到类似（约第 174 行）：
```python
_, log_container = create_streaming_container("🤖 查看 AI 分析过程")
```

修改为：
```python
_, log_container = create_streaming_container("🤖 查看灵知 AI 分析过程")
```

**Step 3: 修改填充建议阶段标题**

找到类似（约第 420 行）：
```python
_, log_container = create_streaming_container("🤖 查看 AI 推理过程")
```

修改为：
```python
_, log_container = create_streaming_container("🤖 查看灵知 AI 推理过程")
```

**Step 4: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 5: 提交修改**

```bash
git add app.py
git commit -m "refactor: rebrand AI log titles with '灵知'

- Update '查看 AI 分析过程' to '查看灵知 AI 分析过程'
- Update '查看 AI 推理过程' to '查看灵知 AI 推理过程'
- Consistent brand messaging"
```

---

## Task 3: 添加数据提取完成后的确认按钮

**Files:**
- Modify: `app.py:405-409` (提取检查阶段的自动跳转逻辑)

**Step 1: 查找自动跳转代码**

使用 grep 查找：

```bash
grep -n "st.session_state.stage = 'filling'" app.py
```

预期找到提取检查阶段末尾的自动跳转代码。

**Step 2: 查看当前自动跳转逻辑**

找到类似（约第 405-409 行）：
```python
# 自动进入下一阶段(仅当置信度不是 low 时)
time.sleep(1.5)
st.session_state.stage = 'filling'
st.rerun()
```

**Step 3: 替换为确认按钮逻辑**

将自动跳转代码替换为：

```python
# 提供确认按钮进入下一阶段(仅当置信度不是 low 时)
st.markdown("---")
if st.button("✅ 确认", type="primary", use_container_width=True):
    st.session_state.stage = 'filling'
    st.rerun()
```

**完整修改上下文：**

找到（约第 403-409 行）：
```python
with st.expander("查看提取的原始数据"):
    st.json(extracted_data)

# 自动进入下一阶段(仅当置信度不是 low 时)
time.sleep(1.5)
st.session_state.stage = 'filling'
st.rerun()
```

修改为：
```python
with st.expander("查看提取的原始数据"):
    st.json(extracted_data)

# 提供确认按钮进入下一阶段(仅当置信度不是 low 时)
st.markdown("---")
if st.button("✅ 确认", type="primary", use_container_width=True):
    st.session_state.stage = 'filling'
    st.rerun()
```

**Step 4: 移除不必要的 import**

检查是否还有其他地方使用 `time.sleep()`：

```bash
grep -n "time\\.sleep" app.py
```

如果只有刚才移除的一处，则从导入中移除 `time`：

找到（约第 4 行）：
```python
import time
```

如果没有其他使用，可以删除这一行。如果有其他使用，保留。

**Step 5: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 6: 提交修改**

```bash
git add app.py
git commit -m "feat: add confirmation button after data extraction

- Replace auto-navigation with confirmation button
- User must click '确认' to proceed
- Remove time.sleep() delay
- Improve user control and workflow clarity"
```

---

## Task 4: 添加结果页打印按钮

**Files:**
- Modify: `app.py` (结果展示阶段)

**Step 1: 查找结果展示阶段代码**

使用 grep 查找：

```bash
grep -n "stage == 'result'" app.py
```

预期找到结果展示阶段的代码块。

**Step 2: 定位结果展示区域末尾**

在结果展示页面的末尾（通常在显示计算结果、元数据等内容之后），查找合适的位置添加打印按钮。

**Step 3: 添加打印按钮和说明**

在结果展示区域末尾添加：

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
```

**Step 4: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 5: 提交修改**

```bash
git add app.py
git commit -m "feat: add print button on results page

- Add print button at the end of results page
- Include reminder note: '呼叫SR前请打印本页'
- Use JavaScript window.print() for browser print dialog
- Improve user workflow for SR requests"
```

---

## Task 5: 验证所有修改

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

**Step 3: 视觉验证清单**

手动启动应用并验证：

```bash
streamlit run app.py
```

验证清单：
- [ ] "查看计算元数据" 默认展开
- [ ] "查看灵知 AI 分析过程" 标题正确显示
- [ ] "查看灵知 AI 推理过程" 标题正确显示
- [ ] 数据提取完成后显示确认按钮
- [ ] 点击确认按钮后跳转到数据填充阶段
- [ ] 结果页显示打印按钮和提示文字
- [ ] 点击打印按钮能正常触发浏览器打印对话框
- [ ] 整体 UI 正常显示

**Step 4: 查看提交历史**

```bash
git log --oneline -4
```

预期：看到 4 个新提交

---

## 验证清单

- [ ] Task 1: "查看计算元数据" 默认展开
- [ ] Task 2: AI 分析/推理过程标题更新为"灵知 AI"
- [ ] Task 3: 添加确认按钮，移除自动跳转
- [ ] Task 4: 结果页添加打印按钮和提示
- [ ] Task 5: 语法检查通过
- [ ] Task 5: Streamlit 启动正常
- [ ] 所有修改已提交到 Git

---

## 预期修改总结

### Expander 默认状态修改

| 组件 | 原状态 | 新状态 |
|------|--------|--------|
| 查看计算元数据 | collapsed (或 expanded=False) | expanded=True |

### AI 日志标题修改

| 位置 | 原标题 | 新标题 |
|------|--------|--------|
| 提取检查阶段 | 🤖 查看 AI 分析过程 | 🤖 查看灵知 AI 分析过程 |
| 填充建议阶段 | 🤖 查看 AI 推理过程 | 🤖 查看灵知 AI 推理过程 |

### 流程控制修改

| 阶段 | 原行为 | 新行为 |
|------|--------|--------|
| 数据提取完成 | 自动跳转 (1.5秒延迟) | 显示确认按钮，手动跳转 |

### 结果页新增功能

| 功能 | 说明 |
|------|------|
| 打印按钮 | 🖨️ 打印本页（使用 JavaScript window.print()） |
| 提示信息 | 📋 呼叫SR前请打印本页 |

---

## 注意事项

1. **确认按钮样式**：使用 `type="primary"` 和 `use_container_width=True` 确保视觉突出
2. **移除 time 模块**：仅在确认没有其他使用时才移除导入
3. **用户体验**：确认按钮让用户有时间查看提取结果和质量报告
4. **一致性**：所有 AI 相关标题统一使用"灵知 AI"品牌

---

## 潜在改进（未来迭代）

1. 在确认按钮上方添加提示文字，说明下一步将做什么
2. 考虑在其他自动跳转的地方也添加确认按钮
3. 为确认按钮添加快捷键支持（Streamlit 限制）
