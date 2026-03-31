"""
AI分析器模块
整合插件分析结果、知识库内容，调用AI进行分析
支持流式响应和并行知识库检索
"""

import os
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator, Dict, Any

from .client import AIClient


class AIAnalyzer:
    """AI分析器，支持流式响应和并行检索"""

    def __init__(self, config_manager, kb_manager=None):
        """
        初始化AI分析器

        Args:
            config_manager: 配置管理器实例
            kb_manager: 知识库管理器实例
        """
        self.config_manager = config_manager
        self.kb_manager = kb_manager
        self.client = self.create_client()
        self.default_prompt_path = self.get_default_prompt_path()

    def create_client(self):
        """创建AI客户端"""
        api_config = self.config_manager.get('api', {})
        return AIClient(api_config)

    def get_default_prompt_path(self):
        """获取默认提示词文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'default_prompt.txt')

    def get_prompt_template_path(self):
        """获取提示词模板文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'default_prompt_template.txt')

    def load_default_prompt(self):
        """加载默认提示词，优先使用用户自定义，否则使用模板"""
        # 先尝试加载用户自定义提示词
        if os.path.exists(self.default_prompt_path):
            with open(self.default_prompt_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return content

        # 回退到模板文件
        template_path = self.get_prompt_template_path()
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()

        return ""

    def analyze(self, plugin_result, log_content, kb_id=None, user_prompt=None) -> Generator[str, None, Dict[str, Any]]:
        """
        流式执行AI分析

        Args:
            plugin_result: 插件分析结果
            log_content: 日志内容
            kb_id: 知识库ID
            user_prompt: 用户自定义提示词

        Yields:
            str: AI分析结果的文本片段

        Returns:
            dict: 完整的分析结果（通过生成器的return值）
        """
        # 并行获取知识库内容
        knowledge_content = ""
        if kb_id and self.kb_manager:
            knowledge_content = self.get_knowledge_content(kb_id, plugin_result)

        # 构建提示词
        prompt = self.build_prompt(
            plugin_result=plugin_result,
            log_content=log_content,
            knowledge_content=knowledge_content,
            user_prompt=user_prompt
        )

        # 流式调用AI分析
        full_analysis = []
        for chunk in self.client.analyze(prompt):
            full_analysis.append(chunk)
            yield chunk

        # 构建返回结果
        result = {
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'kb_id': kb_id,
            'plugin_result': plugin_result,
            'analysis': ''.join(full_analysis)
        }
        return result

    def get_knowledge_content(self, kb_id, plugin_result) -> str:
        """
        并行从知识库获取相关内容

        Args:
            kb_id: 知识库ID
            plugin_result: 插件分析结果

        Returns:
            str: 合并后的知识库内容
        """
        # 根据错误信息构建查询
        queries = []

        if plugin_result.get('errors'):
            for err in plugin_result['errors'][:3]:
                msg = err.get('message', '')
                if msg:
                    queries.append(msg)

        if plugin_result.get('warnings'):
            for warn in plugin_result['warnings'][:2]:
                msg = warn.get('message', '')
                if msg:
                    queries.append(msg)

        if not queries:
            return ""

        # 并行搜索知识库
        all_results = []
        max_workers = min(4, len(queries))  # 最多4个并发

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有查询任务
            future_to_query = {
                executor.submit(self.search_kb, kb_id, query, 2): query
                for query in queries
            }

            # 收集结果
            for future in as_completed(future_to_query):
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception:
                    pass  # 忽略单个查询失败

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

    def search_kb(self, kb_id: str, query: str, top_n: int) -> list:
        """
        搜索单个知识库（用于并行调用）

        Args:
            kb_id: 知识库ID
            query: 查询文本
            top_n: 返回数量

        Returns:
            list: 搜索结果
        """
        if self.kb_manager:
            return self.kb_manager.search(kb_id, query, top_n)
        return []

    def build_prompt(self, plugin_result, log_content, knowledge_content, user_prompt):
        """构建分析提示词"""
        # 格式化插件分析结果
        plugin_analysis = self.format_plugin_result(plugin_result)

        # 加载提示词模板
        prompt_template = self.load_default_prompt()

        # 如果用户提供了提示词，使用用户的
        if user_prompt:
            prompt_template = user_prompt

        # 替换占位符
        prompt = prompt_template.replace('{plugin_analysis}', plugin_analysis)
        prompt = prompt.replace('{knowledge_content}', knowledge_content or "无相关知识库内容")
        prompt = prompt.replace('{log_content}', log_content[:5000])  # 限制长度
        prompt = prompt.replace('{user_prompt}', user_prompt or "无额外说明")

        return prompt

    def format_plugin_result(self, result):
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


def analyze_with_ai(config_manager, kb_manager, plugin_result, log_content, kb_id=None, user_prompt=None) -> Generator[str, None, Dict[str, Any]]:
    """
    使用AI分析日志的便捷函数（流式）

    Args:
        config_manager: 配置管理器
        kb_manager: 知识库管理器
        plugin_result: 插件分析结果
        log_content: 日志内容
        kb_id: 知识库ID
        user_prompt: 用户提示词

    Yields:
        str: AI分析结果的文本片段

    Returns:
        dict: 完整分析结果
    """
    analyzer = AIAnalyzer(config_manager, kb_manager)
    return analyzer.analyze(plugin_result, log_content, kb_id, user_prompt)