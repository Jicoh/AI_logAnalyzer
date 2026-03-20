"""
Plugin system for AI Log Analyzer.

This module provides a standardized plugin architecture for extending
log analysis capabilities.
"""

from plugins.base import BasePlugin, PluginCategory, PluginInfo, AnalysisResult
from plugins.manager import PluginManager, get_plugin_manager

__all__ = [
    'BasePlugin',
    'PluginCategory',
    'PluginInfo',
    'AnalysisResult',
    'PluginManager',
    'get_plugin_manager',
]