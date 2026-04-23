"""
Sage Agent - 智者
深度分析情报，输出 HTML 报告
支持渐进式披露：按需读取日志内容
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, Any, List
from jinja2 import Template

from .client import AIClient
from src.utils import get_logger
from src.utils.json_parser import parse_ai_json_response

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

    def get_html_prompt_path(self):
        """获取HTML生成prompt文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'sage_html_prompt.txt')

    def load_prompt(self):
        """加载提示词"""
        if os.path.exists(self.prompt_path):
            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        return self.DEFAULT_PROMPT

    def load_html_prompt(self):
        """加载HTML生成prompt（降级方案使用）"""
        html_prompt_path = self.get_html_prompt_path()
        if os.path.exists(html_prompt_path):
            with open(html_prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        # 如果文件不存在，使用内置简化版本
        return self.DEFAULT_HTML_PROMPT

    DEFAULT_HTML_PROMPT = """你之前的JSON响应无法被正确解析，请直接生成HTML报告。

## 分析数据
- 机器信息: {machine_info}
- 插件结果: {plugin_result}
- 日志内容: {log_content}
- 知识库: {knowledge_content}
- 用户请求: {user_prompt}

请直接输出完整的HTML代码，从<!DOCTYPE html>开始。"""

    def read_by_keyword(self, file_path: str, keyword: str,
                        context_lines: int = 20, occurrence: int = 1) -> str:
        """
        根据关键词定位并读取日志上下文

        Args:
            file_path: 日志文件路径
            keyword: 关键词或短语
            context_lines: 上下文行数（前后各取这么多行）
            occurrence: 第几次出现（1表示第一次匹配）

        Returns:
            str: 包含关键词及其上下文的日志片段
        """
        if not os.path.exists(file_path):
            logger.warning(f"文件不存在: {file_path}")
            return f"文件不存在: {file_path}"

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"读取文件失败: {str(e)}")
            return f"读取文件失败: {str(e)}"

        # 查找关键词位置
        matches = []
        for i, line in enumerate(lines):
            if keyword in line:
                matches.append(i)

        if not matches:
            logger.warning(f"未找到关键词 '{keyword}'")
            return f"未找到关键词: {keyword}"

        # 获取指定出现的位置
        target_idx = matches[min(occurrence - 1, len(matches) - 1)]

        # 提取上下文
        start = max(0, target_idx - context_lines)
        end = min(len(lines), target_idx + context_lines + 1)

        result_lines = lines[start:end]
        return ''.join(result_lines)

    def read_key_events(self, scout_summary: Dict, log_files: List[str]) -> List[Dict]:
        """
        根据摘要中的关键事件，按需读取日志内容

        Args:
            scout_summary: Scout生成的摘要
            log_files: 实际日志文件路径列表

        Returns:
            list: 包含详细日志内容的关键事件列表
        """
        enriched_events = []
        key_events = scout_summary.get('key_events', [])

        # 创建文件名到路径的映射
        file_map = {}
        for log_file in log_files:
            file_map[os.path.basename(log_file)] = log_file

        for event in key_events:
            importance = event.get('importance', 'medium')

            # 只读取高优先级事件的详细内容
            if importance != 'high':
                enriched_events.append(event)
                continue

            search_context = event.get('search_context', {})
            file_name = event.get('file', '')

            if not search_context or not file_name:
                enriched_events.append(event)
                continue

            # 查找实际文件路径
            actual_path = file_map.get(file_name)
            if not actual_path:
                # 尝试部分匹配
                for name, path in file_map.items():
                    if file_name in name or name in file_name:
                        actual_path = path
                        break

            if not actual_path:
                logger.warning(f"未找到文件: {file_name}")
                enriched_events.append(event)
                continue

            # 读取关键词上下文
            keyword = search_context.get('keyword', '')
            context_lines = search_context.get('context_lines', 20)
            occurrence = search_context.get('occurrence', 1)

            log_detail = self.read_by_keyword(actual_path, keyword, context_lines, occurrence)

            # 添加详细日志到事件
            enriched_event = event.copy()
            enriched_event['log_detail'] = log_detail
            enriched_events.append(enriched_event)

        return enriched_events

    def analyze_with_summary(self, scout_summary: Dict, plugin_result: Dict,
                             machine_info: Dict, log_files: List[str],
                             knowledge_content: str, user_prompt: str) -> Dict[str, Any]:
        """
        基于摘要进行渐进式分析

        Args:
            scout_summary: Scout生成的结构化摘要
            plugin_result: 插件分析结果
            machine_info: 机器信息
            log_files: 实际日志文件路径列表
            knowledge_content: 知识库内容
            user_prompt: 用户提示词

        Returns:
            dict: 包含html和ai_interaction两个字段
        """
        # 按需读取关键事件的详细日志
        enriched_events = self.read_key_events(scout_summary, log_files)

        # 构建日志内容：将高优先级事件的详细内容合并
        log_content_parts = []
        for event in enriched_events:
            if 'log_detail' in event and event['log_detail']:
                log_content_parts.append(f"=== {event.get('title', '事件')} ===")
                log_content_parts.append(f"文件: {event.get('file', '')}")
                log_content_parts.append(f"类型: {event.get('type', '')}")
                log_content_parts.append(event['log_detail'])
                log_content_parts.append("")

        log_content = '\n'.join(log_content_parts) if log_content_parts else "无关键事件日志内容"

        # 添加整体评估和文件概览作为上下文
        files_overview = scout_summary.get('files_overview', [])
        overall_assessment = scout_summary.get('overall_assessment', '')

        context_info = f"\n### Scout摘要概览\n"
        context_info += f"整体评估: {overall_assessment}\n\n"
        context_info += f"文件分析建议:\n"
        for file_info in files_overview:
            context_info += f"- {file_info.get('file')}: {file_info.get('reason')} (优先级: {file_info.get('priority')})\n"

        # 调用原有analyze方法
        return self.analyze(plugin_result, log_content + context_info, machine_info,
                            knowledge_content, user_prompt)

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
        """
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
            log_content=log_content[:8000] if log_content else "无日志内容",
            knowledge_content=knowledge_content or "无知识库内容",
            user_prompt=user_prompt or "无用户提示词"
        )

        # 调用 AI 获取 JSON 响应
        logger.info("Sage 开始深度分析")
        ai_prompt, response_text, success, error_msg = self.call_ai(prompt)

        if not success:
            html_result = self.generate_error_html("AI调用失败", error_msg)
            return {
                'html': html_result,
                'ai_interaction': {
                    'prompt': ai_prompt,
                    'response': response_text,
                    'success': False,
                    'error': error_msg
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
                    'error': "AI未返回有效分析结果"
                }
            }

        # 解析 JSON 数据
        result, error = parse_ai_json_response(response_text)

        if result is None:  # JSON解析失败，启用降级方案
            logger.warning(f"JSON解析失败，启用HTML直接生成降级方案: {error}")

            # 格式化机器信息（用于降级方案）
            machine_info_str = "暂无机器信息"
            if machine_info:
                machine_info_str = "\n".join([
                    f"- {k}: {v}" for k, v in machine_info.items()
                ])

            # 降级方案：让AI直接生成HTML
            html_result, fallback_interaction = self.generate_html_directly(
                plugin_result=plugin_result,
                log_content=log_content,
                machine_info=machine_info_str,
                knowledge_content=knowledge_content,
                user_prompt=user_prompt,
                original_response=response_text
            )

            return {
                'html': html_result,
                'ai_interaction': {
                    'first_attempt': {
                        'prompt': ai_prompt,
                        'response': response_text,
                        'success': True,
                        'error': error
                    },
                    'fallback': fallback_interaction
                }
            }

        # JSON解析成功，使用模板渲染 HTML
        html_result = self.render_html(result)

        return {
            'html': html_result,
            'ai_interaction': {
                'prompt': ai_prompt,
                'response': response_text,
                'success': True,
                'parsed_result': result
            }
        }

    def generate_html_directly(self, plugin_result: Dict, log_content: str,
                               machine_info: str, knowledge_content: str,
                               user_prompt: str, original_response: str) -> tuple:
        """
        降级方案：让AI直接生成HTML
        当JSON解析失败时，把HTML模板发给AI，让它直接输出HTML

        Args:
            plugin_result: 插件分析结果
            log_content: 日志内容
            machine_info: 格式化的机器信息字符串
            knowledge_content: 知识库内容
            user_prompt: 用户提示词
            original_response: AI第一次的响应（供参考）

        Returns:
            tuple: (html_result, ai_interaction_dict)
        """
        html_prompt_template = self.load_html_prompt()

        prompt = html_prompt_template.format(
            machine_info=machine_info,
            plugin_result=self.format_plugin_result(plugin_result),
            log_content=log_content[:5000] if log_content else "无日志内容",
            knowledge_content=knowledge_content[:2000] if knowledge_content else "无知识库内容",
            user_prompt=user_prompt or "无用户提示词",
            original_response=original_response[:2000]
        )

        logger.info("Sage 降级方案：直接生成HTML")
        ai_prompt, response_text, success, error_msg = self.call_ai(prompt)

        if success and response_text.strip():
            html = self.extract_html(response_text)
            return html, {
                'prompt': ai_prompt,
                'response': response_text,
                'success': True,
                'mode': 'html_direct'
            }

        # 如果降级方案也失败，返回错误HTML
        error_html = self.generate_error_html("HTML生成失败", error_msg)
        return error_html, {
            'prompt': ai_prompt,
            'response': response_text,
            'success': False,
            'error': error_msg,
            'mode': 'html_direct'
        }

    def extract_html(self, response_text: str) -> str:
        """
        从AI响应中提取HTML内容
        处理可能被markdown代码块包裹的情况

        Args:
            response_text: AI的响应文本

        Returns:
            str: 提取的HTML内容
        """
        text = response_text.strip()

        # 尝试从```html代码块提取
        match = re.search(r'```html\s*\n?([\s\S]*?)\n?```', text)
        if match:
            return match.group(1).strip()

        # 尝试从普通代码块提取
        match = re.search(r'```\s*\n?([\s\S]*?)\n?```', text)
        if match and '<!DOCTYPE' in match.group(1):
            return match.group(1).strip()

        # 直接返回（假设AI直接输出了HTML）
        if '<!DOCTYPE' in text or '<html' in text.lower():
            return text

        # 包装成简单HTML
        return f"<html><body><pre>{text}</pre></body></html>"

    def parse_json_response(self, response_text: str) -> Dict:
        """解析 AI 返回的 JSON 数据"""
        result, error = parse_ai_json_response(response_text)

        if result is None:
            logger.error(f"JSON解析失败: {error}")
            return {
                'machine_info': {},
                'summary': {'errors': 0, 'warnings': 0, 'info': 0},
                'problems': [{
                    'title': 'AI 输出解析失败',
                    'severity': 'error',
                    'description': error
                }],
                'solutions': [],
                'log_snippets': [{
                    'title': 'AI原始响应',
                    'content': response_text
                }],
                'risk': {'level': '未知', 'description': '无法解析 AI 响应'}
            }

        return result

    def render_html(self, data: Dict) -> str:
        """使用模板渲染 HTML"""
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
        return self.generate_fallback_html(data)

    def call_ai(self, prompt: str) -> tuple:
        """调用 AI 获取完整响应"""
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
        """格式化插件分析结果"""
        lines = []

        for plugin_id, plugin_data in plugin_result.items():
            meta = plugin_data.get('meta', {})
            lines.append(f"### {meta.get('plugin_name', plugin_id)}")
            lines.append(f"- 分析文件: {meta.get('log_files', [])}")

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
                        display_rows = rows[:50]
                        for i, row in enumerate(display_rows):
                            row_values = []
                            for col in columns:
                                key = col.get('key', '')
                                val = row.get(key, '')
                                if isinstance(val, str) and len(val) > 50:
                                    val = val[:50] + '...'
                                row_values.append(str(val))
                            lines.append(f"  {i+1}: {' | '.join(row_values)}")

                        if len(rows) > 50:
                            lines.append(f"  ... 省略 {len(rows) - 50} 行")

                elif section.get('type') == 'timeline':
                    events = section.get('events', [])
                    lines.append(f"\n时间线: {len(events)} 个事件")
                    for event in events[:30]:
                        ts = event.get('timestamp', '')
                        ev_title = event.get('title', '')
                        sev = event.get('severity', 'info')
                        lines.append(f"  [{ts}] {ev_title} [{sev}]")

                elif section.get('type') == 'cards':
                    cards = section.get('cards', [])
                    lines.append(f"\n卡片: {len(cards)} 张")
                    for card in cards[:20]:
                        lines.append(f"  {card.get('title', '')} [{card.get('severity', 'info')}]")

        return '\n'.join(lines)

    def generate_error_html(self, error_title: str, error_detail: str) -> str:
        """生成错误提示 HTML"""
        if self.template:
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
                    'description': '请检查AI配置或稍后重试',
                    'steps': ['检查API配置', '确认网络连接'],
                    'priority': 'high'
                }],
                log_snippets=[],
                risk={'level': '高', 'description': 'AI分析未能正常完成'},
                analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
        return self.generate_fallback_html({
            'machine_info': {},
            'summary': {'errors': 1, 'warnings': 0, 'info': 0},
            'problems': [{'title': error_title, 'severity': 'error', 'description': error_detail}],
            'solutions': [{'title': '建议操作', 'description': '请检查AI配置', 'steps': [], 'priority': 'high'}],
            'log_snippets': [],
            'risk': {'level': '高', 'description': 'AI分析未能正常完成'}
        })

    def generate_fallback_html(self, data: Dict) -> str:
        """生成备用 HTML"""
        machine_info = data.get('machine_info', {})
        summary = data.get('summary', {'errors': 0, 'warnings': 0, 'info': 0})
        problems = data.get('problems', [])
        solutions = data.get('solutions', [])
        risk = data.get('risk', {'level': '未知', 'description': ''})

        html_parts = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">']
        html_parts.append('<title>AI 日志分析报告</title>')
        html_parts.append('<style>body{font-family:sans-serif;padding:20px;background:#f8f9fa;}')
        html_parts.append('.card{background:white;padding:20px;margin:20px auto;border-radius:8px;max-width:800px;}</style>')
        html_parts.append('</head><body>')

        html_parts.append('<div class="card"><h2>机器信息</h2>')
        if machine_info:
            for k, v in machine_info.items():
                html_parts.append(f'<p>{k}: {v}</p>')
        else:
            html_parts.append('<p>暂无机器信息</p>')
        html_parts.append('</div>')

        html_parts.append('<div class="card"><h2>问题摘要</h2>')
        html_parts.append(f'<p style="color:#dc3545">严重问题: {summary.get("errors", 0)}</p>')
        html_parts.append(f'<p style="color:#ffc107">警告: {summary.get("warnings", 0)}</p>')
        html_parts.append('</div>')

        html_parts.append('<div class="card"><h2>问题详情</h2>')
        for p in problems:
            sev = p.get('severity', 'info')
            color = '#dc3545' if sev == 'error' else '#ffc107' if sev == 'warning' else '#0dcaf0'
            html_parts.append(f'<div style="border-left:4px solid {color};padding:8px;margin:10px 0;">')
            html_parts.append(f'<strong>{p.get("title", "")}</strong>')
            if p.get('description'):
                html_parts.append(f'<br><small>{p["description"][:200]}</small>')
            html_parts.append('</div>')
        html_parts.append('</div>')

        html_parts.append('<div class="card"><h2>解决方案</h2>')
        for s in solutions:
            html_parts.append(f'<h3>{s.get("title", "")}</h3>')
            if s.get('steps'):
                html_parts.append('<ul>')
                for step in s['steps']:
                    html_parts.append(f'<li>{step}</li>')
                html_parts.append('</ul>')
        html_parts.append('</div>')

        html_parts.append('<div class="card"><h2>风险评估</h2>')
        html_parts.append(f'<p>风险等级: <strong>{risk.get("level", "未知")}</strong></p>')
        html_parts.append('</div>')

        html_parts.append('</body></html>')
        return ''.join(html_parts)