"""
混合检索模块
结合 BM25 和向量检索，使用 RRF 算法融合结果
"""

from typing import List, Optional
import logging

from .bm25_retriever import BM25Retriever
from .vector_retriever import VectorRetriever

logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    混合检索器
    支持 BM25、向量、混合三种模式
    使用 RRF (Reciprocal Rank Fusion) 算法融合结果
    """

    def __init__(
        self,
        bm25_retriever: BM25Retriever,
        vector_retriever: Optional[VectorRetriever],
        config: dict
    ):
        """
        初始化混合检索器

        Args:
            bm25_retriever: BM25 检索器
            vector_retriever: 向量检索器（可为 None）
            config: 检索配置，包含:
                - mode: 检索模式 (bm25, vector, hybrid)
                - bm25_weight: BM25 权重
                - vector_weight: 向量权重
                - top_n_multiplier: top_n 倍数（用于混合检索时获取更多候选）
        """
        self.bm25_retriever = bm25_retriever
        self.vector_retriever = vector_retriever

        retrieval_config = config.get('retrieval', {})
        self.mode = retrieval_config.get('mode', 'bm25')
        self.bm25_weight = retrieval_config.get('bm25_weight', 0.4)
        self.vector_weight = retrieval_config.get('vector_weight', 0.6)
        self.top_n_multiplier = retrieval_config.get('top_n_multiplier', 2)
        self.rrf_k = retrieval_config.get('rrf_k', 60)  # RRF 参数

    def retrieve(self, query: str, top_n: int = 5) -> List[dict]:
        """
        检索相关文档块

        Args:
            query: 查询文本
            top_n: 返回数量

        Returns:
            list: 相关文档块列表
        """
        if self.mode == 'bm25':
            return self.retrieve_bm25(query, top_n)
        elif self.mode == 'vector':
            return self.retrieve_vector(query, top_n)
        else:  # hybrid
            return self.retrieve_hybrid(query, top_n)

    def retrieve_bm25(self, query: str, top_n: int) -> List[dict]:
        """仅使用 BM25 检索"""
        if not self.bm25_retriever:
            return []
        results = self.bm25_retriever.retrieve(query, top_n)
        # 添加来源标记
        for r in results:
            r['bm25_score'] = r.get('score', 0)
        return results

    def retrieve_vector(self, query: str, top_n: int) -> List[dict]:
        """仅使用向量检索"""
        if not self.vector_retriever or not self.vector_retriever.is_indexed():
            logger.warning("Vector retriever not available, falling back to BM25")
            return self.retrieve_bm25(query, top_n)

        results = self.vector_retriever.retrieve(query, top_n)
        # 添加来源标记
        for r in results:
            r['vector_score'] = r.get('score', 0)
        return results

    def retrieve_hybrid(self, query: str, top_n: int) -> List[dict]:
        """混合检索，使用 RRF 融合"""
        # 检查向量检索器是否可用
        vector_available = self.vector_retriever and self.vector_retriever.is_indexed()

        if not vector_available:
            logger.warning("Vector retriever not available, falling back to BM25 only")
            return self.retrieve_bm25(query, top_n)

        if not self.bm25_retriever:
            logger.warning("BM25 retriever not available, falling back to vector only")
            return self.retrieve_vector(query, top_n)

        # 获取更多候选结果用于融合
        candidate_count = top_n * self.top_n_multiplier

        # 并行获取两种检索结果
        bm25_results = self.bm25_retriever.retrieve(query, candidate_count)
        vector_results = self.vector_retriever.retrieve(query, candidate_count)

        # 使用 RRF 融合
        fused_results = self.rrf_fuse(bm25_results, vector_results, top_n)

        return fused_results

    def rrf_fuse(
        self,
        bm25_results: List[dict],
        vector_results: List[dict],
        top_n: int
    ) -> List[dict]:
        """
        使用 RRF (Reciprocal Rank Fusion) 算法融合结果

        RRF 公式: score(d) = sum(1 / (k + rank(d)))
        其中 k 是常数，默认 60

        Args:
            bm25_results: BM25 检索结果
            vector_results: 向量检索结果
            top_n: 返回数量

        Returns:
            list: 融合后的结果
        """
        # 构建文档 ID 到结果的映射
        chunk_scores = {}  # chunk_id -> {chunk, bm25_score, vector_score, rrf_score}

        # 处理 BM25 结果
        for rank, result in enumerate(bm25_results, 1):
            chunk = result.get('chunk', {})
            chunk_id = self.get_chunk_id(chunk)

            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    'chunk': chunk,
                    'bm25_score': result.get('score', 0),
                    'bm25_rank': rank,
                    'vector_score': 0,
                    'vector_rank': None
                }

            # 计算 BM25 的 RRF 分数
            chunk_scores[chunk_id]['bm25_rrf'] = 1.0 / (self.rrf_k + rank)

        # 处理向量结果
        for rank, result in enumerate(vector_results, 1):
            chunk = result.get('chunk', {})
            chunk_id = self.get_chunk_id(chunk)

            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    'chunk': chunk,
                    'bm25_score': 0,
                    'bm25_rank': None,
                    'vector_score': result.get('score', 0),
                    'vector_rank': rank
                }
            else:
                chunk_scores[chunk_id]['vector_score'] = result.get('score', 0)
                chunk_scores[chunk_id]['vector_rank'] = rank

            # 计算向量的 RRF 分数
            chunk_scores[chunk_id]['vector_rrf'] = 1.0 / (self.rrf_k + rank)

        # 计算最终分数（加权 RRF）
        for chunk_id, data in chunk_scores.items():
            bm25_rrf = data.get('bm25_rrf', 0)
            vector_rrf = data.get('vector_rrf', 0)

            # 加权融合
            data['score'] = (
                self.bm25_weight * bm25_rrf +
                self.vector_weight * vector_rrf
            )

        # 按分数排序
        sorted_results = sorted(
            chunk_scores.values(),
            key=lambda x: x['score'],
            reverse=True
        )[:top_n]

        # 清理内部字段
        for r in sorted_results:
            r.pop('bm25_rrf', None)
            r.pop('vector_rrf', None)
            r.pop('bm25_rank', None)
            r.pop('vector_rank', None)

        return sorted_results

    def get_chunk_id(self, chunk: dict) -> str:
        """
        获取文档块的唯一标识

        Args:
            chunk: 文档块

        Returns:
            str: 唯一标识
        """
        # 使用 doc_id + chunk_index 或 content 作为标识
        doc_id = chunk.get('doc_id', '')
        chunk_index = chunk.get('chunk_index', '')
        content = chunk.get('content', '')

        if doc_id and chunk_index is not None:
            return f"{doc_id}_{chunk_index}"
        elif doc_id:
            return f"{doc_id}_{hash(content)}"
        else:
            # 使用内容哈希
            return str(hash(content))