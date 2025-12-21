"""Skill 调用封装

提供统一的 Skill 调用接口,处理超时和错误
"""
import subprocess
from pathlib import Path
from typing import Optional


class SkillError(Exception):
    """Skill 调用错误"""
    pass


class SkillCaller:
    """Skill 调用器"""

    def __init__(self, timeout: int = 300):
        """初始化 Skill 调用器

        Args:
            timeout: 调用超时时间(秒)
        """
        self.timeout = timeout

    def call_skill(
        self,
        skill_name: str,
        *args,
        check_output: bool = True
    ) -> Optional[str]:
        """调用 Claude CLI Skill

        Args:
            skill_name: Skill 名称 (如 "extract-survey-data")
            *args: Skill 参数
            check_output: 是否检查输出文件

        Returns:
            Skill 的 stdout 输出

        Raises:
            SkillError: Skill 调用失败
        """
        # 检查 Skill 文件是否存在
        skill_path = Path(f".claude/skills/{skill_name}.md")
        if not skill_path.exists():
            raise SkillError(f"Skill not found: {skill_name}")

        try:
            # 调用 Claude CLI
            result = subprocess.run(
                ['claude', 'skill', skill_name] + list(args),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True
            )

            return result.stdout

        except subprocess.TimeoutExpired as e:
            raise SkillError(
                f"Skill '{skill_name}' 执行超时(>{self.timeout}秒)"
            ) from e

        except subprocess.CalledProcessError as e:
            raise SkillError(
                f"Skill '{skill_name}' 执行出错: {e.stderr}"
            ) from e

        except FileNotFoundError:
            raise SkillError(
                "Claude CLI not found. Please ensure Claude CLI is installed."
            )
