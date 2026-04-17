"""
AI客户端模块 - 使用 LangChain
封装AI API调用，支持流式响应
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from src.utils import get_logger

logger = get_logger('ai_client')


class AIClient:
    """AI API客户端，使用 LangChain"""

    def __init__(self, config):
        """
        初始化AI客户端

        Args:
            config: 配置字典，包含api相关配置
        """
        self.base_url = config.get('base_url', '')
        self.api_key = config.get('api_key', '')
        self.model = config.get('model', '')
        self.temperature = config.get('temperature', 0.7)
        self.max_tokens = config.get('max_tokens', 4096)

        # 创建 LangChain ChatOpenAI 实例
        self.llm = ChatOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            streaming=True
        )

    def chat(self, messages, temperature=None, max_tokens=None):
        """
        流式聊天请求

        Args:
            messages: 消息列表，格式 [{"role": "user/assistant/system", "content": "..."}]
            temperature: 温度参数（可选）
            max_tokens: 最大token数（可选）

        Yields:
            str: AI回复的文本片段
        """
        # 转换为 LangChain 消息格式
        lc_messages = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'user':
                lc_messages.append(HumanMessage(content=content))
            elif role == 'assistant':
                lc_messages.append(AIMessage(content=content))
            elif role == 'system':
                lc_messages.append(SystemMessage(content=content))

        # 使用临时配置（如果提供了参数）
        llm = self.llm
        if temperature is not None or max_tokens is not None:
            llm = ChatOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.model,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                streaming=True
            )

        # 流式输出
        for chunk in llm.stream(lc_messages):
            if chunk.content:
                yield chunk.content

    def analyze(self, prompt):
        """
        分析请求的便捷方法

        Args:
            prompt: 提示词

        Yields:
            str: AI分析结果的文本片段
        """
        messages = [{"role": "user", "content": prompt}]
        for chunk in self.chat(messages):
            yield chunk