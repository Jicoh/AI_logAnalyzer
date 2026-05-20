"""
Agent模块

对外统一入口：AgentService

外部调用者应通过AgentService与Agent模块交互，无需了解内部组件。
"""

# 统一对外服务入口（推荐使用）
from .service import AgentService
from .session import AgentSession

# 以下内部导出为兼容现有代码保留，新代码应使用AgentService
from .client import AIClient, AIResponse
from .mcp_client import MCPClient, MCPServerConnection, StdioConnection, WebSocketConnection
from .orchestrator_agent import OrchestratorAgent, ContextState, ORCHESTRATOR_TOOLS
from .subagents import (
    SubagentBase,
    SubagentResult,
    LogAnalyzerSubagent,
    register_log_analyzer_subagent,
    ToolExecutor,
    BUILTIN_TOOLS,
    BUILTIN_TOOL_NAMES
)
from .skill_loader import SkillLoader, SkillInfo, get_skill_loader

__all__ = [
    # 对外统一入口
    'AgentService',
    'AgentSession',
    # 内部组件（兼容保留）
    'AIClient',
    'AIResponse',
    'MCPClient',
    'OrchestratorAgent',
    'ContextState',
    'SubagentBase',
    'SubagentResult',
    'LogAnalyzerSubagent',
    'SkillLoader',
    'SkillInfo',
    'get_skill_loader',
]
