"""
智能助手API路由。
提供会话管理、对话、文件管理等接口。
"""

import os
import zipfile
from io import BytesIO
from flask import Blueprint, jsonify, request, send_file, Response, stream_with_context
from flask_login import current_user

from src.auth.decorators import login_required
from src.session_manager.manager import SessionManager
from src.ai_analyzer.orchestrator_agent import OrchestratorAgent
from src.config_manager.manager import ConfigManager
from src.knowledge_base.manager import KnowledgeBaseManager
from src.utils.file_utils import get_user_data_dir
from src.utils import get_logger

logger = get_logger('assistant_api')

assistant_bp = Blueprint('assistant_api', __name__)


def get_current_user_id():
    """获取当前登录用户的ID（工号）。"""
    if current_user.is_authenticated:
        return current_user.employee_id
    return None


@assistant_bp.route('/api/assistant/sessions', methods=['GET'])
@login_required
def list_sessions():
    """获取用户的会话列表。"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        sessions = manager.list_sessions()

        result = []
        for session in sessions:
            result.append({
                'session_id': session.session_id,
                'created_at': session.created_at,
                'updated_at': session.updated_at,
                'message_count': session.message_count,
                'title': session.title,
                'status': session.status
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取会话列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions', methods=['POST'])
@login_required
def create_session():
    """创建新会话。"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        session_id, error = manager.create_session()

        if error:
            return jsonify({'success': False, 'error': error}), 400

        logger.info(f"创建会话成功: user={user_id}, session={session_id}")
        return jsonify({'success': True, 'data': {'session_id': session_id}})
    except Exception as e:
        logger.error(f"创建会话失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    """删除会话。"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        success, error = manager.delete_session(session_id)

        if not success:
            return jsonify({'success': False, 'error': error}), 400

        logger.info(f"删除会话成功: user={user_id}, session={session_id}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"删除会话失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/messages', methods=['GET'])
@login_required
def get_messages(session_id):
    """获取会话的对话历史。"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        messages = manager.get_conversation(session_id)

        result = []
        for msg in messages:
            result.append({
                'role': msg.role,
                'content': msg.content,
                'timestamp': msg.timestamp
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取对话历史失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/chat', methods=['POST'])
@login_required
def chat(session_id):
    """发送消息并获取AI回复（非流式）。"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        data = request.get_json()
        user_input = data.get('message', '')

        if not user_input:
            return jsonify({'success': False, 'error': '消息不能为空'}), 400

        # 检查会话是否存在
        session_manager = SessionManager(user_id)
        session = session_manager.get_session(session_id)
        if not session:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        # 初始化OrchestratorAgent
        config_manager = ConfigManager()
        kb_manager = KnowledgeBaseManager(config=config_manager.get_all())

        agent = OrchestratorAgent(
            user_id=user_id,
            session_id=session_id,
            config_manager=config_manager,
            kb_manager=kb_manager
        )

        # 调用chat方法
        response, metadata = agent.chat(user_input)

        logger.debug(f"对话完成: session={session_id}, context_usage={metadata.get('context_usage', 0)}")

        return jsonify({
            'success': True,
            'data': {
                'response': response,
                'context_usage': metadata.get('context_usage', 0),
                'tool_calls': metadata.get('tool_call_count', 0)
            }
        })
    except Exception as e:
        logger.error(f"对话失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/state', methods=['GET'])
@login_required
def get_state(session_id):
    """获取会话状态。"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        session = manager.get_session(session_id)

        if not session:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        state = session.state

        return jsonify({
            'success': True,
            'data': {
                'context_usage': state.get('context_usage', 0),
                'tool_calls': state.get('tool_calls', 0),
                'subagent_calls': state.get('subagent_calls', 0),
                'uploaded_files': state.get('uploaded_files', []),
                'notes': state.get('notes', {})
            }
        })
    except Exception as e:
        logger.error(f"获取会话状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/files', methods=['GET'])
@login_required
def list_files(session_id):
    """获取会话工作目录的文件列表。"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        work_dir = manager.get_work_dir(session_id)
        outputs_dir = manager.get_outputs_dir(session_id)

        if not work_dir:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        files = []

        # 遍历工作目录
        if os.path.exists(work_dir):
            for root, dirs, filenames in os.walk(work_dir):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, work_dir)
                    files.append({
                        'name': filename,
                        'path': rel_path,
                        'size': os.path.getsize(file_path),
                        'type': 'work_dir'
                    })

        # 遍历输出目录
        if outputs_dir and os.path.exists(outputs_dir):
            for root, dirs, filenames in os.walk(outputs_dir):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, outputs_dir)
                    files.append({
                        'name': filename,
                        'path': rel_path,
                        'size': os.path.getsize(file_path),
                        'type': 'outputs'
                    })

        return jsonify({'success': True, 'data': files})
    except Exception as e:
        logger.error(f"获取文件列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/files/<path:file_path>', methods=['GET'])
@login_required
def download_file(session_id, file_path):
    """下载单个文件。"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        work_dir = manager.get_work_dir(session_id)
        outputs_dir = manager.get_outputs_dir(session_id)

        if not work_dir:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        # 在工作目录和输出目录中查找文件
        full_path = None
        work_file = os.path.join(work_dir, file_path)
        if os.path.exists(work_file):
            full_path = work_file
        elif outputs_dir:
            output_file = os.path.join(outputs_dir, file_path)
            if os.path.exists(output_file):
                full_path = output_file

        if not full_path:
            return jsonify({'success': False, 'error': '文件不存在'}), 404

        filename = os.path.basename(full_path)
        return send_file(full_path, download_name=filename)
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/files/download-all', methods=['POST'])
@login_required
def download_all_files(session_id):
    """打包下载所有文件。"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        work_dir = manager.get_work_dir(session_id)
        outputs_dir = manager.get_outputs_dir(session_id)

        if not work_dir:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 添加工作目录文件
            if os.path.exists(work_dir):
                for root, dirs, filenames in os.walk(work_dir):
                    for filename in filenames:
                        file_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(file_path, work_dir)
                        zf.write(file_path, os.path.join('work_dir', rel_path))

            # 添加输出目录文件
            if outputs_dir and os.path.exists(outputs_dir):
                for root, dirs, filenames in os.walk(outputs_dir):
                    for filename in filenames:
                        file_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(file_path, outputs_dir)
                        zf.write(file_path, os.path.join('outputs', rel_path))

        zip_buffer.seek(0)

        return send_file(
            zip_buffer,
            download_name=f'session_{session_id}_files.zip',
            mimetype='application/zip'
        )
    except Exception as e:
        logger.error(f"打包下载失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500