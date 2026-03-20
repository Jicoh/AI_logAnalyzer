"""
Analysis API routes with streaming support.
"""

import os
import json
import tempfile
from datetime import datetime
from flask import Blueprint, request, Response, stream_with_context, jsonify

from src.ai_analyzer.analyzer import AIAnalyzer
from src.knowledge_base.manager import KnowledgeBaseManager
from src.config_manager.manager import ConfigManager
from src.utils.file_utils import (
    is_archive_file, is_log_file, extract_archive,
    create_work_directory, ensure_dir
)
from plugins.manager import get_plugin_manager

analyze_bp = Blueprint('analyze_api', __name__)

# Global instances
config_manager = None
kb_manager = None


def get_config_manager():
    """Get or create ConfigManager instance."""
    global config_manager
    if config_manager is None:
        config_manager = ConfigManager()
    return config_manager


def get_kb_manager():
    """Get or create KnowledgeBaseManager instance."""
    global kb_manager
    if config_manager is None:
        get_config_manager()
    if kb_manager is None:
        kb_manager = KnowledgeBaseManager(config=config_manager.get_all())
    return kb_manager


def allowed_log_file(filename):
    """Check if file extension is allowed for log files."""
    lower_name = filename.lower()
    # 支持的格式：tar.gz, tar, zip, txt, log
    ALLOWED_EXTENSIONS = ['.tar.gz', '.tgz', '.tar', '.zip', '.txt', '.log']
    for ext in ALLOWED_EXTENSIONS:
        if lower_name.endswith(ext):
            return True
    return False


def get_file_category(filename):
    """获取文件类别：archive 或 log"""
    lower_name = filename.lower()
    if lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz') or lower_name.endswith('.tar') or lower_name.endswith('.zip'):
        return 'archive'
    return 'log'


def get_temp_base_dir():
    """获取 temp 目录路径"""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    temp_dir = os.path.join(root_dir, 'data', 'temp')
    ensure_dir(temp_dir)
    return temp_dir


def generate_sse_event(data):
    """Format data as SSE event."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@analyze_bp.route('/api/analyze/stream', methods=['POST'])
def analyze_stream():
    """Perform streaming analysis on uploaded log file."""
    from werkzeug.utils import secure_filename

    def generate():
        temp_file_path = None
        work_dir = None
        log_files = []

        try:
            # Check if file is present
            if 'file' not in request.files:
                yield generate_sse_event({'stage': 'error', 'message': 'No file provided'})
                return

            file = request.files['file']
            if file.filename == '':
                yield generate_sse_event({'stage': 'error', 'message': 'No file selected'})
                return

            filename = secure_filename(file.filename)
            if not allowed_log_file(filename):
                yield generate_sse_event({'stage': 'error', 'message': 'Invalid file type. Allowed: tar.gz, tar, zip, txt, log'})
                return

            # Get form data
            plugins = request.form.getlist('plugins')
            enable_ai = request.form.get('enable_ai', 'false').lower() == 'true'
            kb_id = request.form.get('kb_id', '').strip() or None
            user_prompt = request.form.get('user_prompt', '').strip() or None

            # 创建工作目录
            temp_base = get_temp_base_dir()
            work_dir = create_work_directory(temp_base, filename)

            # 保存上传的文件
            uploaded_file_path = os.path.join(work_dir, filename)
            file.save(uploaded_file_path)

            # 根据文件类型处理
            file_category = get_file_category(filename)
            all_log_content = ""
            log_file_paths = []

            if file_category == 'archive':
                # 解压压缩文件
                extract_dir = os.path.join(work_dir, 'extracted')
                extracted_files = extract_archive(uploaded_file_path, extract_dir)

                # 查找所有日志文件
                for f in extracted_files:
                    if is_log_file(f):
                        log_file_paths.append(f)

                if not log_file_paths:
                    yield generate_sse_event({'stage': 'error', 'message': 'No log files found in archive'})
                    return
            else:
                # 直接是日志文件
                log_file_paths = [uploaded_file_path]

            # 读取所有日志内容
            for log_path in log_file_paths:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    all_log_content += f.read() + "\n"

            # Stage 1: Plugin Analysis
            yield generate_sse_event({'stage': 'plugin', 'status': 'start', 'message': f'Analyzing {len(log_file_paths)} log file(s)...'})

            # Get plugin manager and run analysis with selected plugins
            plugin_manager = get_plugin_manager()

            # Use all available plugins if none selected
            selected_plugins = plugins if plugins else [p.id for p in plugin_manager.get_all_plugins()]

            if not selected_plugins:
                yield generate_sse_event({'stage': 'error', 'message': 'No plugins available for analysis'})
                return

            # Run analysis with selected plugins
            try:
                plugin_result = plugin_manager.run_analysis_multiple_files(
                    selected_plugins, log_file_paths
                )
                combined_result = plugin_result.to_dict()
            except Exception as e:
                yield generate_sse_event({'stage': 'error', 'message': f'Plugin analysis failed: {str(e)}'})
                return

            # Save plugin analysis result
            plugin_output_base = os.path.join(get_temp_base_dir(), '..', 'plugin_output')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            plugin_output_dir = os.path.join(plugin_output_base, timestamp)
            ensure_dir(plugin_output_dir)
            plugin_output_file = os.path.join(plugin_output_dir, 'plugin_result.json')
            with open(plugin_output_file, 'w', encoding='utf-8') as f:
                json.dump(combined_result, f, indent=4, ensure_ascii=False)

            yield generate_sse_event({
                'stage': 'plugin',
                'status': 'complete',
                'result': combined_result
            })

            # Stage 2: AI Analysis (if enabled)
            if enable_ai:
                yield generate_sse_event({'stage': 'ai', 'status': 'start', 'message': 'Starting AI analysis...'})

                try:
                    ai_analyzer = AIAnalyzer(
                        config_manager=get_config_manager(),
                        kb_manager=get_kb_manager()
                    )

                    # Stream AI analysis
                    full_analysis = ""
                    for chunk in ai_analyzer.analyze(
                        plugin_result=combined_result,
                        log_content=all_log_content,
                        kb_id=kb_id,
                        user_prompt=user_prompt
                    ):
                        full_analysis += chunk
                        yield generate_sse_event({
                            'stage': 'ai',
                            'chunk': chunk
                        })

                    yield generate_sse_event({
                        'stage': 'ai',
                        'status': 'complete',
                        'result': full_analysis
                    })

                except Exception as e:
                    yield generate_sse_event({
                        'stage': 'ai',
                        'status': 'error',
                        'message': f'AI analysis error: {str(e)}'
                    })

            # Stage 3: Complete
            yield generate_sse_event({
                'stage': 'complete',
                'message': 'Analysis complete',
                'work_dir': work_dir
            })

        except Exception as e:
            yield generate_sse_event({'stage': 'error', 'message': str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@analyze_bp.route('/api/analyze/plugins', methods=['GET'])
def get_plugins():
    """Get available analysis plugins."""
    try:
        manager = get_plugin_manager()
        plugins = [info.to_dict() for info in manager.get_plugins_info()]
        return jsonify({'success': True, 'data': plugins})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/analyze/plugins/categories', methods=['GET'])
def get_plugin_categories():
    """Get plugins grouped by category."""
    try:
        manager = get_plugin_manager()
        categories = manager.get_plugins_by_category_dict()
        return jsonify({'success': True, 'data': categories})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/config', methods=['GET'])
def get_config():
    """Get current AI configuration."""
    try:
        manager = get_config_manager()
        config = manager.get_all()

        # Hide sensitive information
        if 'ai' in config and 'api_key' in config['ai']:
            config['ai']['api_key'] = '***' if config['ai']['api_key'] else ''

        return jsonify({'success': True, 'data': config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/config', methods=['POST'])
def update_config():
    """Update AI configuration."""
    try:
        data = request.get_json()
        manager = get_config_manager()

        # Update only allowed fields
        if 'ai' in data:
            ai_config = data['ai']
            if 'enable_ai' in ai_config:
                manager.set('ai.enable_ai', ai_config['enable_ai'])
            if 'model' in ai_config:
                manager.set('ai.model', ai_config['model'])
            if 'temperature' in ai_config:
                manager.set('ai.temperature', ai_config['temperature'])
            if 'max_tokens' in ai_config:
                manager.set('ai.max_tokens', ai_config['max_tokens'])
            # Don't allow updating API key via web for security

        manager.save()

        return jsonify({'success': True, 'message': 'Configuration updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500