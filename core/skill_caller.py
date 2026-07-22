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
        callback: Optional[Callable[[str, str], None]] = None,
        max_retries: int = 0
    ) -> Dict[str, Any]:
        """调用 Claude Skill(同步包装器)

        Args:
            skill_name: Skill 名称 (如 "extract-survey-data")
            *args: Skill 参数(文件路径等)
            check_output: 是否检查输出文件
            callback: 回调函数 callback(timestamp, message)，每次 AI 回复时调用
            max_retries: 最大重试次数，用于代码生成类任务(如仿真)，失败后自动修复重试

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
            self._call_skill_async(skill_name, *args, check_output=check_output, callback=callback, max_retries=max_retries)
        )

    async def _call_skill_async(
        self,
        skill_name: str,
        *args,
        check_output: bool = True,
        callback: Optional[Callable[[str, str], None]] = None,
        max_retries: int = 0
    ) -> Dict[str, Any]:
        """调用 Claude Skill(异步实现)

        Args:
            skill_name: Skill 名称
            *args: Skill 参数
            check_output: 是否检查输出文件
            callback: 回调函数，每次收到 AI 回复时调用
            max_retries: 最大重试次数(用于仿真代码生成失败后自动修复)

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

        # 配置 Agent SDK
        # 注意: API key 通过环境变量 ANTHROPIC_API_KEY 传递
        options = ClaudeAgentOptions(
            cwd=str(self.project_root),
            setting_sources=["user", "project"],
            allowed_tools=["Skill", "Read", "Write", "Bash"]
        )

        # 重试循环：支持 Agent 多轮修复代码
        last_error = None
        for attempt in range(max_retries + 1):
            all_messages = []
            ai_responses = []
            
            # 构建 prompt（首次用原始 prompt，重试用修正 prompt）
            if attempt == 0:
                prompt = self._build_prompt(skill_name, *args)
            else:
                prompt = self._build_retry_prompt(skill_name, args, last_error, attempt)
                if callback:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    callback(timestamp, f"🔄 第 {attempt} 次重试修复...")

            try:
                async with asyncio.timeout(self.timeout):
                    async for message in query(prompt=prompt, options=options):
                        all_messages.append(str(message))
                        if isinstance(message, AssistantMessage):
                            for block in message.content:
                                if isinstance(block, TextBlock):
                                    print(f"[AI Response] {block.text}")
                                    ai_responses.append(block.text)
                                    if callback:
                                        timestamp = datetime.now().strftime("%H:%M:%S")
                                        callback(timestamp, block.text)
                                    await asyncio.sleep(0.01)
            except asyncio.TimeoutError as e:
                last_error = f"执行超时(>{self.timeout}秒)"
                if callback:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    callback(timestamp, f"❌ {last_error}")
                if attempt < max_retries:
                    continue
                raise SkillError(f"Skill '{skill_name}' {last_error}") from e
            except Exception as e:
                last_error = str(e)
                if callback:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    callback(timestamp, f"❌ 执行出错: {last_error}")
                if attempt < max_retries:
                    continue
                raise SkillError(f"Skill '{skill_name}' 执行出错: {last_error}") from e

            # 检查输出文件（如果需要）
            output_file = None
            if check_output and len(args) >= 2:
                if skill_name == "suggest-data-filling":
                    if len(args) < 3:
                        raise SkillError(f"Skill '{skill_name}' 需要3个参数")
                    output_file = Path(args[2])
                else:
                    output_file = Path(args[1])

                if output_file and not output_file.exists():
                    # 检查是否是仿真脚本执行失败（需要查找错误信息）
                    last_error = self._extract_execution_error(all_messages, output_file)
                    if attempt < max_retries:
                        if callback:
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            callback(timestamp, f"⚠️ 输出不完整: {last_error[:200]}...")
                        continue
                    raise SkillError(
                        f"Skill 执行完成，但未生成预期的输出文件: {output_file}"
                    )
                
                # 仿真任务特殊检查：args[1] 是目录，检查内部是否有实际输出文件
                if skill_name == "plant-simulation" and len(args) >= 3:
                    task_type = args[2]
                    if task_type in ("new_station", "old_station"):
                        output_dir = Path(args[1])
                        # 检查是否有实际仿真输出文件
                        csv_files = list(output_dir.glob("*.csv"))
                        xlsx_files = list(output_dir.glob("*.xlsx"))
                        if not csv_files and not xlsx_files:
                            # 目录存在但没有输出文件 -> 仿真脚本执行失败
                            last_error = self._extract_execution_error(all_messages, output_dir)
                            if attempt < max_retries:
                                if callback:
                                    timestamp = datetime.now().strftime("%H:%M:%S")
                                    callback(timestamp, f"⚠️ 仿真输出文件缺失，触发重试: {last_error[:200]}...")
                                continue
                            raise SkillError(
                                f"仿真执行失败，输出目录 {output_dir} 中没有生成 CSV/Excel 文件"
                            )

            # 成功！返回结果
            result_text = "\n".join(all_messages)
            return {
                "success": True,
                "ai_responses": ai_responses,
                "all_messages": all_messages,
                "result_text": result_text,
                "attempts": attempt + 1
            }

        # 不应到达这里
        raise SkillError(f"Skill '{skill_name}' 重试 {max_retries} 次后仍然失败")

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
                    f"请生成月度运行组合表格并写入 JSON 文件。\n\n"
                    f"## 输入数据\n{args[0]}\n\n"
                    f"## 输出路径\n{args[1]}\n\n"
                    f"## 任务\n"
                    f"1. 根据输入数据中的运行规律描述，整理为 12 个月的运行组合\n"
                    f"2. 每个月包含：\n"
                    f"   - 工作日运行: on_units(开机台数), load_ratio(负载率), description(描述)\n"
                    f"   - 休息日运行: on_units(开机台数), load_ratio(负载率), description(描述)\n"
                    f"   - 季节: winter/transition/summer\n"
                    f"   - representative_load_ratio: 代表性负载率\n"
                    f"3. 必须使用 Write 工具将结果写入 {args[1]}\n\n"
                    f"## 输出 JSON 格式\n"
                    f'{{"monthly_table": [{{"month": 1, "season": "winter", '
                    f'"weekday_operation": {{"on_units": 0, "load_ratio": 0, "description": "不开机"}}, '
                    f'"weekend_operation": {{"on_units": 0, "load_ratio": 0, "description": "不开机"}}, '
                    f'"representative_load_ratio": 0, "cooling_demand_kw": 0, "note": "冬季"}}]}}\n\n'
                    f"## 重要\n"
                    f"- 必须立即使用 Write 工具写入文件，不要只输出 JSON 文本\n"
                    f"- cooling_demand_kw 可以填 0（后续由代码自动计算）"
                )
            elif task_type in ("new_station", "old_station"):
                mode_desc = "新站房仿真（需求冷量+COP计算）" if task_type == "new_station" else "旧站房仿真（基准+优化对比节能率）"
                report_hint = ""
                if task_type == "old_station":
                    report_hint = (
                        f"\n## 旧站房特别要求\n"
                        f"- 报告标题格式: `# {{项目名称}}中央空调冷站 控制策略优化仿真报告`\n"
                        f"- 报告文件名: `{{项目名称}}_COP性能仿真分析报告.md`\n"
                        f"- 节能率必须与输入中的 target_energy_saving_rate 对齐（误差<1%）\n"
                        f"- 报告内容由 AI 根据仿真数据动态生成，参考七章节结构\n"
                    )
                return (
                    f"请使用 plant-simulation skill 生成并执行冷站仿真代码。\n"
                    f"输入数据(汇总JSON): {args[0]}\n"
                    f"输出目录: {args[1]}\n"
                    f"仿真模式: {mode_desc}\n\n"
                    f"请根据 SKILL.md 规范：\n"
                    f"1. 读取输入JSON中的拓扑、COP数据和工况信息\n"
                    f"2. 生成完整的Python仿真脚本到输出目录\n"
                    f"3. **执行前先用 ast.parse 验证脚本语法**\n"
                    f"4. 语法无误后执行脚本\n"
                    f"5. 确保输出8760h CSV、月度Excel、3张分析图表和Markdown报告\n\n"
                    f"## 代码质量要求\n"
                    f"- 多行文本必须用三引号，禁止在单引号中嵌入未转义的换行\n"
                    f"- 报告内容用列表拼接 + '\\n'.join(lines) 写入\n"
                    f"- 生成脚本后先运行: python -c \"import ast; ast.parse(open('{args[1]}/simulate_*.py').read())\"\n"
                    f"- 语法检查通过后再执行脚本"
                    f"{report_hint}"
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

    def _build_retry_prompt(self, skill_name: str, args: tuple, error_info: str, attempt: int) -> str:
        """构建重试修正 prompt，让 Agent 根据错误信息修复代码"""
        output_dir = str(args[1]) if len(args) >= 2 else "未知"
        
        # 截断错误信息，避免过长
        if len(error_info) > 2000:
            error_info = error_info[:2000] + "\n...(截断)"

        return (
            f"## ❌ 上次仿真执行失败（第 {attempt} 次重试）\n\n"
            f"### 错误信息\n```\n{error_info}\n```\n\n"
            f"### 修复步骤（必须严格执行）\n\n"
            f"1. **用 Read 工具**读取输出目录中的仿真脚本 (`{output_dir}/simulate_*.py`)\n"
            f"2. **定位错误位置**（通常是字符串换行、变量未定义、import缺失）\n"
            f"3. **用 Write 工具直接覆盖修复后的完整脚本**（不要请求权限，直接写入）\n"
            f"4. 用 Bash 执行: `python -c \"import ast; ast.parse(open('{output_dir}/simulate_*.py').read())\"`\n"
            f"5. 语法通过后，用 Bash 执行: `python {output_dir}/simulate_*.py`\n"
            f"6. 确认 {output_dir}/ 目录下生成了 *.csv 和 *.xlsx 文件\n\n"
            f"### 常见错误修复示例\n"
            f"- `SyntaxError: unterminated string literal` → 把 `'...'` 改为 `\"...\"` 或 `'''...'''`\n"
            f"- `NameError` → 检查变量是否在使用前定义\n"
            f"- `ModuleNotFoundError` → 用 try/except 包裹 import，缺失时降级\n\n"
            f"### 重要\n"
            f"- 你有 Write 工具权限，直接修复脚本，不要等待用户授权\n"
            f"- 报告写入必须用: `Path(path).write_text(chr(10).join(lines), encoding='utf-8')`\n"
            f"- 输出目录: {output_dir}"
        )

    def _extract_execution_error(self, all_messages: list, output_file: Path) -> str:
        """从 Agent 消息中提取执行错误信息"""
        error_lines = []
        for msg in all_messages:
            msg_str = str(msg)
            # 查找常见错误模式
            if any(kw in msg_str.lower() for kw in ['error', 'traceback', 'exception', 'failed', 'syntaxerror', 'nameerror', 'typeerror']):
                error_lines.append(msg_str)
        
        if error_lines:
            return "\n".join(error_lines[-5:])  # 取最后 5 条错误相关消息
        
        # 查找输出目录中已生成的脚本文件
        output_dir = output_file.parent if output_file.is_file() else output_file
        script_files = list(output_dir.glob("simulate_*.py")) if output_dir.exists() else []
        
        if script_files:
            return f"脚本已生成但未执行成功。脚本文件: {script_files[0].name}\n输出目录: {output_dir}"
        
        return f"输出文件不存在: {output_file}"