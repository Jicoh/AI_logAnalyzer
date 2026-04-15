"""
Scout Agent - 侦察兵
快速探索日志，筛选重要内容
"""

import os
import json
import re
from typing import Dict, Any, List

from .client import AIClient


class ScoutAgent:
    """侦察兵 Agent - 快速探索日志、筛选情报"""

    DEFAULT_PROMPT = """你是一个敏捷的日志侦察兵 Scout。你的任务是快速探索日志，筛选出最重要的情报片段。

## 插件分析结果概要
{plugin_summary}

## 插件提取的机器信息（来自 BMC 信息插件等）
{machine_info_from_plugins}

## 日志文件描述规则
{file_descriptions}

## 可用日志文件（插件分析的文件列表）
{log_files}

## 用户请求
{user_prompt}

请执行以下任务：
1. 根据插件结果中的 meta.log_files，筛选出最需要深入分析的日志内容片段
2. 控制筛选的日志总长度在8000字符内
3. 不要自行提取机器信息，机器信息已从插件结果中获取

请返回一个 JSON 对象，格式如下（直接输出 JSON，不要包裹在代码块中）：
{{"selected_content": "筛选的关键日志片段文本内容", "content_range": {{}}, "selected_files": ["file1.log"], "reason": "筛选原因说明"}}"""

    def __init__(self, config_manager, log_metadata_manager=None):
        """
        初始化侦察兵 Agent

        Args:
            config_manager: 配置管理器实例
            log_metadata_manager: 日志元数据管理器实例
        """
        self.config_manager = config_manager
        self.log_metadata_manager = log_metadata_manager
        api_config = config_manager.get('api', {})
        self.client = AIClient(api_config)
        self.prompt_path = self.get_prompt_path()

    def get_prompt_path(self):
        """获取提示词文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'scout_prompt.txt')

    def load_prompt(self):
        """加载提示词"""
        if os.path.exists(self.prompt_path):
            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        return self.DEFAULT_PROMPT

    def scout_and_extract(self, plugin_summary: str, machine_info_from_plugins: Dict,
                           log_files: List[str], file_descriptions: str,
                           user_prompt: str) -> Dict[str, Any]:
        """
        执行侦察任务

        Args:
            plugin_summary: 插件分析结果概要
            machine_info_from_plugins: 从插件结果中提取的机器信息
            log_files: 日志文件列表
            file_descriptions: 文件描述信息
            user_prompt: 用户提示词

        Returns:
            dict: 侦察结果，包含 selected_content, selected_files, reason
        """
        # 构建提示词
        prompt_template = self.load_prompt()

        # 格式化机器信息
        machine_info_str = "暂无机器信息"
        if machine_info_from_plugins:
            machine_info_str = "\n".join([
                f"- {k}: {v}" for k, v in machine_info_from_plugins.items()
            ])

        prompt = prompt_template.format(
            plugin_summary=plugin_summary,
            machine_info_from_plugins=machine_info_str,
            file_descriptions=file_descriptions or "无文件描述规则",
            log_files="\n".join(log_files) if log_files else "无日志文件",
            user_prompt=user_prompt or "无用户提示词"
        )

        # 调用 AI（收集完整响应）
        response_text = self.call_ai(prompt)

        # 解析 JSON 结果
        result = self.parse_response(response_text)

        # 如果解析失败，使用默认筛选策略
        if result is None:
            result = self.fallback_selection(log_files, plugin_summary)

        return result

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

        try:
            for chunk in self.client.chat(messages):
                full_response += chunk
        except Exception as e:
            import traceback
            traceback.print_exc()

        return full_response

    def parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        解析 AI 响应

        Args:
            response_text: AI 响应文本

        Returns:
            dict: 解析后的结果，或 None（解析失败时）
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

            if not isinstance(result, dict):
                return None

            return result

        except json.JSONDecodeError:
            return None

    def fallback_selection(self, log_files: List[str], plugin_summary: str) -> Dict[str, Any]:
        """
        默认筛选策略（AI 解析失败时使用）

        Args:
            log_files: 日志文件列表
            plugin_summary: 插件分析结果概要

        Returns:
            dict: 默认筛选结果
        """
        # 简单策略：返回所有文件的简要摘要
        return {
            "selected_content": "无法智能筛选，建议检查全部日志内容",
            "selected_files": log_files[:3] if log_files else [],
            "reason": "AI 响应解析失败，使用默认策略"
        }

    def extract_log_content(self, log_files: List[str], max_length: int = 8000) -> str:
        """
        从日志文件提取内容

        Args:
            log_files: 日志文件列表
            max_length: 最大字符长度

        Returns:
            str: 合并后的日志内容
        """
        content_parts = []
        total_length = 0

        for log_file in log_files:
            if not os.path.exists(log_file):
                continue

            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                remaining = max_length - total_length
                if remaining <= 0:
                    break

                if len(content) > remaining:
                    content = content[:remaining]

                content_parts.append(f"=== {os.path.basename(log_file)} ===\n{content}")
                total_length += len(content)

            except Exception:
                continue

        return '\n\n'.join(content_parts)

    def select_plugins(self, user_prompt: str, plugin_descriptions: str) -> Dict[str, Any]:
        """
        模式2：根据用户提示词选择插件

        Args:
            user_prompt: 用户提示词
            plugin_descriptions: 插件描述信息

        Returns:
            dict: 选择结果，包含 selected_plugins, fallback, reason
        """
        selection_prompt = f"""
你是一个预处理 Agent，负责根据用户请求选择合适的插件进行分析。

## 可用插件
{plugin_descriptions}

## 用户请求
{user_prompt}

请根据用户请求，选择最适合的插件进行分析。

返回 JSON 格式结果（仅返回 JSON，不要包含其他内容）：
```json
{
    "selected_plugins": ["plugin_id_1", "plugin_id_2"],
    "fallback": false,
    "reason": "选择原因的简要说明"
}
```

判断规则：
1. 如果用户请求与特定关键词匹配（如 "内存泄露"、"error"、"传感器" 等），选择相关插件
2. 如果用户请求模糊或无明确分析目标，设置 fallback=true，表示需要全量分析
3. 如果用户请求与任何插件能力都不匹配，设置 fallback=true
4. fallback=true 时，selected_plugins 包含所有插件
"""

        response_text = self.call_ai(selection_prompt)
        result = self.parse_response(response_text)

        if result is None:
            return {
                "selected_plugins": [],
                "fallback": True,
                "reason": "AI 响应解析失败，执行全量分析"
            }

        return result