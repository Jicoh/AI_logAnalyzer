"""
分析 API 路由，支持流式响应。
"""

import os
import json
import subprocess
from datetime import datetime
from flask import Blueprint, request, Response, stream_with_context, jsonify
from flask_login import current_user

from src.ai_analyzer.analyzer import analyze_with_agent
from src.ai_analyzer.subagents import LogAnalyzerSubagent
from src.knowledge_base.manager import KnowledgeBaseManager
from src.log_metadata.manager import LogMetadataManager
from src.settings_manager.manager import SettingsManager
from src.utils.file_utils import (
    is_archive_file, is_log_file, is_valid_log_file, extract_archive_recursive,
    create_work_directory, create_batch_work_directory, create_single_log_output_dir,
    ensure_dir, get_files_in_directory, find_log_files_in_directory,
    get_project_root, get_data_dir, get_user_data_dir, is_safe_path, clean_filename
)
from src.storage.quota import StorageQuota, format_size
from src.utils import get_logger
from plugins.manager import get_plugin_manager
from plugins import render_html
from plugins.base import count_severity

logger = get_logger('analyze_api')

analyze_bp = Blueprint('analyze_api', __name__)


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

# 全局实例
kb_manager = None
log_metadata_manager = None
settings_manager = None


def get_plugin_manager_with_custom():
    """获取包含自定义插件目录的插件管理器。"""
    root_dir = get_project_root()
    custom_dir = os.path.join(root_dir, 'custom_plugins')
    return get_plugin_manager(custom_dirs=[custom_dir])


def get_settings_manager():
    """获取或创建 SettingsManager 实例。"""
    global settings_manager
    if settings_manager is None:
        settings_manager = SettingsManager()
    return settings_manager


def get_kb_manager():
    """获取或创建 KnowledgeBaseManager 实例。"""
    global kb_manager
    if settings_manager is None:
        get_settings_manager()
    if kb_manager is None:
        kb_manager = KnowledgeBaseManager(config=settings_manager.get_all())
    return kb_manager


def get_log_metadata_manager():
    """获取或创建 LogMetadataManager 实例。"""
    global log_metadata_manager
    if log_metadata_manager is None:
        log_metadata_manager = LogMetadataManager()
    return log_metadata_manager


def allowed_log_file(filename):
    """检查文件扩展名是否为允许的日志文件。"""
    lower_name = filename.lower()
    # 支持的格式：tar.gz, tar, zip, txt, log
    ALLOWED_EXTENSIONS = ['.tar.gz', '.tgz', '.tar', '.zip', '.txt', '.log']
    for ext in ALLOWED_EXTENSIONS:
        if lower_name.endswith(ext):
            return True
    return False


def resolve_shortcut(lnk_path: str) -> str:
    """解析 Windows 快捷方式(.lnk)文件，获取实际目标路径。"""
    try:
        result = subprocess.run(
            ['powershell', '-command',
             f"(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_path}').TargetPath"],
            capture_output=True, text=True, timeout=5
        )
        target_path = result.stdout.strip()
        if target_path and os.path.exists(target_path):
            return target_path
    except Exception as e:
        logger.warning(f"解析快捷方式失败: {str(e)}")
    return lnk_path


def normalize_path(path: str) -> str:
    """规范化路径：去除双引号、解析快捷方式。"""
    # 去除首尾双引号
    path = path.strip()
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    # 解析快捷方式
    if path.lower().endswith('.lnk'):
        resolved = resolve_shortcut(path)
        if resolved != path:
            return resolved
    return path


def detect_tool_type(exe_path: str) -> str:
    """根据路径自动检测工具类型。"""
    lower_path = exe_path.lower()
    if 'code' in lower_path and ('vscode' in lower_path or 'visual' in lower_path):
        return 'vscode'
    if 'notepad++' in lower_path or 'notepadplus' in lower_path:
        return 'notepad++'
    return 'custom'


def open_log_viewer(work_dir: str):
    """使用配置的查看器打开日志目录。"""
    settings_manager = get_settings_manager()

    if not settings_manager.get('log_viewer.enabled'):
        logger.info("日志查看器未启用，跳过自动打开")
        return

    exe_path = settings_manager.get('log_viewer.exe_path', '')

    logger.info(f"准备打开日志查看器: exe_path={exe_path}, work_dir={work_dir}")

    if not exe_path:
        logger.warning("日志查看器路径为空")
        return

    # 规范化路径
    exe_path = normalize_path(exe_path)
    logger.info(f"规范化路径: {exe_path}")

    if not os.path.exists(exe_path):
        logger.warning(f"日志查看器路径不存在: {exe_path}")
        return

    if not os.path.exists(work_dir):
        logger.warning(f"工作目录不存在: {work_dir}")
        return

    # 自动检测工具类型
    tool_type = detect_tool_type(exe_path)
    logger.info(f"检测到工具类型: {tool_type}")

    try:
        if tool_type == 'notepad++':
            # Notepad++: 新窗口 + 工程模式打开
            # -multiInst: 强制新开窗口
            # -nosession: 不加载之前的会话（避免继承已有标签页）
            # -openFoldersAsWorkspace: 以工程形式打开文件夹
            subprocess.Popen([exe_path, '-multiInst', '-nosession', '-openFoldersAsWorkspace', work_dir], shell=False)
            logger.info(f"使用 Notepad++ 工程模式打开: {work_dir}")
        else:
            subprocess.Popen([exe_path, work_dir], shell=False)
            logger.info(f"使用 {tool_type} 打开: {work_dir}")
    except Exception as e:
        logger.error(f"打开日志查看器失败: {str(e)}")


def get_file_category(filename):
    """获取文件类别：archive 或 log"""
    lower_name = filename.lower()
    if lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz') or lower_name.endswith('.tar') or lower_name.endswith('.zip'):
        return 'archive'
    return 'log'


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
    kb_id: str = None,
    user_prompt: str = None,
    log_rules_id: str = None
) -> dict:
    """
    执行 AI 分析并保存结果。

    Returns:
        dict: AI 分析结果信息，包含 html_path 和 analysis_time
    """
    log_source = {'type': 'local_file', 'paths': log_file_paths}

    result = analyze_with_agent(
        settings_manager=settings_manager,
        kb_manager=get_kb_manager(),
        log_metadata_manager=get_log_metadata_manager(),
        plugin_result=plugin_result,
        log_source=log_source,
        kb_id=kb_id,
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
        'kb_id': kb_id,
        'html_path': ai_html_relative
    }


def handle_ai_selection(
    log_file_paths: list,
    user_prompt: str,
    log_rules_id: str,
    plugin_manager
) -> tuple:
    """
    处理 AI 智能选择插件和文件。

    Returns:
        tuple: (selected_plugins, selected_log_files, selection_result)
    """
    if log_rules_id:
        get_log_metadata_manager().set_active_rules(log_rules_id)

    selection_subagent = LogAnalyzerSubagent(
        settings_manager=settings_manager,
        log_metadata_manager=get_log_metadata_manager(),
        plugin_manager=plugin_manager
    )
    selection_result = selection_subagent.smart_select(log_file_paths, user_prompt, log_rules_id)

    return (
        selection_result['selected_plugins'],
        selection_result['selected_files'],
        selection_result
    )


@analyze_bp.route('/api/analyze/stream', methods=['POST'])
def analyze_stream():
    """对上传的日志文件执行流式分析。"""
    from werkzeug.utils import secure_filename

    def generate():
        temp_file_path = None
        work_dir = None

        try:
            # 获取当前用户
            user_id = get_current_user_id()
            if not user_id:
                yield generate_sse_event({'stage': 'error', 'message': '请先登录'})
                return

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

            # 检查配额（预估文件大小）
            quota = StorageQuota(user_id)
            # 获取文件大小（从 Content-Length 或估算）
            content_length = request.content_length or 50 * 1024 * 1024  # 默认估算50MB
            allowed, quota_error = quota.check_upload(content_length)
            if not allowed:
                yield generate_sse_event({'stage': 'error', 'message': quota_error})
                return

            # 获取表单数据
            plugins = request.form.getlist('plugins')
            enable_ai = request.form.get('enable_ai', 'false').lower() == 'true'
            ai_selection_mode = request.form.get('ai_selection_mode', 'false').lower() == 'true'
            kb_id = request.form.get('kb_id', '').strip() or None
            user_prompt = request.form.get('user_prompt', '').strip() or None
            log_rules_id = request.form.get('log_rules_id', '').strip() or None

            # 创建工作目录（用户隔离）
            temp_base = get_user_data_dir(user_id, 'temp')
            work_dir = create_work_directory(temp_base, filename)

            # 根据文件类型处理，确定分析路径
            file_category = get_file_category(filename)
            log_file_paths = []  # 用于AI分析读取日志内容
            analysis_path = None  # 用于插件分析的路径

            if file_category == 'archive':
                # 保存压缩包到临时位置，解压后删除
                temp_archive_path = os.path.join(temp_base, f"temp_{filename}")
                file.save(temp_archive_path)

                try:
                    # 解压压缩文件到工作目录（递归解压嵌套压缩包）
                    extracted_files = extract_archive_recursive(temp_archive_path, work_dir)
                finally:
                    # 删除临时压缩包
                    if os.path.exists(temp_archive_path):
                        os.remove(temp_archive_path)

                # 查找所有日志文件（用于AI分析）
                log_file_paths = find_log_files_in_directory(work_dir)

                if not log_file_paths:
                    yield generate_sse_event({'stage': 'error', 'message': 'No log files found in archive'})
                    return

                # 插件分析使用工作目录
                analysis_path = work_dir
            else:
                # 直接是日志文件，保存到工作目录
                uploaded_file_path = os.path.join(work_dir, filename)
                file.save(uploaded_file_path)
                log_file_paths = [uploaded_file_path]
                # 插件分析使用文件路径
                analysis_path = uploaded_file_path

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

                    selection_subagent = LogAnalyzerSubagent(
                        settings_manager=settings_manager,
                        log_metadata_manager=get_log_metadata_manager(),
                        plugin_manager=plugin_manager
                    )
                    selection_result = selection_subagent.smart_select(log_file_paths, user_prompt, log_rules_id)

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
                'message': f'Analyzing with {len(selected_plugins)} plugin(s)...'
            })

            if not selected_plugins:
                yield generate_sse_event({'stage': 'error', 'message': 'No plugins available for analysis'})
                return

            # 使用选定的插件分析
            try:
                # 使用日志回调函数，支持不同日志级别
                combined_result = plugin_manager.run_analysis(
                    selected_plugins, analysis_path,
                    log_callback=log_callback
                )
            except Exception as e:
                yield generate_sse_event({'stage': 'error', 'message': f'Plugin analysis failed: {str(e)}'})
                return

            # 保存插件分析结果（用户隔离）
            analysis_output_dir, plugin_output_file, _ = create_analysis_output_dir(user_id, filename)
            html_relative_path = save_and_render_plugin_result(combined_result, plugin_output_file)

            yield generate_sse_event({
                'stage': 'plugin',
                'status': 'complete',
                'result': combined_result
            })

            # 第2阶段：AI分析（如果启用）
            ai_result_data = None
            if enable_ai:
                yield generate_sse_event({'stage': 'ai', 'status': 'start', 'message': 'AI 分析中...'})

                try:
                    ai_result_data = run_ai_analysis(
                        combined_result, log_file_paths, analysis_output_dir,
                        kb_id, user_prompt, log_rules_id
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

            # 构建完成事件数据
            complete_data = {
                'stage': 'complete',
                'message': 'Analysis complete',
                'work_dir': work_dir,
                'html_path': html_relative_path
            }
            # 如果有 AI 分析结果，也传递 ai_html_path
            if ai_result_data and ai_result_data.get('html_path'):
                complete_data['ai_html_path'] = ai_result_data['html_path']

            # 自动打开日志查看器
            open_log_viewer(work_dir)

            yield generate_sse_event(complete_data)

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


# 待分析路径（用于 IPC）
_pending_analyze_path = None


@analyze_bp.route('/api/trigger-analysis', methods=['POST'])
def trigger_analysis():
    """设置待分析路径，用于已运行服务接收分析请求。"""
    global _pending_analyze_path
    try:
        data = request.get_json()
        path = data.get('path', '')
        if not path:
            return jsonify({'success': False, 'error': '路径不能为空'})

        _pending_analyze_path = path
        logger.info(f"设置待分析路径: {path}")
        return jsonify({'success': True, 'message': '分析请求已设置'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@analyze_bp.route('/api/pending-analysis', methods=['GET'])
def get_pending_analysis():
    """获取待分析路径。"""
    global _pending_analyze_path
    path = _pending_analyze_path
    _pending_analyze_path = None  # 获取后清除
    if path:
        return jsonify({'success': True, 'data': {'path': path}})
    return jsonify({'success': True, 'data': {'path': None}})


@analyze_bp.route('/api/analyze/local-stream', methods=['POST'])
def analyze_local_stream():
    """对本地路径执行流式分析（支持文件和目录）。"""
    def generate():
        work_dir = None
        batch_output_dir = None

        try:
            # 获取当前用户
            user_id = get_current_user_id()
            if not user_id:
                yield generate_sse_event({'stage': 'error', 'message': '请先登录'})
                return

            # 获取路径参数
            data = request.get_json()
            path = data.get('path', '')
            plugins = data.get('plugins', [])
            enable_ai = data.get('enable_ai', False)
            ai_selection_mode = data.get('ai_selection_mode', False)
            kb_id = data.get('kb_id', '').strip() or None
            user_prompt = data.get('user_prompt', '').strip() or None
            log_rules_id = data.get('log_rules_id', '').strip() or None

            if not path:
                yield generate_sse_event({'stage': 'error', 'message': '路径不能为空'})
                return

            # 验证路径
            if not os.path.exists(path):
                yield generate_sse_event({'stage': 'error', 'message': f'路径不存在: {path}'})
                return

            # 检查配额
            quota = StorageQuota(user_id)
            # 估算文件/目录大小
            if os.path.isfile(path):
                estimated_size = os.path.getsize(path)
            else:
                estimated_size = sum(os.path.getsize(f) for f in find_log_files_in_directory(path))
            allowed, quota_error = quota.check_upload(estimated_size)
            if not allowed:
                yield generate_sse_event({'stage': 'error', 'message': quota_error})
                return

            plugin_manager = get_plugin_manager_with_custom()
            temp_base = get_user_data_dir(user_id, 'temp')

            if os.path.isfile(path):
                # 单文件分析
                filename = os.path.basename(path)
                lower_name = filename.lower()
                is_archive = (lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz') or
                              lower_name.endswith('.tar') or lower_name.endswith('.zip'))

                work_dir = create_work_directory(temp_base, filename)

                if is_archive:
                    # 解压压缩包
                    extracted_files = extract_archive_recursive(path, work_dir)
                    log_file_paths = find_log_files_in_directory(work_dir)
                    analysis_path = work_dir
                else:
                    # 普通日志文件，复制到工作目录
                    import shutil
                    dest_path = os.path.join(work_dir, filename)
                    shutil.copy2(path, dest_path)
                    log_file_paths = [dest_path]
                    analysis_path = dest_path

                if not log_file_paths:
                    yield generate_sse_event({'stage': 'error', 'message': '未找到日志文件'})
                    return

                # 选择插件
                selected_plugins = []
                selected_log_files = log_file_paths
                selection_result = None

                if ai_selection_mode and enable_ai:
                    yield generate_sse_event({
                        'stage': 'selection',
                        'status': 'start',
                        'message': 'AI 正在智能选择插件...'
                    })
                    try:
                        if log_rules_id:
                            get_log_metadata_manager().set_active_rules(log_rules_id)
                        selection_subagent = LogAnalyzerSubagent(
                            settings_manager=settings_manager,
                            log_metadata_manager=get_log_metadata_manager(),
                            plugin_manager=plugin_manager
                        )
                        selection_result = selection_subagent.smart_select(log_file_paths, user_prompt, log_rules_id)
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
                            'message': f'AI 选择失败: {str(e)}'
                        })
                        selected_plugins = [p.id for p in plugin_manager.get_all_plugins()]
                        selected_log_files = log_file_paths
                else:
                    selected_plugins = plugins if plugins else [p.id for p in plugin_manager.get_all_plugins()]
                    selected_log_files = log_file_paths

                # 插件分析
                yield generate_sse_event({
                    'stage': 'plugin',
                    'status': 'start',
                    'message': f'使用 {len(selected_plugins)} 个插件分析...'
                })

                combined_result = plugin_manager.run_analysis(
                    selected_plugins, analysis_path,
                    log_callback=log_callback
                )

                # 保存结果（用户隔离）
                analysis_output_dir, plugin_output_file, _ = create_analysis_output_dir(user_id, filename)
                html_relative_path = save_and_render_plugin_result(combined_result, plugin_output_file)

                yield generate_sse_event({
                    'stage': 'plugin',
                    'status': 'complete',
                    'result': combined_result
                })

                # AI 分析
                ai_result_data = None
                if enable_ai:
                    yield generate_sse_event({'stage': 'ai', 'status': 'start', 'message': 'AI 分析中...'})
                    try:
                        ai_result_data = run_ai_analysis(
                            combined_result, log_file_paths, analysis_output_dir,
                            kb_id, user_prompt, log_rules_id
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

                # 完成
                root_dir = get_project_root()
                html_relative_path = os.path.relpath(plugin_output_file.replace('.json', '.html'), root_dir)
                complete_data = {
                    'stage': 'complete',
                    'message': 'Analysis complete',
                    'work_dir': work_dir,
                    'html_path': html_relative_path
                }
                if ai_result_data and ai_result_data.get('html_path'):
                    complete_data['ai_html_path'] = ai_result_data['html_path']

                # 自动打开日志查看器
                open_log_viewer(work_dir)

                yield generate_sse_event(complete_data)

            elif os.path.isdir(path):
                # 目录批量分析
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

                # 查找分析单元
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
                        import shutil
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

                total_units = len(analysis_units)
                yield generate_sse_event({
                    'stage': 'batch',
                    'status': 'files_found',
                    'total': total_units,
                    'message': f'发现 {total_units} 个分析单元'
                })

                selected_plugins = plugins if plugins else [p.id for p in plugin_manager.get_all_plugins()]
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
                        'message': f'分析: {unit_name} ({idx + 1}/{total_units})'
                    })

                    single_output_dir = create_single_log_output_dir(batch_output_dir, unit_name)

                    try:
                        plugin_result = plugin_manager.run_analysis(
                            selected_plugins, unit_path,
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


@analyze_bp.route('/api/analyze/batch/stream', methods=['POST'])
def analyze_batch_stream():
    """批量分析多个日志文件（文件夹上传模式）。"""
    from werkzeug.utils import secure_filename

    def generate():
        work_dir = None
        batch_output_dir = None

        try:
            # 检查是否有文件
            files = request.files.getlist('files')
            if not files or len(files) == 0:
                yield generate_sse_event({'stage': 'error', 'message': 'No files provided'})
                return

            # 获取文件夹名（从第一个文件的相对路径提取）
            first_file = files[0]
            folder_name = request.form.get('folder_name', 'uploaded_folder')

            # 获取表单数据
            plugins = request.form.getlist('plugins')
            enable_ai = request.form.get('enable_ai', 'false').lower() == 'true'
            kb_id = request.form.get('kb_id', '').strip() or None
            user_prompt = request.form.get('user_prompt', '').strip() or None
            log_rules_id = request.form.get('log_rules_id', '').strip() or None

            # 创建批量工作目录
            temp_base = get_data_dir('temp')
            work_dir = create_batch_work_directory(temp_base, folder_name)

            # 创建批量输出目录
            analysis_output_base = os.path.join(temp_base, '..', 'analysis_output')
            batch_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            clean_folder_name = folder_name
            for ext in ['.tar.gz', '.tgz', '.tar', '.zip']:
                if clean_folder_name.lower().endswith(ext):
                    clean_folder_name = clean_folder_name[:-len(ext)]
                    break
            batch_dir_name = f"{batch_timestamp}_{clean_folder_name}"
            batch_output_dir = os.path.join(analysis_output_base, batch_dir_name)
            ensure_dir(batch_output_dir)

            yield generate_sse_event({
                'stage': 'batch',
                'status': 'start',
                'message': f'开始批量分析...',
                'work_dir': work_dir
            })

            # 处理上传的文件，构建分析单元列表
            # 每个分析单元是一个路径（目录或文件）
            analysis_units = []
            for file in files:
                filename = secure_filename(file.filename)
                if not filename:
                    continue

                # 检查文件类型
                lower_name = filename.lower()
                is_archive = (lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz') or
                              lower_name.endswith('.tar') or lower_name.endswith('.zip'))

                if is_archive:
                    # 压缩文件：先保存到临时位置，解压后删除压缩包
                    temp_archive_path = os.path.join(work_dir, f"_temp_{filename}")
                    file.save(temp_archive_path)

                    try:
                        # 解压到工作目录
                        extract_dir_name = os.path.splitext(filename)[0]
                        # 处理 .tar.gz 的双重扩展名
                        if lower_name.endswith('.tar.gz'):
                            extract_dir_name = filename[:-7]  # 移除 .tar.gz
                        elif lower_name.endswith('.tgz'):
                            extract_dir_name = filename[:-4]  # 移除 .tgz
                        extract_dir = os.path.join(work_dir, extract_dir_name)
                        ensure_dir(extract_dir)
                        extract_archive_recursive(temp_archive_path, extract_dir)
                        # 分析单元为解压后的目录
                        analysis_units.append({
                            'path': extract_dir,
                            'name': extract_dir_name,
                            'is_archive': True
                        })
                    finally:
                        # 删除临时压缩包
                        if os.path.exists(temp_archive_path):
                            os.remove(temp_archive_path)
                elif is_valid_log_file(filename):
                    # 普通日志文件：直接保存到工作目录
                    file_path = os.path.join(work_dir, filename)
                    file.save(file_path)
                    # 分析单元为文件
                    analysis_units.append({
                        'path': file_path,
                        'name': filename,
                        'is_archive': False
                    })
                # 其他文件类型跳过

            if not analysis_units:
                yield generate_sse_event({'stage': 'error', 'message': '未找到有效的日志文件'})
                return

            total_units = len(analysis_units)
            yield generate_sse_event({
                'stage': 'batch',
                'status': 'files_found',
                'total': total_units,
                'message': f'发现 {total_units} 个分析单元'
            })

            # 获取插件管理器
            plugin_manager = get_plugin_manager_with_custom()
            selected_plugins = plugins if plugins else [p.id for p in plugin_manager.get_all_plugins()]

            if not selected_plugins:
                yield generate_sse_event({'stage': 'error', 'message': '没有可用的插件'})
                return

            # 分析每个单元
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

                # 创建单个单元的输出目录
                single_output_dir = create_single_log_output_dir(batch_output_dir, unit_name)

                # 插件分析
                try:
                    # 使用日志回调函数，支持不同日志级别
                    plugin_result = plugin_manager.run_analysis(
                        selected_plugins, unit_path,
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

                # 保存插件结果
                plugin_output_file = os.path.join(single_output_dir, 'plugin_result.json')
                html_relative_path = save_and_render_plugin_result(plugin_result, plugin_output_file)

                # 获取该单元内的日志文件列表（用于AI分析）
                log_files_in_unit = find_log_files_in_directory(unit_path) if os.path.isdir(unit_path) else [unit_path]

                # AI分析（如果启用）
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

                # 记录结果
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

            # 生成汇总JSON
            batch_summary_file = os.path.join(batch_output_dir, 'batch_summary.json')
            summary_data = {
                'batch_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'folder_name': folder_name,
                'total_files': total_units,
                'files': batch_results
            }
            with open(batch_summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=4, ensure_ascii=False)

            # 生成汇总HTML
            from plugins.renderer.html_renderer import render_batch_html
            batch_html_path = render_batch_html(batch_summary_file)

            batch_html_relative = os.path.relpath(batch_html_path, get_project_root())

            # 构建前端需要的文件列表
            frontend_files = []
            for filename, file_data in batch_results.items():
                # 计算错误和警告数
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
