#!/usr/bin/env python3
"""
使用LLM智能提取空压机调研表数据并进行质量检查
"""

import json
import sys
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    import pandas as pd
except ImportError:
    print("错误: 需要安装 pandas 库")
    print("请运行: pip install pandas")
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    print("错误: 需要安装 openpyxl 库")
    print("请运行: pip install openpyxl")
    sys.exit(1)

try:
    from docx import Document
    from docx.table import Table
except ImportError:
    print("警告: python-docx 未安装，Word文档读取功能将不可用")
    Document = None

try:
    from pptx import Presentation
except ImportError:
    print("警告: python-pptx 未安装，PowerPoint文档读取功能将不可用")
    Presentation = None

# LLM相关导入 - 使用Claude Agent SDK的方式
try:
    # 优先使用环境变量配置的AI提供商
    ai_provider = os.getenv('AI_PROVIDER', 'openai')
    
    if ai_provider == 'openai':
        import openai
        from openai import OpenAI
    elif ai_provider == 'anthropic':
        import anthropic
    else:
        # 默认使用openai
        import openai
        from openai import OpenAI
        
except ImportError as e:
    print(f"错误: 需要安装相应的AI库: {str(e)}")
    print("请运行: pip install openai 或 pip install anthropic")
    sys.exit(1)


class LLMDataExtractor:
    """基于LLM的数据提取器"""
    
    def __init__(self):
        """初始化LLM客户端"""
        # 从环境变量获取配置
        self.api_provider = os.getenv('AI_PROVIDER', 'openai')
        
        print(f"🤖 [LLM初始化] 使用AI提供商: {self.api_provider}")
        
        if self.api_provider == 'openai':
            self.client = OpenAI(
                api_key=os.getenv('OPENAI_API_KEY'),
                base_url=os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
            )
            self.model = os.getenv('OPENAI_MODEL', 'gpt-4')
        elif self.api_provider == 'anthropic':
            self.client = anthropic.Anthropic(
                api_key=os.getenv('ANTHROPIC_API_KEY'),
                base_url=os.getenv('ANTHROPIC_BASE_URL')
            )
            self.model = os.getenv('ANTHROPIC_MODEL', 'claude-3-sonnet-20240229')
        else:
            raise ValueError(f"不支持的AI提供商: {self.api_provider}")
        
        print(f"🤖 [LLM初始化] 使用模型: {self.model}")
    
    def extract_text_from_file(self, file_path: str) -> str:
        """从文件中提取文本内容"""
        file_path = Path(file_path)
        file_ext = file_path.suffix.lower()
        
        print(f"📄 [文本提取] 处理文件: {file_path.name} (格式: {file_ext})")
        
        try:
            if file_ext in ['.xlsx', '.xls']:
                return self._extract_text_from_excel(file_path)
            elif file_ext in ['.docx', '.doc']:
                return self._extract_text_from_word(file_path)
            elif file_ext in ['.pptx', '.ppt']:
                return self._extract_text_from_ppt(file_path)
            else:
                raise ValueError(f"不支持的文件格式: {file_ext}")
        except Exception as e:
            print(f"❌ [文本提取] 失败: {str(e)}")
            raise
    
    def _extract_text_from_excel(self, file_path: Path) -> str:
        """从Excel文件提取文本"""
        text_content = []
        
        try:
            # 尝试读取所有工作表
            excel_file = pd.ExcelFile(file_path)
            print(f"📊 [Excel提取] 发现工作表: {excel_file.sheet_names}")
            
            for sheet_name in excel_file.sheet_names:
                print(f"📋 [Excel提取] 处理工作表: {sheet_name}")
                
                # 读取工作表数据
                df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
                
                # 添加工作表标题
                text_content.append(f"\n=== 工作表: {sheet_name} ===\n")
                
                # 转换为文本格式
                for index, row in df.iterrows():
                    row_text = []
                    for col_idx, cell_value in enumerate(row):
                        if pd.notna(cell_value) and str(cell_value).strip():
                            row_text.append(f"列{col_idx+1}: {str(cell_value).strip()}")
                    
                    if row_text:
                        text_content.append(f"行{index+1}: " + " | ".join(row_text))
                
                text_content.append("")  # 空行分隔
            
            result = "\n".join(text_content)
            print(f"📝 [Excel提取] 提取文本长度: {len(result)} 字符")
            return result
            
        except Exception as e:
            raise Exception(f"Excel文件读取失败: {str(e)}")
    
    def _extract_text_from_word(self, file_path: Path) -> str:
        """从Word文档提取文本"""
        if Document is None:
            raise Exception("Word文档读取功能不可用，请安装 python-docx")
        
        text_content = []
        
        try:
            doc = Document(file_path)
            print(f"📄 [Word提取] 发现段落: {len(doc.paragraphs)} 个")
            print(f"📊 [Word提取] 发现表格: {len(doc.tables)} 个")
            
            # 提取段落文本
            for i, paragraph in enumerate(doc.paragraphs):
                if paragraph.text.strip():
                    text_content.append(f"段落{i+1}: {paragraph.text.strip()}")
            
            # 提取表格文本
            for table_idx, table in enumerate(doc.tables):
                text_content.append(f"\n=== 表格{table_idx+1} ===")
                
                for row_idx, row in enumerate(table.rows):
                    row_text = []
                    for col_idx, cell in enumerate(row.cells):
                        if cell.text.strip():
                            row_text.append(f"列{col_idx+1}: {cell.text.strip()}")
                    
                    if row_text:
                        text_content.append(f"行{row_idx+1}: " + " | ".join(row_text))
                
                text_content.append("")  # 空行分隔
            
            result = "\n".join(text_content)
            print(f"📝 [Word提取] 提取文本长度: {len(result)} 字符")
            return result
            
        except Exception as e:
            raise Exception(f"Word文档读取失败: {str(e)}")
    
    def _extract_text_from_ppt(self, file_path: Path) -> str:
        """从PowerPoint文件提取文本"""
        if Presentation is None:
            raise Exception("PowerPoint文档读取功能不可用，请安装 python-pptx")
        
        text_content = []
        
        try:
            prs = Presentation(file_path)
            print(f"📊 [PPT提取] 发现幻灯片: {len(prs.slides)} 张")
            
            for slide_idx, slide in enumerate(prs.slides):
                text_content.append(f"\n=== 幻灯片{slide_idx+1} ===")
                
                # 提取文本框内容
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        text_content.append(f"文本框: {shape.text.strip()}")
                    
                    # 提取表格内容
                    if shape.has_table:
                        table = shape.table
                        text_content.append("表格内容:")
                        
                        for row_idx, row in enumerate(table.rows):
                            row_text = []
                            for col_idx, cell in enumerate(row.cells):
                                if cell.text.strip():
                                    row_text.append(f"列{col_idx+1}: {cell.text.strip()}")
                            
                            if row_text:
                                text_content.append(f"  行{row_idx+1}: " + " | ".join(row_text))
                
                text_content.append("")  # 空行分隔
            
            result = "\n".join(text_content)
            print(f"📝 [PPT提取] 提取文本长度: {len(result)} 字符")
            return result
            
        except Exception as e:
            raise Exception(f"PowerPoint文档读取失败: {str(e)}")
    
    def extract_structured_data(self, text_content: str, original_filename: str = "") -> Dict[str, Any]:
        """使用LLM从文本中提取结构化数据"""
        print(f"🤖 [LLM提取] 开始智能数据提取...")
        
        # 构建提示词
        prompt = self._build_extraction_prompt(text_content, original_filename)
        
        try:
            # 根据不同的AI提供商调用
            if self.api_provider == 'openai':
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个专业的空压机调研表数据提取专家。请仔细分析文档内容，提取所需的结构化数据。"
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,  # 降低随机性，提高一致性
                    max_tokens=4000
                )
                llm_response = response.choices[0].message.content
                
            elif self.api_provider == 'anthropic':
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    temperature=0.1,
                    system="你是一个专业的空压机调研表数据提取专家。请仔细分析文档内容，提取所需的结构化数据。",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )
                llm_response = response.content[0].text
            
            print(f"🤖 [LLM提取] 收到响应，长度: {len(llm_response)} 字符")
            
            # 提取JSON部分
            extracted_data = self._parse_llm_response(llm_response)
            
            print(f"✅ [LLM提取] 数据提取完成")
            return extracted_data
            
        except Exception as e:
            print(f"❌ [LLM提取] 失败: {str(e)}")
            raise Exception(f"LLM数据提取失败: {str(e)}")
    
    def _build_extraction_prompt(self, text_content: str, original_filename: str) -> str:
        """构建数据提取提示词"""
        
        # 截断过长的文本内容
        max_content_length = 8000
        if len(text_content) > max_content_length:
            text_content = text_content[:max_content_length] + "\n...(内容已截断)"
        
        prompt = f"""
请从以下空压机调研表文档中提取结构化数据。

文档名称: {original_filename}

文档内容:
{text_content}

请提取以下字段的信息，如果某个字段在文档中找不到，请设置为null：

## 项目基本信息
- companyName: 企业名称/公司名称
- companyShortName: 企业简称（从企业名称中去掉"有限公司"等后缀）
- projectName: 项目名称（如果没有明确的项目名称，可以基于企业名称生成，如"XX公司空压系统节能项目"）
- projectLocation: 项目所在地/地址
- industryType: 行业类型（如钢铁、化工、制造业等）

## 系统运行参数
- totalAnnualEnergyConsumption: 空压系统年度总用量（单位：万kWh，只提取数值）
- electricityPrice: 平均电价（单位：元/kWh，只提取数值）
- alarmPressureLowerLimit: 现有系统报警压力下限（单位：bar，只提取数值）
- averagePressure: 近14天系统平均压力/运行压力（单位：bar，只提取数值）
- dailyRunningHours: 每天开机时间/日运行时间（单位：小时，只提取数值）
- annualRunningDays: 年运行天数（单位：天，只提取数值）

## 设备清单
equipmentList: 数组，每个设备包含：
- equipmentNumber: 设备编号
- brand: 品牌
- model: 型号
- equipmentType: 设备类型（螺杆式、离心式等）
- manufactureYear: 出厂年份（只提取数值，如2018）
- runningStatus: 运行状态（运行、备用、故障、停用）
- ratedPower: 铭牌功率（单位：kW，只提取数值）
- ratedFlow: 铭牌流量（单位：m³/min，只提取数值）
- station: 所属站房（如"空压一站"、"空压二站"等，如果没有明确说明，可设为"空压站"）

请以JSON格式返回提取的数据，格式如下：

```json
{{
  "companyName": "企业名称",
  "companyShortName": "企业简称",
  "projectName": "项目名称",
  "projectLocation": "项目地址",
  "industryType": "行业类型",
  "totalAnnualEnergyConsumption": 数值或null,
  "electricityPrice": 数值或null,
  "alarmPressureLowerLimit": 数值或null,
  "averagePressure": 数值或null,
  "dailyRunningHours": 数值或null,
  "annualRunningDays": 数值或null,
  "equipmentList": [
    {{
      "equipmentNumber": "设备编号",
      "brand": "品牌",
      "model": "型号",
      "equipmentType": "设备类型",
      "manufactureYear": 数值或null,
      "runningStatus": "运行状态",
      "ratedPower": 数值或null,
      "ratedFlow": 数值或null,
      "station": "所属站房"
    }}
  ]
}}
```

注意事项：
1. 数值字段请只返回纯数字，不要包含单位
2. 如果文档中有多个相似的数值，请选择最合理的一个
3. 设备清单中可能包含多台设备，请全部提取
4. 如果某些信息不明确，可以基于上下文进行合理推断
5. 请确保返回的是有效的JSON格式
"""
        
        return prompt
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析LLM响应，提取JSON数据"""
        
        # 尝试提取JSON部分
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 如果没有找到代码块，尝试直接解析整个响应
            json_str = response.strip()
        
        try:
            data = json.loads(json_str)
            
            # 数据清理和验证
            cleaned_data = self._clean_extracted_data(data)
            return cleaned_data
            
        except json.JSONDecodeError as e:
            print(f"❌ [JSON解析] 失败: {str(e)}")
            print(f"原始响应: {response[:500]}...")
            
            # 尝试修复常见的JSON问题
            try:
                fixed_json = self._fix_json_format(json_str)
                data = json.loads(fixed_json)
                cleaned_data = self._clean_extracted_data(data)
                return cleaned_data
            except:
                raise Exception(f"无法解析LLM响应为有效JSON: {str(e)}")
    
    def _fix_json_format(self, json_str: str) -> str:
        """尝试修复常见的JSON格式问题"""
        
        # 移除可能的前后缀
        json_str = json_str.strip()
        if json_str.startswith('```'):
            json_str = json_str[3:]
        if json_str.endswith('```'):
            json_str = json_str[:-3]
        if json_str.startswith('json'):
            json_str = json_str[4:]
        
        # 移除注释
        json_str = re.sub(r'//.*?\n', '\n', json_str)
        
        # 修复尾随逗号
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        return json_str.strip()
    
    def _clean_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """清理和验证提取的数据"""
        
        # 确保必要字段存在
        required_fields = [
            "companyName", "companyShortName", "projectName", "projectLocation", "industryType",
            "totalAnnualEnergyConsumption", "electricityPrice", "alarmPressureLowerLimit",
            "averagePressure", "dailyRunningHours", "annualRunningDays", "equipmentList"
        ]
        
        for field in required_fields:
            if field not in data:
                data[field] = None
        
        # 清理数值字段
        numeric_fields = [
            "totalAnnualEnergyConsumption", "electricityPrice", "alarmPressureLowerLimit",
            "averagePressure", "dailyRunningHours", "annualRunningDays"
        ]
        
        for field in numeric_fields:
            if data[field] is not None:
                data[field] = self._extract_numeric_value(data[field])
        
        # 清理设备列表
        if data["equipmentList"] and isinstance(data["equipmentList"], list):
            cleaned_equipment = []
            for equipment in data["equipmentList"]:
                if isinstance(equipment, dict):
                    # 确保设备字段完整
                    equipment_fields = ["equipmentNumber", "brand", "model", "equipmentType", "manufactureYear", "runningStatus", "ratedPower", "ratedFlow", "station"]
                    for field in equipment_fields:
                        if field not in equipment:
                            equipment[field] = None
                    
                    # 清理数值字段
                    if equipment["ratedPower"] is not None:
                        equipment["ratedPower"] = self._extract_numeric_value(equipment["ratedPower"])
                    if equipment["ratedFlow"] is not None:
                        equipment["ratedFlow"] = self._extract_numeric_value(equipment["ratedFlow"])
                    if equipment["manufactureYear"] is not None:
                        equipment["manufactureYear"] = self._extract_numeric_value(equipment["manufactureYear"])
                    
                    cleaned_equipment.append(equipment)
            
            data["equipmentList"] = cleaned_equipment
        else:
            data["equipmentList"] = []
        
        # 生成默认值
        if not data["companyShortName"] and data["companyName"]:
            data["companyShortName"] = self._generate_short_name(data["companyName"])
        
        if not data["projectName"] and data["companyShortName"]:
            data["projectName"] = f"{data['companyShortName']}空压系统节能项目"
        
        return data
    
    def _extract_numeric_value(self, value) -> Optional[float]:
        """从字符串中提取数值"""
        if value is None:
            return None
        
        if isinstance(value, (int, float)):
            return float(value)
        
        if isinstance(value, str):
            # 移除常见单位和符号
            value = re.sub(r'[万kWh元/bar小时天℃°C]', '', value)
            value = value.strip()
            
            # 提取数字
            match = re.search(r'(\d+\.?\d*)', value)
            if match:
                return float(match.group(1))
        
        return None
    
    def _generate_short_name(self, company_name: str) -> str:
        """生成企业简称"""
        if not company_name:
            return ""
        
        # 移除常见后缀
        suffixes = ["有限公司", "有限责任公司", "股份有限公司", "集团有限公司", "集团", "公司", "企业"]
        short_name = company_name
        
        for suffix in suffixes:
            if short_name.endswith(suffix):
                short_name = short_name[:-len(suffix)]
                break
        
        return short_name.strip()


def calculate_completeness(extracted_data: Dict[str, Any]) -> float:
    """计算数据完整度"""
    
    # 定义关键字段及其权重
    key_fields = {
        "companyName": 0.1,
        "projectName": 0.05,
        "projectLocation": 0.05,
        "industryType": 0.05,
        "totalAnnualEnergyConsumption": 0.2,  # 高权重
        "electricityPrice": 0.1,
        "alarmPressureLowerLimit": 0.15,  # 高权重
        "averagePressure": 0.15,  # 高权重
        "dailyRunningHours": 0.1,
        "annualRunningDays": 0.05
    }
    
    total_weight = 0
    filled_weight = 0
    
    # 检查项目信息字段
    for field, weight in key_fields.items():
        total_weight += weight
        value = extracted_data.get(field)
        if value is not None and value != "" and str(value).strip() != "":
            filled_weight += weight
    
    # 设备信息权重
    equipment_weight = 0.2
    total_weight += equipment_weight
    
    equipment_list = extracted_data.get("equipmentList", [])
    if equipment_list:
        equipment_completeness = 0
        for equipment in equipment_list:
            equipment_fields = ["equipmentNumber", "brand", "model", "equipmentType", "manufactureYear", "runningStatus", "ratedPower", "ratedFlow"]
            filled_count = 0
            for field in equipment_fields:
                value = equipment.get(field)
                if value is not None and value != "" and str(value).strip() != "":
                    filled_count += 1
            equipment_completeness += filled_count / len(equipment_fields)
        
        # 平均设备完整度
        avg_equipment_completeness = equipment_completeness / len(equipment_list)
        filled_weight += equipment_weight * avg_equipment_completeness
    
    return filled_weight / total_weight if total_weight > 0 else 0


def check_quality_issues(extracted_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """检查数据质量问题"""
    issues = []
    
    # 检查关键字段缺失
    critical_fields = {
        "totalAnnualEnergyConsumption": "空压系统年度总用量",
        "alarmPressureLowerLimit": "系统报警压力下限",
        "averagePressure": "系统平均压力"
    }
    
    for field, field_name in critical_fields.items():
        value = extracted_data.get(field)
        if value is None or value == "":
            issues.append({
                "field": field,
                "severity": "critical",
                "description": f"缺失关键字段: {field_name}",
                "message": f"{field_name}是节能计算的关键参数，必须提供"
            })
    
    # 检查数值范围
    numeric_checks = {
        "electricityPrice": (0.3, 2.0, "电价"),
        "alarmPressureLowerLimit": (2.0, 15.0, "报警压力下限"),
        "averagePressure": (3.0, 20.0, "平均压力"),
        "dailyRunningHours": (1, 24, "每天开机时间"),
        "annualRunningDays": (200, 365, "年运行天数")
    }
    
    for field, (min_val, max_val, field_name) in numeric_checks.items():
        value = extracted_data.get(field)
        if value is not None and isinstance(value, (int, float)):
            if value < min_val or value > max_val:
                issues.append({
                    "field": field,
                    "severity": "medium",
                    "description": f"{field_name}数值异常: {value}",
                    "message": f"{field_name}应在{min_val}-{max_val}范围内"
                })
    
    # 检查设备信息
    equipment_list = extracted_data.get("equipmentList", [])
    if not equipment_list:
        issues.append({
            "field": "equipmentList",
            "severity": "high",
            "description": "未找到设备信息",
            "message": "需要提供空压机设备清单信息"
        })
    else:
        for i, equipment in enumerate(equipment_list):
            # 检查设备功率
            power = equipment.get("ratedPower")
            if power is None:
                issues.append({
                    "field": f"equipmentList[{i}].ratedPower",
                    "severity": "high",
                    "description": f"设备{i+1}缺失铭牌功率",
                    "message": "设备铭牌功率是计算的关键参数"
                })
            elif isinstance(power, (int, float)) and (power < 5 or power > 1000):
                issues.append({
                    "field": f"equipmentList[{i}].ratedPower",
                    "severity": "medium",
                    "description": f"设备{i+1}功率异常: {power}kW",
                    "message": "空压机功率通常在5-1000kW范围内"
                })
    
    return issues


def generate_summary(extracted_data: Dict[str, Any], completeness: float, issues: List[Dict[str, Any]]) -> str:
    """生成质量检查总结"""
    
    percentage = int(completeness * 100)
    
    # 统计问题数量
    critical_count = sum(1 for issue in issues if issue["severity"] == "critical")
    high_count = sum(1 for issue in issues if issue["severity"] == "high")
    medium_count = sum(1 for issue in issues if issue["severity"] == "medium")
    
    # 基础总结
    if not issues:
        return f"数据完整度{percentage}%，未发现数据质量问题。"
    
    # 构建问题描述
    problem_parts = []
    if critical_count > 0:
        problem_parts.append(f"{critical_count}个严重问题")
    if high_count > 0:
        problem_parts.append(f"{high_count}个高优先级问题")
    if medium_count > 0:
        problem_parts.append(f"{medium_count}个中等问题")
    
    problem_desc = "、".join(problem_parts)
    
    if completeness < 0.5:
        return f"数据完整度{percentage}%，数据严重不足。发现{problem_desc}，建议补充完整调研表。"
    elif completeness < 0.8:
        return f"数据完整度{percentage}%，建议补充缺失信息。发现{problem_desc}。"
    else:
        return f"数据完整度{percentage}%，数据质量良好。发现{problem_desc}。"


def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("用法: python extract_air_compressor_data_llm.py <输入文件路径> <输出JSON路径> [原始文件名]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    original_filename = sys.argv[3] if len(sys.argv) > 3 else Path(input_file).name
    
    print(f"🚀 [LLM数据提取] 开始处理文件: {original_filename}")
    print(f"📁 [LLM数据提取] 输入文件: {input_file}")
    print(f"📁 [LLM数据提取] 输出文件: {output_file}")
    
    try:
        # 初始化提取器
        extractor = LLMDataExtractor()
        
        # 提取文本内容
        print(f"📄 [步骤1] 提取文档文本内容...")
        text_content = extractor.extract_text_from_file(input_file)
        
        # 使用LLM提取结构化数据
        print(f"🤖 [步骤2] 使用LLM提取结构化数据...")
        extracted_data = extractor.extract_structured_data(text_content, original_filename)
        
        # 计算完整度
        print(f"📊 [步骤3] 计算数据完整度...")
        completeness = calculate_completeness(extracted_data)
        
        # 质量检查
        print(f"🔍 [步骤4] 进行数据质量检查...")
        issues = check_quality_issues(extracted_data)
        
        # 确定置信度
        if completeness >= 0.8:
            confidence_level = "high"
        elif completeness >= 0.5:
            confidence_level = "medium"
        else:
            confidence_level = "low"
        
        # 生成总结
        summary = generate_summary(extracted_data, completeness, issues)
        
        # 构建结果
        result = {
            "error": False,
            "extracted_data": extracted_data,
            "quality_report": {
                "completeness": round(completeness, 3),
                "confidence_level": confidence_level,
                "issues": issues,
                "summary": summary,
                "need_rejection": False,
                "rejection_reasons": []
            }
        }
        
        # 保存结果
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"✅ [LLM数据提取] 处理完成")
        print(f"📊 数据完整度: {completeness * 100:.1f}%")
        print(f"🎯 置信水平: {confidence_level}")
        print(f"⚠️  问题数量: {len(issues)}")
        print(f"📄 结果已保存到: {output_file}")
        
    except Exception as e:
        print(f"❌ [LLM数据提取] 处理失败: {str(e)}")
        
        # 保存错误结果
        error_result = {
            "error": True,
            "message": f"数据提取失败: {str(e)}",
            "extracted_data": {},
            "quality_report": {
                "completeness": 0.0,
                "confidence_level": "low",
                "issues": [],
                "summary": f"数据提取失败: {str(e)}",
                "need_rejection": True,
                "rejection_reasons": [str(e)]
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        sys.exit(1)


if __name__ == "__main__":
    main()