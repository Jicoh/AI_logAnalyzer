"""
Subagent模块
提供Subagent基类、注册表和日志分析Subagent
"""

from .base import SubagentBase, SubagentResult
from .registry import SubagentRegistry, get_registry
from .log_analyzer import LogAnalyzerSubagent, register_log_analyzer_subagent

__all__ = [
    'SubagentBase',
    'SubagentResult',
    'SubagentRegistry',
    'get_registry',
    'LogAnalyzerSubagent',
    'register_log_analyzer_subagent'
]