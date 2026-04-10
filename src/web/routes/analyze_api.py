"""
分析 API 路由，支持流式响应。
"""

import os
import json
import tempfile
from datetime import datetime
from flask import Blueprint, request, Response, stream_with_context, jsonify

from src.ai_analyzer.analyzer import AIAnalyzer
from src.ai_analyzer.selection_agent import SelectionAgent
from src.knowledge_base.manager import KnowledgeBaseManager
from src.log_metadata.manager import LogMetadataManager
from src.config_manager.manager import ConfigManager
from src.plugin_selection.manager import PluginSelectionManager
from src.utils.file_utils import (
    is_archive_file, is_log_file, extract_archive,
    create_work_directory, ensure_dir
)
from plugins.manager import get_plugin_manager

analyze_bp = Blueprint('analyze_api', __name__)

# 全局实例
config_manager = None
kb_manager = None
log_metadata_manager = None
plugin_selection_manager = None


def get_project_root():
    """获取项目根目录。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def get_plugin_manager_with_custom():
    """获取包含自定义插件目录的插件管理器。"""
    root_dir = get_project_root()
    custom_dir = os.path.join(root_dir, 'custom_plugins')
    return get_plugin_manager(custom_dirs=[custom_dir])


def get_config_manager():
    """获取或创建 ConfigManager 实例。"""
    global config_manager
    if config_manager is None:
        config_manager = ConfigManager()
    return config_manager


def get_kb_manager():
    """获取或创建 KnowledgeBaseManager 实例。"""
    global kb_manager
    if config_manager is None:
        get_config_manager()
    if kb_manager is None:
        kb_manager = KnowledgeBaseManager(config=config_manager.get_all())
    return kb_manager


def get_log_metadata_manager():
    """获取或创建 LogMetadataManager 实例。"""
    global log_metadata_manager
    if log_metadata_manager is None:
        log_metadata_manager = LogMetadataManager()
    return log_metadata_manager


def get_plugin_selection_manager():
    """获取或创建 PluginSelectionManager 实例。"""
    global plugin_selection_manager
    if plugin_selection_manager is None:
        plugin_selection_manager = PluginSelectionManager()
    return plugin_selection_manager


def allowed_log_file(filename):
    """检查文件扩展名是否为允许的日志文件。"""
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
    """将数据格式化为 SSE 事件。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@analyze_bp.route('/api/analyze/stream', methods=['POST'])
def analyze_stream():
    """对上传的日志文件执行流式分析。"""
    from werkzeug.utils import secure_filename

    def generate():
        temp_file_path = None
        work_dir = None
        log_files = []

        try:
            # 检查是否有文件
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

            # 获取表单数据
            plugins = request.form.getlist('plugins')
            enable_ai = request.form.get('enable_ai', 'false').lower() == 'true'
            kb_id = request.form.get('kb_id', '').strip() or None
            user_prompt = request.form.get('user_prompt', '').strip() or None
            ai_selection_mode = request.form.get('ai_selection_mode', 'false').lower() == 'true'
            log_rules_id = request.form.get('log_rules_id', '').strip() or None

            # 创建工作目录
            temp_base = get_temp_base_dir()
            work_dir = create_work_directory(temp_base, filename)

            # 根据文件类型处理
            file_category = get_file_category(filename)
            all_log_content = ""
            log_file_paths = []

            if file_category == 'archive':
                # 保存压缩包到临时位置，解压后删除
                temp_archive_path = os.path.join(temp_base, f"temp_{filename}")
                file.save(temp_archive_path)

                try:
                    # 解压压缩文件到工作目录
                    extracted_files = extract_archive(temp_archive_path, work_dir)
                finally:
                    # 删除临时压缩包
                    if os.path.exists(temp_archive_path):
                        os.remove(temp_archive_path)

                # 查找所有日志文件
                for f in extracted_files:
                    if is_log_file(f):
                        log_file_paths.append(f)

                if not log_file_paths:
                    yield generate_sse_event({'stage': 'error', 'message': 'No log files found in archive'})
                    return
            else:
                # 直接是日志文件，保存到工作目录
                uploaded_file_path = os.path.join(work_dir, filename)
                file.save(uploaded_file_path)
                log_file_paths = [uploaded_file_path]

            # 读取所有日志内容
            for log_path in log_file_paths:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    all_log_content += f.read() + "\n"

            # Get plugin manager
            plugin_manager = get_plugin_manager_with_custom()

            # Initialize selection variables
            selected_plugins = []
            selected_log_files = log_file_paths
            selection_result = None

            # Stage 0: AI Selection (if enabled)
            if ai_selection_mode and enable_ai:
                yield generate_sse_event({
                    'stage': 'selection',
                    'status': 'start',
                    'message': 'AI 正在智能选择插件...'
                })

                try:
                    # 使用指定的日志规则
                    if log_rules_id:
                        get_log_metadata_manager().set_active_rules(log_rules_id)

                    selection_agent = SelectionAgent(
                        config_manager=get_config_manager(),
                        log_metadata_manager=get_log_metadata_manager(),
                        plugin_manager=plugin_manager
                    )
                    selection_result = selection_agent.select(log_file_paths, user_prompt, log_rules_id)

                    selected_plugins = selection_result['selected_plugins']
                    selected_log_files = selection_result['selected_files']

                    yield generate_sse_event({
                        'stage': 'selection',
                        'status': 'complete',
                        'result': selection_result
                    })

                except Exception as e:
                    yield generate_sse_event({
                        'stage': 'selection',
                        'status': 'error',
                        'message': f'AI 选择失败: {str(e)}，将执行全量分析'
                    })
                    # 回退到所有插件和文件
                    selected_plugins = [p.id for p in plugin_manager.get_all_plugins()]
                    selected_log_files = log_file_paths
            else:
                # 使用用户选择的插件或所有插件
                selected_plugins = plugins if plugins else [p.id for p in plugin_manager.get_all_plugins()]
                selected_log_files = log_file_paths

            # 第1阶段：插件分析
            yield generate_sse_event({
                'stage': 'plugin',
                'status': 'start',
                'message': f'Analyzing {len(selected_log_files)} log file(s) with {len(selected_plugins)} plugin(s)...'
            })

            if not selected_plugins:
                yield generate_sse_event({'stage': 'error', 'message': 'No plugins available for analysis'})
                return

            # 使用选定的插件分析选定的文件
            try:
                plugin_result = plugin_manager.run_analysis_multiple_files(
                    selected_plugins, selected_log_files
                )
                combined_result = plugin_result.to_dict()
            except Exception as e:
                yield generate_sse_event({'stage': 'error', 'message': f'Plugin analysis failed: {str(e)}'})
                return

            # 保存插件分析结果
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

            # 第2阶段：AI分析（如果启用）
            ai_result_data = None
            if enable_ai:
                yield generate_sse_event({'stage': 'ai', 'status': 'start', 'message': 'Starting AI analysis...'})

                try:
                    ai_analyzer = AIAnalyzer(
                        config_manager=get_config_manager(),
                        kb_manager=get_kb_manager()
                    )

                    # 流式 AI 分析
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

                    ai_result_data = {
                        'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'kb_id': kb_id,
                        'analysis': full_analysis
                    }

                    # 保存 AI 结果
                    ai_output_file = os.path.join(plugin_output_dir, 'ai_result.json')
                    with open(ai_output_file, 'w', encoding='utf-8') as f:
                        json.dump(ai_result_data, f, indent=4, ensure_ascii=False)

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

            # 第3阶段：完成
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
    """获取可用的分析插件。"""
    try:
        manager = get_plugin_manager_with_custom()
        plugins = [info.to_dict() for info in manager.get_plugins_info()]
        return jsonify({'success': True, 'data': plugins})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/analyze/plugins/categories', methods=['GET'])
def get_plugin_categories():
    """获取按类别分组的插件。"""
    try:
        manager = get_plugin_manager_with_custom()
        categories = manager.get_plugins_by_category_dict()
        return jsonify({'success': True, 'data': categories})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/config', methods=['GET'])
def get_config():
    """获取当前 AI 配置。"""
    try:
        manager = get_config_manager()
        manager.reload()  # 每次请求都重新加载配置文件
        config = manager.get_all()
        return jsonify({'success': True, 'data': config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/config', methods=['POST'])
def update_config():
    """更新 AI 配置。"""
    try:
        data = request.get_json()
        manager = get_config_manager()

        # 更新 API 设置
        if 'api' in data:
            api_config = data['api']
            if 'base_url' in api_config:
                manager.set('api.base_url', api_config['base_url'])
            if 'api_key' in api_config and api_config['api_key']:
                manager.set('api.api_key', api_config['api_key'])
            if 'model' in api_config:
                manager.set('api.model', api_config['model'])
            if 'temperature' in api_config:
                manager.set('api.temperature', float(api_config['temperature']))
            if 'max_tokens' in api_config:
                manager.set('api.max_tokens', int(api_config['max_tokens']))

        # 更新 BM25 设置
        if 'bm25' in data:
            bm25_config = data['bm25']
            if 'k1' in bm25_config:
                manager.set('bm25.k1', float(bm25_config['k1']))
            if 'b' in bm25_config:
                manager.set('bm25.b', float(bm25_config['b']))

        # 更新 Embedding 设置
        if 'embedding' in data:
            emb_config = data['embedding']
            if 'enabled' in emb_config:
                manager.set('embedding.enabled', emb_config['enabled'])
            if 'provider' in emb_config:
                manager.set('embedding.provider', emb_config['provider'])
            if 'base_url' in emb_config:
                manager.set('embedding.base_url', emb_config['base_url'])
            if 'api_key' in emb_config:
                manager.set('embedding.api_key', emb_config['api_key'])
            if 'model' in emb_config:
                manager.set('embedding.model', emb_config['model'])
            if 'dimension' in emb_config:
                manager.set('embedding.dimension', int(emb_config['dimension']))
            if 'batch_size' in emb_config:
                manager.set('embedding.batch_size', int(emb_config['batch_size']))

        # 更新 Retrieval 设置
        if 'retrieval' in data:
            ret_config = data['retrieval']
            if 'mode' in ret_config:
                manager.set('retrieval.mode', ret_config['mode'])
            if 'bm25_weight' in ret_config:
                manager.set('retrieval.bm25_weight', float(ret_config['bm25_weight']))
            if 'vector_weight' in ret_config:
                manager.set('retrieval.vector_weight', float(ret_config['vector_weight']))
            if 'rrf_k' in ret_config:
                manager.set('retrieval.rrf_k', int(ret_config['rrf_k']))

        manager.save()

        return jsonify({'success': True, 'message': 'Configuration updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# 配置目录
CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    'config'
)
# 用户自定义提示词文件
DEFAULT_PROMPT_FILE = os.path.join(CONFIG_DIR, 'default_prompt.txt')
# 默认提示词模板（只读）
DEFAULT_PROMPT_TEMPLATE = os.path.join(CONFIG_DIR, 'default_prompt_template.txt')


def get_default_prompt_template():
    """获取默认提示词模板内容。"""
    if os.path.exists(DEFAULT_PROMPT_TEMPLATE):
        with open(DEFAULT_PROMPT_TEMPLATE, 'r', encoding='utf-8') as f:
            return f.read()
    # 文件缺失时的回退模板
    return """你是一名专业的服务器BMC日志分析专家。请根据以下信息分析日志中存在的问题，并提供可能的原因和解决方案。

## 日志分析结果
{plugin_analysis}

## 相关知识库内容
{knowledge_content}

## 日志原文
{log_content}

## 用户补充说明
{user_prompt}

请按照以下格式输出分析报告：

### 问题总结
简要总结日志中发现的主要问题。

### 问题详情
列出每个问题的详细信息：
1. 问题类型
2. 发生时间
3. 影响范围
4. 可能原因

### 解决方案建议
针对每个问题提供具体的解决方案建议。

### 风险评估
评估当前问题的严重程度和潜在风险。"""


@analyze_bp.route('/api/config/prompt', methods=['GET'])
def get_prompt():
    """获取默认提示词内容。"""
    try:
        if os.path.exists(DEFAULT_PROMPT_FILE):
            with open(DEFAULT_PROMPT_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = ''

        return jsonify({'success': True, 'data': {'content': content}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/config/prompt', methods=['POST'])
def update_prompt():
    """更新默认提示词内容。"""
    try:
        data = request.get_json()
        content = data.get('content', '')

        # 确保配置目录存在
        config_dir = os.path.dirname(DEFAULT_PROMPT_FILE)
        os.makedirs(config_dir, exist_ok=True)

        with open(DEFAULT_PROMPT_FILE, 'w', encoding='utf-8') as f:
            f.write(content)

        return jsonify({'success': True, 'message': 'Prompt updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/config/prompt/reset', methods=['POST'])
def reset_prompt():
    """重置默认提示词为原始内容。"""
    try:
        default_content = get_default_prompt_template()

        # Ensure config directory exists
        os.makedirs(CONFIG_DIR, exist_ok=True)

        with open(DEFAULT_PROMPT_FILE, 'w', encoding='utf-8') as f:
            f.write(default_content)

        return jsonify({'success': True, 'data': {'content': default_content}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/plugin-selection', methods=['GET'])
def get_plugin_selection():
    """获取插件选择和 AI 设置。"""
    try:
        manager = get_plugin_selection_manager()
        manager.reload()
        config = manager.get_all()
        return jsonify({'success': True, 'data': config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@analyze_bp.route('/api/plugin-selection', methods=['POST'])
def update_plugin_selection():
    """更新插件选择和 AI 设置。"""
    try:
        data = request.get_json()
        manager = get_plugin_selection_manager()

        if 'selected_plugins' in data:
            manager.set('selected_plugins', data['selected_plugins'])
        if 'selected_kb_id' in data:
            manager.set('selected_kb_id', data['selected_kb_id'])
        if 'selected_log_rules_id' in data:
            manager.set('selected_log_rules_id', data['selected_log_rules_id'])
        if 'enable_ai' in data:
            manager.set('enable_ai', data['enable_ai'])
        if 'ai_selection_mode' in data:
            manager.set('ai_selection_mode', data['ai_selection_mode'])

        manager.save()

        return jsonify({'success': True, 'message': 'Plugin selection updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500