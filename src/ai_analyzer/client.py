"""
AI客户端模块
封装AI API调用，支持流式响应
"""

import json
import requests
from src.utils import get_logger

logger = get_logger('ai_client')


class AIClient:
    """AI API客户端，支持流式响应"""

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
            "stream": True  # 启用流式响应
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120,
            stream=True  # 流式读取
        )
        response.raise_for_status()
        logger.debug(f"API响应状态码: {response.status_code}")

        # 解析SSE格式的流式响应
        # 使用 iter_content 而不是 iter_lines 以确保真正的流式输出
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

                # SSE格式: data: {...}
                if line.startswith('data: '):
                    data_str = line[6:]  # 去掉 'data: ' 前缀

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