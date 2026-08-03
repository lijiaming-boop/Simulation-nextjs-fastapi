# packages/ — 复用业务包（占位）

> 状态：**占位**（P1 阶段迁入）
> 上级：[REFACTOR.md](../REFACTOR.md)

将现有业务代码平移至此，让 `apps/api`（FastAPI）与 `app.py`（Streamlit）并行期都能 import。

## 迁移映射

| 目标位置 | 来源 | 迁移时机 |
|---------|-----|---------|
| `packages/core/` | 根目录 `core/` | P1 |
| `packages/config/` | 根目录 `config/` | P1 |
| `packages/skills/` | `.claude/skills/` | P1（保留 `.claude/settings.local.json` 在原位置） |

## 迁移方案

**P1 阶段采用 `git mv` + Python 包路径重定向**：

1. `git mv core packages/core`
2. `git mv config packages/config`
3. `git mv .claude/skills packages/skills`
4. 在项目根添加 `pyproject.toml`，把 `packages/` 作为源码根：
   ```toml
   [tool.setuptools.packages.find]
   where = ["packages"]
   ```
5. 更新 `app.py` 与所有测试的 import：
   - `from core.xxx` → `from packages.core.xxx`
   - `from config.xxx` → `from packages.config.xxx`
6. 更新 `.claude/skills` 引用路径（`core/skill_caller.py` 中的脚本命令）

## 迁移前的约束

- 保持三个包对外的类导出接口不变（SkillCaller / DataFiller / ExcelCalculator / SessionManager / AirCompressorCalculator / CellMapping / TemplateConfig / WeatherService）
- pytest 需要能同时用旧路径与新路径过渡（可用 `sys.path.insert` 或 conftest.py 兼容）
