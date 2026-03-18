"""
知识库管理模块
管理知识库的创建、删除、查询和文档管理
"""

import os
import json
import uuid
from datetime import datetime

from .document_loader import DocumentLoader, load_document_chunks
from .bm25_retriever import BM25Retriever


class KnowledgeBaseManager:
    """知识库管理器"""

    def __init__(self, document_dir=None, config=None):
        """
        初始化知识库管理器

        Args:
            document_dir: 文档存储目录
            config: 配置字典，包含bm25参数
        """
        if document_dir is None:
            document_dir = self._get_default_document_dir()
        self.document_dir = document_dir
        self.config = config or {}
        self.kb_registry_path = os.path.join(self.document_dir, 'kb_registry.json')
        self.kb_registry = self._load_registry()

    def _get_default_document_dir(self):
        """获取默认文档目录"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'document')

    def _load_registry(self):
        """加载知识库注册表"""
        if os.path.exists(self.kb_registry_path):
            with open(self.kb_registry_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'knowledge_bases': {}}

    def _save_registry(self):
        """保存知识库注册表"""
        os.makedirs(os.path.dirname(self.kb_registry_path), exist_ok=True)
        with open(self.kb_registry_path, 'w', encoding='utf-8') as f:
            json.dump(self.kb_registry, f, indent=4, ensure_ascii=False)

    def create(self, name, description=''):
        """
        创建知识库

        Args:
            name: 知识库名称
            description: 知识库描述

        Returns:
            str: 知识库ID
        """
        kb_id = f"kb_{uuid.uuid4().hex[:8]}"
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        kb_info = {
            'kb_id': kb_id,
            'name': name,
            'description': description,
            'version': '1.0',
            'created_at': now,
            'updated_at': now,
            'document_count': 0,
            'documents': []
        }

        # 创建知识库目录
        kb_dir = os.path.join(self.document_dir, kb_id)
        os.makedirs(kb_dir, exist_ok=True)

        # 保存知识库元数据
        kb_meta_path = os.path.join(kb_dir, 'metadata.json')
        with open(kb_meta_path, 'w', encoding='utf-8') as f:
            json.dump(kb_info, f, indent=4, ensure_ascii=False)

        # 更新注册表
        self.kb_registry['knowledge_bases'][kb_id] = {
            'name': name,
            'path': kb_dir
        }
        self._save_registry()

        return kb_id

    def delete(self, kb_id):
        """
        删除知识库

        Args:
            kb_id: 知识库ID

        Returns:
            bool: 是否成功
        """
        if kb_id not in self.kb_registry['knowledge_bases']:
            return False

        kb_dir = os.path.join(self.document_dir, kb_id)
        if os.path.exists(kb_dir):
            import shutil
            shutil.rmtree(kb_dir)

        del self.kb_registry['knowledge_bases'][kb_id]
        self._save_registry()

        return True

    def get(self, kb_id):
        """
        获取知识库信息

        Args:
            kb_id: 知识库ID

        Returns:
            dict: 知识库信息
        """
        kb_dir = os.path.join(self.document_dir, kb_id)
        kb_meta_path = os.path.join(kb_dir, 'metadata.json')

        if not os.path.exists(kb_meta_path):
            return None

        with open(kb_meta_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def list(self):
        """
        列出所有知识库

        Returns:
            list: 知识库信息列表
        """
        result = []
        for kb_id, kb_info in self.kb_registry['knowledge_bases'].items():
            kb_data = self.get(kb_id)
            if kb_data:
                result.append(kb_data)
        return result

    def add_document(self, kb_id, file_path):
        """
        向知识库添加文档

        Args:
            kb_id: 知识库ID
            file_path: 文档路径

        Returns:
            str: 文档ID
        """
        kb_info = self.get(kb_id)
        if not kb_info:
            raise ValueError(f"知识库不存在: {kb_id}")

        # 加载文档
        loader = DocumentLoader()
        doc = loader.load(file_path)

        # 生成文档ID
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 分块处理
        chunks = loader.load_and_split(file_path)

        # 保存文档和分块
        kb_dir = os.path.join(self.document_dir, kb_id)
        doc_dir = os.path.join(kb_dir, doc_id)
        os.makedirs(doc_dir, exist_ok=True)

        # 保存文档元数据
        doc_meta = {
            'doc_id': doc_id,
            'file_name': doc['file_name'],
            'file_type': doc['file_type'],
            'char_count': doc['char_count'],
            'chunk_count': len(chunks),
            'source_path': file_path,
            'created_at': now
        }

        with open(os.path.join(doc_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
            json.dump(doc_meta, f, indent=4, ensure_ascii=False)

        # 保存文档块
        with open(os.path.join(doc_dir, 'chunks.json'), 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False)

        # 更新知识库元数据
        kb_info['documents'].append(doc_meta)
        kb_info['document_count'] = len(kb_info['documents'])
        kb_info['updated_at'] = now

        kb_meta_path = os.path.join(kb_dir, 'metadata.json')
        with open(kb_meta_path, 'w', encoding='utf-8') as f:
            json.dump(kb_info, f, indent=4, ensure_ascii=False)

        # 更新索引
        self._update_index(kb_id)

        return doc_id

    def remove_document(self, kb_id, doc_id):
        """
        从知识库移除文档

        Args:
            kb_id: 知识库ID
            doc_id: 文档ID

        Returns:
            bool: 是否成功
        """
        kb_info = self.get(kb_id)
        if not kb_info:
            return False

        # 删除文档目录
        kb_dir = os.path.join(self.document_dir, kb_id)
        doc_dir = os.path.join(kb_dir, doc_id)
        if os.path.exists(doc_dir):
            import shutil
            shutil.rmtree(doc_dir)

        # 更新知识库元数据
        kb_info['documents'] = [
            doc for doc in kb_info['documents'] if doc['doc_id'] != doc_id
        ]
        kb_info['document_count'] = len(kb_info['documents'])
        kb_info['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        kb_meta_path = os.path.join(kb_dir, 'metadata.json')
        with open(kb_meta_path, 'w', encoding='utf-8') as f:
            json.dump(kb_info, f, indent=4, ensure_ascii=False)

        # 更新索引
        self._update_index(kb_id)

        return True

    def _update_index(self, kb_id):
        """更新知识库索引"""
        kb_info = self.get(kb_id)
        if not kb_info:
            return

        kb_dir = os.path.join(self.document_dir, kb_id)

        # 收集所有文档块
        all_chunks = []
        for doc_meta in kb_info['documents']:
            doc_id = doc_meta['doc_id']
            chunks_path = os.path.join(kb_dir, doc_id, 'chunks.json')
            if os.path.exists(chunks_path):
                with open(chunks_path, 'r', encoding='utf-8') as f:
                    chunks = json.load(f)
                    all_chunks.extend(chunks)

        # 构建索引
        if all_chunks:
            bm25_config = self.config.get('bm25', {})
            retriever = BM25Retriever(
                k1=bm25_config.get('k1', 1.5),
                b=bm25_config.get('b', 0.75)
            )
            retriever.index_documents(all_chunks)
            retriever.save_index(os.path.join(kb_dir, 'index'))

    def get_retriever(self, kb_id):
        """
        获取知识库检索器

        Args:
            kb_id: 知识库ID

        Returns:
            BM25Retriever: 检索器实例
        """
        kb_dir = os.path.join(self.document_dir, kb_id)
        index_path = os.path.join(kb_dir, 'index')

        if not os.path.exists(index_path):
            return None

        bm25_config = self.config.get('bm25', {})
        retriever = BM25Retriever(
            k1=bm25_config.get('k1', 1.5),
            b=bm25_config.get('b', 0.75)
        )
        retriever.load_index(index_path)
        return retriever

    def search(self, kb_id, query, top_n=5):
        """
        在知识库中搜索

        Args:
            kb_id: 知识库ID
            query: 查询文本
            top_n: 返回数量

        Returns:
            list: 搜索结果
        """
        retriever = self.get_retriever(kb_id)
        if not retriever:
            return []
        return retriever.retrieve(query, top_n)