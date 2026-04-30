"""
会话管理模块
管理智能助手用户的聊天会话
"""

import os
import json
import random
import string
import shutil
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, asdict

from src.utils.file_utils import get_user_data_dir, ensure_dir, read_json, write_json
from src.utils import get_logger

logger = get_logger('session_manager')


@dataclass
class Message:
    """对话消息"""
    role: str
    content: str
    timestamp: str


@dataclass
class SessionInfo:
    """会话摘要信息"""
    session_id: str
    created_at: str
    updated_at: str
    message_count: int
    title: str
    status: str


@dataclass
class Session:
    """完整会话信息"""
    session_id: str
    work_dir: str
    outputs_dir: str
    conversation: List[Message]
    state: Dict[str, Any]


class SessionManager:
    """会话管理器"""

    MAX_SESSIONS_PER_USER = 3

    def __init__(self, user_id: str):
        """
        初始化会话管理器

        Args:
            user_id: 用户ID（工号）
        """
        self.user_id = user_id
        self.sessions_dir = get_user_data_dir(user_id, 'sessions')
        logger.debug(f"会话目录: {self.sessions_dir}")

    def generate_session_id(self) -> str:
        """生成会话ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        random_str = ''.join(random.choices(string.ascii_lowercase, k=6))
        return f"session_{timestamp}_{random_str}"

    def create_session(self) -> Tuple[Optional[str], Optional[str]]:
        """
        创建新会话

        Returns:
            Tuple: (session_id, error_message)
            - 成功: (session_id, None)
            - 失败: (None, error_message)
        """
        existing = self.list_sessions()
        if len(existing) >= self.MAX_SESSIONS_PER_USER:
            logger.warning(f"用户 {self.user_id} 会话数量已达上限")
            return None, "会话数量已达上限（3个），请先删除旧会话"

        session_id = self.generate_session_id()
        session_dir = os.path.join(self.sessions_dir, session_id)

        work_dir = os.path.join(session_dir, 'work_dir')
        outputs_dir = os.path.join(session_dir, 'outputs')

        ensure_dir(work_dir)
        ensure_dir(outputs_dir)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        state = {
            "created_at": now,
            "updated_at": now,
            "title": "",
            "status": "active",
            "context_usage": 0.0
        }

        conversation = {
            "messages": []
        }

        state_file = os.path.join(session_dir, 'state.json')
        conversation_file = os.path.join(session_dir, 'conversation.json')

        write_json(state_file, state)
        write_json(conversation_file, conversation)

        logger.info(f"创建会话: {session_id}")
        return session_id, None

    def delete_session(self, session_id: str) -> Tuple[bool, Optional[str]]:
        """
        删除会话及其工作目录

        Args:
            session_id: 会话ID

        Returns:
            Tuple: (success, error_message)
        """
        session_dir = os.path.join(self.sessions_dir, session_id)

        if not os.path.exists(session_dir):
            logger.warning(f"会话不存在: {session_id}")
            return False, "会话不存在"

        try:
            shutil.rmtree(session_dir)
            logger.info(f"删除会话: {session_id}")
            return True, None
        except Exception as e:
            logger.error(f"删除会话失败: {session_id}, {str(e)}")
            return False, str(e)

    def list_sessions(self) -> List[SessionInfo]:
        """
        获取用户的所有会话列表

        Returns:
            List[SessionInfo]: 会话列表，按更新时间倒序排列
        """
        if not os.path.exists(self.sessions_dir):
            return []

        sessions = []
        for session_id in os.listdir(self.sessions_dir):
            session_dir = os.path.join(self.sessions_dir, session_id)
            if not os.path.isdir(session_dir):
                continue

            state_file = os.path.join(session_dir, 'state.json')
            conversation_file = os.path.join(session_dir, 'conversation.json')

            if not os.path.exists(state_file):
                continue

            try:
                state = read_json(state_file)
                conversation = read_json(conversation_file) if os.path.exists(conversation_file) else {"messages": []}

                session_info = SessionInfo(
                    session_id=session_id,
                    created_at=state.get('created_at', ''),
                    updated_at=state.get('updated_at', ''),
                    message_count=len(conversation.get('messages', [])),
                    title=state.get('title', ''),
                    status=state.get('status', 'active')
                )
                sessions.append(session_info)
            except Exception as e:
                logger.warning(f"读取会话信息失败: {session_id}, {str(e)}")
                continue

        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取指定会话的完整信息

        Args:
            session_id: 会话ID

        Returns:
            Session: 会话信息，不存在时返回None
        """
        session_dir = os.path.join(self.sessions_dir, session_id)

        if not os.path.exists(session_dir):
            return None

        state_file = os.path.join(session_dir, 'state.json')
        conversation_file = os.path.join(session_dir, 'conversation.json')

        if not os.path.exists(state_file):
            return None

        try:
            state = read_json(state_file)
            conversation_data = read_json(conversation_file) if os.path.exists(conversation_file) else {"messages": []}

            messages = []
            for msg in conversation_data.get('messages', []):
                messages.append(Message(
                    role=msg.get('role', ''),
                    content=msg.get('content', ''),
                    timestamp=msg.get('timestamp', '')
                ))

            return Session(
                session_id=session_id,
                work_dir=os.path.join(session_dir, 'work_dir'),
                outputs_dir=os.path.join(session_dir, 'outputs'),
                conversation=messages,
                state=state
            )
        except Exception as e:
            logger.error(f"获取会话失败: {session_id}, {str(e)}")
            return None

    def save_message(self, session_id: str, role: str, content: str) -> Tuple[bool, Optional[str]]:
        """
        保存对话消息

        Args:
            session_id: 会话ID
            role: 角色（user/assistant/system）
            content: 消息内容

        Returns:
            Tuple: (success, error_message)
        """
        session_dir = os.path.join(self.sessions_dir, session_id)

        if not os.path.exists(session_dir):
            return False, "会话不存在"

        conversation_file = os.path.join(session_dir, 'conversation.json')
        state_file = os.path.join(session_dir, 'state.json')

        try:
            conversation = read_json(conversation_file) if os.path.exists(conversation_file) else {"messages": []}

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            message = {
                "role": role,
                "content": content,
                "timestamp": now
            }
            conversation['messages'].append(message)
            write_json(conversation_file, conversation)

            state = read_json(state_file)
            state['updated_at'] = now

            if role == 'user' and not state.get('title'):
                state['title'] = content[:50] if len(content) > 50 else content

            write_json(state_file, state)

            logger.debug(f"保存消息: session={session_id}, role={role}")
            return True, None
        except Exception as e:
            logger.error(f"保存消息失败: {session_id}, {str(e)}")
            return False, str(e)

    def get_conversation(self, session_id: str) -> List[Message]:
        """
        获取对话历史

        Args:
            session_id: 会话ID

        Returns:
            List[Message]: 消息列表
        """
        session = self.get_session(session_id)
        if session is None:
            return []
        return session.conversation

    def update_state(self, session_id: str, state_updates: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        更新会话状态

        Args:
            session_id: 会话ID
            state_updates: 状态更新字典

        Returns:
            Tuple: (success, error_message)
        """
        session_dir = os.path.join(self.sessions_dir, session_id)

        if not os.path.exists(session_dir):
            return False, "会话不存在"

        state_file = os.path.join(session_dir, 'state.json')

        try:
            state = read_json(state_file)

            for key, value in state_updates.items():
                state[key] = value

            state['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            write_json(state_file, state)

            logger.debug(f"更新会话状态: session={session_id}")
            return True, None
        except Exception as e:
            logger.error(f"更新会话状态失败: {session_id}, {str(e)}")
            return False, str(e)

    def get_work_dir(self, session_id: str) -> Optional[str]:
        """
        获取会话工作目录

        Args:
            session_id: 会话ID

        Returns:
            str: 工作目录路径，不存在时返回None
        """
        session = self.get_session(session_id)
        if session is None:
            return None
        return session.work_dir

    def get_outputs_dir(self, session_id: str) -> Optional[str]:
        """
        获取会话输出目录

        Args:
            session_id: 会话ID

        Returns:
            str: 输出目录路径，不存在时返回None
        """
        session = self.get_session(session_id)
        if session is None:
            return None
        return session.outputs_dir