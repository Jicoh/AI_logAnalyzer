"""
文档加载器模块
支持多种格式文档的加载和分块处理
"""

import os
import re

# 顶层导入，确保 PyInstaller 正确打包
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None


class DocumentLoader:
    """文档加载器，支持多种格式"""

    SUPPORTED_FORMATS = ['.txt', '.md', '.pdf', '.docx']

    def __init__(self, chunk_size=500, chunk_overlap=50):
        """
        初始化文档加载器

        Args:
            chunk_size: 分块大小（字符数）
            chunk_overlap: 分块重叠大小
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load(self, file_path):
        """
        加载文档

        Args:
            file_path: 文档路径

        Returns:
            dict: 包含文档内容和元数据
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext not in self.SUPPORTED_FORMATS:
            raise ValueError(f"不支持的文件格式: {ext}")

        loader_map = {
            '.txt': self.load_txt,
            '.md': self.load_txt,
            '.pdf': self.load_pdf,
            '.docx': self.load_docx
        }

        content = loader_map[ext](file_path)

        return {
            'file_path': file_path,
            'file_name': os.path.basename(file_path),
            'file_type': ext[1:],
            'content': content,
            'char_count': len(content)
        }

    def load_txt(self, file_path):
        """加载txt/md文件"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def load_pdf(self, file_path):
        """加载PDF文件"""
        if PdfReader is None:
            raise ImportError("请安装pypdf: pip install pypdf")

        reader = PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return '\n'.join(text_parts)

    def load_docx(self, file_path):
        """加载Word文档"""
        if Document is None:
            raise ImportError("请安装python-docx: pip install python-docx")

        doc = Document(file_path)
        text_parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        return '\n'.join(text_parts)

    def split_into_chunks(self, content):
        """
        将文本分割成块

        Args:
            content: 文本内容

        Returns:
            list: 文本块列表
        """
        if len(content) <= self.chunk_size:
            return [content]

        chunks = []
        start = 0

        while start < len(content):
            end = start + self.chunk_size

            if end >= len(content):
                chunks.append(content[start:].strip())
                break

            # 尝试在句子边界分割
            chunk = content[start:end]
            last_period = max(
                chunk.rfind('。'),
                chunk.rfind('！'),
                chunk.rfind('？'),
                chunk.rfind('.'),
                chunk.rfind('!'),
                chunk.rfind('?'),
                chunk.rfind('\n')
            )

            if last_period > self.chunk_size // 2:
                end = start + last_period + 1

            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - self.chunk_overlap
            if start < 0:
                start = 0

        return chunks

    def load_and_split(self, file_path):
        """
        加载文档并分块

        Args:
            file_path: 文档路径

        Returns:
            list: 文档块列表，每块包含内容和元数据
        """
        doc = self.load(file_path)
        chunks = self.split_into_chunks(doc['content'])

        result = []
        for i, chunk in enumerate(chunks):
            result.append({
                'content': chunk,
                'chunk_id': i,
                'total_chunks': len(chunks),
                'file_name': doc['file_name'],
                'file_type': doc['file_type'],
                'source': file_path
            })

        return result


def load_document_chunks(file_path, chunk_size=500, chunk_overlap=50):
    """
    加载文档并分块的便捷函数

    Args:
        file_path: 文档路径
        chunk_size: 分块大小
        chunk_overlap: 分块重叠

    Returns:
        list: 文档块列表
    """
    loader = DocumentLoader(chunk_size, chunk_overlap)
    return loader.load_and_split(file_path)