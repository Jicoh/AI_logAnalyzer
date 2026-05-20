"""
Agent模块统一服务入口

外部调用者（Web/CLI/Serve）通过此类与Agent模块交互，
无需了解内部的Subagent、QueryEngine等组件。
"""

import os
from typing import Dict, Any, List, Tuple, Optional

from src.utils import get_logger

logger = get_logger('agent_service')


class AgentService:
    """Agent模块统一服务入口

    封装了所有Agent能力，对外提供简洁的接口：
    - analyze: 日志分析（插件 + AI）
    - chat/chat_stream: 智能助手对话
    - run_plugin_only: 纯插件分析

    外部调用者无需了解LogAnalyzerSubagent、OrchestratorAgent、
    QueryEngine等内部组件的存在。
    """

    def __init__(self, config_manager=None, kb_manager=None,
                 plugin_manager=None, log_metadata_manager=None,
                 mcp_client=None):
        """初始化Agent服务

        Args:
            config_manager: 系统配置管理器（可选，延迟初始化）
            kb_manager: 知识库管理器（可选，延迟初始化）
            plugin_manager: 插件管理器（可选，延迟初始化）
            log_metadata_manager: 日志元数据管理器（可选，延迟初始化）
            mcp_client: MCP客户端（可选）
        """
        self._config_manager = config_manager
        self._kb_manager = kb_manager
        self._plugin_manager = plugin_manager
        self._log_metadata_manager = log_metadata_manager
        self._mcp_client = mcp_client

        # 内部组件（延迟初始化）
        self._subagent_registry = None
        self._query_engine = None
        self._ai_client = None

    # ---- 延迟初始化属性 ----

    @property
    def config_manager(self):
        if self._config_manager is None:
            from src.system_config_manager import SystemConfigManager
            self._config_manager = SystemConfigManager()
        return self._config_manager

    @property
    def kb_manager(self):
        if self._kb_manager is None:
            from src.knowledge_base import KnowledgeBaseManager
            self._kb_manager = KnowledgeBaseManager(
                config=self.config_manager.get_all()
            )
        return self._kb_manager

    @property
    def plugin_manager(self):
        if self._plugin_manager is None:
            from plugins.manager import get_plugin_manager
            from src.utils.file_utils import get_project_root
            root_dir = get_project_root()
            custom_dir = os.path.join(root_dir, 'custom_plugins')
            self._plugin_manager = get_plugin_manager(custom_dirs=[custom_dir])
        return self._plugin_manager

    @property
    def log_metadata_manager(self):
        if self._log_metadata_manager is None:
            from src.log_metadata import LogMetadataManager
            self._log_metadata_manager = LogMetadataManager()
        return self._log_metadata_manager

    @property
    def subagent_registry(self):
        if self._subagent_registry is None:
            from .subagents import get_registry
            from .subagents.log_analyzer import register_log_analyzer_subagent
            self._subagent_registry = get_registry()
            register_log_analyzer_subagent(
                self._subagent_registry,
                config_manager=self.config_manager,
                kb_manager=self.kb_manager,
                mcp_client=self._mcp_client,
                log_metadata_manager=self.log_metadata_manager,
                plugin_manager=self.plugin_manager
            )
        return self._subagent_registry

    # ---- 对外接口：日志分析 ----

    def analyze(
        self,
        log_files: List[str],
        plugin_result: Dict = None,
        kb_ids: List[str] = None,
        user_prompt: str = None,
        log_rules_id: str = None,
        user_intent: str = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """统一日志分析接口（插件分析 + AI分析）

        替代目前外部直接调用 LogAnalyzerSubagent.analyze() 的方式。

        Args:
            log_files: 日志文件路径列表
            plugin_result: 插件分析结果（可选，为None时触发智能选择）
            kb_ids: 知识库ID列表
            user_prompt: 用户提示词
            log_rules_id: 日志规则ID
            user_intent: 用户意图
            user_id: 用户ID（用于保存ai_temp记录）

        Returns:
            dict: {'html': str, 'interaction_record': dict, 'intent_response': str}
        """
        from .subagents.log_analyzer import LogAnalyzerSubagent

        subagent = LogAnalyzerSubagent(
            config_manager=self.config_manager,
            kb_manager=self.kb_manager,
            log_metadata_manager=self.log_metadata_manager,
            plugin_manager=self.plugin_manager
        )

        return subagent.analyze(
            log_files=log_files,
            plugin_result=plugin_result,
            kb_ids=kb_ids,
            user_prompt=user_prompt,
            log_rules_id=log_rules_id,
            user_intent=user_intent,
            user_id=user_id
        )

    def run_plugin_only(
        self,
        source: str,
        plugin_ids: List[str],
        log_content: Dict[str, List[str]],
        task_name: str = "",
        bmc_ip: str = "",
        date: str = "",
        log_callback=None
    ) -> Dict:
        """纯插件分析接口（无AI）

        供Serve模块和CLI的纯插件分析场景使用。

        Args:
            source: 分析来源（'system' 或 'cli'）
            plugin_ids: 插件ID列表
            log_content: 日志内容字典 {"文件名": ["行1", "行2"]}
            task_name: 任务名称
            bmc_ip: BMC IP地址
            date: 日期
            log_callback: 日志回调函数

        Returns:
            dict: 插件分析结果
        """
        return self.plugin_manager.run_analysis(
            source=source,
            plugin_ids=plugin_ids,
            log_content=log_content,
            task_name=task_name,
            bmc_ip=bmc_ip,
            date=date,
            log_callback=log_callback
        )

    # ---- 对外接口：智能助手对话 ----

    def chat(
        self,
        session_id: str,
        user_input: str,
        user_id: str = None,
        kb_context: str = None,
        kb_ids: List[str] = None,
        session_context: Dict = None
    ) -> Tuple[str, Dict[str, Any]]:
        """对话接口（非流式）

        替代目前外部直接调用 OrchestratorAgent.chat() 的方式。

        Args:
            session_id: 会话ID
            user_input: 用户输入
            user_id: 用户ID
            kb_context: 知识库检索上下文
            kb_ids: 知识库ID列表
            session_context: 额外会话上下文

        Returns:
            Tuple: (响应内容, 元数据)
        """
        # 加载会话
        from .session import AgentSession
        from src.session_manager.manager import SessionManager

        session_manager = SessionManager(user_id or 'anonymous')
        session = AgentSession.from_flask_session(
            session_id=session_id,
            user_id=user_id or 'anonymous',
            session_manager=session_manager
        )

        # 设置知识库上下文和ID
        if kb_context:
            session.set_kb_context(kb_context)
        if kb_ids:
            session.set_kb_ids(kb_ids)

        # 构建QueryEngine
        query_engine = self._build_query_engine(session)

        # 执行对话循环
        result = query_engine.run(
            session_state=session.state,
            user_input=user_input,
            conversation_history=session.conversation_history,
            session_context=session.to_prompt_context()
        )

        # 更新并保存会话
        self._update_session_after_chat(session, session_manager, user_input, result)

        return result['final_response'], result['metadata']

    def chat_stream(
        self,
        session_id: str,
        user_input: str,
        user_id: str = None,
        kb_context: str = None,
        kb_ids: List[str] = None,
        session_context: Dict = None
    ):
        """对话接口（流式）

        替代目前外部直接调用 OrchestratorAgent.chat_stream() 的方式。

        Args:
            session_id: 会话ID
            user_input: 用户输入
            user_id: 用户ID
            kb_context: 知识库检索上下文
            kb_ids: 知识库ID列表
            session_context: 额外会话上下文

        Yields:
            str: AI响应的文本片段
        """
        from .session import AgentSession
        from src.session_manager.manager import SessionManager

        session_manager = SessionManager(user_id or 'anonymous')
        session = AgentSession.from_flask_session(
            session_id=session_id,
            user_id=user_id or 'anonymous',
            session_manager=session_manager
        )

        # 设置知识库上下文和ID
        if kb_context:
            session.set_kb_context(kb_context)
        if kb_ids:
            session.set_kb_ids(kb_ids)

        query_engine = self._build_query_engine(session)

        full_response = ""
        for chunk in query_engine.run_stream(
            session_state=session.state,
            user_input=user_input,
            conversation_history=session.conversation_history,
            session_context=session.to_prompt_context()
        ):
            full_response += chunk
            yield chunk

        # 保存会话状态
        session.add_message("user", user_input)
        session.add_message("assistant", full_response)
        if user_input:
            session_manager.save_message(session_id, "user", user_input)
        if full_response:
            session_manager.save_message(session_id, "assistant", full_response)

    # ---- 内部方法 ----

    def _build_query_engine(self, session):
        """为指定会话构建QueryEngine"""
        from .client import AIClient
        from .core.query_engine import QueryEngine
        from .core.tool_router import ToolRouter
        from .core.context_manager import ContextManager
        from .core.prompt_builder import SystemPromptBuilder
        from .skill_loader import get_skill_loader

        # API配置
        api_config = self.config_manager.get('api', {})
        ai_client = AIClient(api_config)

        # 上下文限制
        orchestrator_config = self.config_manager.get('orchestrator', {})
        context_limit = orchestrator_config.get('context_limit', 120000)
        compression_threshold = orchestrator_config.get('compression_threshold', 0.8)
        compression_retain_rounds = orchestrator_config.get('compression_retain_rounds', 5)
        max_rounds = orchestrator_config.get('max_rounds', 20)
        tool_call_limit = orchestrator_config.get('tool_call_limit', 50)

        # 核心组件
        context_manager = ContextManager(
            ai_client=ai_client,
            total_limit=context_limit,
            compression_threshold=compression_threshold,
            compression_retain_rounds=compression_retain_rounds
        )

        skill_loader = get_skill_loader()
        skill_loader.scan()

        prompt_builder = SystemPromptBuilder(
            skill_loader=skill_loader,
            subagent_registry=self.subagent_registry
        )

        tool_router = ToolRouter(
            subagent_registry=self.subagent_registry,
            mcp_client=self._mcp_client,
            session_manager=None,  # QueryEngine内部不直接操作session
            session_id=session.session_id,
            session_state=session.state,
            work_dir=session.work_dir,
            outputs_dir=session.outputs_dir,
            kb_manager=self.kb_manager,
            get_api_config=lambda: self.config_manager.get('api', {})
        )

        return QueryEngine(
            ai_client=ai_client,
            tool_router=tool_router,
            context_manager=context_manager,
            prompt_builder=prompt_builder,
            max_rounds=max_rounds,
            tool_call_limit=tool_call_limit
        )

    def _update_session_after_chat(self, session, session_manager,
                                   user_input: str, result: Dict):
        """对话完成后更新并保存会话"""
        messages = result.get('messages', [])

        # 提取本轮新增的assistant和tool消息更新到历史
        if user_input:
            session.add_message("user", user_input)
            session_manager.save_message(session.session_id, "user", user_input)

        # 从messages中提取assistant的final response
        final_response = result.get('final_response', '')
        if final_response:
            session.add_message("assistant", final_response)
            session_manager.save_message(
                session.session_id, "assistant", final_response
            )

        # 更新会话状态
        metadata = result.get('metadata', {})
        session.update_state({
            "tool_calls": metadata.get("tool_call_count", 0),
            "context_usage": metadata.get("context_usage", 0.0)
        })
        session_manager.update_state(session.session_id, {
            "tool_calls": session.state.get("tool_calls", 0),
            "context_usage": session.state.get("context_usage", 0.0)
        })
