"""
Log Analyzer Subagent
将LogAnalyzerAgent改造为Subagent接口
"""

import os
from typing import Dict, Any, List, Optional
from datetime import datetime

from .subagent_base import SubagentBase, SubagentResult
from .log_analyzer_agent import LogAnalyzerAgent
from src.utils import get_logger

logger = get_logger('log_analyzer_subagent')


class LogAnalyzerSubagent(SubagentBase):
    """日志分析Subagent"""

    name = "log_analyzer"
    description = "BMC服务器日志分析，识别问题并提供解决方案"
    capabilities = [
        "日志文件分析",
        "问题识别",
        "风险评估",
        "解决方案推荐",
        "知识库检索",
        "针对性回答用户问题"
    ]

    def __init__(self, config_manager=None, kb_manager=None, mcp_client=None):
        super().__init__(config_manager, kb_manager, mcp_client)
        self.agent = None
        self.user_intent = None

    def _init_agent(self, api_config: Dict = None):
        """
        延迟初始化Agent

        Args:
            api_config: 传入的API配置（从context获取），优先级高于config_manager
        """
        if self.agent is None:
            # 优先使用传入的api_config
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

    def execute(
        self,
        request: str,
        context: Dict[str, Any],
        work_dir: str
    ) -> SubagentResult:
        """
        执行日志分析任务

        Args:
            request: 用户请求（分析意图描述，包含用户具体关注点）
            context: 上下文信息，包含:
                - plugin_result: 插件分析结果
                - log_files: 日志文件路径列表
                - machine_info: 机器信息
                - knowledge_content: 知识库内容
                - log_rules: 日志规则
                - analysis_templates: 分析模板
                - kb_id: 知识库ID
                - user_intent: 用户的具体意图（可选，由Orchestrator提取）
                - subagent_api_config: Subagent专用API配置（可选）
            work_dir: 工作目录

        Returns:
            SubagentResult: 分析结果，包含intent_response直接回应用户意图
        """
        # 从context获取API配置
        api_config = context.get('subagent_api_config')
        self._init_agent(api_config)
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
            # 构建增强的user_prompt，包含用户意图
            enhanced_prompt = self._build_enhanced_prompt(request, self.user_intent)

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

            # 从交互记录中提取intent_response
            intent_response = self._extract_intent_response(interaction_record, self.user_intent)

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
            logger.error(f"日志分析失败: {str(e)}")
            return SubagentResult(
                success=False,
                content="",
                error=str(e)
            )

    def _build_enhanced_prompt(self, request: str, user_intent: str) -> str:
        """构建增强的用户提示词，强调用户意图"""
        if user_intent and user_intent != request:
            return f"【用户关注点】{user_intent}\n\n【分析请求】{request}"
        return request

    def _extract_intent_response(self, interaction_record: Dict, user_intent: str) -> str:
        """从交互记录中提取针对用户意图的回应"""
        if not user_intent:
            return ""

        # 尝试从final_output中提取分析摘要
        final_output = interaction_record.get('agent', {}).get('final_output', {})
        if final_output:
            summary = final_output.get('analysis_summary', '')
            if summary:
                return summary

        return ""

    def validate_context(self, context: Dict[str, Any]) -> bool:
        """验证上下文"""
        return 'log_files' in context and len(context.get('log_files', [])) > 0


def register_log_analyzer_subagent(registry, config_manager=None, kb_manager=None, mcp_client=None):
    """
    注册日志分析Subagent

    Args:
        registry: Subagent注册表
        config_manager: 配置管理器
        kb_manager: 知识库管理器
        mcp_client: MCP客户端
    """
    subagent = LogAnalyzerSubagent(config_manager, kb_manager, mcp_client)
    registry.register(subagent)