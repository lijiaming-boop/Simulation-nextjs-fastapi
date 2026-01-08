# UI 文本优化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 优化两处 UI 文本，提升用户体验和术语准确性

**Architecture:** 修改 `app.py` 中的状态提示和按钮文案

**Tech Stack:** Streamlit, Python

---

## Task 1: 更新计算引擎状态提示文本

**Files:**
- Modify: `app.py:582` (计算阶段的状态提示)

**Step 1: 查找计算引擎状态提示**

使用 grep 查找：

```bash
grep -n "正在调用Excel计算引擎" app.py
```

预期找到第 582 行。

**Step 2: 修改状态提示文本**

找到（约第 582 行）：
```python
status_text.text("正在调用Excel计算引擎...")
```

修改为：
```python
status_text.text("正在调用AI计算引擎...")
```

**Step 3: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 4: 提交修改**

```bash
git add app.py
git commit -m "refactor: update calculation engine name to AI

- Change '正在调用Excel计算引擎...' to '正在调用AI计算引擎...'
- More accurate description of the AI-powered calculation process"
```

---

## Task 2: 更新确认按钮文案

**Files:**
- Modify: `app.py:408` (提取检查阶段的确认按钮)

**Step 1: 查找确认按钮**

使用 grep 查找：

```bash
grep -n "✅ 确认" app.py
```

预期找到两处：
- 第 408 行：提取检查阶段的确认按钮（需要修改）
- 第 530 行：填充建议阶段的确认按钮（不需要修改）

**Step 2: 读取上下文确认修改位置**

读取第 408 行附近的代码，确认这是提取检查阶段的确认按钮：

```python
# 提供确认按钮进入下一阶段(仅当置信度不是 low 时)
st.markdown("---")
if st.button("✅ 确认", type="primary", use_container_width=True):
    st.session_state.stage = 'filling'
    st.rerun()
```

**Step 3: 修改按钮文案**

修改为：
```python
# 提供确认按钮进入下一阶段(仅当置信度不是 low 时)
st.markdown("---")
if st.button("✅ 确认，进行下一步", type="primary", use_container_width=True):
    st.session_state.stage = 'filling'
    st.rerun()
```

**Step 4: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 5: 提交修改**

```bash
git add app.py
git commit -m "refactor: improve confirmation button text clarity

- Change '✅ 确认' to '✅ 确认，进行下一步'
- Make button action more explicit for better UX"
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

- [ ] Task 1: 计算引擎状态提示更新为"AI计算引擎"
- [ ] Task 2: 确认按钮文案更新为"确认，进行下一步"
- [ ] Task 3: 语法检查通过
- [ ] Task 3: Streamlit 启动正常
- [ ] 所有修改已提交到 Git

---

## 预期修改总结

### 状态提示文本修改

| 位置 | 原文案 | 新文案 |
|------|--------|--------|
| 计算阶段 (app.py:582) | 正在调用Excel计算引擎... | 正在调用AI计算引擎... |

### 按钮文案修改

| 位置 | 原文案 | 新文案 |
|------|--------|--------|
| 提取检查阶段 (app.py:408) | ✅ 确认 | ✅ 确认，进行下一步 |

---

## 注意事项

1. **术语准确性**：使用"AI计算引擎"更准确地描述系统的混合架构
2. **按钮明确性**：添加"进行下一步"让用户更清楚点击按钮的作用
3. **不修改其他按钮**：第 530 行的"✅ 确认填充,开始计算"已经很明确，不需要修改

---

## 潜在改进（未来迭代）

1. 考虑统一所有按钮的文案风格
2. 在状态提示中添加进度百分比
3. 为按钮添加悬停提示（tooltip）
