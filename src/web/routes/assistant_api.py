"""
智能助手API路由
提供会话管理、对话、文件管理、知识库检索等接口
"""

import os
import json
import zipfile
from io import BytesIO
from flask import Blueprint, jsonify, request, send_file, Response, stream_with_context
from flask_login import current_user

from src.auth.decorators import login_required
from src.session_manager.manager import SessionManager
from src.agent.orchestrator_agent import OrchestratorAgent
from src.system_config_manager.manager import SystemConfigManager
from src.knowledge_base.manager import KnowledgeBaseManager
from src.user_config_manager.manager import UserConfigManager
from src.utils.file_utils import get_user_data_dir, is_safe_path
from src.utils import get_logger
from plugins.manager import get_plugin_manager
from src.log_metadata.manager import LogMetadataManager

logger = get_logger('assistant_api')

assistant_bp = Blueprint('assistant_api', __name__)


def get_current_user_id():
    """获取当前登录用户的ID"""
    if current_user.is_authenticated:
        return current_user.employee_id
    return None


# ==================== 会话管理 ====================

@assistant_bp.route('/api/assistant/sessions', methods=['GET'])
@login_required
def list_sessions():
    """获取用户的会话列表"""
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
                'title': session.title,
                'created_at': session.created_at,
                'updated_at': session.updated_at,
                'message_count': session.message_count,
                'status': session.status
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取会话列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions', methods=['POST'])
@login_required
def create_session():
    """创建新会话"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        session_id, error = manager.create_session()

        if error:
            return jsonify({'success': False, 'error': error}), 400

        logger.info(f"创建会话: user={user_id}, session={session_id}")
        return jsonify({'success': True, 'data': {'session_id': session_id}})
    except Exception as e:
        logger.error(f"创建会话失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    """删除会话"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        success, error = manager.delete_session(session_id)

        if not success:
            return jsonify({'success': False, 'error': error}), 400

        logger.info(f"删除会话: user={user_id}, session={session_id}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"删除会话失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/messages', methods=['GET'])
@login_required
def get_messages(session_id):
    """获取会话的对话历史"""
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
        logger.error(f"获取消息失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/state', methods=['GET'])
@login_required
def get_state(session_id):
    """获取会话状态"""
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
        logger.error(f"获取状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/files', methods=['GET'])
@login_required
def list_files(session_id):
    """获取会话工作目录的文件列表"""
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
                        'size': os.path.getsize(file_path)
                    })

        # 遍历输出目录
        if outputs_dir and os.path.exists(outputs_dir):
            for root, dirs, filenames in os.walk(outputs_dir):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, outputs_dir)
                    files.append({
                        'name': filename,
                        'path': 'outputs/' + rel_path,
                        'size': os.path.getsize(file_path)
                    })

        return jsonify({'success': True, 'data': files})
    except Exception as e:
        logger.error(f"获取文件列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


def resolve_session_file_path(rel_path: str, work_dir: str, outputs_dir: str):
    """
    解析会话文件路径，返回安全验证后的完整路径

    Args:
        rel_path: 相对路径，可能以'outputs/'开头
        work_dir: 工作目录
        outputs_dir: 输出目录

    Returns:
        tuple: (full_path, display_path) 或 (None, None) 如果路径无效
    """
    OUTPUTS_PREFIX = 'outputs/'

    if rel_path.startswith(OUTPUTS_PREFIX):
        actual_path = rel_path[len(OUTPUTS_PREFIX):]
        output_file = os.path.join(outputs_dir, actual_path)
        if is_safe_path(output_file, outputs_dir):
            return output_file, os.path.join('outputs', actual_path)
    else:
        work_file = os.path.join(work_dir, rel_path)
        if is_safe_path(work_file, work_dir):
            return work_file, os.path.join('work_dir', rel_path)

    return None, None


@assistant_bp.route('/api/assistant/sessions/<session_id>/files/<path:file_path>', methods=['GET'])
@login_required
def download_file(session_id, file_path):
    """下载单个文件"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        work_dir = manager.get_work_dir(session_id)
        outputs_dir = manager.get_outputs_dir(session_id)

        if not work_dir:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        full_path, _ = resolve_session_file_path(file_path, work_dir, outputs_dir)

        if not full_path or not os.path.exists(full_path):
            return jsonify({'success': False, 'error': '文件不存在'}), 404

        filename = os.path.basename(full_path)
        return send_file(full_path, download_name=filename)
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/files/download-all', methods=['GET'])
@login_required
def download_all_files(session_id):
    """打包下载所有文件"""
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
            if os.path.exists(work_dir):
                for root, dirs, filenames in os.walk(work_dir):
                    for filename in filenames:
                        file_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(file_path, work_dir)
                        zf.write(file_path, os.path.join('work_dir', rel_path))

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


@assistant_bp.route('/api/assistant/sessions/<session_id>/files/download', methods=['POST'])
@login_required
def download_selected_files(session_id):
    """下载选中的文件（打包为zip）"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        data = request.get_json()
        paths = data.get('paths', [])
        if not paths:
            return jsonify({'success': False, 'error': '未选择文件'}), 400

        manager = SessionManager(user_id)
        work_dir = manager.get_work_dir(session_id)
        outputs_dir = manager.get_outputs_dir(session_id)

        if not work_dir:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        zip_buffer = BytesIO()
        skipped = []

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rel_path in paths:
                full_path, zip_inner_path = resolve_session_file_path(rel_path, work_dir, outputs_dir)
                if full_path and os.path.exists(full_path):
                    try:
                        zf.write(full_path, zip_inner_path)
                    except Exception as e:
                        skipped.append({'path': rel_path, 'error': str(e)})
                else:
                    skipped.append({'path': rel_path, 'error': '文件不存在或路径不安全'})

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            download_name=f'session_{session_id}_selected.zip',
            mimetype='application/zip'
        )
    except Exception as e:
        logger.error(f"下载选中文件失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/files', methods=['DELETE'])
@login_required
def delete_files(session_id):
    """删除选中的文件"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        data = request.get_json()
        paths = data.get('paths', [])
        if not paths:
            return jsonify({'success': False, 'error': '未选择文件'}), 400

        manager = SessionManager(user_id)
        work_dir = manager.get_work_dir(session_id)
        outputs_dir = manager.get_outputs_dir(session_id)

        if not work_dir:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        deleted = []
        failed = []

        for rel_path in paths:
            full_path, _ = resolve_session_file_path(rel_path, work_dir, outputs_dir)
            if full_path:
                try:
                    os.remove(full_path)
                    deleted.append(rel_path)
                except FileNotFoundError:
                    failed.append({'path': rel_path, 'error': '文件不存在'})
                except PermissionError as e:
                    failed.append({'path': rel_path, 'error': str(e)})
                except Exception as e:
                    failed.append({'path': rel_path, 'error': str(e)})
            else:
                failed.append({'path': rel_path, 'error': '路径不安全或无效'})

        logger.info(f"删除文件: user={user_id}, session={session_id}, deleted={len(deleted)}, failed={len(failed)}")
        return jsonify({
            'success': True,
            'data': {'deleted': deleted, 'failed': failed}
        })
    except Exception as e:
        logger.error(f"删除文件失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@assistant_bp.route('/api/assistant/sessions/<session_id>/files/upload', methods=['POST'])
@login_required
def upload_file(session_id):
    """上传文件到会话工作目录"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        manager = SessionManager(user_id)
        work_dir = manager.get_work_dir(session_id)
        if not work_dir:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有上传文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '文件名为空'}), 400

        filename = file.filename
        save_path = os.path.join(work_dir, filename)
        if not is_safe_path(save_path, work_dir):
            return jsonify({'success': False, 'error': '不安全的文件名'}), 400

        file.save(save_path)

        session = manager.get_session(session_id)
        uploaded_files = session.state.get('uploaded_files', [])
        if filename not in uploaded_files:
            uploaded_files.append(filename)
        manager.update_state(session_id, {'uploaded_files': uploaded_files})

        logger.info(f"上传文件: user={user_id}, session={session_id}, file={filename}")

        return jsonify({
            'success': True,
            'data': {
                'filename': filename,
                'size': os.path.getsize(save_path),
                'path': filename
            }
        })
    except Exception as e:
        logger.error(f"上传文件失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 对话接口 ====================

@assistant_bp.route('/api/assistant/sessions/<session_id>/chat', methods=['POST'])
@login_required
def chat(session_id):
    """
    发送消息并获取AI回复
    支持知识库检索增强
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'success': False, 'error': '请先登录'}), 401

        data = request.get_json()
        user_input = data.get('message', '')
        kb_ids = data.get('kb_ids', [])

        if not user_input:
            return jsonify({'success': False, 'error': '消息不能为空'}), 400

        # 检查会话是否存在
        session_manager = SessionManager(user_id)
        session = session_manager.get_session(session_id)
        if not session:
            return jsonify({'success': False, 'error': '会话不存在'}), 404

        # 初始化组件
        settings_manager = SystemConfigManager()
        kb_manager = KnowledgeBaseManager(config=settings_manager.get_all())

        # 知识库检索（如果有选择的知识库）
        kb_context = ""
        if kb_ids:
            kb_context = retrieve_knowledge_context(kb_manager, kb_ids, user_input)
            logger.debug(f"知识库检索结果: {len(kb_context)}字符")

        # 初始化OrchestratorAgent
        plugin_manager = get_plugin_manager()
        log_metadata_manager = LogMetadataManager()
        agent = OrchestratorAgent(
            user_id=user_id,
            session_id=session_id,
            settings_manager=settings_manager,
            kb_manager=kb_manager,
            plugin_manager=plugin_manager,
            log_metadata_manager=log_metadata_manager
        )

        # 设置知识库上下文
        if kb_context:
            agent.set_kb_context(kb_context)

        # 设置知识库ID给Subagent使用
        if kb_ids:
            agent.set_kb_ids(kb_ids)

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


def retrieve_knowledge_context(kb_manager, kb_ids, query):
    """
    从多个知识库检索相关内容

    Args:
        kb_manager: 知识库管理器
        kb_ids: 知识库ID列表
        query: 用户查询

    Returns:
        str: 检索结果文本
    """
    contexts = []

    for kb_id in kb_ids:
        try:
            kb_info = kb_manager.get(kb_id)
            if not kb_info:
                continue

            # 执行检索
            results = kb_manager.search(kb_id, query, top_k=3)

            if results:
                kb_name = kb_info.get('name', kb_id)
                context_parts = []
                for result in results:
                    content = result.get('content', '')
                    if content:
                        context_parts.append(content)

                if context_parts:
                    contexts.append(f"【{kb_name}】\n" + "\n".join(context_parts))

        except Exception as e:
            logger.warning(f"知识库检索失败: kb_id={kb_id}, error={str(e)}")

    if contexts:
        return "\n\n".join(contexts)
    return ""


# ==================== 流式对话 ====================

def generate_sse_event(data):
    """生成SSE事件字符串"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@assistant_bp.route('/api/assistant/sessions/<session_id>/chat-stream', methods=['POST'])
@login_required
def chat_stream(session_id):
    """发送消息并获取AI流式回复"""
    def generate():
        try:
            user_id = get_current_user_id()
            if not user_id:
                yield generate_sse_event({'error': '请先登录'})
                return

            data = request.get_json()
            user_input = data.get('message', '')
            kb_ids = data.get('kb_ids', [])

            if not user_input:
                yield generate_sse_event({'error': '消息不能为空'})
                return

            # 检查会话
            session_manager = SessionManager(user_id)
            session = session_manager.get_session(session_id)
            if not session:
                yield generate_sse_event({'error': '会话不存在'})
                return

            # 初始化组件
            settings_manager = SystemConfigManager()
            kb_manager = KnowledgeBaseManager(config=settings_manager.get_all())

            # 知识库检索
            kb_context = ""
            if kb_ids:
                kb_context = retrieve_knowledge_context(kb_manager, kb_ids, user_input)

            # 初始化Agent
            plugin_manager = get_plugin_manager()
            log_metadata_manager = LogMetadataManager()
            agent = OrchestratorAgent(
                user_id=user_id,
                session_id=session_id,
                settings_manager=settings_manager,
                kb_manager=kb_manager,
                plugin_manager=plugin_manager,
                log_metadata_manager=log_metadata_manager
            )

            if kb_context:
                agent.set_kb_context(kb_context)

            # 设置知识库ID给Subagent使用
            if kb_ids:
                agent.set_kb_ids(kb_ids)

            # 流式调用
            for chunk in agent.chat_stream(user_input):
                yield generate_sse_event({'content': chunk})

            yield generate_sse_event({'done': True})

        except Exception as e:
            logger.error(f"流式对话失败: {str(e)}")
            yield generate_sse_event({'error': str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )