"""
Subagent注册表模块
管理所有可用的Subagent
"""

from typing import Dict, List, Optional, Type
from src.utils import get_logger

from .subagent_base import SubagentBase, SubagentResult

logger = get_logger('subagent_registry')


class SubagentRegistry:
    """Subagent注册表"""

    def __init__(self):
        """初始化注册表"""
        self._subagents: Dict[str, SubagentBase] = {}
        self._subagent_classes: Dict[str, Type[SubagentBase]] = {}

    def register(self, subagent: SubagentBase) -> bool:
        """
        注册Subagent实例

        Args:
            subagent: Subagent实例

        Returns:
            bool: 注册是否成功
        """
        if not subagent.name:
            logger.warning("Subagent缺少name属性，无法注册")
            return False

        if subagent.name in self._subagents:
            logger.warning(f"Subagent已存在: {subagent.name}")
            return False

        self._subagents[subagent.name] = subagent
        logger.info(f"注册Subagent: {subagent.name}")
        return True

    def register_class(self, name: str, cls: Type[SubagentBase]) -> bool:
        """
        注册Subagent类（延迟实例化）

        Args:
            name: Subagent名称
            cls: Subagent类

        Returns:
            bool: 注册是否成功
        """
        if name in self._subagent_classes:
            logger.warning(f"Subagent类已存在: {name}")
            return False

        self._subagent_classes[name] = cls
        logger.info(f"注册Subagent类: {name}")
        return True

    def get(self, name: str) -> Optional[SubagentBase]:
        """
        获取Subagent实例

        Args:
            name: Subagent名称

        Returns:
            SubagentBase: Subagent实例，不存在时返回None
        """
        return self._subagents.get(name)

    def create_instance(
        self,
        name: str,
        config_manager=None,
        kb_manager=None,
        mcp_client=None
    ) -> Optional[SubagentBase]:
        """
        创建Subagent实例（从注册的类）

        Args:
            name: Subagent名称
            config_manager: 配置管理器
            kb_manager: 知识库管理器
            mcp_client: MCP客户端

        Returns:
            SubagentBase: 新创建的实例，不存在时返回None
        """
        cls = self._subagent_classes.get(name)
        if cls is None:
            return None

        return cls(config_manager, kb_manager, mcp_client)

    def list_all(self) -> List[Dict[str, any]]:
        """
        获取所有已注册的Subagent信息

        Returns:
            List: Subagent信息列表
        """
        result = []
        for name, subagent in self._subagents.items():
            result.append(subagent.get_info())
        for name, cls in self._subagent_classes.items():
            if name not in self._subagents:
                result.append({
                    "name": name,
                    "description": cls.description if hasattr(cls, 'description') else "",
                    "capabilities": cls.capabilities if hasattr(cls, 'capabilities') else []
                })
        return result

    def has(self, name: str) -> bool:
        """检查Subagent是否已注册"""
        return name in self._subagents or name in self._subagent_classes

    def execute(
        self,
        name: str,
        request: str,
        context: Dict[str, any],
        work_dir: str
    ) -> Optional[SubagentResult]:
        """
        执行指定Subagent

        Args:
            name: Subagent名称
            request: 用户请求
            context: 上下文信息
            work_dir: 工作目录

        Returns:
            SubagentResult: 执行结果，Subagent不存在时返回None
        """
        subagent = self.get(name)
        if subagent is None:
            logger.warning(f"Subagent不存在: {name}")
            return None

        if not subagent.validate_context(context):
            return SubagentResult(
                success=False,
                content="",
                error="上下文不满足执行条件"
            )

        try:
            result = subagent.execute(request, context, work_dir)
            logger.debug(f"Subagent执行完成: {name}, success={result.success}")
            return result
        except Exception as e:
            logger.error(f"Subagent执行失败: {name}, {str(e)}")
            return SubagentResult(
                success=False,
                content="",
                error=str(e)
            )


# 全局注册表实例
_registry = None


def get_registry() -> SubagentRegistry:
    """获取全局注册表实例"""
    global _registry
    if _registry is None:
        _registry = SubagentRegistry()
    return _registry