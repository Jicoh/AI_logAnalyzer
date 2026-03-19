"""
Analysis API routes with streaming support.
"""

import os
import json
import tempfile
from flask import Blueprint, request, Response, stream_with_context

from src.plugin_analyzer.analyzer import LogAnalyzer
from src.ai_analyzer.analyzer import AIAnalyzer
from src.knowledge_base.manager import KnowledgeBaseManager
from src.config_manager.manager import ConfigManager

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
    ALLOWED_EXTENSIONS = {'log', 'txt'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_sse_event(data):
    """Format data as SSE event."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@analyze_bp.route('/api/analyze/stream', methods=['POST'])
def analyze_stream():
    """Perform streaming analysis on uploaded log file."""
    from werkzeug.utils import secure_filename

    def generate():
        temp_file_path = None

        try:
            # Check if file is present
            if 'file' not in request.files:
                yield generate_sse_event({'stage': 'error', 'message': 'No file provided'})
                return

            file = request.files['file']
            if file.filename == '':
                yield generate_sse_event({'stage': 'error', 'message': 'No file selected'})
                return

            if not allowed_log_file(file.filename):
                yield generate_sse_event({'stage': 'error', 'message': 'Invalid file type. Allowed: log, txt'})
                return

            # Get form data
            plugins = request.form.getlist('plugins')
            enable_ai = request.form.get('enable_ai', 'false').lower() == 'true'
            kb_id = request.form.get('kb_id', '').strip() or None
            user_prompt = request.form.get('user_prompt', '').strip() or None

            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.log', delete=False) as temp_file:
                file.save(temp_file)
                temp_file_path = temp_file.name

            # Read log content
            with open(temp_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                log_content = f.read()

            # Stage 1: Plugin Analysis
            yield generate_sse_event({'stage': 'plugin', 'status': 'start', 'message': 'Starting plugin analysis...'})

            analyzer = LogAnalyzer(config=get_config_manager().get_all())
            plugin_result = analyzer.analyze(temp_file_path)

            yield generate_sse_event({
                'stage': 'plugin',
                'status': 'complete',
                'result': plugin_result
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
                        plugin_result=plugin_result,
                        log_content=log_content,
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
            yield generate_sse_event({'stage': 'complete', 'message': 'Analysis complete'})

        except Exception as e:
            yield generate_sse_event({'stage': 'error', 'message': str(e)})

        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass

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
    # Currently only one built-in plugin
    plugins = [
        {
            'id': 'log_parser',
            'name': 'Log Parser',
            'description': 'Parse log files and extract errors, warnings, and statistics',
            'enabled': True
        }
    ]
    return jsonify({'success': True, 'data': plugins})


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