"""
AI分析器模块
整合插件分析结果、知识库内容，调用AI进行分析
"""

import os
import json
from datetime import datetime

from .client import AIClient


class AIAnalyzer:
    """AI分析器"""

    def __init__(self, config_manager, kb_manager=None):
        """
        初始化AI分析器

        Args:
            config_manager: 配置管理器实例
            kb_manager: 知识库管理器实例
        """
        self.config_manager = config_manager
        self.kb_manager = kb_manager
        self.client = self._create_client()
        self.default_prompt_path = self._get_default_prompt_path()

    def _create_client(self):
        """创建AI客户端"""
        api_config = self.config_manager.get('api', {})
        return AIClient(api_config)

    def _get_default_prompt_path(self):
        """获取默认提示词文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'default_prompt.txt')

    def _load_default_prompt(self):
        """加载默认提示词"""
        if os.path.exists(self.default_prompt_path):
            with open(self.default_prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    def analyze(self, plugin_result, log_content, kb_id=None, user_prompt=None):
        """
        执行AI分析

        Args:
            plugin_result: 插件分析结果
            log_content: 日志内容
            kb_id: 知识库ID
            user_prompt: 用户自定义提示词

        Returns:
            dict: 分析结果
        """
        # 获取知识库内容
        knowledge_content = ""
        if kb_id and self.kb_manager:
            knowledge_content = self._get_knowledge_content(kb_id, plugin_result)

        # 构建提示词
        prompt = self._build_prompt(
            plugin_result=plugin_result,
            log_content=log_content,
            knowledge_content=knowledge_content,
            user_prompt=user_prompt
        )

        # 调用AI分析
        analysis_result = self.client.analyze(prompt)

        # 构建返回结果
        return {
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'kb_id': kb_id,
            'plugin_result': plugin_result,
            'analysis': analysis_result
        }

    def _get_knowledge_content(self, kb_id, plugin_result):
        """从知识库获取相关内容"""
        # 根据错误信息构建查询
        queries = []

        if plugin_result.get('errors'):
            for err in plugin_result['errors'][:3]:
                queries.append(err.get('message', ''))

        if plugin_result.get('warnings'):
            for warn in plugin_result['warnings'][:2]:
                queries.append(warn.get('message', ''))

        # 搜索知识库
        all_results = []
        for query in queries:
            if query:
                results = self.kb_manager.search(kb_id, query, top_n=2)
                all_results.extend(results)

        # 去重并合并
        seen = set()
        content_parts = []
        for result in all_results:
            chunk = result.get('chunk', {})
            content = chunk.get('content', '')
            if content and content not in seen:
                seen.add(content)
                content_parts.append(content)

        return '\n\n'.join(content_parts)

    def _build_prompt(self, plugin_result, log_content, knowledge_content, user_prompt):
        """构建分析提示词"""
        # 格式化插件分析结果
        plugin_analysis = self._format_plugin_result(plugin_result)

        # 加载提示词模板
        prompt_template = self._load_default_prompt()

        # 如果用户提供了提示词，使用用户的
        if user_prompt:
            prompt_template = user_prompt

        # 替换占位符
        prompt = prompt_template.replace('{plugin_analysis}', plugin_analysis)
        prompt = prompt.replace('{knowledge_content}', knowledge_content or "无相关知识库内容")
        prompt = prompt.replace('{log_content}', log_content[:5000])  # 限制长度
        prompt = prompt.replace('{user_prompt}', user_prompt or "无额外说明")

        return prompt

    def _format_plugin_result(self, result):
        """格式化插件分析结果"""
        lines = []
        lines.append(f"日志文件: {result.get('log_file', '未知')}")
        lines.append(f"分析时间: {result.get('analysis_time', '未知')}")
        lines.append(f"错误数量: {result.get('error_count', 0)}")
        lines.append(f"警告数量: {result.get('warning_count', 0)}")

        stats = result.get('statistics', {})
        lines.append(f"总行数: {stats.get('total_lines', 0)}")
        lines.append(f"错误率: {stats.get('error_rate', 0):.6f}")

        if result.get('errors'):
            lines.append("\n错误列表:")
            for i, err in enumerate(result['errors'][:5], 1):
                lines.append(f"  {i}. [{err.get('level', 'ERROR')}] {err.get('message', '')[:100]}")

        if result.get('warnings'):
            lines.append("\n警告列表:")
            for i, warn in enumerate(result['warnings'][:5], 1):
                lines.append(f"  {i}. [{warn.get('level', 'WARN')}] {warn.get('message', '')[:100]}")

        return '\n'.join(lines)

    def save_result(self, result, output_path):
        """保存分析结果"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=4)


def analyze_with_ai(config_manager, kb_manager, plugin_result, log_content, kb_id=None, user_prompt=None):
    """
    使用AI分析日志的便捷函数

    Args:
        config_manager: 配置管理器
        kb_manager: 知识库管理器
        plugin_result: 插件分析结果
        log_content: 日志内容
        kb_id: 知识库ID
        user_prompt: 用户提示词

    Returns:
        dict: 分析结果
    """
    analyzer = AIAnalyzer(config_manager, kb_manager)
    return analyzer.analyze(plugin_result, log_content, kb_id, user_prompt)