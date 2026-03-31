"""
AI 选择 Agent
用于智能选择插件和日志文件
"""

import json
import re
from typing import Dict, List, Any, Optional

from src.ai_analyzer.client import AIClient
from src.log_metadata.manager import LogMetadataManager
from plugins.manager import PluginManager


class SelectionAgent:
    """AI 智能选择 Agent"""

    SELECTION_PROMPT = """
你是一个预处理 Agent，负责根据用户请求选择合适的插件和日志文件进行分析。

## 可用插件
{plugin_descriptions}

## 日志文件
{file_descriptions}

## 用户请求
{user_prompt}

请根据用户请求，选择最适合的插件和日志文件进行分析。

返回 JSON 格式结果（仅返回 JSON，不要包含其他内容）：
```json
{
    "selected_plugins": ["plugin_id_1", "plugin_id_2"],
    "selected_files": ["file_1.log", "file_2.log"],
    "fallback": false,
    "reason": "选择原因的简要说明"
}
```

判断规则：
1. 如果用户请求与特定关键词匹配（如 "内存泄露"、"error"、"传感器" 等），选择相关插件和文件
2. 如果用户请求模糊或无明确分析目标，设置 fallback=true，表示需要全量分析
3. 如果用户请求与任何插件能力或文件关键词都不匹配，设置 fallback=true
4. fallback=true 时，selected_plugins 和 selected_files 包含所有插件和文件
5. 优先选择能解决用户问题的最精简组合，避免冗余分析
"""

    def __init__(self, config_manager, log_metadata_manager: LogMetadataManager,
                 plugin_manager: PluginManager):
        """
        初始化选择 Agent

        Args:
            config_manager: 配置管理器
            log_metadata_manager: 日志元数据管理器
            plugin_manager: 插件管理器
        """
        self.config_manager = config_manager
        self.log_metadata_manager = log_metadata_manager
        self.plugin_manager = plugin_manager

        # 创建 AI 客户端
        api_config = config_manager.get('api', {})
        self.ai_client = AIClient(api_config)

    def select(self, log_files: List[str], user_prompt: str, rules_id: str = None) -> Dict[str, Any]:
        """
        执行智能选择

        Args:
            log_files: 日志文件路径列表
            user_prompt: 用户提示词
            rules_id: 规则集ID，默认使用激活的规则集

        Returns:
            dict: 选择结果，包含 selected_plugins, selected_files, fallback, reason
        """
        # 检查是否有用户提示词
        if not user_prompt or not user_prompt.strip():
            return self.fallback_result(log_files, "无用户提示词，执行全量分析")

        # 检查 API 配置
        if not self.ai_client.base_url or not self.ai_client.api_key:
            return self.fallback_result(log_files, "API 配置不完整，执行全量分析")

        # 获取插件描述
        plugin_descriptions = self.plugin_manager.get_plugins_ai_description()

        # 获取文件描述（使用指定的规则集）
        file_descriptions = self.log_metadata_manager.get_file_descriptions(log_files, rules_id)

        # 构建提示词
        prompt = self.SELECTION_PROMPT.format(
            plugin_descriptions=plugin_descriptions,
            file_descriptions=file_descriptions,
            user_prompt=user_prompt
        )

        try:
            # 调用 AI（非流式）
            response_text = self.call_ai(prompt)

            # 解析 JSON 结果
            result = self.parse_response(response_text, log_files)

            return result

        except Exception as e:
            return self.fallback_result(log_files, f"AI 选择失败: {str(e)}，执行全量分析")

    def call_ai(self, prompt: str) -> str:
        """
        调用 AI 获取完整响应

        Args:
            prompt: 提示词

        Returns:
            str: AI 响应文本
        """
        messages = [{"role": "user", "content": prompt}]
        full_response = ""

        # 使用流式接口但收集完整响应
        for chunk in self.ai_client.chat(messages):
            full_response += chunk

        return full_response

    def parse_response(self, response_text: str, log_files: List[str]) -> Dict[str, Any]:
        """
        解析 AI 响应

        Args:
            response_text: AI 响应文本
            log_files: 原始日志文件列表

        Returns:
            dict: 解析后的选择结果
        """
        # 尝试提取 JSON
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            json_text = json_match.group(1)
        else:
            # 尝试直接解析
            json_text = response_text

        try:
            result = json.loads(json_text.strip())

            # 验证结果格式
            if not isinstance(result, dict):
                return self.fallback_result(log_files, "响应格式错误")

            # 检查 fallback
            if result.get('fallback', False):
                return self.fallback_result(log_files, result.get('reason', '用户请求不明确'))

            # 验证选择的插件
            selected_plugins = result.get('selected_plugins', [])
            all_plugin_ids = [p.id for p in self.plugin_manager.get_all_plugins()]
            valid_plugins = [p for p in selected_plugins if p in all_plugin_ids]

            if not valid_plugins:
                return self.fallback_result(log_files, "未选择有效插件，执行全量分析")

            # 验证选择的文件
            selected_files = result.get('selected_files', [])
            log_filenames = [self.get_filename(f) for f in log_files]
            valid_files = []

            for selected_file in selected_files:
                # 匹配文件名（支持部分匹配）
                for log_file in log_files:
                    if selected_file in log_file or self.get_filename(log_file) == selected_file:
                        valid_files.append(log_file)
                        break

            if not valid_files:
                return self.fallback_result(log_files, "未选择有效文件，执行全量分析")

            return {
                'selected_plugins': valid_plugins,
                'selected_files': valid_files,
                'fallback': False,
                'reason': result.get('reason', 'AI 选择完成')
            }

        except json.JSONDecodeError:
            return self.fallback_result(log_files, "JSON 解析失败，执行全量分析")

    def get_filename(self, file_path: str) -> str:
        """获取文件名"""
        import os
        return os.path.basename(file_path)

    def fallback_result(self, log_files: List[str], reason: str) -> Dict[str, Any]:
        """
        生成 fallback 结果

        Args:
            log_files: 日志文件列表
            reason: 原因

        Returns:
            dict: fallback 结果
        """
        all_plugin_ids = [p.id for p in self.plugin_manager.get_all_plugins()]

        return {
            'selected_plugins': all_plugin_ids,
            'selected_files': log_files,
            'fallback': True,
            'reason': reason
        }