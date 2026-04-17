"""
Agent Coordinator - Scout + Sage 协调器
管理双 Agent 的流程协调
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List

from .scout_agent import ScoutAgent
from .sage_agent import SageAgent
from src.utils import get_logger
from src.utils.file_utils import get_ai_temp_dir, write_json
from plugins.base import count_severity

logger = get_logger('agent_coordinator')


class AgentCoordinator:
    """Scout + Sage 协调器"""

    def __init__(self, config_manager, kb_manager=None, log_metadata_manager=None):
        """
        初始化协调器

        Args:
            config_manager: 配置管理器实例
            kb_manager: 知识库管理器实例
            log_metadata_manager: 日志元数据管理器实例
        """
        self.config_manager = config_manager
        self.kb_manager = kb_manager
        self.log_metadata_manager = log_metadata_manager

        self.scout = ScoutAgent(config_manager, log_metadata_manager)
        self.sage = SageAgent(config_manager)

    def extract_machine_info_from_plugins(self, plugin_result: Dict) -> Dict[str, Any]:
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
            'ip_address': '未知',
            'mac_address': '未知'
        }

        # 检查常见的机器信息插件 ID
        info_plugin_ids = ['bmc_info', 'system_info', 'machine_info', 'hardware_info']

        for plugin_id, plugin_data in plugin_result.items():
            # 检查是否是机器信息插件
            if plugin_id in info_plugin_ids or 'info' in plugin_id.lower():
                sections = plugin_data.get('sections', [])
                for section in sections:
                    if section.get('type') == 'stats':
                        for item in section.get('items', []):
                            label = item.get('label', '')
                            value = item.get('value', '')

                            if isinstance(value, str):
                                # 根据标签匹配机器信息字段
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
                                elif 'IP' in label or 'ip_address' in label.lower():
                                    machine_info['ip_address'] = value
                                elif 'MAC' in label or 'mac_address' in label.lower():
                                    machine_info['mac_address'] = value

            # 也检查卡片类型的数据
            sections = plugin_data.get('sections', [])
            for section in sections:
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
                                    elif '型号' in key or 'Model' in key or '机型' in key:
                                        machine_info['model'] = val
                                    elif '产品' in key or 'Product' in key:
                                        machine_info['product_name'] = val
                                    elif '主板' in key or 'Board' in key:
                                        machine_info['board_type'] = val
                                    elif 'BMC' in key and '版本' in key:
                                        machine_info['bmc_version'] = val
                                    elif 'BIOS' in key:
                                        machine_info['bios_version'] = val
                                    elif '固件' in key or 'Firmware' in key:
                                        machine_info['firmware_version'] = val
                                    elif 'IP' in key or 'ip_address' in key.lower():
                                        machine_info['ip_address'] = val
                                    elif 'MAC' in key or 'mac_address' in key.lower():
                                        machine_info['mac_address'] = val

        return machine_info

        return machine_info

    def get_plugin_log_files(self, plugin_result: Dict) -> List[str]:
        """
        获取插件分析涉及的日志文件列表

        Args:
            plugin_result: 插件分析结果

        Returns:
            list: 日志文件路径列表
        """
        log_files = []

        for plugin_id, plugin_data in plugin_result.items():
            meta = plugin_data.get('meta', {})
            files = meta.get('log_files', [])

            if isinstance(files, list):
                log_files.extend(files)
            elif files:  # 兼容旧的单文件格式
                log_files.append(files)

        return list(set(log_files))  # 去重

    def format_plugin_summary(self, plugin_result: Dict) -> str:
        """
        格式化插件分析结果概要

        Args:
            plugin_result: 插件分析结果

        Returns:
            str: 格式化后的概要文本
        """
        summary_lines = []

        for plugin_id, plugin_data in plugin_result.items():
            meta = plugin_data.get('meta', {})
            plugin_name = meta.get('plugin_name', plugin_id)
            sections = plugin_data.get('sections', [])
            counts = count_severity(sections)
            summary_lines.append(
                f"- {plugin_name}: 错误 {counts['errors']} 个, 警告 {counts['warnings']} 个"
            )

        return '\n'.join(summary_lines)

    def get_file_descriptions(self, log_files: List[str], log_rules_id: str = None) -> str:
        """
        获取文件描述信息

        Args:
            log_files: 日志文件列表
            log_rules_id: 规则集 ID

        Returns:
            str: 文件描述文本
        """
        if not self.log_metadata_manager or not log_rules_id:
            return "无文件描述规则"

        return self.log_metadata_manager.get_file_descriptions(log_files, log_rules_id)

    def get_knowledge_content(self, kb_id: str, plugin_result: Dict) -> str:
        """
        获取知识库内容

        Args:
            kb_id: 知识库 ID
            plugin_result: 插件分析结果

        Returns:
            str: 知识库内容
        """
        if not self.kb_manager or not kb_id:
            return ""

        # 根据插件结果中的错误和警告构建查询
        queries = []

        for plugin_id, plugin_data in plugin_result.items():
            sections = plugin_data.get('sections', [])
            for section in sections:
                if section.get('type') == 'table':
                    severity = section.get('severity', '')
                    if severity in ['error', 'warning']:
                        for row in section.get('rows', [])[:3]:
                            message = row.get('message', '')
                            if message:
                                queries.append(message[:100])

        if not queries:
            return ""

        # 搜索知识库
        results = []
        for query in queries[:5]:
            try:
                search_results = self.kb_manager.search(kb_id, query, 2)
                results.extend(search_results)
            except Exception:
                continue

        # 去重并合并
        seen = set()
        content_parts = []
        for result in results:
            chunk = result.get('chunk', {})
            content = chunk.get('content', '')
            if content and content not in seen:
                seen.add(content)
                content_parts.append(content)

        return '\n\n'.join(content_parts)

    def run_analysis(self, plugin_result: Dict, log_files: List[str],
                     kb_id: str = None, user_prompt: str = None,
                     log_rules_id: str = None, actual_log_paths: List[str] = None) -> str:

        logger.debug(f"开始协调分析，日志文件数: {len(log_files)}")

        # 初始化AI交互记录
        ai_interactions = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'scout': None,
            'sage': None
        }

        # 1. 从插件结果提取机器信息
        machine_info = self.extract_machine_info_from_plugins(plugin_result)
        logger.debug(f"提取机器信息: {machine_info}")

        # 2. 获取插件分析的日志文件列表
        plugin_log_files = self.get_plugin_log_files(plugin_result)

        # 3. 获取文件描述信息
        file_descriptions = self.get_file_descriptions(plugin_log_files, log_rules_id)

        # 4. 格式化插件概要
        plugin_summary = self.format_plugin_summary(plugin_result)

        # 5. Scout 侦察日志（使用实际日志路径）
        logger.debug(f"准备调用Scout")
        try:
            scout_data = self.scout.scout_and_extract(
                plugin_summary=plugin_summary,
                machine_info_from_plugins=machine_info,
                log_files=actual_log_paths or [],  # 传绝对路径，让 Scout 能读取内容
                file_descriptions=file_descriptions,
                user_prompt=user_prompt or ""
            )

        except Exception as e:
            logger.error(f"Scout调用异常: {type(e).__name__}: {str(e)}")
            raise

        # 提取侦察结果和AI交互记录
        scout_result = scout_data.get('result')
        if scout_result is None:
            logger.error("Scout返回的result为None")
            scout_result = self.scout.fallback_selection(actual_log_paths or [], plugin_summary)
        ai_interactions['scout'] = scout_data.get('ai_interaction')

        # 验证 scout_result 类型
        if not isinstance(scout_result, dict):
            logger.error(f"scout_result类型错误: {type(scout_result)}, 值: {scout_result}")
            scout_result = {"selected_content": "", "selected_files": [], "reason": "结果类型错误"}

        # 6. 提取日志内容
        selected_files = scout_result.get('selected_files', [])
        selected_content = scout_result.get('selected_content', '')
        logger.debug(f"Scout返回: selected_content长度={len(selected_content)}, selected_files={selected_files}")

        # 如果 Scout 没有返回内容，直接从实际文件读取
        if not selected_content and actual_log_paths:
            selected_content = self.scout.extract_log_content(actual_log_paths, 8000)
            logger.debug(f"从实际文件读取日志内容，长度: {len(selected_content)}")

        # 7. 获取知识库内容
        knowledge_content = self.get_knowledge_content(kb_id, plugin_result)
        if knowledge_content:
            logger.debug(f"知识库内容长度: {len(knowledge_content)}")

        # 8. Sage 分析
        logger.debug("Sage开始深度分析")
        sage_data = self.sage.analyze(
            plugin_result=plugin_result,
            log_content=selected_content,
            machine_info=machine_info,
            knowledge_content=knowledge_content,
            user_prompt=user_prompt or ""
        )

        # 提取HTML结果和AI交互记录
        html_result = sage_data['html']
        ai_interactions['sage'] = sage_data['ai_interaction']

        # 9. 保存AI交互记录到临时目录
        self.save_ai_temp(ai_interactions)

        return html_result

    def save_ai_temp(self, ai_interactions: Dict[str, Any]):
        """
        保存AI交互记录到临时目录

        Args:
            ai_interactions: AI交互记录数据
        """
        try:
            ai_temp_dir = get_ai_temp_dir()
            output_file = os.path.join(ai_temp_dir, 'ai_analysis.json')
            write_json(output_file, ai_interactions)
            logger.debug(f"AI交互记录已保存: {output_file}")
        except Exception as e:
            logger.error(f"保存AI交互记录失败: {str(e)}")