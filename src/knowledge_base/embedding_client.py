"""
Embedding API 客户端
支持 OpenAI 兼容格式的 Embedding API
"""

import requests
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Embedding API 客户端"""

    def __init__(self, config: dict):
        """
        初始化 Embedding 客户端

        Args:
            config: 配置字典，包含:
                - enabled: 是否启用
                - provider: 提供商 (openai, etc.)
                - base_url: API 基础 URL
                - api_key: API 密钥
                - model: 模型名称
                - dimension: 向量维度
                - batch_size: 批处理大小
        """
        self.enabled = config.get('enabled', False)
        self.provider = config.get('provider', 'openai')
        self.base_url = config.get('base_url', 'https://api.openai.com/v1')
        self.api_key = config.get('api_key', '')
        self.model = config.get('model', 'text-embedding-3-small')
        self.dimension = config.get('dimension', 1536)
        self.batch_size = config.get('batch_size', 100)
        self.timeout = config.get('timeout', 60)

    def is_enabled(self) -> bool:
        """检查是否启用且配置正确"""
        if not self.enabled:
            return False
        if not self.api_key:
            logger.warning("Embedding API key not configured")
            return False
        if not self.base_url:
            logger.warning("Embedding API base_url not configured")
            return False
        return True

    def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        批量文本向量化

        Args:
            texts: 文本列表

        Returns:
            向量列表，失败返回 None
        """
        if not self.is_enabled():
            return None

        if not texts:
            return []

        all_embeddings = []

        # 分批处理
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            embeddings = self.embed_batch(batch)
            if embeddings is None:
                return None
            all_embeddings.extend(embeddings)

        return all_embeddings

    def embed_query(self, query: str) -> Optional[List[float]]:
        """
        单查询向量化

        Args:
            query: 查询文本

        Returns:
            向量，失败返回 None
        """
        if not self.is_enabled():
            return None

        result = self.embed_batch([query])
        if result is None or len(result) == 0:
            return None
        return result[0]

    def embed_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        调用 Embedding API 处理一批文本

        Args:
            texts: 文本列表

        Returns:
            向量列表，失败返回 None
        """
        # 确保 base_url 以正确的格式
        base_url = self.base_url.rstrip('/')
        url = f"{base_url}/embeddings"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "input": texts,
            "model": self.model
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code != 200:
                logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # 提取向量，按索引排序
            embeddings_data = data.get('data', [])
            embeddings_data.sort(key=lambda x: x.get('index', 0))

            embeddings = [item['embedding'] for item in embeddings_data]

            return embeddings

        except requests.exceptions.Timeout:
            logger.error("Embedding API timeout")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Embedding API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Embedding API unexpected error: {e}")
            return None

    def test_connection(self) -> tuple:
        """
        测试 API 连接

        Returns:
            (success: bool, message: str)
        """
        if not self.enabled:
            return False, "Embedding is disabled"

        if not self.api_key:
            return False, "API key not configured"

        if not self.base_url:
            return False, "Base URL not configured"

        # 发送测试请求
        result = self.embed_batch(["test"])

        if result is not None:
            return True, f"Connection successful, model: {self.model}, dimension: {len(result[0])}"
        else:
            return False, "Failed to connect to Embedding API"