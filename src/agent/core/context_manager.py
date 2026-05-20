"""
上下文管理器

负责token计算、上下文压缩、历史消息管理
"""

import json
from typing import Dict, Any, List
from dataclasses import dataclass

from src.utils import get_logger

logger = get_logger('context_manager')


@dataclass
class ContextState:
    """上下文状态"""
    total_limit: int = 120000
    used_tokens: int = 0
    available_tokens: int = 0
    usage_ratio: float = 0.0
    needs_compression: bool = False

    def update(self, used: int):
        """更新状态"""
        self.used_tokens = used
        self.available_tokens = self.total_limit - used
        self.usage_ratio = used / self.total_limit if self.total_limit > 0 else 0
        self.needs_compression = self.usage_ratio >= 0.8


class ContextManager:
    """上下文管理器

    负责token计算、上下文压缩、历史消息管理
    """

    def __init__(self, ai_client, total_limit: int = 120000,
                 compression_threshold: float = 0.8, compression_retain_rounds: int = 5):
        self.ai_client = ai_client
        self.total_limit = total_limit
        self.compression_threshold = compression_threshold
        self.compression_retain_rounds = compression_retain_rounds
        self.state = ContextState(total_limit=total_limit)

    def calculate_usage(self, messages: List[Dict], tools: List[Dict] = None) -> int:
        """计算上下文使用量"""
        return self.ai_client.count_tokens(messages, tools or [])

    def check_and_compress(self, messages: List[Dict], tools: List[Dict] = None) -> List[Dict]:
        """检查上下文使用率并按需压缩"""
        current_tokens = self.calculate_usage(messages, tools)
        self.state.update(current_tokens)

        if self.state.needs_compression:
            messages = self.compress(messages, tools)
            current_tokens = self.calculate_usage(messages, tools)
            self.state.update(current_tokens)

        return messages

    def compress(self, messages: List[Dict], tools: List[Dict] = None) -> List[Dict]:
        """压缩上下文"""
        if len(messages) <= 2:
            return messages

        logger.info("开始压缩上下文...")

        retain_count = self.compression_retain_rounds * 2
        system_message = messages[0] if messages and messages[0].get('role') == 'system' else None

        if system_message:
            recent_messages = messages[-retain_count:] if len(messages) > retain_count + 1 else messages[1:]
            to_compress = messages[1:-retain_count] if len(messages) > retain_count + 1 else []
        else:
            recent_messages = messages[-retain_count:] if len(messages) > retain_count else messages
            to_compress = messages[:-retain_count] if len(messages) > retain_count else []

        if not to_compress:
            return messages

        compression_prompt = f"""请将以下对话历史压缩为简洁摘要，保留关键信息。

# 对话历史
{json.dumps(to_compress, ensure_ascii=False, indent=2)}

# 输出要求
1. 保留关键决策和结论
2. 保留用户的重要需求
3. 记录已执行的操作
4. 格式：几条关键要点，每条不超过50字

请输出摘要："""

        try:
            from src.agent.client import AIClient
            summary_response = self.ai_client.chat_with_tools([
                {"role": "user", "content": compression_prompt}
            ])
            summary = summary_response.content or "对话历史已压缩"

            new_messages = []
            if system_message:
                new_messages.append(system_message)

            new_messages.append({
                "role": "user",
                "content": f"[历史摘要] {summary}"
            })
            new_messages.append({
                "role": "assistant",
                "content": "我已了解之前的对话内容，继续为您服务。"
            })
            new_messages.extend(recent_messages)

            new_tokens = self.calculate_usage(new_messages, tools)
            logger.info(f"压缩完成: {len(messages)} -> {len(new_messages)} 条消息, "
                       f"tokens: {self.calculate_usage(messages, tools)} -> {new_tokens}")

            return new_messages

        except Exception as e:
            logger.error(f"上下文压缩失败: {str(e)}")
            return messages
