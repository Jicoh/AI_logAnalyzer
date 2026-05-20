"""
Agent会话管理

管理单个Agent会话的状态：工作目录、对话历史、已执行操作、上下文状态等
"""

import os
from typing import Dict, Any, List, Optional

from src.utils import get_logger

logger = get_logger('agent_session')


class AgentSession:
    """Agent会话

    管理单个会话的完整状态，包括：
    - 基础信息（session_id, user_id）
    - 工作目录和输出目录
    - 对话历史
    - 会话状态（notes, uploaded_files, tool_calls等）
    - 知识库关联
    """

    def __init__(self, session_id: str, user_id: str = None,
                 work_dir: str = None, outputs_dir: str = None):
        self.session_id = session_id
        self.user_id = user_id
        self.work_dir = work_dir or ""
        self.outputs_dir = outputs_dir or ""
        self.conversation_history: List[Dict] = []
        self.state: Dict[str, Any] = {
            "notes": {},
            "uploaded_files": [],
            "subagent_calls": 0,
            "tool_calls": 0,
            "kb_ids": []
        }

    @classmethod
    def from_flask_session(cls, session_id: str, user_id: str,
                           session_manager=None) -> "AgentSession":
        """从Flask会话管理器创建AgentSession

        Args:
            session_id: 会话ID
            user_id: 用户ID
            session_manager: SessionManager实例

        Returns:
            AgentSession: 初始化好的会话对象
        """
        instance = cls(session_id=session_id, user_id=user_id)

        if session_manager:
            session = session_manager.get_session(session_id)
            if session:
                instance.work_dir = session.work_dir
                instance.outputs_dir = session.outputs_dir
                for msg in session.conversation:
                    instance.conversation_history.append({
                        "role": msg.role,
                        "content": msg.content
                    })
                instance.state.update(session.state.copy())
            else:
                raise ValueError(f"会话不存在: {session_id}")

        return instance

    def add_message(self, role: str, content: str, **kwargs):
        """添加消息到对话历史"""
        msg = {"role": role, "content": content}
        msg.update(kwargs)
        self.conversation_history.append(msg)

    def get_state(self) -> Dict[str, Any]:
        """获取当前会话状态"""
        return self.state.copy()

    def update_state(self, updates: Dict):
        """更新会话状态"""
        self.state.update(updates)

    def set_kb_ids(self, kb_ids: List[str]):
        """设置知识库ID列表"""
        self.state["kb_ids"] = kb_ids

    def set_kb_context(self, kb_context: str):
        """设置知识库上下文"""
        self.state["kb_context"] = kb_context

    def to_prompt_context(self) -> Dict[str, Any]:
        """转换为构建prompt所需的上下文字典"""
        return {
            "work_dir": self.work_dir,
            "context_usage_ratio": self.state.get("context_usage", 0.0),
            "kb_context": self.state.get("kb_context", ""),
            "uploaded_files": self.state.get("uploaded_files", []),
            "notes": self.state.get("notes", {}),
            "user_id": self.user_id
        }

    def get_recent_history(self, max_messages: int = None) -> List[Dict]:
        """获取最近的对话历史

        Args:
            max_messages: 最大消息数，None表示全部

        Returns:
            List[Dict]: 对话历史列表
        """
        if max_messages is None:
            return self.conversation_history.copy()
        return self.conversation_history[-max_messages:].copy()
