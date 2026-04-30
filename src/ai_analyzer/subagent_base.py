"""
Subagent基类模块
定义Subagent的标准接口和返回结构
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass
class SubagentResult:
    """Subagent执行结果"""
    success: bool
    content: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "content": self.content,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata
        }


class SubagentBase(ABC):
    """Subagent基类"""

    name: str = ""
    description: str = ""
    capabilities: List[str] = []

    def __init__(self, config_manager=None, kb_manager=None, mcp_client=None):
        """
        初始化Subagent

        Args:
            config_manager: 配置管理器
            kb_manager: 知识库管理器
            mcp_client: MCP客户端
        """
        self.config_manager = config_manager
        self.kb_manager = kb_manager
        self.mcp_client = mcp_client

    @abstractmethod
    def execute(
        self,
        request: str,
        context: Dict[str, Any],
        work_dir: str
    ) -> SubagentResult:
        """
        执行Subagent任务

        Args:
            request: 用户请求/任务描述
            context: 上下文信息（包含插件结果、知识库内容等）
            work_dir: 工作目录路径

        Returns:
            SubagentResult: 执行结果
        """
        pass

    def get_info(self) -> Dict[str, Any]:
        """获取Subagent信息"""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities
        }

    def validate_context(self, context: Dict[str, Any]) -> bool:
        """
        验证上下文是否满足执行条件

        Args:
            context: 上下文信息

        Returns:
            bool: 是否可以执行
        """
        return True