"""
Skill 调用封装 — 从 Simulation-moudle 复制并适配
使用 Claude Agent SDK 调用 .claude/skills/ 下的 Skill
"""
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable

# ═══════════════════════════════════════════════
# 显式加载项目 .env，覆盖系统环境变量
# 项目的 AI 配置（公司代理/Key）优先于用户个人环境变量
# ═══════════════════════════════════════════════
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _val = _line.split("=", 1)
            os.environ[_key.strip()] = _val.strip()

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock


class SkillError(Exception):
    """Skill 调用错误"""
    pass


class SkillCaller:
    """Skill 调用器（基于 Claude Agent SDK）"""

    def __init__(
        self,
        timeout: int = 300,
        api_key: Optional[str] = None,
        project_root: Optional[Path] = None
    ):
        self.timeout = timeout
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')

        if not self.api_key:
            raise SkillError("ANTHROPIC_API_KEY 环境变量未设置")

        if project_root:
            self.project_root = Path(project_root).resolve()
        else:
            # 默认：当前文件 → core/quote/ → core/ → 项目根目录
            self.project_root = Path(__file__).parent.parent.parent.resolve()

        self.skills_dir = self.project_root / ".claude" / "skills"
        if not self.skills_dir.exists():
            raise SkillError(f"Skills 目录不存在: {self.skills_dir}")

    def call_skill(
        self,
        skill_name: str,
        *args,
        check_output: bool = True,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """调用 Claude Skill（同步包装器）"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self._call_skill_async(skill_name, *args,
                                   check_output=check_output, callback=callback)
        )

    async def _call_skill_async(
        self,
        skill_name: str,
        *args,
        check_output: bool = True,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """调用 Claude Skill（异步实现）"""
        skill_path = self.skills_dir / skill_name
        skill_md = skill_path / "SKILL.md"

        if not skill_md.exists():
            skill_md_old = self.skills_dir / f"{skill_name}.md"
            if not skill_md_old.exists():
                raise SkillError(f"Skill not found: {skill_name}")

        prompt = self._build_prompt(skill_name, *args)

        options = ClaudeAgentOptions(
            cwd=str(self.project_root),
            setting_sources=["user", "project"],
            allowed_tools=["Skill", "Read", "Write", "Bash"]
        )

        all_messages = []
        ai_responses = []

        try:
            async with asyncio.timeout(self.timeout):
                async for message in query(prompt=prompt, options=options):
                    all_messages.append(str(message))

                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                ai_responses.append(block.text)
                                if callback:
                                    timestamp = datetime.now().strftime("%H:%M:%S")
                                    callback(timestamp, block.text)
                                await asyncio.sleep(0.01)

        except asyncio.TimeoutError as e:
            if callback:
                callback(datetime.now().strftime("%H:%M:%S"),
                         f"超时（>{self.timeout}秒）")
            raise SkillError(f"Skill '{skill_name}' 执行超时") from e
        except Exception as e:
            import traceback
            if callback:
                callback(datetime.now().strftime("%H:%M:%S"),
                         f"出错: {str(e)}")
            raise SkillError(f"Skill '{skill_name}' 执行出错: {str(e)}") from e

        result_text = "\n".join(all_messages)

        return {
            "success": True,
            "ai_responses": ai_responses,
            "all_messages": all_messages,
            "result_text": result_text
        }

    def _build_prompt(self, skill_name: str, *args) -> str:
        """构建 Skill 调用提示词"""
        if skill_name == "read-energy-survey":
            if len(args) < 2:
                raise SkillError("需要2个参数: 调研表路径, 输出JSON路径")
            return (
                f"请使用 read-energy-survey skill 读取标准能管项目调研表。\n\n"
                f"调研表路径: {args[0]}\n"
                f"输出JSON路径: {args[1]}\n\n"
                f"步骤:\n"
                f"1. 先用 openpyxl 读取调研表所有非空单元格\n"
                f"2. 按照 SKILL.md 中的单元格映射规则提取数据\n"
                f"3. 输出为 project.json（格式严格按 SKILL.md 要求）\n"
                f"4. 打印提取摘要确认\n\n"
                f"重要：deployment_mode 映射: "
                f"'云端部署'→cloud, '私有部署（我方服务器/工控机）'→private_our, "
                f"'私有部署（客户服务器/工控机）'→private_client"
            )

        # 通用提示词
        params_str = ', '.join(str(arg) for arg in args)
        return (
            f"请使用 {skill_name} skill 完成任务。\n"
            f"参数: {params_str}"
        )
