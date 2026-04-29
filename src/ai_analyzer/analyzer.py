"""
AI分析器模块
整合插件分析结果、知识库内容，调用AI进行分析
支持流式响应和并行知识库检索
"""

import os
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator, Dict, Any, List

from .client import AIClient
from .log_analyzer_agent import LogAnalyzerAgent
from .mcp_client import MCPClient


def extract_machine_info_from_plugins(plugin_result: Dict) -> Dict[str, Any]:
    """
    从插件结果中提取机器信息

    Args:
        plugin_result: 插件分析结果

    Returns:
        dict: 机器信息字典
    """
    machine_info = {
        'serial_number': '未知',
        'model': '未知',
        'product_name': '未知',
        'board_type': '未知',
        'bmc_version': '未知',
        'bios_version': '未知',
        'firmware_version': '未知',
        'bmc_ip_address': '未知'
    }

    info_plugin_ids = ['bmc_info', 'system_info', 'machine_info', 'hardware_info']

    for plugin_id, plugin_data in plugin_result.items():
        if plugin_id in info_plugin_ids or 'info' in plugin_id.lower():
            sections = plugin_data.get('sections', [])
            for section in sections:
                if section.get('type') == 'stats':
                    for item in section.get('items', []):
                        label = item.get('label', '')
                        value = item.get('value', '')

                        if isinstance(value, str):
                            if '序列号' in label or 'Serial' in label:
                                machine_info['serial_number'] = value
                            elif '型号' in label or 'Model' in label or '机型' in label:
                                machine_info['model'] = value
                            elif '产品' in label or 'Product' in label:
                                machine_info['product_name'] = value
                            elif '主板' in label or 'Board' in label:
                                machine_info['board_type'] = value
                            elif 'BMC' in label and '版本' in label:
                                machine_info['bmc_version'] = value
                            elif 'BIOS' in label:
                                machine_info['bios_version'] = value
                            elif '固件' in label or 'Firmware' in label:
                                machine_info['firmware_version'] = value
                            elif 'IP' in label and 'BMC' in label:
                                machine_info['bmc_ip_address'] = value

                if section.get('type') == 'cards':
                    for card in section.get('cards', []):
                        card_title = card.get('title', '')
                        content = card.get('content', {})

                        if '机器' in card_title or '系统' in card_title or 'BMC' in card_title:
                            metrics = content.get('metrics', {})
                            for key, val in metrics.items():
                                if isinstance(val, str):
                                    if '序列号' in key or 'Serial' in key:
                                        machine_info['serial_number'] = val
                                    elif '型号' in key or 'Model' in key:
                                        machine_info['model'] = val
                                    elif 'BMC' in key and '版本' in key:
                                        machine_info['bmc_version'] = val

    return machine_info


def load_analysis_templates() -> str:
    """
    加载分析模板配置

    Returns:
        str: 格式化的分析模板字符串
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    template_path = os.path.join(project_root, 'config', 'analysis_templates.json')

    if not os.path.exists(template_path):
        return ""

    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        templates = data.get('templates', [])
        lines = []
        for t in templates:
            lines.append(f"### {t.get('problem_type', '未知类型')}")
            keywords = t.get('keywords', [])
            if keywords:
                lines.append(f"关键词: {', '.join(keywords)}")
            logic = t.get('analysis_logic', [])
            if logic:
                lines.append("分析步骤:")
                for step in logic:
                    lines.append(f"  {step}")
            causes = t.get('typical_causes', [])
            if causes:
                lines.append(f"典型原因: {', '.join(causes)}")
            lines.append("")

        return '\n'.join(lines)
    except Exception:
        return ""


def analyze_with_agent(
    config_manager,
    kb_manager,
    log_metadata_manager=None,
    plugin_result: Dict = None,
    log_files: List[str] = None,
    kb_id: str = None,
    user_prompt: str = None,
    log_rules_id: str = None,
    mcp_client: MCPClient = None
) -> Dict[str, Any]:
    """
    使用LogAnalyzerAgent进行分析

    Args:
        config_manager: 配置管理器
        kb_manager: 知识库管理器
        log_metadata_manager: 日志元数据管理器
        plugin_result: 插件分析结果
        log_files: 日志文件路径列表
        kb_id: 知识库ID
        user_prompt: 用户提示词
        log_rules_id: 日志规则ID
        mcp_client: MCP客户端实例（可选，如未提供则自动创建）

    Returns:
        dict: 包含html和interaction_record的结果
    """
    from src.utils.file_utils import get_ai_temp_dir, write_json
    from src.utils import get_logger

    logger = get_logger('analyze_with_agent')

    # 创建MCP客户端（如果未提供）
    if mcp_client is None:
        mcp_config = config_manager.get('mcp_servers', {})
        if mcp_config:
            try:
                mcp_client = MCPClient(config_manager)
                logger.info(f"MCP客户端已创建，状态: {mcp_client.get_server_status()}")
            except Exception as e:
                logger.warning(f"创建MCP客户端失败: {str(e)}")
                mcp_client = None

    # 1. 提取机器信息
    machine_info = extract_machine_info_from_plugins(plugin_result or {})

    # 2. 获取日志规则描述
    log_rules = ""
    if log_metadata_manager and log_rules_id:
        try:
            # 获取插件分析的日志文件列表
            plugin_log_files = []
            for plugin_id, plugin_data in (plugin_result or {}).items():
                meta = plugin_data.get('meta', {})
                files = meta.get('log_files', [])
                if isinstance(files, list):
                    plugin_log_files.extend(files)
                elif files:
                    plugin_log_files.append(files)
            plugin_log_files = list(set(plugin_log_files))

            log_rules = log_metadata_manager.get_file_descriptions(plugin_log_files, log_rules_id)
        except Exception as e:
            logger.warning(f"获取日志规则失败: {str(e)}")
            log_rules = "无文件描述规则"
    else:
        log_rules = "无日志规则"

    # 3. 获取知识库内容（基础检索）
    knowledge_content = ""
    if kb_id and kb_manager:
        queries = []
        for plugin_id, plugin_data in (plugin_result or {}).items():
            sections = plugin_data.get('sections', [])
            for section in sections:
                if section.get('type') == 'table':
                    severity = section.get('severity', '')
                    if severity in ['error', 'warning']:
                        for row in section.get('rows', [])[:3]:
                            message = row.get('message', '')
                            if message:
                                queries.append(message[:100])

        if queries:
            try:
                results = []
                for query in queries[:5]:
                    search_results = kb_manager.search(kb_id, query, 2)
                    results.extend(search_results)

                seen = set()
                content_parts = []
                for result in results:
                    chunk = result.get('chunk', {})
                    content = chunk.get('content', '')
                    if content and content not in seen:
                        seen.add(content)
                        content_parts.append(content[:500])

                knowledge_content = '\n\n'.join(content_parts)
            except Exception as e:
                logger.warning(f"知识库检索失败: {str(e)}")

    # 4. 加载分析模板
    analysis_templates = load_analysis_templates()

    # 5. 创建Agent并执行分析
    agent = LogAnalyzerAgent(config_manager, kb_manager, mcp_client)

    result = agent.run_analysis(
        plugin_result=plugin_result or {},
        log_files=log_files or [],
        machine_info=machine_info,
        knowledge_content=knowledge_content,
        log_rules=log_rules,
        analysis_templates=analysis_templates,
        user_prompt=user_prompt or "",
        kb_id=kb_id
    )

    # 6. 保存ai_temp记录
    try:
        ai_temp_dir = get_ai_temp_dir()
        output_file = os.path.join(ai_temp_dir, 'ai_analysis.json')
        write_json(output_file, result.get('interaction_record', {}))
        logger.debug(f"AI交互记录已保存: {output_file}")
    except Exception as e:
        logger.error(f"保存AI交互记录失败: {str(e)}")

    return result


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