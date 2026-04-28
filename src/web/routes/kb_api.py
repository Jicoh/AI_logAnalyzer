"""
知识库 API 路由。
"""

import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from src.knowledge_base.manager import KnowledgeBaseManager
from src.config_manager.manager import ConfigManager
from src.auth.decorators import admin_required

kb_bp = Blueprint('kb_api', __name__)

# 全局实例
config_manager = None
kb_manager = None


def get_kb_manager():
    """获取或创建 KnowledgeBaseManager 实例。"""
    global config_manager, kb_manager
    if config_manager is None:
        config_manager = ConfigManager()
    if kb_manager is None:
        kb_manager = KnowledgeBaseManager(config=config_manager.get_all())
    return kb_manager


def allowed_file(filename):
    """检查文件扩展名是否允许。"""
    ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx', 'doc'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@kb_bp.route('/api/kb', methods=['GET'])
def list_kb():
    """列出所有知识库。"""
    try:
        manager = get_kb_manager()
        kb_list = manager.list()
        # 为前端兼容性添加 'id' 字段作为 'kb_id' 的别名
        for kb in kb_list:
            if 'kb_id' in kb and 'id' not in kb:
                kb['id'] = kb['kb_id']
            # 添加向量索引状态
            kb_dir = os.path.join(manager.document_dir, kb.get('kb_id') or kb.get('id'))
            kb['vector_indexed'] = os.path.exists(os.path.join(kb_dir, 'vector_index'))
        return jsonify({'success': True, 'data': kb_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb', methods=['POST'])
@admin_required
def create_kb():
    """创建新的知识库。"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400

        manager = get_kb_manager()
        kb_id = manager.create(name, description)
        kb_info = manager.get(kb_id)

        # 为前端兼容性添加 'id' 字段作为 'kb_id' 的别名
        if kb_info and 'kb_id' in kb_info and 'id' not in kb_info:
            kb_info['id'] = kb_info['kb_id']

        return jsonify({'success': True, 'data': kb_info}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>', methods=['GET'])
def get_kb(kb_id):
    """获取知识库详情。"""
    try:
        manager = get_kb_manager()
        kb_info = manager.get(kb_id)

        if kb_info is None:
            return jsonify({'success': False, 'error': '知识库不存在'}), 404

        # 为前端兼容性添加 'id' 字段作为 'kb_id' 的别名
        if 'kb_id' in kb_info and 'id' not in kb_info:
            kb_info['id'] = kb_info['kb_id']

        # 添加向量索引状态
        kb_dir = os.path.join(manager.document_dir, kb_id)
        kb_info['vector_indexed'] = os.path.exists(os.path.join(kb_dir, 'vector_index'))

        return jsonify({'success': True, 'data': kb_info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>', methods=['DELETE'])
@admin_required
def delete_kb(kb_id):
    """删除知识库。"""
    try:
        manager = get_kb_manager()
        success = manager.delete(kb_id)

        if not success:
            return jsonify({'success': False, 'error': '知识库不存在'}), 404

        return jsonify({'success': True, 'message': '知识库已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>/documents', methods=['POST'])
@admin_required
def upload_document(kb_id):
    """上传文档到知识库。"""
    try:
        # 检查知识库是否存在
        manager = get_kb_manager()
        kb_info = manager.get(kb_id)
        if kb_info is None:
            return jsonify({'success': False, 'error': '知识库不存在'}), 404

        # 检查是否有文件
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '未提供文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '未选择文件'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': '不允许的文件类型。允许: txt, md, pdf, docx, doc'}), 400

        # 保存文件到上传目录
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'data', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(uploads_dir, unique_filename)
        file.save(file_path)

        # 添加文档到知识库
        doc_id = manager.add_document(kb_id, file_path)

        return jsonify({
            'success': True,
            'data': {
                'doc_id': doc_id,
                'filename': filename,
                'original_filename': file.filename
            }
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>/documents/<doc_id>', methods=['DELETE'])
@admin_required
def delete_document(kb_id, doc_id):
    """从知识库删除文档。"""
    try:
        manager = get_kb_manager()

        # 检查知识库是否存在
        kb_info = manager.get(kb_id)
        if kb_info is None:
            return jsonify({'success': False, 'error': '知识库不存在'}), 404

        success = manager.remove_document(kb_id, doc_id)

        if not success:
            return jsonify({'success': False, 'error': '文档不存在'}), 404

        return jsonify({'success': True, 'message': '文档已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>/search', methods=['POST'])
def search_kb(kb_id):
    """在知识库中搜索。"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        top_n = data.get('top_n', 5)

        if not query:
            return jsonify({'success': False, 'error': '查询不能为空'}), 400

        manager = get_kb_manager()

        # 检查知识库是否存在
        kb_info = manager.get(kb_id)
        if kb_info is None:
            return jsonify({'success': False, 'error': '知识库不存在'}), 404

        results = manager.search(kb_id, query, top_n)

        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>/reindex', methods=['POST'])
@admin_required
def reindex_kb(kb_id):
    """重建知识库索引（包括向量索引）"""
    try:
        manager = get_kb_manager()
        result = manager.reindex(kb_id)

        if result['status'] == 'success':
            return jsonify({
                'success': True,
                'message': result['message'],
                'indexed_count': result['indexed_count'],
                'vector_index': result['vector_index']
            })
        else:
            return jsonify({'success': False, 'error': result['message']}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500