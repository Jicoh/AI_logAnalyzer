"""
向量检索模块
使用 Faiss 进行向量相似度搜索
"""

import os
import json
import pickle
import math
import logging
from typing import List, Optional

import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

from .embedding_client import EmbeddingClient

logger = logging.getLogger(__name__)


class VectorStore:
    """向量存储，使用 Faiss 进行相似度搜索"""

    def __init__(self, dimension: int = 1536, faiss_config: dict = None):
        """
        初始化向量存储

        Args:
            dimension: 向量维度
            faiss_config: Faiss 配置，包含:
                - enabled: 是否启用 Faiss (默认 True)
                - index_type: 索引类型 (auto/flat/ivf)
                - nlist: IVF 聚类数量 (默认 100)
                - nprobe: 搜索探测聚类数 (默认 10)
                - use_gpu: 是否使用 GPU (默认 False)
        """
        if not FAISS_AVAILABLE:
            logger.warning("Faiss not available, falling back to numpy implementation")

        self.dimension = dimension
        self.faiss_config = faiss_config or {}
        self.index = None
        self.doc_count = 0

        # 旧 numpy 实现 (用于回退)
        self.vectors = None

    def create_index(self, n_vectors: int) -> bool:
        """
        创建 Faiss 索引

        Args:
            n_vectors: 向量数量

        Returns:
            bool: 是否成功创建
        """
        if not FAISS_AVAILABLE or not self.faiss_config.get('enabled', True):
            return False

        index_type = self.faiss_config.get('index_type', 'auto')

        # 根据数据规模自动选择索引类型
        if index_type == 'auto':
            if n_vectors < 100000:
                index_type = 'flat'
            else:
                index_type = 'ivf'

        try:
            if index_type == 'flat':
                # 暴力搜索，精度最高
                self.index = faiss.IndexFlatIP(self.dimension)
                logger.info(f"Created Faiss IndexFlatIP with dimension {self.dimension}")
            else:
                # IVF 索引
                nlist = self.faiss_config.get('nlist', max(100, int(math.sqrt(n_vectors))))
                quantizer = faiss.IndexFlatIP(self.dimension)
                self.index = faiss.IndexIVFFlat(quantizer, self.dimension, nlist)
                logger.info(f"Created Faiss IndexIVFFlat with nlist={nlist}")

            return True
        except Exception as e:
            logger.error(f"Failed to create Faiss index: {e}")
            self.index = None
            return False

    def add_vectors(self, vectors: List[List[float]]):
        """
        添加向量

        Args:
            vectors: 向量列表
        """
        if not vectors:
            return

        vectors_np = np.array(vectors, dtype=np.float32)

        # 使用 Faiss
        if FAISS_AVAILABLE and self.faiss_config.get('enabled', True):
            # 归一化向量 (内积 + 归一化 = 余弦相似度)
            faiss.normalize_L2(vectors_np)

            # 首次创建索引
            if self.index is None:
                if not self.create_index(len(vectors_np)):
                    # 回退到 numpy
                    self.add_vectors_numpy(vectors)
                    return

            # IVF 索引需要训练
            if isinstance(self.index, faiss.IndexIVFFlat):
                if not self.index.is_trained:
                    self.index.train(vectors_np)

            self.index.add(vectors_np)
            self.doc_count = self.index.ntotal
            logger.info(f"Added {len(vectors)} vectors to Faiss index, total: {self.doc_count}")
        else:
            # 使用 numpy 回退
            self.add_vectors_numpy(vectors)

    def add_vectors_numpy(self, vectors: List[List[float]]):
        """使用 numpy 添加向量 (回退方案)"""
        new_vectors = np.array(vectors, dtype=np.float32)

        if self.vectors is None:
            self.vectors = new_vectors
        else:
            self.vectors = np.vstack([self.vectors, new_vectors])

        self.doc_count = len(self.vectors)
        logger.info(f"Added {len(vectors)} vectors to numpy store, total: {self.doc_count}")

    def search(self, query_vector: List[float], top_n: int = 10) -> List[tuple]:
        """
        搜索最相似的向量

        Args:
            query_vector: 查询向量
            top_n: 返回数量

        Returns:
            list: [(文档索引, 相似度分数), ...]
        """
        if self.doc_count == 0:
            return []

        # 使用 Faiss
        if self.index is not None:
            return self.search_faiss(query_vector, top_n)
        else:
            return self.search_numpy(query_vector, top_n)

    def search_faiss(self, query_vector: List[float], top_n: int) -> List[tuple]:
        """使用 Faiss 搜索"""
        query = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(query)

        # IVF 索引设置 nprobe
        if isinstance(self.index, faiss.IndexIVFFlat):
            nprobe = self.faiss_config.get('nprobe', 10)
            self.index.nprobe = min(nprobe, self.index.nlist)

        # 搜索
        actual_top_n = min(top_n, self.doc_count)
        distances, indices = self.index.search(query, actual_top_n)

        # 过滤无效结果 (Faiss 返回 -1 表示无效)
        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if idx >= 0:
                results.append((int(idx), float(dist)))

        return results

    def search_numpy(self, query_vector: List[float], top_n: int) -> List[tuple]:
        """使用 numpy 搜索 (回退方案)"""
        if self.vectors is None:
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

        if self.index is not None:
            # 保存 Faiss 索引
            faiss.write_index(self.index, file_path + '.faiss')

            # 保存元数据
            meta = {
                'dimension': self.dimension,
                'doc_count': self.doc_count,
                'index_type': 'ivf' if isinstance(self.index, faiss.IndexIVFFlat) else 'flat',
                'backend': 'faiss'
            }
            with open(file_path + '.meta.json', 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)

            logger.info(f"Saved Faiss index to {file_path}.faiss")
        else:
            # 保存 numpy 格式
            data = {
                'dimension': self.dimension,
                'doc_count': self.doc_count,
                'vectors': self.vectors
            }
            with open(file_path, 'wb') as f:
                pickle.dump(data, f)

            logger.info(f"Saved numpy vectors to {file_path}")

    def load(self, file_path: str):
        """加载向量存储，支持新旧格式自动迁移"""
        faiss_path = file_path + '.faiss'
        meta_path = file_path + '.meta.json'

        # 尝试加载 Faiss 格式
        if os.path.exists(faiss_path) and os.path.exists(meta_path):
            try:
                self.index = faiss.read_index(faiss_path)
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                self.dimension = meta['dimension']
                self.doc_count = meta['doc_count']
                logger.info(f"Loaded Faiss index from {faiss_path}, {self.doc_count} vectors")
                return
            except Exception as e:
                logger.error(f"Failed to load Faiss index: {e}")

        # 尝试加载旧 pickle 格式并迁移
        if os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)

                self.dimension = data['dimension']
                self.doc_count = data['doc_count']
                old_vectors = data.get('vectors')

                if old_vectors is not None and len(old_vectors) > 0:
                    # 迁移到 Faiss
                    if FAISS_AVAILABLE and self.faiss_config.get('enabled', True):
                        self.create_index(len(old_vectors))
                        self.add_vectors(old_vectors.tolist())
                        # 保存为新格式
                        self.save(file_path)
                        # 删除旧文件
                        os.remove(file_path)
                        logger.info(f"Migrated {self.doc_count} vectors to Faiss format")
                    else:
                        # 保持 numpy 格式
                        self.vectors = old_vectors
                        logger.info(f"Loaded {self.doc_count} vectors from numpy format")

            except Exception as e:
                logger.error(f"Failed to load vector store: {e}")


class VectorRetriever:
    """向量检索器，提供与 BM25Retriever 相同的接口"""

    def __init__(self, embedding_client: EmbeddingClient, dimension: int = 1536, faiss_config: dict = None):
        """
        初始化向量检索器

        Args:
            embedding_client: Embedding 客户端
            dimension: 向量维度
            faiss_config: Faiss 配置
        """
        self.embedding_client = embedding_client
        self.vector_store = VectorStore(dimension, faiss_config)
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