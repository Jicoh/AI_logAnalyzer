"""
AI客户端模块
封装AI API调用，支持流式响应和工具调用
"""

import json
import requests
from src.utils import get_logger

logger = get_logger('ai_client')


class AIResponse:
    """AI响应封装类"""

    def __init__(self, content: str = None, tool_calls: list = None):
        self.content = content
        self.tool_calls = tool_calls or []

    def has_tool_calls(self) -> bool:
        """判断是否有工具调用"""
        return len(self.tool_calls) > 0

    def to_message(self) -> dict:
        """转换为消息格式"""
        if self.has_tool_calls():
            return {
                "role": "assistant",
                "tool_calls": self.tool_calls
            }
        return {
            "role": "assistant",
            "content": self.content
        }


class AIClient:
    """AI API客户端，支持流式响应和工具调用"""

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

    def chat(self, messages, temperature=None, max_tokens=None):
        """
        流式聊天请求

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数

        Yields:
            str: AI回复的文本片段
        """
        if not self.base_url or not self.api_key:
            logger.error("API配置不完整，请检查base_url和api_key")
            raise ValueError("API配置不完整，请检查base_url和api_key")

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        logger.debug(f"开始API调用: {url}, model={self.model}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "stream": True
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120,
            stream=True
        )
        response.raise_for_status()
        logger.debug(f"API响应状态码: {response.status_code}")

        # 解析SSE格式的流式响应
        buffer = ""
        for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
            if not chunk:
                continue

            buffer += chunk

            # 处理缓冲区中的完整行
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()

                if not line:
                    continue

                # SSE格式: data: {...} 或 data:{...}
                # 兼容两种格式：冒号后有无空格
                if line.startswith('data:'):
                    # 提取data后面的内容
                    data_str = line[5:]  # 去掉 'data:'
                    if data_str.startswith(' '):
                        data_str = data_str[1:]  # 去掉空格

                    # 结束标记
                    if data_str.strip() == '[DONE]':
                        break

                    try:
                        data = json.loads(data_str)
                        choices = data.get('choices', [])
                        if choices:
                            delta = choices[0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue

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

    def chat_with_tools(self, messages, tools=None, tool_choice="auto"):
        """
        支持工具调用的聊天请求（非流式）

        Args:
            messages: 消息列表
            tools: 工具定义列表（OpenAI格式）
            tool_choice: "auto" / "required" / "none"

        Returns:
            AIResponse: 响应对象，包含content或tool_calls
        """
        if not self.base_url or not self.api_key:
            logger.error("API配置不完整，请检查base_url和api_key")
            raise ValueError("API配置不完整，请检查base_url和api_key")

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        logger.debug(f"开始API调用(工具模式): {url}, model={self.model}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        logger.debug(f"API响应状态码: {response.status_code}")

        data = response.json()
        choices = data.get('choices', [])
        if not choices:
            logger.warning("API返回空choices")
            return AIResponse(content="")

        message = choices[0].get('message', {})
        content = message.get('content', '')
        tool_calls = message.get('tool_calls', [])

        # 记录usage信息
        usage = data.get('usage', {})
        if usage:
            logger.debug(f"Token使用: prompt={usage.get('prompt_tokens')}, "
                        f"completion={usage.get('completion_tokens')}, "
                        f"total={usage.get('total_tokens')}")

        return AIResponse(content=content, tool_calls=tool_calls)

    def count_tokens(self, messages: list) -> int:
        """
        粗略估算消息的token数量

        Args:
            messages: 消息列表

        Returns:
            int: 估算的token数量
        """
        total = 0
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, str):
                # 中文约1.5字符/token，英文约4字符/token
                # 简化估算：平均2.5字符/token
                total += len(content) // 2.5
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        total += len(item.get('text', '')) // 2.5
        return int(total)