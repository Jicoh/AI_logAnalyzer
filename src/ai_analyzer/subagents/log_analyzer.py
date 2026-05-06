"""
Log Analyzer Subagent
日志分析Subagent，支持智能选择和分析两种模式
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base import SubagentBase, SubagentResult
from src.ai_analyzer.log_analyzer_agent import LogAnalyzerAgent
from src.ai_analyzer.client import AIClient
from src.utils import get_logger

logger = get_logger('log_analyzer_subagent')


class LogAnalyzerSubagent(SubagentBase):
    """日志分析Subagent，支持智能选择模式"""

    name = "log_analyzer"
    description = "BMC服务器日志分析，识别问题并提供解决方案"
    capabilities = [
        "日志文件分析",
        "问题识别",
        "风险评估",
        "解决方案推荐",
        "知识库检索",
        "针对性回答用户问题",
        "智能选择插件和文件"
    ]

    # 智能选择提示词
    SELECTION_PROMPT = """
你是一个预处理Agent，负责根据用户请求选择合适的插件和日志文件进行分析。

## 可用插件
{plugin_descriptions}

## 日志文件
{file_descriptions}

## 用户请求
{user_prompt}

请根据用户请求，选择最适合的插件和日志文件进行分析。

返回JSON格式结果（仅返回JSON，不要包含其他内容）：
```json
{
    "selected_plugins": ["plugin_id_1", "plugin_id_2"],
    "selected_files": ["file_1.log", "file_2.log"],
    "fallback": false,
    "reason": "选择原因的简要说明"
}
```

判断规则：
1. 如果用户请求与特定关键词匹配（如"内存泄露"、"error"、"传感器"等），选择相关插件和文件
2. 如果用户请求模糊或无明确分析目标，设置fallback=true，表示需要全量分析
3. 如果用户请求与任何插件能力或文件关键词都不匹配，设置fallback=true
4. fallback=true时，selected_plugins和selected_files包含所有插件和文件
5. 优先选择能解决用户问题的最精简组合，避免冗余分析
"""

    def __init__(self, config_manager=None, kb_manager=None, mcp_client=None,
                 log_metadata_manager=None, plugin_manager=None):
        super().__init__(config_manager, kb_manager, mcp_client)
        self.agent = None
        self.user_intent = None
        self.log_metadata_manager = log_metadata_manager
        self.plugin_manager = plugin_manager

    def init_agent(self, api_config: Dict = None):
        """
        延迟初始化Agent

        Args:
            api_config: 传入的API配置（从context获取），优先级高于config_manager
        """
        if self.agent is None:
            if api_config:
                self.agent = LogAnalyzerAgent(
                    config_manager=self.config_manager,
                    kb_manager=self.kb_manager,
                    mcp_client=self.mcp_client,
                    api_config=api_config
                )
            elif self.config_manager:
                self.agent = LogAnalyzerAgent(
                    config_manager=self.config_manager,
                    kb_manager=self.kb_manager,
                    mcp_client=self.mcp_client
                )

    def smart_select(
        self,
        log_files: List[str],
        user_prompt: str,
        rules_id: str = None
    ) -> Dict[str, Any]:
        """
        智能选择插件和文件

        Args:
            log_files: 日志文件路径列表
            user_prompt: 用户提示词
            rules_id: 规则集ID

        Returns:
            dict: 选择结果，包含selected_plugins, selected_files, fallback, reason
        """
        # 检查必要组件
        if not self.log_metadata_manager or not self.plugin_manager:
            logger.warning("缺少log_metadata_manager或plugin_manager，执行全量分析")
            return self.fallback_result(log_files, "缺少必要组件")

        # 检查用户提示词
        if not user_prompt or not user_prompt.strip():
            logger.debug("无用户提示词，执行全量分析")
            return self.fallback_result(log_files, "无用户提示词，执行全量分析")

        # 检查API配置
        api_config = self.config_manager.get('api', {}) if self.config_manager else {}
        if not api_config.get('base_url') or not api_config.get('api_key'):
            logger.warning("API配置不完整，执行全量分析")
            return self.fallback_result(log_files, "API配置不完整")

        # 获取插件描述
        plugin_descriptions = self.plugin_manager.get_plugins_ai_description()

        # 获取文件描述
        file_descriptions = self.log_metadata_manager.get_file_descriptions(log_files, rules_id)

        # 构建提示词
        prompt = self.SELECTION_PROMPT.format(
            plugin_descriptions=plugin_descriptions,
            file_descriptions=file_descriptions,
            user_prompt=user_prompt
        )

        try:
            logger.debug(f"智能选择开始，日志文件数: {len(log_files)}")

            # 创建AI客户端调用
            ai_client = AIClient(api_config)
            messages = [{"role": "user", "content": prompt}]

            # 收集完整响应
            response_text = ""
            for chunk in ai_client.chat(messages):
                response_text += chunk

            # 解析结果
            result = self.parse_selection_response(response_text, log_files)
            logger.debug(f"智能选择完成，结果: {result.get('reason', '未知')}")

            return result

        except Exception as e:
            logger.error(f"智能选择失败: {str(e)}", exc_info=True)
            return self.fallback_result(log_files, f"智能选择失败: {str(e)}")

    def parse_selection_response(self, response_text: str, log_files: List[str]) -> Dict[str, Any]:
        """
        解析智能选择响应

        Args:
            response_text: AI响应文本
            log_files: 原始日志文件列表

        Returns:
            dict: 解析后的选择结果
        """
        # 提取JSON
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            json_text = json_match.group(1)
        else:
            json_text = response_text

        try:
            result = json.loads(json_text.strip())

            if not isinstance(result, dict):
                return self.fallback_result(log_files, "响应格式错误")

            # 检查fallback
            if result.get('fallback', False):
                return self.fallback_result(log_files, result.get('reason', '用户请求不明确'))

            # 验证插件
            selected_plugins = result.get('selected_plugins', [])
            all_plugin_ids = [p.id for p in self.plugin_manager.get_all_plugins()]
            valid_plugins = [p for p in selected_plugins if p in all_plugin_ids]

            if not valid_plugins:
                return self.fallback_result(log_files, "未选择有效插件")

            # 验证文件
            selected_files = result.get('selected_files', [])
            valid_files = []
            for selected_file in selected_files:
                for log_file in log_files:
                    if selected_file in log_file or os.path.basename(log_file) == selected_file:
                        valid_files.append(log_file)
                        break

            if not valid_files:
                return self.fallback_result(log_files, "未选择有效文件")

            return {
                'selected_plugins': valid_plugins,
                'selected_files': valid_files,
                'fallback': False,
                'reason': result.get('reason', '智能选择完成')
            }

        except json.JSONDecodeError:
            return self.fallback_result(log_files, "JSON解析失败")

    def fallback_result(self, log_files: List[str], reason: str) -> Dict[str, Any]:
        """生成fallback结果"""
        all_plugin_ids = [p.id for p in self.plugin_manager.get_all_plugins()] if self.plugin_manager else []
        return {
            'selected_plugins': all_plugin_ids,
            'selected_files': log_files,
            'fallback': True,
            'reason': reason
        }

    def execute(
        self,
        request: str,
        context: Dict[str, Any],
        work_dir: str
    ) -> SubagentResult:
        """
        执行日志分析任务

        Args:
            request: 用户请求（分析意图描述）
            context: 上下文信息，包含:
                - plugin_result: 插件分析结果
                - log_files: 日志文件路径列表
                - machine_info: 机器信息
                - knowledge_content: 知识库内容
                - log_rules: 日志规则
                - analysis_templates: 分析模板
                - kb_id: 知识库ID
                - user_intent: 用户的具体意图
                - subagent_api_config: Subagent专用API配置
                - enable_selection: 是否启用智能选择模式
            work_dir: 工作目录

        Returns:
            SubagentResult: 分析结果
        """
        # 从context获取API配置
        api_config = context.get('subagent_api_config')
        self.init_agent(api_config)
        self.user_intent = context.get('user_intent', request)

        if self.agent is None:
            return SubagentResult(
                success=False,
                content="",
                error="Agent未初始化，缺少config_manager或api_config"
            )

        plugin_result = context.get('plugin_result', {})
        log_files = context.get('log_files', [])
        machine_info = context.get('machine_info', {})
        knowledge_content = context.get('knowledge_content', '')
        log_rules = context.get('log_rules', '')
        analysis_templates = context.get('analysis_templates', '')
        kb_id = context.get('kb_id')

        if not log_files:
            return SubagentResult(
                success=False,
                content="",
                error="缺少日志文件"
            )

        try:
            # 构建增强的user_prompt
            enhanced_prompt = self.build_enhanced_prompt(request, self.user_intent)

            result = self.agent.run_analysis(
                plugin_result=plugin_result,
                log_files=log_files,
                machine_info=machine_info,
                knowledge_content=knowledge_content,
                log_rules=log_rules,
                analysis_templates=analysis_templates,
                user_prompt=enhanced_prompt,
                kb_id=kb_id
            )

            html = result.get('html', '')
            interaction_record = result.get('interaction_record', {})

            # 提取intent_response
            intent_response = self.extract_intent_response(interaction_record, self.user_intent)

            return SubagentResult(
                success=True,
                content=intent_response or "分析完成，请查看详细报告",
                data={
                    "html": html,
                    "interaction_record": interaction_record,
                    "intent_response": intent_response
                },
                metadata={
                    "analysis_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "log_files": [os.path.basename(f) for f in log_files],
                    "kb_used": bool(knowledge_content),
                    "user_intent": self.user_intent
                }
            )

        except Exception as e:
            logger.error(f"日志分析失败: {str(e)}", exc_info=True)
            return SubagentResult(
                success=False,
                content="",
                error=str(e)
            )

    def build_enhanced_prompt(self, request: str, user_intent: str) -> str:
        """构建增强的用户提示词"""
        if user_intent and user_intent != request:
            return f"【用户关注点】{user_intent}\n\n【分析请求】{request}"
        return request

    def extract_intent_response(self, interaction_record: Dict, user_intent: str) -> str:
        """从交互记录中提取针对用户意图的回应"""
        if not user_intent:
            return ""

        final_output = interaction_record.get('agent', {}).get('final_output', {})
        if final_output:
            summary = final_output.get('analysis_summary', '')
            if summary:
                return summary

        return ""

    def validate_context(self, context: Dict[str, Any]) -> bool:
        """验证上下文"""
        return 'log_files' in context and len(context.get('log_files', [])) > 0


def register_log_analyzer_subagent(registry, config_manager=None, kb_manager=None,
                                    mcp_client=None, log_metadata_manager=None,
                                    plugin_manager=None):
    """
    注册日志分析Subagent

    Args:
        registry: Subagent注册表
        config_manager: 配置管理器
        kb_manager: 知识库管理器
        mcp_client: MCP客户端
        log_metadata_manager: 日志元数据管理器
        plugin_manager: 插件管理器
    """
    subagent = LogAnalyzerSubagent(
        config_manager, kb_manager, mcp_client,
        log_metadata_manager, plugin_manager
    )
    registry.register(subagent)