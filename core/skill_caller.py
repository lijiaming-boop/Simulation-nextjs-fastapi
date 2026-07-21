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
        skill_path = self.skills_dir / skill_name
        skill_md = skill_path / "SKILL.md"

        # 兼容旧版单文件格式
        if not skill_md.exists():
            skill_md_old = self.skills_dir / f"{skill_name}.md"
            if not skill_md_old.exists():
                raise SkillError(f"Skill not found: {skill_name}")

        # 构建提示词
        prompt = self._build_prompt(skill_name, *args)

        # 配置 Agent SDK
        # 注意: API key 通过环境变量 ANTHROPIC_API_KEY 传递
        options = ClaudeAgentOptions(
            cwd=str(self.project_root),
            setting_sources=["user", "project"],
            allowed_tools=["Skill", "Read", "Write", "Bash"]
        )

        # 调用 Agent SDK（添加超时控制）
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
                                print(f"[AI Response] {block.text}")
                                ai_responses.append(block.text)

                                # 调用回调函数（新增）
                                if callback:
                                    timestamp = datetime.now().strftime("%H:%M:%S")
                                    callback(timestamp, block.text)

                                # 等待一小段时间让 Streamlit 有机会重绘
                                await asyncio.sleep(0.01)

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
                callback(timestamp, f"❌ 执行出错: {str(e)}")
            raise SkillError(f"Skill '{skill_name}' 执行出错: {str(e)}") from e

        # 合并结果文本
        result_text = "\n".join(all_messages)

        # 检查输出文件(如果需要)
        if check_output and len(args) >= 2:
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

        elif skill_name == "plant-simulation":
            if len(args) < 3:
                raise SkillError(
                    "plant-simulation 需要3个参数: "
                    "输入数据路径, 输出路径/目录, 任务类型"
                )
            task_type = args[2]

            if task_type == "extract_topology":
                return (
                    f"请使用 plant-simulation skill 从调研表中提取冷站设备拓扑信息。\n"
                    f"调研表路径: {args[0]}\n"
                    f"输出JSON路径: {args[1]}\n"
                    f"请读取Excel文件，识别冷水主机、冷却泵、冷冻泵、冷却塔和特殊结构信息，"
                    f"按型号汇总台数，输出结构化JSON。"
                )
            elif task_type == "parse_topology":
                return (
                    f"请使用 plant-simulation skill 解析用户输入的设备拓扑描述。\n"
                    f"用户输入文件: {args[0]}\n"
                    f"输出JSON路径: {args[1]}\n"
                    f"请将自然语言描述解析为结构化设备拓扑JSON。"
                )
            elif task_type == "parse_cop_curve":
                return (
                    f"请使用 plant-simulation skill 识别性能曲线图片中的COP数据。\n"
                    f"图片路径: {args[0]}\n"
                    f"输出JSON路径: {args[1]}\n"
                    f"请读取图片，提取冷却水温度×负荷率的二维COP查找表。"
                )
            elif task_type == "generate_operating":
                return (
                    f"请使用 plant-simulation skill 生成月度运行组合表格。\n"
                    f"输入数据: {args[0]}\n"
                    f"输出JSON路径: {args[1]}\n"
                    f"请整理为12个月的冷机运行组合、负载率和冷量需求。"
                )
            elif task_type in ("new_station", "old_station"):
                mode_desc = "新站房仿真（需求冷量+COP计算）" if task_type == "new_station" else "旧站房仿真（基准+优化对比节能率）"
                return (
                    f"请使用 plant-simulation skill 生成并执行冷站仿真代码。\n"
                    f"输入数据(汇总JSON): {args[0]}\n"
                    f"输出目录: {args[1]}\n"
                    f"仿真模式: {mode_desc}\n"
                    f"请根据 SKILL.md 规范：\n"
                    f"1. 读取输入JSON中的拓扑、COP数据和工况信息\n"
                    f"2. 生成完整的Python仿真脚本到输出目录\n"
                    f"3. 执行仿真脚本\n"
                    f"4. 确保输出8760h CSV、月度Excel、3张分析图表和Markdown报告"
                )
            else:
                return (
                    f"请使用 plant-simulation skill 完成任务。\n"
                    f"输入: {args[0]}\n"
                    f"输出: {args[1]}\n"
                    f"任务类型: {task_type}"
                )

        else:
            # 通用提示词
            params_str = ', '.join(str(arg) for arg in args)
            return (
                f"请使用 {skill_name} skill 完成任务。\n"
                f"参数: {params_str}"
            )