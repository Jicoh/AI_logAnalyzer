"""
向量检索模块
使用向量相似度进行文档检索
"""

import os
import json
import pickle
import numpy as np
from typing import List, Optional
import logging

from .embedding_client import EmbeddingClient

logger = logging.getLogger(__name__)


class VectorStore:
    """向量存储，使用 numpy 进行相似度搜索"""

    def __init__(self, dimension: int = 1536):
        """
        初始化向量存储

        Args:
            dimension: 向量维度
        """
        self.dimension = dimension
        self.vectors = None  # numpy 数组，shape: (n, dimension)
        self.doc_count = 0

    def add_vectors(self, vectors: List[List[float]]):
        """
        添加向量

        Args:
            vectors: 向量列表
        """
        if not vectors:
            return

        new_vectors = np.array(vectors, dtype=np.float32)

        if self.vectors is None:
            self.vectors = new_vectors
        else:
            self.vectors = np.vstack([self.vectors, new_vectors])

        self.doc_count = len(self.vectors)

    def search(self, query_vector: List[float], top_n: int = 10) -> List[tuple]:
        """
        搜索最相似的向量

        Args:
            query_vector: 查询向量
            top_n: 返回数量

        Returns:
            list: [(文档索引, 相似度分数), ...]
        """
        if self.vectors is None or self.doc_count == 0:
            return []

        query = np.array(query_vector, dtype=np.float32)

        # 归一化查询向量
        query_norm = query / (np.linalg.norm(query) + 1e-8)

        # 归一化所有向量
        norms = np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-8
        normalized_vectors = self.vectors / norms

        # 计算余弦相似度
        similarities = np.dot(normalized_vectors, query_norm)

        # 获取 top_n 索引
        top_indices = np.argsort(similarities)[::-1][:top_n]

        return [(int(idx), float(similarities[idx])) for idx in top_indices]

    def save(self, file_path: str):
        """保存向量存储"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        data = {
            'dimension': self.dimension,
            'doc_count': self.doc_count,
            'vectors': self.vectors
        }
        with open(file_path, 'wb') as f:
            pickle.dump(data, f)

    def load(self, file_path: str):
        """加载向量存储"""
        with open(file_path, 'rb') as f:
            data = pickle.load(f)

        self.dimension = data['dimension']
        self.doc_count = data['doc_count']
        self.vectors = data['vectors']


class VectorRetriever:
    """向量检索器，提供与 BM25Retriever 相同的接口"""

    def __init__(self, embedding_client: EmbeddingClient, dimension: int = 1536):
        """
        初始化向量检索器

        Args:
            embedding_client: Embedding 客户端
            dimension: 向量维度
        """
        self.embedding_client = embedding_client
        self.vector_store = VectorStore(dimension)
        self.chunks = []
        self.indexed = False

    def index_documents(self, chunks: List[dict]) -> bool:
        """
        索引文档块

        Args:
            chunks: 文档块列表，每块包含 content 字段

        Returns:
            bool: 是否成功
        """
        if not chunks:
            return True

        if not self.embedding_client.is_enabled():
            logger.warning("Embedding client not enabled, skipping vector indexing")
            return False

        self.chunks = chunks
        texts = [chunk['content'] for chunk in chunks]

        # 获取向量
        logger.info(f"Indexing {len(texts)} documents with embedding...")
        vectors = self.embedding_client.embed_texts(texts)

        if vectors is None:
            logger.error("Failed to get embeddings")
            return False

        # 添加到向量存储
        self.vector_store.add_vectors(vectors)
        self.indexed = True
        logger.info(f"Successfully indexed {len(vectors)} documents")

        return True

    def retrieve(self, query: str, top_n: int = 5) -> List[dict]:
        """
        检索相关文档块

        Args:
            query: 查询文本
            top_n: 返回数量

        Returns:
            list: 相关文档块列表
        """
        if not self.indexed:
            return []

        # 获取查询向量
        query_vector = self.embedding_client.embed_query(query)
        if query_vector is None:
            logger.error("Failed to get query embedding")
            return []

        # 搜索
        results = self.vector_store.search(query_vector, top_n)

        return [
            {
                'chunk': self.chunks[idx],
                'score': score
            }
            for idx, score in results if score > 0
        ]

    def save_index(self, file_path: str):
        """保存索引"""
        self.vector_store.save(file_path)
        # 保存 chunks
        chunk_path = file_path + '.chunks'
        with open(chunk_path, 'w', encoding='utf-8') as f:
            json.dump(self.chunks, f, ensure_ascii=False)

    def load_index(self, file_path: str):
        """加载索引"""
        self.vector_store.load(file_path)
        # 加载 chunks
        chunk_path = file_path + '.chunks'
        if os.path.exists(chunk_path):
            with open(chunk_path, 'r', encoding='utf-8') as f:
                self.chunks = json.load(f)
        self.indexed = True

    def is_indexed(self) -> bool:
        """检查是否已索引"""
        return self.indexed and self.vector_store.doc_count > 0