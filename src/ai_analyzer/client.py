"""
AI客户端模块
封装AI API调用
"""

import json
import requests


class AIClient:
    """AI API客户端"""

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
        发送聊天请求

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            str: AI回复内容
        """
        if not self.base_url or not self.api_key:
            raise ValueError("API配置不完整，请检查base_url和api_key")

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens
        }

        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        result = response.json()
        return result['choices'][0]['message']['content']

    def analyze(self, prompt):
        """
        分析请求的便捷方法

        Args:
            prompt: 提示词

        Returns:
            str: AI分析结果
        """
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages)


def create_client(config):
    """
    创建AI客户端的便捷函数

    Args:
        config: 配置字典

    Returns:
        AIClient: AI客户端实例
    """
    return AIClient(config)