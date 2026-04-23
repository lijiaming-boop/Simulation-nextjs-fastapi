"""Skill 调用封装(使用 Claude Agent SDK)

提供统一的 Skill 调用接口,使用异步方式调用 Claude Agent SDK
"""
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock


class SkillError(Exception):
    """Skill 调用错误"""
    pass


class SkillCaller:
    """Skill 调用器(基于 Claude Agent SDK)"""

    def __init__(
        self,
        timeout: int = 300,
        api_key: Optional[str] = None,
        project_root: Optional[Path] = None
    ):
        """初始化 Skill 调用器

        Args:
            timeout: 调用超时时间(秒)
            api_key: Anthropic API Key,如果不提供则从环境变量读取
            project_root: 项目根目录,包含 .claude/skills/ 目录

        Raises:
            SkillError: API key 未配置
        """
        self.timeout = timeout
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')

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

    def call_skill(
        self,
        skill_name: str,
        *args,
        check_output: bool = True,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """调用 Claude Skill(同步包装器)

        Args:
            skill_name: Skill 名称 (如 "extract-survey-data")
            *args: Skill 参数(文件路径等)
            check_output: 是否检查输出文件
            callback: 回调函数 callback(timestamp, message)，每次 AI 回复时调用

        Returns:
            包含执行结果的字典，结构如下：
            {
                "success": True,
                "ai_responses": ["AI回复1", "AI回复2", ...],
                "all_messages": ["消息1", "消息2", ...],
                "result_text": "合并的文本"
            }

        Raises:
            SkillError: Skill 调用失败
        """
        # 在新的事件循环中运行异步调用
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self._call_skill_async(skill_name, *args, check_output=check_output, callback=callback)
        )

    async def _call_skill_async(
        self,
        skill_name: str,
        *args,
        check_output: bool = True,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """调用 Claude Skill(异步实现)

        Args:
            skill_name: Skill 名称
            *args: Skill 参数
            check_output: 是否检查输出文件
            callback: 回调函数，每次收到 AI 回复时调用

        Returns:
            包含执行结果的字典

        Raises:
            SkillError: Skill 调用失败
        """
        # 检查 Skill 是否存在
        print(f"🔍 [SkillCaller] 查找技能: {skill_name}")
        skill_path = self.skills_dir / skill_name
        skill_md = skill_path / "SKILL.md"
        print(f"📁 [SkillCaller] 技能路径: {skill_path}")

        # 兼容旧版单文件格式
        if not skill_md.exists():
            skill_md_old = self.skills_dir / f"{skill_name}.md"
            if not skill_md_old.exists():
                print(f"❌ [SkillCaller] 技能未找到: {skill_name}")
                raise SkillError(f"Skill not found: {skill_name}")
            print(f"📄 [SkillCaller] 使用旧版技能文件: {skill_md_old}")
        else:
            print(f"📄 [SkillCaller] 使用新版技能文件: {skill_md}")

        # 构建提示词
        print(f"📝 [SkillCaller] 构建提示词，参数数量: {len(args)}")
        prompt = self._build_prompt(skill_name, *args)
        print(f"📏 [SkillCaller] 提示词长度: {len(prompt)} 字符")
        
        # 检查提示词长度，如果过长则优化
        if len(prompt) > 4000:  # 降低阈值，更早触发优化
            print(f"⚠️  [SkillCaller] 提示词过长，进行优化...")
            prompt = self._optimize_prompt(prompt, skill_name, *args)
            print(f"📏 [SkillCaller] 优化后提示词长度: {len(prompt)} 字符")

        # 配置 Agent SDK
        # 注意: API key 通过环境变量 ANTHROPIC_API_KEY 传递
        print(f"⚙️  [SkillCaller] 配置Agent SDK")
        print(f"   - 工作目录: {self.project_root}")
        print(f"   - 超时时间: {self.timeout}秒")
        print(f"   - API端点: {os.getenv('ANTHROPIC_BASE_URL', '默认')}")
        print(f"   - 模型: {os.getenv('ANTHROPIC_MODEL', '默认')}")
        
        options = ClaudeAgentOptions(
            cwd=str(self.project_root),
            setting_sources=["user", "project"],
            allowed_tools=["Skill", "Read", "Write", "Bash"]
        )

        # 调用 Agent SDK（添加超时控制）
        print(f"🚀 [SkillCaller] 开始调用Claude Agent SDK...")
        all_messages = []
        ai_responses = []
        try:
            async with asyncio.timeout(self.timeout):  # 添加超时控制
                async for message in query(prompt=prompt, options=options):
                    # 收集所有消息的字符串表示
                    all_messages.append(str(message))

                    # 只提取 AssistantMessage 的文本内容
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                # 打印AI响应内容到console（方便调试）
                                print(f"🤖 [AI Response] {block.text}")
                                ai_responses.append(block.text)

                                # 调用回调函数（新增）
                                if callback:
                                    timestamp = datetime.now().strftime("%H:%M:%S")
                                    callback(timestamp, block.text)

                                # 等待一小段时间让 Streamlit 有机会重绘
                                await asyncio.sleep(0.01)
                    else:
                        # 记录其他类型的消息
                        print(f"📨 [Other Message] {type(message).__name__}: {str(message)[:100]}...")

        except asyncio.TimeoutError as e:
            # 错误时也调用回调
            if callback:
                timestamp = datetime.now().strftime("%H:%M:%S")
                callback(timestamp, f"❌ 执行超时（>{self.timeout}秒）")
            raise SkillError(
                f"Skill '{skill_name}' 执行超时(>{self.timeout}秒)"
            ) from e
        except Exception as e:
            # 错误时也调用回调
            if callback:
                timestamp = datetime.now().strftime("%H:%M:%S")
                callback(timestamp, f"❌ 执行出错: {str(type(e).__name__)}: {str(e)}")
                import traceback
                callback(timestamp, f"详细错误信息: {traceback.format_exc()}")
            # 添加更多调试信息
            import traceback
            print(f"调用 Skill '{skill_name}' 时发生错误:")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            print(f"详细堆栈: {traceback.format_exc()}")
            raise SkillError(f"Skill '{skill_name}' 执行出错: {str(e)}") from e

        # 合并结果文本
        result_text = "\n".join(all_messages)
        print(f"✅ [SkillCaller] 技能执行完成")
        print(f"   - 收到消息数: {len(all_messages)}")
        print(f"   - AI回复数: {len(ai_responses)}")
        print(f"   - 总文本长度: {len(result_text)} 字符")

        # 检查输出文件(如果需要)
        if check_output and len(args) >= 2:
            print(f"🔍 [SkillCaller] 检查输出文件...")
            # 根据不同的skill确定输出文件的位置
            if skill_name == "suggest-data-filling":
                # suggest-data-filling: args[0]=输入, args[1]=输入, args[2]=输出
                if len(args) < 3:
                    raise SkillError(
                        f"Skill '{skill_name}' 需要3个参数"
                    )
                output_file = Path(args[2])
            else:
                # 其他skill: args[0]=输入, args[1]=输出
                output_file = Path(args[1])
            
            if not output_file.exists():
                raise SkillError(
                    f"Skill 执行完成,但未生成预期的输出文件: {output_file}"
                )

        # 返回详细结果
        return {
            "success": True,
            "ai_responses": ai_responses,
            "all_messages": all_messages,
            "result_text": result_text
        }

    def _optimize_prompt(self, prompt: str, skill_name: str, *args) -> str:
        """优化过长的提示词"""
        # 对于空压机技能，使用超简化的提示词
        if skill_name == "extract-and-check-data-air-compressor":
            if len(args) < 2:
                raise SkillError(
                    "extract-and-check-data-air-compressor 需要至少2个参数"
                )
            # 使用最简化的命令，减少上下文长度
            cmd = f"python .claude/skills/extract-and-check-data-air-compressor/scripts/extract_and_check_data_air_compressor.py {args[0]} {args[1]}"
            if len(args) >= 3:
                cmd += f" '{args[2]}'"
            
            optimized_prompt = f"请执行以下命令：\n{cmd}\n\n这将提取空压机调研表数据并生成JSON结果。"
            return optimized_prompt
        
        # 对于LLM版本的空压机技能
        elif skill_name == "extract-air-compressor-data-llm":
            if len(args) < 2:
                raise SkillError(
                    "extract-air-compressor-data-llm 需要至少2个参数"
                )
            cmd = f"python .claude/skills/extract-air-compressor-data-llm/scripts/extract_air_compressor_data_llm.py {args[0]} {args[1]}"
            if len(args) >= 3:
                cmd += f" '{args[2]}'"
            
            optimized_prompt = f"执行LLM智能数据提取：\n{cmd}"
            return optimized_prompt
        
        # 对于其他技能，截断过长的内容
        if len(prompt) > 8000:
            return prompt[:7500] + "\n...(内容已截断，请执行相应的脚本)"
        
        return prompt

    def _build_prompt(self, skill_name: str, *args) -> str:
        """构建 Skill 调用提示词

        根据不同的 skill 构建合适的提示词
        """
        if skill_name == "extract-and-check-data":
            if len(args) < 2:
                raise SkillError(
                    "extract-and-check-data 需要至少2个参数: 输入Excel路径, 输出JSON路径, [原始文件名]"
                )
            prompt = (
                f"请使用 extract-and-check-data skill 从调研表中提取数据并进行质量检查。\n"
                f"请使用以下命令执行脚本：\n"
                f"python .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py {args[0]} {args[1]}"
            )
            # 如果提供了原始文件名,添加到提示词中
            if len(args) >= 3:
                prompt += f" {args[2]}"
            prompt += "\n"
            prompt += "请确保输出包含 extracted_data 和 quality_report 两部分。"
            return prompt

        elif skill_name == "extract-survey-data":
            if len(args) < 2:
                raise SkillError(
                    "extract-survey-data 需要2个参数: 输入Excel路径, 输出JSON路径"
                )
            return (
                f"请使用 extract-survey-data skill 从调研表中提取数据。\n"
                f"请使用以下命令执行脚本：\n"
                f"python .claude/skills/extract-survey-data/scripts/extract_survey_data.py {args[0]} {args[1]}\n"
                f"请确保输出为有效的 JSON 格式。"
            )

        elif skill_name == "check-data-quality":
            if len(args) < 2:
                raise SkillError(
                    "check-data-quality 需要2个参数: 提取数据JSON路径, 输出报告路径"
                )
            return (
                f"请使用 check-data-quality skill 检查数据质量。\n"
                f"请使用以下命令执行脚本：\n"
                f"python .claude/skills/check-data-quality/scripts/check_data_quality.py {args[0]} {args[1]}\n"
                f"请生成包含完整率、置信度和问题列表的质量报告。"
            )

        elif skill_name == "suggest-data-filling":
            if len(args) < 3:
                raise SkillError(
                    "suggest-data-filling 需要3个参数: "
                    "提取数据路径, 质量报告路径, 输出建议路径"
                )
            return (
                f"请使用 suggest-data-filling skill 生成数据填充建议。\n"
                f"请使用以下命令执行脚本：\n"
                f"python .claude/skills/suggest-data-filling/scripts/suggest_data_filling.py {args[0]} {args[1]} {args[2]}\n"
                f"请基于季节模式和插值法提供智能填充建议。"
            )

        elif skill_name == "extract-and-check-data-air-compressor":
            if len(args) < 2:
                raise SkillError(
                    "extract-and-check-data-air-compressor 需要至少2个参数: 输入文件路径, 输出JSON路径, [原始文件名]"
                )
            # 使用简化的提示词，减少token消耗
            cmd = f"python .claude/skills/extract-and-check-data-air-compressor/scripts/extract_and_check_data_air_compressor.py {args[0]} {args[1]}"
            if len(args) >= 3:
                cmd += f" '{args[2]}'"
            
            prompt = f"执行空压机数据提取：\n{cmd}\n\n输出JSON包含extracted_data和quality_report。"
            return prompt

        elif skill_name == "extract-air-compressor-data-llm":
            if len(args) < 2:
                raise SkillError(
                    "extract-air-compressor-data-llm 需要至少2个参数: 输入文件路径, 输出JSON路径, [原始文件名]"
                )
            # 使用LLM版本的空压数据提取
             cmd = f"python .claude/skills/extract-air-compressor-data-llm/scripts/extract_air_compressor_data_llm.py {args[0]} {args[1]}"
            if len(args) >= 3:
                cmd += f" '{args[2]}'"
            
            prompt = f"执行LLM智能空压机数据提取：\n{cmd}\n\n使用大语言模型智能识别和提取调研表中的结构化数据。"
            return prompt

        else:
            # 通用提示词
            params_str = ', '.join(str(arg) for arg in args)
            return (
                f"请使用 {skill_name} skill 完成任务。\n"
                f"参数: {params_str}"
            )