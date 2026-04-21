"""
Sage Agent - 智者
深度分析情报，输出 HTML 报告
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, Any
from jinja2 import Template

from .client import AIClient
from src.utils import get_logger

logger = get_logger('sage_agent')


class SageAgent:
    """智者 Agent - 深度分析情报并输出 HTML 报告"""

    TEMPLATE_PATH = None

    def __init__(self, config_manager):
        """
        初始化智者 Agent

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        api_config = config_manager.get('api', {})
        self.client = AIClient(api_config)
        self.prompt_path = self.get_prompt_path()
        self.template_path = self.get_template_path()
        self.template = self.load_template()

    def get_template_path(self):
        """获取 HTML 模板文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'plugins', 'renderer', 'ai_report_template.html')

    def load_template(self):
        """加载 HTML 模板"""
        if os.path.exists(self.template_path):
            with open(self.template_path, 'r', encoding='utf-8') as f:
                return Template(f.read())
        return None

    def get_prompt_path(self):
        """获取提示词文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'sage_prompt.txt')

    def load_prompt(self):
        """加载提示词"""
        if os.path.exists(self.prompt_path):
            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        # 默认提示词（JSON 格式）
        return """你是一个智慧的日志分析专家 Sage。根据以下情报进行深度分析并输出结构化的 JSON 数据。

## 机器信息（来自插件分析）
{machine_info}

## 插件分析结果
{plugin_result}

## 筛选的日志内容
{log_content}

## 知识库内容
{knowledge_content}

## 用户请求
{user_prompt}

请根据上述信息，输出一个 JSON 对象，包含以下字段：

1. machine_info: 机器核心信息对象，必须包含以下字段（从插件结果中提取，若插件结果中无相关信息则填"未知"）：
   - serial_number: 序列号
   - model: 机型/型号
   - product_name: 产品名称
   - board_type: 主板类型
   - bmc_version: BMC版本
   - bios_version: BIOS版本
   - firmware_version: 固件版本
   - ip_address: IP地址
   - mac_address: MAC地址（如有）

2. summary: 问题摘要，包含 errors（严重问题数）、warnings（警告数）、info（提示数）
3. problems: 问题列表，每个问题包含 title、severity（error/warning/info）、description、source（可选）
4. solutions: 解决方案列表，每个方案包含 title、description、steps（步骤列表）、priority（high/medium/low）
5. log_snippets: 相关日志片段列表，每个片段包含 title（可选）、content
6. risk: 风险评估，包含 level（高/中/低）、description

直接输出 JSON 对象，不要包含代码块标记或其他解释内容。输出格式示例：
{"machine_info": {"serial_number": "xxx", "model": "xxx", "product_name": "xxx", "board_type": "xxx", "bmc_version": "xxx", "bios_version": "xxx", "firmware_version": "xxx", "ip_address": "xxx", "mac_address": "xxx"}, "summary": {"errors": 0, "warnings": 0, "info": 0}, "problems": [], "solutions": [], "log_snippets": [], "risk": {"level": "低", "description": ""}}"""

    def analyze(self, plugin_result: Dict, log_content: str, machine_info: Dict,
                knowledge_content: str, user_prompt: str) -> Dict[str, Any]:
        """
        执行分析任务，输出 HTML 报告

        Args:
            plugin_result: 插件分析结果
            log_content: 筛选后的日志内容
            machine_info: 机器信息
            knowledge_content: 知识库内容
            user_prompt: 用户提示词

        Returns:
            dict: 包含html和ai_interaction两个字段
                - html: HTML格式的分析报告
                - ai_interaction: AI交互记录，包含prompt和response
        """
        # 构建提示词
        prompt_template = self.load_prompt()

        # 格式化插件结果
        plugin_result_str = self.format_plugin_result(plugin_result)

        # 格式化机器信息
        machine_info_str = "暂无机器信息"
        if machine_info:
            machine_info_str = "\n".join([
                f"- {k}: {v}" for k, v in machine_info.items()
            ])

        prompt = prompt_template.format(
            machine_info=machine_info_str,
            plugin_result=plugin_result_str,
            log_content=log_content[:6000] if log_content else "无日志内容",
            knowledge_content=knowledge_content or "无知识库内容",
            user_prompt=user_prompt or "无用户提示词"
        )

        # 调用 AI 获取 JSON 响应
        logger.info("Sage 开始深度分析")
        ai_prompt, response_text, success, error_msg = self.call_ai(prompt)

        # 检查是否失败
        if not success:
            html_result = self.generate_error_html("AI调用失败", error_msg)
            return {
                'html': html_result,
                'ai_interaction': {
                    'prompt': ai_prompt,
                    'response': response_text,
                    'success': False,
                    'error': error_msg,
                    'params': {
                        'plugin_result': plugin_result,
                        'log_content': log_content,
                        'machine_info': machine_info,
                        'knowledge_content': knowledge_content,
                        'user_prompt': user_prompt
                    }
                }
            }

        if not response_text.strip():
            html_result = self.generate_error_html("AI返回空内容", "AI未返回有效分析结果")
            return {
                'html': html_result,
                'ai_interaction': {
                    'prompt': ai_prompt,
                    'response': response_text,
                    'success': True,
                    'error': "AI未返回有效分析结果",
                    'params': {
                        'plugin_result': plugin_result,
                        'log_content': log_content,
                        'machine_info': machine_info,
                        'knowledge_content': knowledge_content,
                        'user_prompt': user_prompt
                    }
                }
            }

        # 解析 JSON 数据
        analysis_data = self.parse_json_response(response_text)

        # 使用模板渲染 HTML
        html_result = self.render_html(analysis_data)

        return {
            'html': html_result,
            'ai_interaction': {
                'prompt': ai_prompt,
                'response': response_text,
                'success': True,
                'parsed_result': analysis_data,
                'params': {
                    'plugin_result': plugin_result,
                    'log_content': log_content,
                    'machine_info': machine_info,
                    'knowledge_content': knowledge_content,
                    'user_prompt': user_prompt
                }
            }
        }

    def parse_json_response(self, response_text: str) -> Dict:
        """
        解析 AI 返回的 JSON 数据

        Args:
            response_text: AI 响应文本

        Returns:
            dict: 解析后的数据
        """
        # 清理响应文本
        text = response_text.strip()

        # 移除可能的 <think> 标签内容（某些AI模型会输出思考过程）
        think_match = re.search(r'<think>[\s\S]*?</think>', text)
        if think_match:
            text = text.replace(think_match.group(0), '').strip()

        # 移除控制字符（JSON只允许 \t \n \r，其他控制字符必须移除）
        cleaned_text = []
        for char in text:
            code = ord(char)
            if code >= 32 or code in (9, 10, 13):  # 可打印字符或 TAB/LF/CR
                cleaned_text.append(char)
        text = ''.join(cleaned_text)

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 markdown 代码块中的 JSON
        code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 尝试提取 JSON 对象（使用括号计数法找到第一个完整JSON）
        start_idx = text.find('{')
        if start_idx >= 0:
            brace_count = 0
            end_idx = start_idx
            in_string = False
            escape_next = False

            for i, char in enumerate(text[start_idx:], start_idx):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\' and in_string:
                    escape_next = True
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i
                        break

            if end_idx > start_idx:
                json_str = text[start_idx:end_idx + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # 尝试修复常见问题：末尾多余的逗号
                    json_str_fixed = re.sub(r',\s*}', '}', json_str)
                    json_str_fixed = re.sub(r',\s*]', ']', json_str_fixed)
                    try:
                        return json.loads(json_str_fixed)
                    except json.JSONDecodeError:
                        pass

        # 解析失败，返回默认结构
        logger.error(f"JSON解析失败，响应文本长度: {len(response_text)}")

        # 返回默认结构
        return {
            'machine_info': {},
            'summary': {'errors': 0, 'warnings': 0, 'info': 0},
            'problems': [{'title': 'AI 输出解析失败', 'severity': 'error', 'description': response_text}],
            'solutions': [],
            'log_snippets': [],
            'risk': {'level': '未知', 'description': '无法解析 AI 响应'}
        }

    def render_html(self, data: Dict) -> str:
        """
        使用模板渲染 HTML

        Args:
            data: 分析数据

        Returns:
            str: HTML 内容
        """
        if self.template:
            return self.template.render(
                machine_info=data.get('machine_info', {}),
                summary=data.get('summary', {'errors': 0, 'warnings': 0, 'info': 0}),
                problems=data.get('problems', []),
                solutions=data.get('solutions', []),
                log_snippets=data.get('log_snippets', []),
                risk=data.get('risk', {'level': '未知', 'description': ''}),
                analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

        # 模板不存在时生成基本 HTML
        return self.generate_fallback_html(data)

    def call_ai(self, prompt: str) -> tuple:
        """
        调用 AI 获取完整响应

        Args:
            prompt: 提示词

        Returns:
            tuple: (提示词, 响应文本, 是否成功, 错误信息)
        """
        messages = [{"role": "user", "content": prompt}]
        full_response = ""

        try:
            for chunk in self.client.chat(messages):
                full_response += chunk
            return prompt, full_response, True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error(f"AI调用失败: {error_msg}")
            return prompt, "", False, error_msg

    def format_plugin_result(self, plugin_result: Dict) -> str:
        """
        格式化插件分析结果

        Args:
            plugin_result: 插件分析结果字典

        Returns:
            str: 格式化后的文本
        """
        lines = []

        for plugin_id, plugin_data in plugin_result.items():
            meta = plugin_data.get('meta', {})
            lines.append(f"### {meta.get('plugin_name', plugin_id)}")
            lines.append(f"- 插件ID: {plugin_id}")
            lines.append(f"- 分析文件: {meta.get('log_files', [])}")
            lines.append(f"- 分析时间: {meta.get('analysis_time', '未知')}")

            # 统计信息
            sections = plugin_data.get('sections', [])
            for section in sections:
                if section.get('type') == 'stats':
                    lines.append("\n统计概览:")
                    for item in section.get('items', []):
                        label = item.get('label', '')
                        value = item.get('value', '')
                        unit = item.get('unit', '')
                        severity = item.get('severity', 'info')
                        lines.append(f"  - {label}: {value}{unit} [{severity}]")

                elif section.get('type') == 'table':
                    title = section.get('title', '表格')
                    rows = section.get('rows', [])
                    columns = section.get('columns', [])
                    lines.append(f"\n{title}: {len(rows)} 条记录")

                    if rows:
                        col_labels = [col.get('label', col.get('key', '')) for col in columns]
                        lines.append(f"  列: {', '.join(col_labels)}")

                        # 小数据全传，大数据截断（超过100行）
                        display_rows = rows if len(rows) <= 100 else rows[:100]
                        for i, row in enumerate(display_rows):
                            row_values = []
                            for col in columns:
                                key = col.get('key', '')
                                val = row.get(key, '')
                                if isinstance(val, str) and len(val) > 50:
                                    val = val[:50] + '...'
                                row_values.append(str(val))
                            lines.append(f"  行{i+1}: {' | '.join(row_values)}")

                        if len(rows) > 100:
                            lines.append(f"  ... 省略 {len(rows) - 100} 行")

                elif section.get('type') == 'timeline':
                    title = section.get('title', '时间线')
                    events = section.get('events', [])
                    lines.append(f"\n{title}: {len(events)} 个事件")

                    # 小数据全传，大数据截断（超过50个）
                    display_events = events if len(events) <= 50 else events[:50]
                    for i, event in enumerate(display_events):
                        ts = event.get('timestamp', '')
                        ev_title = event.get('title', '')
                        sev = event.get('severity', 'info')
                        desc = event.get('description', '')
                        lines.append(f"  [{ts}] {ev_title} [{sev}]")
                        if desc:
                            desc_short = desc[:80] + '...' if len(desc) > 80 else desc
                            lines.append(f"    {desc_short}")

                    if len(events) > 50:
                        lines.append(f"  ... 省略 {len(events) - 50} 个事件")

                elif section.get('type') == 'cards':
                    title = section.get('title', '卡片')
                    cards = section.get('cards', [])
                    lines.append(f"\n{title}: {len(cards)} 张卡片")

                    # 小数据全传，大数据截断（超过20张）
                    display_cards = cards if len(cards) <= 20 else cards[:20]
                    for i, card in enumerate(display_cards):
                        card_title = card.get('title', '')
                        sev = card.get('severity', 'info')
                        content = card.get('content', {})
                        lines.append(f"  {card_title} [{sev}]")
                        if content:
                            for key, val in list(content.items())[:10]:
                                if isinstance(val, str) and len(val) > 50:
                                    val = val[:50] + '...'
                                lines.append(f"    {key}: {val}")

                    if len(cards) > 20:
                        lines.append(f"  ... 省略 {len(cards) - 20} 张卡片")

                elif section.get('type') == 'chart':
                    title = section.get('title', '图表')
                    chart_type = section.get('chart_type', 'bar')
                    data = section.get('data', {})
                    labels = data.get('labels', [])
                    values = data.get('values', [])
                    lines.append(f"\n{title} ({chart_type}图):")
                    # 小数据全传，大数据截断（超过50项）
                    display_count = min(len(labels), len(values))
                    display_items = display_count if display_count <= 50 else 50
                    for i in range(display_items):
                        lines.append(f"  {labels[i]}: {values[i]}")
                    if display_count > 50:
                        lines.append(f"  ... 省略 {display_count - 50} 项")

                elif section.get('type') == 'search_box':
                    title = section.get('title', '搜索框')
                    data = section.get('data', [])
                    lines.append(f"\n{title}: {len(data)} 条数据")

                elif section.get('type') == 'raw':
                    title = section.get('title', '原始数据')
                    data = section.get('data', {})
                    lines.append(f"\n{title}:")
                    # 小数据全传，大数据截断（超过20项）
                    items = list(data.items())
                    display_items = items if len(items) <= 20 else items[:20]
                    for key, val in display_items:
                        if isinstance(val, str) and len(val) > 100:
                            val = val[:100] + '...'
                        elif isinstance(val, (list, dict)):
                            val = str(val)[:100] + '...'
                        lines.append(f"  {key}: {val}")
                    if len(items) > 20:
                        lines.append(f"  ... 省略 {len(items) - 20} 项")

        return '\n'.join(lines)

    def generate_error_html(self, error_title: str, error_detail: str) -> str:
        """
        生成错误提示 HTML

        Args:
            error_title: 错误标题
            error_detail: 错误详情

        Returns:
            str: 错误提示 HTML
        """
        if self.template:
            # 使用模板渲染错误状态
            return self.template.render(
                machine_info={},
                summary={'errors': 1, 'warnings': 0, 'info': 0},
                problems=[{
                    'title': error_title,
                    'severity': 'error',
                    'description': error_detail,
                    'source': 'AI分析系统'
                }],
                solutions=[{
                    'title': '建议操作',
                    'description': '请检查AI配置是否正确，或稍后重试',
                    'steps': ['检查API配置（base_url, api_key）', '确认网络连接正常', '查看后台日志获取详细错误信息'],
                    'priority': 'high'
                }],
                log_snippets=[],
                risk={'level': '高', 'description': 'AI分析未能正常完成'},
                analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

        # 备用HTML生成
        return self.generate_fallback_html({
            'machine_info': {},
            'summary': {'errors': 1, 'warnings': 0, 'info': 0},
            'problems': [{'title': error_title, 'severity': 'error', 'description': error_detail}],
            'solutions': [{'title': '建议操作', 'description': '请检查AI配置或稍后重试', 'steps': [], 'priority': 'high'}],
            'log_snippets': [],
            'risk': {'level': '高', 'description': 'AI分析未能正常完成'}
        })

    def generate_fallback_html(self, data: Dict) -> str:
        """
        生成备用 HTML（模板不可用时）

        Args:
            data: 分析数据

        Returns:
            str: HTML 内容
        """
        machine_info = data.get('machine_info', {})
        summary = data.get('summary', {'errors': 0, 'warnings': 0, 'info': 0})
        problems = data.get('problems', [])
        solutions = data.get('solutions', [])
        log_snippets = data.get('log_snippets', [])
        risk = data.get('risk', {'level': '未知', 'description': ''})

        html_parts = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">']
        html_parts.append('<title>AI 日志分析报告</title>')
        html_parts.append('<style>body{font-family:sans-serif;padding:20px;background:#f8f9fa;}')
        html_parts.append('.card{background:white;padding:20px;margin:20px auto;border-radius:8px;max-width:800px;}</style>')
        html_parts.append('</head><body>')

        # 机器信息
        html_parts.append('<div class="card"><h2>机器信息</h2>')
        if machine_info:
            html_parts.append('<table style="width:100%"><tbody>')
            for k, v in machine_info.items():
                html_parts.append(f'<tr><th>{k}</th><td>{v}</td></tr>')
            html_parts.append('</tbody></table>')
        else:
            html_parts.append('<p>暂无机器信息</p>')
        html_parts.append('</div>')

        # 问题摘要
        html_parts.append('<div class="card"><h2>问题摘要</h2>')
        html_parts.append(f'<p style="color:#dc3545">严重问题: {summary.get("errors", 0)}</p>')
        html_parts.append(f'<p style="color:#ffc107">警告: {summary.get("warnings", 0)}</p>')
        html_parts.append('</div>')

        # 问题详情
        html_parts.append('<div class="card"><h2>问题详情</h2>')
        for p in problems:
            html_parts.append(f'<div style="margin:10px 0;border-left:4px solid ')
            sev = p.get('severity', 'info')
            color = '#dc3545' if sev == 'error' else '#ffc107' if sev == 'warning' else '#0dcaf0'
            html_parts.append(f'{color};padding:8px;">')
            html_parts.append(f'<strong>{p.get("title", "")}</strong>')
            if p.get('description'):
                html_parts.append(f'<br><small>{p["description"]}</small>')
            html_parts.append('</div>')
        html_parts.append('</div>')

        # 解决方案
        html_parts.append('<div class="card"><h2>解决方案</h2>')
        for s in solutions:
            html_parts.append(f'<h3>{s.get("title", "")}</h3>')
            if s.get('description'):
                html_parts.append(f'<p>{s["description"]}</p>')
            if s.get('steps'):
                html_parts.append('<ul>')
                for step in s['steps']:
                    html_parts.append(f'<li>{step}</li>')
                html_parts.append('</ul>')
        html_parts.append('</div>')

        # 风险评估
        html_parts.append('<div class="card"><h2>风险评估</h2>')
        level = risk.get('level', '未知')
        html_parts.append(f'<p>风险等级: <strong>{level}</strong></p>')
        if risk.get('description'):
            html_parts.append(f'<p>{risk["description"]}</p>')
        html_parts.append('</div>')

        html_parts.append('</body></html>')
        return ''.join(html_parts)