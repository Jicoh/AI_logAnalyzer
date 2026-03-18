"""
BM25检索模块
使用BM25算法进行文档检索
"""

import os
import json
import pickle
from collections import Counter


class BM25:
    """BM25检索实现"""

    def __init__(self, k1=1.5, b=0.75):
        """
        初始化BM25

        Args:
            k1: BM25参数k1，控制词频饱和度
            b: BM25参数b，控制文档长度归一化
        """
        self.k1 = k1
        self.b = b
        self.doc_count = 0
        self.avgdl = 0
        self.doc_freqs = {}
        self.doc_len = []
        self.doc_vecs = []
        self.idf = {}
        self.documents = []

    def fit(self, documents):
        """
        构建索引

        Args:
            documents: 文档列表，每个文档是分词后的列表或字符串
        """
        self.documents = documents
        self.doc_count = len(documents)
        self.doc_len = []
        self.doc_freqs = {}

        # 处理文档
        doc_terms_list = []
        total_len = 0

        for doc in documents:
            if isinstance(doc, str):
                terms = self._tokenize(doc)
            else:
                terms = doc

            self.doc_len.append(len(terms))
            total_len += len(terms)

            term_freqs = Counter(terms)
            doc_terms_list.append(term_freqs)

            for term in term_freqs.keys():
                if term not in self.doc_freqs:
                    self.doc_freqs[term] = 0
                self.doc_freqs[term] += 1

        self.avgdl = total_len / self.doc_count if self.doc_count > 0 else 0
        self.doc_vecs = doc_terms_list
        self._calculate_idf()

    def _tokenize(self, text):
        """简单分词"""
        # 使用jieba进行中文分词
        try:
            import jieba
            return list(jieba.cut(text))
        except ImportError:
            # 回退到简单分词
            return text.lower().split()

    def _calculate_idf(self):
        """计算IDF值"""
        import math
        for term, df in self.doc_freqs.items():
            self.idf[term] = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)

    def get_scores(self, query):
        """
        计算查询与所有文档的BM25分数

        Args:
            query: 查询文本或分词列表

        Returns:
            list: 分数列表
        """
        if isinstance(query, str):
            query_terms = self._tokenize(query)
        else:
            query_terms = query

        scores = []
        for idx, doc_vec in enumerate(self.doc_vecs):
            score = self._score_document(query_terms, doc_vec, self.doc_len[idx])
            scores.append(score)

        return scores

    def _score_document(self, query_terms, doc_vec, doc_len):
        """计算单个文档的BM25分数"""
        score = 0.0
        for term in query_terms:
            if term not in doc_vec:
                continue

            tf = doc_vec[term]
            idf = self.idf.get(term, 0)

            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
            score += idf * numerator / denominator

        return score

    def search(self, query, top_n=10):
        """
        检索最相关的文档

        Args:
            query: 查询文本
            top_n: 返回的文档数量

        Returns:
            list: [(文档索引, 分数), ...]
        """
        scores = self.get_scores(query)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_n]

    def save(self, file_path):
        """保存索引到文件"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        # 将Counter转换为dict以便序列化
        doc_vecs_dict = [dict(vec) for vec in self.doc_vecs]
        data = {
            'k1': self.k1,
            'b': self.b,
            'doc_count': self.doc_count,
            'avgdl': self.avgdl,
            'doc_freqs': self.doc_freqs,
            'doc_len': self.doc_len,
            'idf': self.idf,
            'doc_vecs': doc_vecs_dict
        }
        with open(file_path, 'wb') as f:
            pickle.dump(data, f)
        # 单独保存文档
        doc_path = file_path + '.docs'
        with open(doc_path, 'w', encoding='utf-8') as f:
            json.dump(self.documents, f, ensure_ascii=False)

    def load(self, file_path):
        """从文件加载索引"""
        with open(file_path, 'rb') as f:
            data = pickle.load(f)

        self.k1 = data['k1']
        self.b = data['b']
        self.doc_count = data['doc_count']
        self.avgdl = data['avgdl']
        self.doc_freqs = data['doc_freqs']
        self.doc_len = data['doc_len']
        self.idf = data['idf']
        # 将dict转换回Counter
        self.doc_vecs = [Counter(vec) for vec in data.get('doc_vecs', [])]

        doc_path = file_path + '.docs'
        if os.path.exists(doc_path):
            with open(doc_path, 'r', encoding='utf-8') as f:
                self.documents = json.load(f)


class BM25Retriever:
    """BM25检索器，提供更高级的接口"""

    def __init__(self, k1=1.5, b=0.75):
        self.bm25 = BM25(k1, b)
        self.chunks = []
        self.indexed = False

    def index_documents(self, chunks):
        """
        索引文档块

        Args:
            chunks: 文档块列表，每块包含content字段
        """
        self.chunks = chunks
        documents = [chunk['content'] for chunk in chunks]
        self.bm25.fit(documents)
        self.indexed = True

    def retrieve(self, query, top_n=5):
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

        results = self.bm25.search(query, top_n)
        return [
            {
                'chunk': self.chunks[idx],
                'score': score
            }
            for idx, score in results if score > 0
        ]

    def save_index(self, file_path):
        """保存索引"""
        self.bm25.save(file_path)
        chunk_path = file_path + '.chunks'
        with open(chunk_path, 'w', encoding='utf-8') as f:
            json.dump(self.chunks, f, ensure_ascii=False)

    def load_index(self, file_path):
        """加载索引"""
        self.bm25.load(file_path)
        chunk_path = file_path + '.chunks'
        if os.path.exists(chunk_path):
            with open(chunk_path, 'r', encoding='utf-8') as f:
                self.chunks = json.load(f)
        self.indexed = True