"""
Scout Agent - 侦察兵
快速探索日志，生成结构化摘要
"""

import os
import json
import re
from typing import Dict, Any, List

from .client import AIClient
from src.utils import get_logger
from src.utils.json_parser import parse_ai_json_response

logger = get_logger('scout_agent')


class ScoutAgent:
    """侦察兵 Agent - 快速探索日志、生成摘要"""

    DEFAULT_PROMPT = """你是一个敏捷的日志侦察兵 Scout。你的任务是快速探索日志，生成结构化摘要供深度分析使用。

## 插件分析结果概要
{plugin_summary}

## 插件提取的机器信息（来自 BMC 信息插件等）
{machine_info_from_plugins}

## 日志文件描述规则
{file_descriptions}

## 可用日志文件（插件分析的文件列表）
{log_files}

## 日志内容片段
{log_content}

## 用户请求
{user_prompt}

请执行以下任务：
1. 分析插件结果概要，理解已发现的问题类型和数量
2. 根据日志内容和用户请求，识别需要深入分析的关键事件
3. 为每个关键事件生成关键词引用（用于后续按需读取详细内容）

请返回一个 JSON 对象（直接输出 JSON，不要包裹在代码块中），包含以下字段：

- files_overview: 文件分析概览列表，每个元素包含：
  - file: 文件名
  - reason: 该文件需要分析的原因
  - priority: 优先级（1-3，1最高）
  - estimated_relevance: 预估相关性（high/medium/low）

- key_events: 关键事件列表，每个元素包含：
  - type: 事件类型（error/warning/info）
  - title: 事件简述（一句话描述）
  - file: 所在文件名
  - search_context: 关键词定位信息：
    - keyword: 用于定位的关键词或短语
    - context_lines: 建议读取的上下文行数
    - occurrence: 第几次出现（默认1）
  - importance: 重要程度（high/medium/low）

- overall_assessment: 整体问题评估

注意：
- keyword应该是日志中能唯一或较准确定位该事件的关键词
- 优先关注error和warning级别的事件
- 不要自行提取机器信息"""

    @staticmethod
    def _escape_braces(text: str) -> str:
        """转义花括号，防止 format 解析为占位符"""
        if not text:
            return ""
        return text.replace('{', '{{').replace('}', '}}')

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

    def generate_summary(self, plugin_summary: str, machine_info_from_plugins: Dict,
                         log_files: List[str], file_descriptions: str,
                         user_prompt: str, max_retries: int = 4) -> Dict[str, Any]:
        """
        执行侦察任务，生成结构化摘要
        支持JSON解析失败时的重试机制

        Args:
            plugin_summary: 插件分析结果概要
            machine_info_from_plugins: 从插件结果中提取的机器信息
            log_files: 日志文件列表
            file_descriptions: 文件描述信息
            user_prompt: 用户提示词
            max_retries: JSON解析失败时的最大重试次数（默认2次）

        Returns:
            dict: 包含summary和ai_interaction两个字段
                - summary: 结构化摘要，包含 files_overview, key_events, overall_assessment
                - ai_interaction: AI交互记录，包含 prompt和response
        """
        logger.info(f"Scout 开始侦察，日志文件数: {len(log_files)}")
        prompt_template = self.load_prompt()

        # 格式化机器信息
        machine_info_str = "暂无机器信息"
        if machine_info_from_plugins:
            machine_info_str = "\n".join([
                f"- {k}: {v}" for k, v in machine_info_from_plugins.items()
            ])

        # 快速扫描日志内容（减少长度）
        log_content = "无日志内容"
        if log_files:
            log_content = self.quick_scan_logs(log_files, max_length=4000)

        # 显示文件名（不是完整路径）
        log_file_names = [os.path.basename(f) for f in log_files] if log_files else []

        prompt = prompt_template.format(
            plugin_summary=self._escape_braces(plugin_summary),
            machine_info_from_plugins=self._escape_braces(machine_info_str),
            file_descriptions=self._escape_braces(file_descriptions or "无文件描述规则"),
            log_files=self._escape_braces("\n".join(log_file_names) if log_file_names else "无日志文件"),
            log_content=self._escape_braces(log_content),
            user_prompt=self._escape_braces(user_prompt or "无用户提示词")
        )

        # 调用 AI（收集完整响应）
        ai_prompt, response_text = self.call_ai(prompt)

        # 解析 JSON 结果
        summary = self.parse_summary_response(response_text)

        # 重试机制：JSON解析失败时，让AI修正后重新输出
        retry_interactions = []
        retry_count = 0
        while summary is None and retry_count < max_retries:
            retry_count += 1
            logger.debug(f"JSON解析失败(第{retry_count}次重试)")

            # 获取上次的解析错误信息
            result, parse_error = parse_ai_json_response(response_text, ['files_overview', 'key_events'])

            # 记录本次失败的交互
            retry_interactions.append({
                'attempt': retry_count,
                'response': response_text,
                'error': parse_error
            })

            # 构建重试提示词
            retry_prompt = self.build_retry_json_prompt(prompt, response_text, parse_error)
            ai_prompt, response_text = self.call_ai(retry_prompt)

            # 重新尝试解析
            summary = self.parse_summary_response(response_text)

        # 重试全部失败后，使用fallback策略
        if summary is None:
            logger.warning(f"JSON解析重试{max_retries}次后仍失败，使用fallback策略")
            summary = self.fallback_summary(log_files, plugin_summary)

        # 返回摘要和AI交互记录
        ai_interaction = {
            'prompt': ai_prompt,
            'response': response_text,
            'params': {
                'plugin_summary': plugin_summary,
                'machine_info_from_plugins': machine_info_from_plugins,
                'log_files': log_files,
                'file_descriptions': file_descriptions,
                'user_prompt': user_prompt,
                'log_content_preview': log_content[:500] if log_content else ""
            }
        }
        if retry_interactions:
            ai_interaction['retries'] = retry_interactions

        return {
            'summary': summary,
            'ai_interaction': ai_interaction
        }

    def build_retry_json_prompt(self, original_prompt: str, failed_response: str, error: str) -> str:
        """
        构建JSON重试提示词，告诉AI其JSON格式错误并要求修正

        Args:
            original_prompt: 原始提示词
            failed_response: AI失败的响应
            error: 解析错误信息

        Returns:
            str: 重试提示词
        """
        error_preview = failed_response[:2000] if len(failed_response) > 2000 else failed_response

        return f"""你之前的JSON响应无法被正确解析，请检查并修正格式后重新输出。

## 解析错误信息
{error}

## 你之前的响应（有格式错误）
{error_preview}

## 请修正以下问题后重新输出JSON
1. 检查字符串中的特殊字符是否正确转义（双引号用\"，换行用\\n）
2. 确保所有花括号和方括号正确配对
3. 移除任何JSON之外的多余文本或注释
4. 数组和对象最后一项后不要加逗号

请直接输出修正后的完整JSON对象，不要包含任何解释或代码块标记。"""

    def quick_scan_logs(self, log_files: List[str], max_length: int = 4000) -> str:
        """
        快速扫描日志文件，提取关键片段用于AI分析

        Args:
            log_files: 日志文件列表
            max_length: 最大字符长度（减少为4000）

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

    def call_ai(self, prompt: str) -> tuple:
        """
        调用 AI 获取完整响应

        Args:
            prompt: 提示词

        Returns:
            tuple: (提示词, AI响应文本)
        """
        messages = [{"role": "user", "content": prompt}]
        full_response = ""

        try:
            for chunk in self.client.chat(messages):
                full_response += chunk
        except Exception as e:
            logger.error(f"AI调用失败: {str(e)}")

        return prompt, full_response

    def parse_summary_response(self, response_text: str) -> Dict[str, Any]:
        """
        解析摘要响应

        Args:
            response_text: AI 响应文本

        Returns:
            dict: 解析后的摘要，或 None（解析失败时）
        """
        required_fields = ['files_overview', 'key_events']
        result, error = parse_ai_json_response(response_text, required_fields)

        if result is None:
            logger.warning(f"JSON解析失败: {error}")
            return None

        return result

    def fallback_summary(self, log_files: List[str], plugin_summary: str) -> Dict[str, Any]:
        """
        默认摘要策略（AI 解析失败时使用）

        Args:
            log_files: 日志文件列表
            plugin_summary: 插件分析结果概要

        Returns:
            dict: 默认摘要结果
        """
        log_file_names = [os.path.basename(f) for f in log_files] if log_files else []

        return {
            "files_overview": [
                {
                    "file": fname,
                    "reason": "需要分析",
                    "priority": 1,
                    "estimated_relevance": "high"
                }
                for fname in log_file_names[:5]
            ],
            "key_events": [],
            "overall_assessment": "AI摘要生成失败，建议全量分析"
        }

    # 保留旧方法以兼容现有调用
    def scout_and_extract(self, plugin_summary: str, machine_info_from_plugins: Dict,
                           log_files: List[str], file_descriptions: str,
                           user_prompt: str) -> Dict[str, Any]:
        """
        执行侦察任务（兼容旧接口）

        Returns:
            dict: 包含result和ai_interaction两个字段
        """
        data = self.generate_summary(plugin_summary, machine_info_from_plugins,
                                     log_files, file_descriptions, user_prompt)

        # 将summary转换为旧格式result，便于兼容
        summary = data['summary']
        result = {
            "files_overview": summary.get("files_overview", []),
            "key_events": summary.get("key_events", []),
            "overall_assessment": summary.get("overall_assessment", "")
        }

        return {
            'result': result,
            'ai_interaction': data['ai_interaction']
        }

    def extract_log_content(self, log_files: List[str], max_length: int = 8000) -> str:
        """从日志文件提取内容（保留供外部使用）"""
        return self.quick_scan_logs(log_files, max_length)

    def fallback_selection(self, log_files: List[str], plugin_summary: str) -> Dict[str, Any]:
        """默认筛选策略（兼容旧接口）"""
        return self.fallback_summary(log_files, plugin_summary)

    def select_plugins(self, user_prompt: str, plugin_descriptions: str) -> Dict[str, Any]:
        """
        根据用户提示词选择插件

        Args:
            user_prompt: 用户提示词
            plugin_descriptions: 插件描述信息

        Returns:
            dict: 选择结果
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
1. 如果用户请求与特定关键词匹配，选择相关插件
2. 如果用户请求模糊或无明确分析目标，设置 fallback=true
3. 如果用户请求与任何插件能力都不匹配，设置 fallback=true
"""

        response_text = self.call_ai(selection_prompt)
        result = self.parse_summary_response(response_text)

        if result is None:
            return {
                "selected_plugins": [],
                "fallback": True,
                "reason": "AI 响应解析失败，执行全量分析"
            }

        return result