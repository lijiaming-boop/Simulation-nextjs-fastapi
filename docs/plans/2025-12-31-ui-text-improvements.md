# UI 文本优化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 优化 Streamlit 应用的用户界面文本，提升专业性和用户体验

**Architecture:** 直接修改 `app.py` 中的文本字符串，不涉及逻辑变更

**Tech Stack:** Streamlit, Python

---

## Task 1: 更新流程进度指示器文案

**Files:**
- Modify: `app.py:94` (stages 列表)

**Step 1: 查找 stages 列表**

使用 grep 查找：

```bash
grep -n "stages = \[" app.py
```

预期找到第 94 行。

**Step 2: 修改 stages 列表**

找到（约第 94 行）：
```python
stages = ['上传', '提取+质量检查', '填充建议', '计算', '结果']
```

修改为：
```python
stages = ['上传调研表', '数据提取+质量检查', '数据填充', '节能测算', '结果展示']
```

**Step 3: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 4: 提交修改**

```bash
git add app.py
git commit -m "refactor: update stage progress indicator labels

- Update stages list with full descriptive names
- 上传调研表、数据提取+质量检查、数据填充、节能测算、结果展示"
```

---

## Task 2: 添加"灵知AI："前缀到日志消息

**Files:**
- Modify: `app.py` (流式日志回调函数)

**Step 1: 查找日志回调函数**

使用 grep 查找回调函数位置：

```bash
grep -n "def on_text_received" app.py
```

预期找到 2 处：提取检查阶段和填充建议阶段。

**Step 2: 修改提取检查阶段的回调函数**

找到类似（约第 182-187 行）：
```python
def on_text_received(timestamp: str, text: str):
    """接收到 AI 文本时的回调"""
    # 添加时间戳前缀
    log_entry = f"**[{timestamp}]** {text}"
    streaming_logs.append(log_entry)
    update_streaming_container(log_container, streaming_logs)
```

修改为：
```python
def on_text_received(timestamp: str, text: str):
    """接收到 AI 文本时的回调"""
    # 添加时间戳和品牌前缀
    log_entry = f"**[{timestamp}]** 灵知AI：{text}"
    streaming_logs.append(log_entry)
    update_streaming_container(log_container, streaming_logs)
```

**Step 3: 修改填充建议阶段的回调函数**

找到类似（约第 427-432 行）：
```python
def on_text_received(timestamp: str, text: str):
    """接收到 AI 文本时的回调"""
    # 添加时间戳前缀
    log_entry = f"**[{timestamp}]** {text}"
    streaming_logs.append(log_entry)
    update_streaming_container(log_container, streaming_logs)
```

修改为：
```python
def on_text_received(timestamp: str, text: str):
    """接收到 AI 文本时的回调"""
    # 添加时间戳和品牌前缀
    log_entry = f"**[{timestamp}]** 灵知AI：{text}"
    streaming_logs.append(log_entry)
    update_streaming_container(log_container, streaming_logs)
```

**Step 4: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 5: 提交修改**

```bash
git add app.py
git commit -m "feat: add '灵知AI:' prefix to streaming log messages

- Add brand prefix after timestamp in log entries
- Apply to both extract-check and filling stages
- Format: [HH:MM:SS] 灵知AI：<message>"
```

---

## Task 3: 修改成功提示文案

**Files:**
- Modify: `app.py` (成功消息文本)

**Step 1: 查找"数据提取成功"文本**

使用 grep 查找：

```bash
grep -n "数据提取成功" app.py
```

**Step 2: 修改成功消息**

找到类似：
```python
st.success("✅ 数据提取成功")
```

修改为：
```python
st.success("✅ 数据提取完成")
```

**Step 3: 检查是否有其他类似的"成功"文案**

查找所有可能需要统一的成功消息：

```bash
grep -n "成功" app.py | grep -v "✅"
```

如果发现其他"xxx成功"的文案，根据语境判断是否需要改为"xxx完成"。

**Step 4: 验证语法**

```bash
python3 -m py_compile app.py
```

预期：无错误

**Step 5: 提交修改**

```bash
git add app.py
git commit -m "refactor: change '数据提取成功' to '数据提取完成'

- Use '完成' instead of '成功' for consistency
- More professional and neutral tone"
```

---

## Task 4: 验证所有修改

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
- [ ] stages 列表已更新（5 个标签）
- [ ] AI 日志有"灵知AI："前缀
- [ ] 成功消息显示"完成"而非"成功"
- [ ] 整体 UI 正常显示

**Step 4: 创建最终提交（如果有遗漏的修改）**

如果在验证中发现需要额外修改的地方，补充修改后：

```bash
git add app.py
git commit -m "chore: final UI text adjustments"
```

---

## 验证清单

- [ ] Task 1: stages 列表已更新
- [ ] Task 2: 2 处回调函数添加"灵知AI："前缀
- [ ] Task 3: "数据提取成功" → "数据提取完成"
- [ ] Task 4: 语法检查通过
- [ ] Task 4: Streamlit 启动正常
- [ ] 所有修改已提交到 Git

---

## 预期修改总结

### 流程进度指示器修改

| 原文案 | 新文案 |
|--------|--------|
| 上传 | 上传调研表 |
| 提取+质量检查 | 数据提取+质量检查 |
| 填充建议 | 数据填充 |
| 计算 | 节能测算 |
| 结果 | 结果展示 |

### 日志前缀修改

| 原格式 | 新格式 |
|--------|--------|
| `[HH:MM:SS] <message>` | `[HH:MM:SS] 灵知AI：<message>` |

### 成功消息修改

| 原文案 | 新文案 |
|--------|--------|
| ✅ 数据提取成功 | ✅ 数据提取完成 |

---

## 注意事项

1. **仅修改文本字符串**：不涉及任何逻辑变更
2. **保持 Emoji 图标**：所有图标保持不变
3. **一致性**：确保所有类似文案使用统一的用词
4. **Git 提交规范**：每个任务独立提交，便于回滚
