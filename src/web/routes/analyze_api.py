"""
分析 API 路由，支持流式响应。
"""

import os
import json
from datetime import datetime
from flask import Blueprint, request, Response, stream_with_context, jsonify
from flask_login import current_user

from src.agent.subagents.log_analyzer import LogAnalyzerSubagent
from src.knowledge_base.manager import KnowledgeBaseManager
from src.log_metadata.manager import LogMetadataManager
from src.system_config_manager.manager import SystemConfigManager
from src.utils.file_utils import (
    is_valid_log_file, extract_archive_recursive,
    create_work_directory, create_batch_work_directory, create_single_log_output_dir,
    ensure_dir, get_files_in_directory, find_log_files_in_directory,
    get_project_root, get_data_dir, get_user_data_dir, clean_filename, is_safe_path,
    allowed_log_file, get_file_category, read_log_files_to_content
)
from src.storage.quota import StorageQuota
from src.utils import get_logger
from plugins.manager import get_plugin_manager
from plugins import render_html
from plugins.base import count_severity

logger = get_logger('analyze_api')

analyze_bp = Blueprint('analyze_api', __name__)


def get_allowed_base_dirs():
    """获取允许访问的基础目录列表"""
    return [
        get_project_root()  # 允许访问项目根目录下的所有路径（用于本地日志分析）
    ]


def validate_path_access(path: str) -> tuple:
    """
    验证路径是否在允许范围内（本地路径分析）
    注意：本地分析允许更广泛的路径访问

    Args:
        path: 要验证的路径

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        abs_path = os.path.abspath(path)
        # 防止访问系统关键路径
        dangerous_paths = ['/etc', '/sys', '/proc', '/root', '/home', 'C:\\Windows', 'C:\\System32']
        for dangerous in dangerous_paths:
            if abs_path.startswith(dangerous):
                return False, '禁止访问系统关键目录'
        return True, None
    except Exception as e:
        return False, f'路径验证失败: {str(e)}'


def get_current_user_id():
    """获取当前登录用户的ID（工号）。"""
    if current_user.is_authenticated:
        return current_user.employee_id
    return None


def log_callback(message: str, level: str = "info"):
    """日志回调适配函数，根据级别调用不同的日志方法。"""
    # success 映射为 info
    log_level = level if level in ['info', 'warning', 'error'] else 'info'
    log_method = getattr(logger, log_level, logger.info)
    log_method(message)

# 模块级单例实例（延迟初始化）
_settings_manager = None
_kb_manager = None
_log_metadata_manager = None


def _init_managers():
    """初始化管理器实例（首次调用时创建）。"""
    global _settings_manager, _kb_manager, _log_metadata_manager
    if _settings_manager is None:
        _settings_manager = SystemConfigManager()
        _kb_manager = KnowledgeBaseManager(config=_settings_manager.get_all())
        _log_metadata_manager = LogMetadataManager()


def get_plugin_manager_with_custom():
    """获取包含自定义插件目录的插件管理器。"""
    root_dir = get_project_root()
    custom_dir = os.path.join(root_dir, 'custom_plugins')
    return get_plugin_manager(custom_dirs=[custom_dir])


def get_settings_manager():
    """获取 SystemConfigManager 单例实例。"""
    _init_managers()
    return _settings_manager


def get_kb_manager():
    """获取 KnowledgeBaseManager 单例实例。"""
    _init_managers()
    return _kb_manager


def get_log_metadata_manager():
    """获取 LogMetadataManager 单例实例。"""
    _init_managers()
    return _log_metadata_manager


def generate_sse_event(data):
    """生成SSE事件字符串。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_analysis_output_dir(user_id: str, filename: str) -> tuple:
    """
    创建分析输出目录。

    Returns:
        tuple: (analysis_output_dir, plugin_output_file, timestamp)
    """
    analysis_output_base = get_user_data_dir(user_id, 'analysis_output')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    clean_name = clean_filename(filename)
    dir_name = f"{timestamp}_{clean_name}"
    analysis_output_dir = os.path.join(analysis_output_base, dir_name)
    ensure_dir(analysis_output_dir)
    plugin_output_file = os.path.join(analysis_output_dir, 'plugin_result.json')
    return analysis_output_dir, plugin_output_file, timestamp


def save_and_render_plugin_result(plugin_result: dict, output_file: str) -> str:
    """
    保存插件分析结果并生成 HTML。

    Returns:
        str: HTML 文件的相对路径
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(plugin_result, f, indent=4, ensure_ascii=False)
    render_html(output_file)
    root_dir = get_project_root()
    html_path = os.path.relpath(output_file.replace('.json', '.html'), root_dir)
    return html_path


def run_ai_analysis(
    plugin_result: dict,
    log_file_paths: list,
    analysis_output_dir: str,
    kb_ids: list = None,
    user_prompt: str = None,
    log_rules_id: str = None
) -> dict:
    """
    执行 AI 分析并保存结果。

    Returns:
        dict: AI 分析结果信息，包含 html_path 和 analysis_time
    """
    subagent = LogAnalyzerSubagent(
        config_manager=get_settings_manager(),
        kb_manager=get_kb_manager(),
        log_metadata_manager=get_log_metadata_manager(),
        plugin_manager=get_plugin_manager_with_custom()
    )

    result = subagent.analyze(
        log_files=log_file_paths,
        plugin_result=plugin_result,
        kb_ids=kb_ids or [],
        user_prompt=user_prompt,
        log_rules_id=log_rules_id
    )

    html_result = result.get('html', '')
    ai_html_file = os.path.join(analysis_output_dir, 'ai_analysis.html')
    with open(ai_html_file, 'w', encoding='utf-8') as f:
        f.write(html_result)

    ai_html_relative = os.path.relpath(ai_html_file, get_project_root())
    return {
        'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'kb_ids': kb_ids,
        'html_path': ai_html_relative
    }


def _process_batch_units(
    analysis_units: list,
    selected_plugins: list,
    batch_output_dir: str,
    folder_name: str,
    enable_ai: bool,
    kb_id: str,
    user_prompt: str,
    log_rules_id: str
):
    """
    批量分析处理核心逻辑（生成器）。
    处理每个分析单元，生成汇总结果，yield SSE 事件。
    """
    plugin_manager = get_plugin_manager_with_custom()
    total_units = len(analysis_units)

    yield generate_sse_event({
        'stage': 'batch',
        'status': 'files_found',
        'total': total_units,
        'message': f'发现 {total_units} 个分析单元'
    })

    batch_results = {}
    for idx, unit in enumerate(analysis_units):
        unit_name = unit['name']
        unit_path = unit['path']

        yield generate_sse_event({
            'stage': 'batch',
            'status': 'start_file',
            'current': idx + 1,
            'total': total_units,
            'file': unit_name,
            'message': f'开始分析: {unit_name} ({idx + 1}/{total_units})'
        })

        single_output_dir = create_single_log_output_dir(batch_output_dir, unit_name)

        try:
            unit_log_content = read_log_files_to_content(unit_path)
            plugin_result = plugin_manager.run_analysis(
                'system', selected_plugins, unit_log_content,
                log_callback=log_callback
            )
        except Exception as e:
            yield generate_sse_event({
                'stage': 'batch',
                'status': 'file_error',
                'file': unit_name,
                'message': f'插件分析失败: {str(e)}'
            })
            continue

        plugin_output_file = os.path.join(single_output_dir, 'plugin_result.json')
        html_relative_path = save_and_render_plugin_result(plugin_result, plugin_output_file)

        log_files_in_unit = find_log_files_in_directory(unit_path) if os.path.isdir(unit_path) else [unit_path]

        ai_result = None
        if enable_ai:
            yield generate_sse_event({
                'stage': 'batch',
                'status': 'ai_start',
                'file': unit_name,
                'message': f'AI分析: {unit_name}'
            })
            try:
                ai_result = run_ai_analysis(
                    plugin_result, log_files_in_unit, single_output_dir,
                    kb_id, user_prompt, log_rules_id
                )
                yield generate_sse_event({
                    'stage': 'batch',
                    'status': 'ai_complete',
                    'file': unit_name
                })
            except Exception as e:
                yield generate_sse_event({
                    'stage': 'batch',
                    'status': 'ai_error',
                    'file': unit_name,
                    'message': f'AI分析失败: {str(e)}'
                })

        batch_results[unit_name] = {
            'output_dir': os.path.basename(single_output_dir),
            'plugin_result': plugin_result,
            'html_path': html_relative_path,
            'ai_result': ai_result
        }

        yield generate_sse_event({
            'stage': 'batch',
            'status': 'file_complete',
            'current': idx + 1,
            'total': total_units,
            'file': unit_name,
            'html_path': html_relative_path,
            'message': f'完成: {unit_name}'
        })

    # 汇总
    batch_summary_file = os.path.join(batch_output_dir, 'batch_summary.json')
    summary_data = {
        'batch_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'folder_name': folder_name,
        'total_files': total_units,
        'files': batch_results
    }
    with open(batch_summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, indent=4, ensure_ascii=False)

    from plugins.renderer.html_renderer import render_batch_html
    batch_html_path = render_batch_html(batch_summary_file)
    batch_html_relative = os.path.relpath(batch_html_path, get_project_root())

    # 构建前端文件列表
    frontend_files = []
    for filename, file_data in batch_results.items():
        total_errors = 0
        total_warnings = 0
        plugin_result = file_data.get('plugin_result', {})
        for plugin_id, plugin_data in plugin_result.items():
            if isinstance(plugin_data, dict):
                sections = plugin_data.get('sections', [])
                counts = count_severity(sections)
                total_errors += counts['errors']
                total_warnings += counts['warnings']
        frontend_files.append({
            'filename': filename,
            'html_path': file_data.get('html_path', ''),
            'errors': total_errors,
            'warnings': total_warnings,
            'has_ai': file_data.get('ai_result') is not None
        })

    yield generate_sse_event({
        'stage': 'batch',
        'status': 'complete',
        'html_path': batch_html_relative,
        'files': frontend_files,
        'message': f'批量分析完成，共 {total_units} 个分析单元'
    })


@analyze_bp.route('/api/analyze/stream', methods=['POST'])
def analyze_stream():
    """对上传的日志文件执行流式分析。"""
    from werkzeug.utils import secure_filename

    def generate():
        try:
            # 获取当前用户
            user_id = get_current_user_id()
            if not user_id:
                yield generate_sse_event({'stage': 'error', 'message': '请先登录'})
                return

            # 验证上传请求
            validation_result = _validate_upload_request(user_id)
            if validation_result.get('error'):
                yield generate_sse_event({'stage': 'error', 'message': validation_result['error']})
                return

            file = validation_result['file']
            filename = validation_result['filename']

            # 获取表单数据
            form_data = _get_form_data()

            # 处理上传文件
            file_result = _handle_uploaded_file(user_id, file, filename)
            if file_result.get('error'):
                yield generate_sse_event({'stage': 'error', 'message': file_result['error']})
                return

            # 执行分析流水线
            yield from _run_analysis_pipeline(
                user_id=user_id,
                analysis_path=file_result['analysis_path'],
                log_file_paths=file_result['log_file_paths'],
                filename=filename,
                work_dir=file_result['work_dir'],
                **form_data
            )

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


def _validate_upload_request(user_id: str) -> dict:
    """
    验证上传请求（用户、文件、配额）。

    Returns:
        dict: 验证结果，包含 file, filename 或 error
    """
    from werkzeug.utils import secure_filename

    # 检查是否有文件
    if 'file' not in request.files:
        return {'error': 'No file provided'}

    file = request.files['file']
    if file.filename == '':
        return {'error': 'No file selected'}

    filename = secure_filename(file.filename)
    if not allowed_log_file(filename):
        return {'error': 'Invalid file type. Allowed: tar.gz, tar, zip, txt, log'}

    # 检查配额
    quota = StorageQuota(user_id)
    content_length = request.content_length or 50 * 1024 * 1024
    allowed, quota_error = quota.check_upload(content_length)
    if not allowed:
        return {'error': quota_error}

    return {'file': file, 'filename': filename}


def _get_form_data() -> dict:
    """获取表单数据。"""
    return {
        'plugins': request.form.getlist('plugins'),
        'enable_ai': request.form.get('enable_ai', 'false').lower() == 'true',
        'kb_ids': request.form.getlist('kb_ids'),
        'user_prompt': request.form.get('user_prompt', '').strip() or None,
        'log_rules_id': request.form.get('log_rules_id', '').strip() or None
    }


def _handle_uploaded_file(user_id: str, file, filename: str) -> dict:
    """
    处理上传文件（保存、解压）。

    Returns:
        dict: 包含 work_dir, analysis_path, log_file_paths 或 error
    """
    temp_base = get_user_data_dir(user_id, 'temp')
    work_dir = create_work_directory(temp_base, filename)

    file_category = get_file_category(filename)
    log_file_paths = []
    analysis_path = None

    if file_category == 'archive':
        # 保存压缩包到临时位置，解压后删除
        temp_archive_path = os.path.join(temp_base, f"temp_{filename}")
        file.save(temp_archive_path)

        try:
            extract_archive_recursive(temp_archive_path, work_dir)
        finally:
            if os.path.exists(temp_archive_path):
                os.remove(temp_archive_path)

        log_file_paths = find_log_files_in_directory(work_dir)
        if not log_file_paths:
            return {'error': 'No log files found in archive'}

        analysis_path = work_dir
    else:
        # 直接是日志文件，保存到工作目录
        uploaded_file_path = os.path.join(work_dir, filename)
        file.save(uploaded_file_path)
        log_file_paths = [uploaded_file_path]
        analysis_path = uploaded_file_path

    return {
        'work_dir': work_dir,
        'analysis_path': analysis_path,
        'log_file_paths': log_file_paths
    }


def _run_analysis_pipeline(
    user_id: str,
    analysis_path: str,
    log_file_paths: list,
    filename: str,
    work_dir: str,
    plugins: list,
    enable_ai: bool,
    kb_ids: list,
    user_prompt: str,
    log_rules_id: str
):
    """
    执行分析流水线（生成器）。

    Yields:
        str: SSE 事件字符串
    """
    plugin_manager = get_plugin_manager_with_custom()
    selected_plugins = plugins if plugins else [p.id for p in plugin_manager.get_all_plugins()]

    # 第1阶段：插件分析
    yield generate_sse_event({
        'stage': 'plugin',
        'status': 'start',
        'message': f'Analyzing with {len(selected_plugins)} plugin(s)...'
    })

    if not selected_plugins:
        yield generate_sse_event({'stage': 'error', 'message': 'No plugins available for analysis'})
        return

    try:
        log_content = read_log_files_to_content(analysis_path)
        combined_result = plugin_manager.run_analysis(
            'system', selected_plugins, log_content,
            log_callback=log_callback
        )
    except Exception as e:
        yield generate_sse_event({'stage': 'error', 'message': f'Plugin analysis failed: {str(e)}'})
        return

    # 保存插件分析结果
    analysis_output_dir, plugin_output_file, _ = create_analysis_output_dir(user_id, filename)
    html_relative_path = save_and_render_plugin_result(combined_result, plugin_output_file)

    yield generate_sse_event({
        'stage': 'plugin',
        'status': 'complete',
        'result': combined_result
    })

    # 第2阶段：AI分析
    ai_result_data = None
    if enable_ai:
        yield generate_sse_event({'stage': 'ai', 'status': 'start', 'message': 'AI 分析中...'})

        try:
            ai_result_data = run_ai_analysis(
                combined_result, log_file_paths, analysis_output_dir,
                kb_ids, user_prompt, log_rules_id
            )
            yield generate_sse_event({
                'stage': 'ai',
                'status': 'complete',
                'html_path': ai_result_data['html_path']
            })
        except Exception as e:
            logger.error(f"AI分析失败: {str(e)}")
            yield generate_sse_event({
                'stage': 'ai',
                'status': 'error',
                'message': f'AI analysis error: {str(e)}'
            })

    # 第3阶段：完成
    complete_data = {
        'stage': 'complete',
        'message': 'Analysis complete',
        'work_dir': work_dir,
        'html_path': html_relative_path
    }
    if ai_result_data and ai_result_data.get('html_path'):
        complete_data['ai_html_path'] = ai_result_data['html_path']

    yield generate_sse_event(complete_data)


@analyze_bp.route('/api/analyze/local-path', methods=['POST'])
def validate_local_path():
    """验证本地路径并返回文件信息。"""
    try:
        data = request.get_json()
        path = data.get('path', '')
        if not path:
            return jsonify({'success': False, 'error': '路径不能为空'})

        # 解码 URL 编码的路径
        import urllib.parse
        path = urllib.parse.unquote(path)

        # 安全检查：路径必须在允许范围内
        is_valid, error_msg = validate_path_access(path)
        if not is_valid:
            logger.warning(f"非法路径访问尝试: {path}")
            return jsonify({'success': False, 'error': error_msg}), 403

        # 验证路径是否存在
        if not os.path.exists(path):
            return jsonify({'success': False, 'error': f'路径不存在: {path}'})

        # 获取路径信息
        if os.path.isfile(path):
            filename = os.path.basename(path)
            file_size = os.path.getsize(path)
            lower_name = filename.lower()

            # 判断文件类型
            is_archive = (lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz') or
                          lower_name.endswith('.tar') or lower_name.endswith('.zip'))
            is_log = lower_name.endswith('.log') or lower_name.endswith('.txt')

            if not is_archive and not is_log:
                return jsonify({'success': False, 'error': f'不支持的文件类型: {filename}'})

            return jsonify({
                'success': True,
                'data': {
                    'type': 'file',
                    'path': path,
                    'filename': filename,
                    'size': file_size,
                    'is_archive': is_archive
                }
            })
        elif os.path.isdir(path):
            # 目录模式
            folder_name = os.path.basename(path) or os.path.basename(os.path.dirname(path))
            # 查找目录中的日志文件
            log_files = find_log_files_in_directory(path)
            archive_files = []
            for f in get_files_in_directory(path):
                lower_f = f.lower()
                if (lower_f.endswith('.tar.gz') or lower_f.endswith('.tgz') or
                    lower_f.endswith('.tar') or lower_f.endswith('.zip')):
                    archive_files.append(f)

            return jsonify({
                'success': True,
                'data': {
                    'type': 'directory',
                    'path': path,
                    'folder_name': folder_name,
                    'log_count': len(log_files),
                    'archive_count': len(archive_files)
                }
            })
        else:
            return jsonify({'success': False, 'error': '路径既不是文件也不是目录'})

    except Exception as e:
        logger.error(f"验证路径失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})


@analyze_bp.route('/api/analyze/local-stream', methods=['POST'])
def analyze_local_stream():
    """对本地路径执行流式分析（支持文件和目录）。"""
    def generate():
        try:
            # 获取当前用户
            user_id = get_current_user_id()
            if not user_id:
                yield generate_sse_event({'stage': 'error', 'message': '请先登录'})
                return

            # 获取路径参数
            data = request.get_json()
            path = data.get('path', '')

            # 验证本地路径
            validation_result = _validate_local_path(user_id, path)
            if validation_result.get('error'):
                yield generate_sse_event({'stage': 'error', 'message': validation_result['error']})
                return

            # 获取分析参数
            plugins = data.get('plugins', [])
            enable_ai = data.get('enable_ai', False)
            kb_id = data.get('kb_id', '').strip() or None
            user_prompt = data.get('user_prompt', '').strip() or None
            log_rules_id = data.get('log_rules_id', '').strip() or None

            if os.path.isfile(path):
                # 单文件分析
                yield from _analyze_single_local_file(
                    user_id, path, plugins, enable_ai, kb_id, user_prompt, log_rules_id
                )
            elif os.path.isdir(path):
                # 目录批量分析
                yield from _analyze_local_directory(
                    user_id, path, plugins, enable_ai, kb_id, user_prompt, log_rules_id
                )

        except Exception as e:
            logger.error(f"本地路径分析失败: {str(e)}")
            yield generate_sse_event({'stage': 'error', 'message': str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


def _validate_local_path(user_id: str, path: str) -> dict:
    """
    验证本地路径（安全检查、配额检查）。

    Returns:
        dict: 包含 path_info 或 error
    """
    if not path:
        return {'error': '路径不能为空'}

    # 安全检查
    is_valid, error_msg = validate_path_access(path)
    if not is_valid:
        logger.warning(f"非法路径访问尝试: {path}")
        return {'error': error_msg}

    # 验证路径存在
    if not os.path.exists(path):
        return {'error': f'路径不存在: {path}'}

    # 检查配额
    quota = StorageQuota(user_id)
    if os.path.isfile(path):
        estimated_size = os.path.getsize(path)
    else:
        estimated_size = sum(os.path.getsize(f) for f in find_log_files_in_directory(path))
    allowed, quota_error = quota.check_upload(estimated_size)
    if not allowed:
        return {'error': quota_error}

    return {'path': path}


def _analyze_single_local_file(
    user_id: str,
    path: str,
    plugins: list,
    enable_ai: bool,
    kb_id: str,
    user_prompt: str,
    log_rules_id: str
):
    """
    分析单个本地文件（生成器）。

    Yields:
        str: SSE 事件字符串
    """
    import shutil

    filename = os.path.basename(path)
    lower_name = filename.lower()
    is_archive = (lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz') or
                  lower_name.endswith('.tar') or lower_name.endswith('.zip'))

    temp_base = get_user_data_dir(user_id, 'temp')
    work_dir = create_work_directory(temp_base, filename)

    if is_archive:
        extract_archive_recursive(path, work_dir)
        log_file_paths = find_log_files_in_directory(work_dir)
        analysis_path = work_dir
    else:
        dest_path = os.path.join(work_dir, filename)
        shutil.copy2(path, dest_path)
        log_file_paths = [dest_path]
        analysis_path = dest_path

    if not log_file_paths:
        yield generate_sse_event({'stage': 'error', 'message': '未找到日志文件'})
        return

    yield from _run_analysis_pipeline(
        user_id=user_id,
        analysis_path=analysis_path,
        log_file_paths=log_file_paths,
        filename=filename,
        work_dir=work_dir,
        plugins=plugins,
        enable_ai=enable_ai,
        kb_ids=[kb_id] if kb_id else [],
        user_prompt=user_prompt,
        log_rules_id=log_rules_id
    )


def _analyze_local_directory(
    user_id: str,
    path: str,
    plugins: list,
    enable_ai: bool,
    kb_id: str,
    user_prompt: str,
    log_rules_id: str
):
    """
    分析本地目录（批量分析生成器）。

    Yields:
        str: SSE 事件字符串
    """
    import shutil

    temp_base = get_user_data_dir(user_id, 'temp')
    folder_name = os.path.basename(path) or 'analysis_folder'
    work_dir = create_batch_work_directory(temp_base, folder_name)

    batch_output_dir = os.path.join(temp_base, '..', 'analysis_output')
    batch_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    batch_dir_name = f"{batch_timestamp}_{folder_name}"
    batch_output_dir = os.path.join(batch_output_dir, batch_dir_name)
    ensure_dir(batch_output_dir)

    yield generate_sse_event({
        'stage': 'batch',
        'status': 'start',
        'message': '开始批量分析...',
        'work_dir': work_dir
    })

    # 构建分析单元
    analysis_units = []
    for f in get_files_in_directory(path):
        lower_f = f.lower()
        is_archive = (lower_f.endswith('.tar.gz') or lower_f.endswith('.tgz') or
                      lower_f.endswith('.tar') or lower_f.endswith('.zip'))
        is_log = lower_f.endswith('.log') or lower_f.endswith('.txt')

        if is_archive:
            extract_dir_name = os.path.splitext(os.path.basename(f))[0]
            if lower_f.endswith('.tar.gz'):
                extract_dir_name = os.path.basename(f)[:-7]
            elif lower_f.endswith('.tgz'):
                extract_dir_name = os.path.basename(f)[:-4]
            extract_dir = os.path.join(work_dir, extract_dir_name)
            ensure_dir(extract_dir)
            extract_archive_recursive(f, extract_dir)
            analysis_units.append({
                'path': extract_dir,
                'name': extract_dir_name,
                'is_archive': True
            })
        elif is_log:
            dest_path = os.path.join(work_dir, os.path.basename(f))
            shutil.copy2(f, dest_path)
            analysis_units.append({
                'path': dest_path,
                'name': os.path.basename(f),
                'is_archive': False
            })

    if not analysis_units:
        yield generate_sse_event({'stage': 'error', 'message': '未找到有效的日志文件'})
        return

    # 执行批量分析
    yield from _process_batch_units(
        analysis_units, plugins, batch_output_dir, folder_name,
        enable_ai, kb_id, user_prompt, log_rules_id
    )


@analyze_bp.route('/api/analyze/batch/stream', methods=['POST'])
def analyze_batch_stream():
    """批量分析多个日志文件（文件夹上传模式）。"""
    from werkzeug.utils import secure_filename

    def generate():
        try:
            # 检查是否有文件
            files = request.files.getlist('files')
            if not files or len(files) == 0:
                yield generate_sse_event({'stage': 'error', 'message': 'No files provided'})
                return

            # 获取表单数据
            folder_name = request.form.get('folder_name', 'uploaded_folder')
            plugins = request.form.getlist('plugins')
            enable_ai = request.form.get('enable_ai', 'false').lower() == 'true'
            kb_ids = request.form.getlist('kb_ids')
            user_prompt = request.form.get('user_prompt', '').strip() or None
            log_rules_id = request.form.get('log_rules_id', '').strip() or None

            # 准备批量分析环境
            batch_setup = _prepare_batch_analysis(folder_name)
            work_dir = batch_setup['work_dir']
            batch_output_dir = batch_setup['batch_output_dir']
            clean_folder_name = batch_setup['clean_folder_name']

            yield generate_sse_event({
                'stage': 'batch',
                'status': 'start',
                'message': f'开始批量分析...',
                'work_dir': work_dir
            })

            # 处理上传文件
            analysis_units = _process_uploaded_batch_files(files, work_dir)

            if not analysis_units:
                yield generate_sse_event({'stage': 'error', 'message': '未找到有效的日志文件'})
                return

            # 选择插件
            plugin_manager = get_plugin_manager_with_custom()
            selected_plugins = plugins if plugins else [p.id for p in plugin_manager.get_all_plugins()]

            if not selected_plugins:
                yield generate_sse_event({'stage': 'error', 'message': '没有可用的插件'})
                return

            # 执行批量分析
            yield from _process_batch_units(
                analysis_units, selected_plugins, batch_output_dir, clean_folder_name,
                enable_ai, kb_ids, user_prompt, log_rules_id
            )

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


def _prepare_batch_analysis(folder_name: str) -> dict:
    """
    准备批量分析环境（创建工作目录和输出目录）。

    Returns:
        dict: 包含 work_dir, batch_output_dir, clean_folder_name
    """
    from werkzeug.utils import secure_filename

    temp_base = get_data_dir('temp')
    work_dir = create_batch_work_directory(temp_base, folder_name)

    # 清理文件夹名
    clean_folder_name = folder_name
    for ext in ['.tar.gz', '.tgz', '.tar', '.zip']:
        if clean_folder_name.lower().endswith(ext):
            clean_folder_name = clean_folder_name[:-len(ext)]
            break

    # 创建输出目录
    analysis_output_base = os.path.join(temp_base, '..', 'analysis_output')
    batch_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    batch_dir_name = f"{batch_timestamp}_{clean_folder_name}"
    batch_output_dir = os.path.join(analysis_output_base, batch_dir_name)
    ensure_dir(batch_output_dir)

    return {
        'work_dir': work_dir,
        'batch_output_dir': batch_output_dir,
        'clean_folder_name': clean_folder_name
    }


def _process_uploaded_batch_files(files: list, work_dir: str) -> list:
    """
    处理批量上传的文件（保存、解压）。

    Args:
        files: 上传的文件列表
        work_dir: 工作目录

    Returns:
        list: 分析单元列表
    """
    from werkzeug.utils import secure_filename

    analysis_units = []
    for file in files:
        filename = secure_filename(file.filename)
        if not filename:
            continue

        lower_name = filename.lower()
        is_archive = (lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz') or
                      lower_name.endswith('.tar') or lower_name.endswith('.zip'))

        if is_archive:
            # 压缩文件：保存、解压、删除
            temp_archive_path = os.path.join(work_dir, f"_temp_{filename}")
            file.save(temp_archive_path)

            try:
                extract_dir_name = os.path.splitext(filename)[0]
                if lower_name.endswith('.tar.gz'):
                    extract_dir_name = filename[:-7]
                elif lower_name.endswith('.tgz'):
                    extract_dir_name = filename[:-4]
                extract_dir = os.path.join(work_dir, extract_dir_name)
                ensure_dir(extract_dir)
                extract_archive_recursive(temp_archive_path, extract_dir)
                analysis_units.append({
                    'path': extract_dir,
                    'name': extract_dir_name,
                    'is_archive': True
                })
            finally:
                if os.path.exists(temp_archive_path):
                    os.remove(temp_archive_path)
        elif is_valid_log_file(filename):
            # 普通日志文件
            file_path = os.path.join(work_dir, filename)
            file.save(file_path)
            analysis_units.append({
                'path': file_path,
                'name': filename,
                'is_archive': False
            })

    return analysis_units
