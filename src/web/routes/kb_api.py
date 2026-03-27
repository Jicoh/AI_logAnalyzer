"""
Knowledge Base API routes.
"""

import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from src.knowledge_base.manager import KnowledgeBaseManager
from src.config_manager.manager import ConfigManager

kb_bp = Blueprint('kb_api', __name__)

# Global instances
config_manager = None
kb_manager = None


def get_kb_manager():
    """Get or create KnowledgeBaseManager instance."""
    global config_manager, kb_manager
    if config_manager is None:
        config_manager = ConfigManager()
    if kb_manager is None:
        kb_manager = KnowledgeBaseManager(config=config_manager.get_all())
    return kb_manager


def allowed_file(filename):
    """Check if file extension is allowed."""
    ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx', 'doc'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@kb_bp.route('/api/kb', methods=['GET'])
def list_kb():
    """List all knowledge bases."""
    try:
        manager = get_kb_manager()
        kb_list = manager.list()
        # Add 'id' field as alias for 'kb_id' for frontend compatibility
        for kb in kb_list:
            if 'kb_id' in kb and 'id' not in kb:
                kb['id'] = kb['kb_id']
        return jsonify({'success': True, 'data': kb_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb', methods=['POST'])
def create_kb():
    """Create a new knowledge base."""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400

        manager = get_kb_manager()
        kb_id = manager.create(name, description)
        kb_info = manager.get(kb_id)

        # Add 'id' field as alias for 'kb_id' for frontend compatibility
        if kb_info and 'kb_id' in kb_info and 'id' not in kb_info:
            kb_info['id'] = kb_info['kb_id']

        return jsonify({'success': True, 'data': kb_info}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>', methods=['GET'])
def get_kb(kb_id):
    """Get knowledge base details."""
    try:
        manager = get_kb_manager()
        kb_info = manager.get(kb_id)

        if kb_info is None:
            return jsonify({'success': False, 'error': 'Knowledge base not found'}), 404

        # Add 'id' field as alias for 'kb_id' for frontend compatibility
        if 'kb_id' in kb_info and 'id' not in kb_info:
            kb_info['id'] = kb_info['kb_id']

        return jsonify({'success': True, 'data': kb_info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>', methods=['DELETE'])
def delete_kb(kb_id):
    """Delete a knowledge base."""
    try:
        manager = get_kb_manager()
        success = manager.delete(kb_id)

        if not success:
            return jsonify({'success': False, 'error': 'Knowledge base not found'}), 404

        return jsonify({'success': True, 'message': 'Knowledge base deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>/documents', methods=['POST'])
def upload_document(kb_id):
    """Upload a document to knowledge base."""
    try:
        # Check if knowledge base exists
        manager = get_kb_manager()
        kb_info = manager.get(kb_id)
        if kb_info is None:
            return jsonify({'success': False, 'error': 'Knowledge base not found'}), 404

        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not allowed. Allowed: txt, md, pdf, docx, doc'}), 400

        # Save file to uploads directory
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'data', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(uploads_dir, unique_filename)
        file.save(file_path)

        # Add document to knowledge base
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
def delete_document(kb_id, doc_id):
    """Delete a document from knowledge base."""
    try:
        manager = get_kb_manager()

        # Check if knowledge base exists
        kb_info = manager.get(kb_id)
        if kb_info is None:
            return jsonify({'success': False, 'error': 'Knowledge base not found'}), 404

        success = manager.remove_document(kb_id, doc_id)

        if not success:
            return jsonify({'success': False, 'error': 'Document not found'}), 404

        return jsonify({'success': True, 'message': 'Document deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>/search', methods=['POST'])
def search_kb(kb_id):
    """Search in knowledge base."""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        top_n = data.get('top_n', 5)

        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400

        manager = get_kb_manager()

        # Check if knowledge base exists
        kb_info = manager.get(kb_id)
        if kb_info is None:
            return jsonify({'success': False, 'error': 'Knowledge base not found'}), 404

        results = manager.search(kb_id, query, top_n)

        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@kb_bp.route('/api/kb/<kb_id>/reindex', methods=['POST'])
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