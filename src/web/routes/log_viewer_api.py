"""
日志查看 API 路由
提供日志文件树、内容查看、时间筛选等功能
"""

import os
import json
import urllib.parse
from datetime import datetime, timedelta
from typing import Tuple, List, Dict
from flask import Blueprint, request, jsonify
from src.utils.file_utils import (
    find_log_files_in_directory, get_files_in_directory, is_valid_log_file,
    get_project_root, get_data_dir
)
from src.utils.log_time_parser import (
    detect_time_format, get_file_time_range, read_log_lines,
    filter_log_by_time, filter_log_by_center_time, filter_log_by_quick_mode,
    filter_multi_files_by_time, filter_multi_files_by_center_time, filter_multi_files_by_quick_mode,
    parse_user_input_time
)
from src.utils import get_logger

logger = get_logger('log_viewer_api')

log_viewer_bp = Blueprint('log_viewer_api', __name__)


def determine_analysis_type(work_dir: str) -> Tuple[str, List]:
    """
    判断分析类型（通过检查 analysis_output 目录）

    Returns:
        tuple: (analysis_type, items)
        - 'single_file': 单文件分析，items 为日志文件列表
        - 'folder_batch': 文件夹分析，items 为分析单元列表
    """
    items = os.listdir(work_dir)

    # 通过检查对应的 analysis_output 目录来判断类型
    # temp 目录名和 analysis_output 目录名相同（都是时间戳_文件名格式）
    analysis_output_base = get_data_dir('analysis_output')
    folder_name = os.path.basename(work_dir)
    output_dir = os.path.join(analysis_output_base, folder_name)

    # 检查是否有 batch_summary.json（文件夹分析的标志）
    batch_summary_path = os.path.join(output_dir, 'batch_summary.json')
    if os.path.exists(batch_summary_path):
        # 文件夹分析
        units = []
        subdirs = [f for f in items if os.path.isdir(os.path.join(work_dir, f))]
        for subdir in subdirs:
            subdir_path = os.path.join(work_dir, subdir)
            log_files = find_log_files_in_directory(subdir_path)
            units.append({
                'name': subdir,
                'path': subdir_path,
                'file_count': len(log_files)
            })
        return 'folder_batch', units

    # 单文件分析
    # 检查直接是否有日志文件
    direct_log_files = [f for f in items if is_valid_log_file(os.path.join(work_dir, f))]

    # 检查子目录
    subdirs = [f for f in items if os.path.isdir(os.path.join(work_dir, f))]

    if direct_log_files:
        return 'single_file', [os.path.join(work_dir, f) for f in direct_log_files]
    elif len(subdirs) == 1:
        subdir_path = os.path.join(work_dir, subdirs[0])
        log_files = find_log_files_in_directory(subdir_path)
        if log_files:
            return 'single_file', log_files
        else:
            return 'single_file', []
    elif len(subdirs) > 1:
        # 兼容：如果 output 目录不存在，按目录结构判断
        units = []
        for subdir in subdirs:
            subdir_path = os.path.join(work_dir, subdir)
            log_files = find_log_files_in_directory(subdir_path)
            units.append({
                'name': subdir,
                'path': subdir_path,
                'file_count': len(log_files)
            })
        return 'folder_batch', units
    else:
        return 'unknown', []


def get_recent_work_dir():
    """获取最近一次分析的工作目录及分析类型"""
    temp_dir = get_data_dir('temp')

    if not os.path.exists(temp_dir):
        return None

    # 获取最新的temp目录
    folders = sorted(os.listdir(temp_dir), reverse=True)

    for folder in folders:
        folder_path = os.path.join(temp_dir, folder)
        if not os.path.isdir(folder_path):
            continue

        # 判断分析类型
        analysis_type, items = determine_analysis_type(folder_path)

        if analysis_type == 'unknown' or not items:
            continue

        display_name = folder.split('_', 1)[-1] if '_' in folder else folder

        return {
            'path': folder_path,
            'analysis_type': analysis_type,
            'display_name': display_name,
            'items': items
        }

    return None


def get_all_temp_folders():
    """获取 temp 目录下所有工作目录列表"""
    temp_dir = get_data_dir('temp')

    if not os.path.exists(temp_dir):
        return []

    folders = sorted(os.listdir(temp_dir), reverse=True)
    result = []

    for folder in folders:
        folder_path = os.path.join(temp_dir, folder)
        if not os.path.isdir(folder_path):
            continue

        analysis_type, items = determine_analysis_type(folder_path)
        if analysis_type == 'unknown' or not items:
            continue

        result.append({
            'path': folder_path,
            'display_name': folder,
            'analysis_type': analysis_type,
            'folder_name': folder
        })

    return result


def build_file_tree(dir_path: str, max_depth: int = 3) -> list:
    """
    构建文件树结构

    Args:
        dir_path: 目录路径
        max_depth: 最大递归深度

    Returns:
        list: [{name, path, is_file, children}]
    """
    result = []

    try:
        items = sorted(os.listdir(dir_path))
    except Exception as e:
        logger.warning(f"无法读取目录: {dir_path} - {e}")
        return result

    for item in items:
        item_path = os.path.join(dir_path, item)

        if os.path.isfile(item_path):
            # 只显示日志文件
            if is_valid_log_file(item_path) or item.lower().endswith('.json'):
                result.append({
                    'name': item,
                    'path': item_path,
                    'is_file': True,
                    'size': os.path.getsize(item_path)
                })
        elif os.path.isdir(item_path):
            # 递归构建子目录
            children = []
            if max_depth > 0:
                children = build_file_tree(item_path, max_depth - 1)

            # 只显示有内容的目录
            if children:
                result.append({
                    'name': item,
                    'path': item_path,
                    'is_file': False,
                    'children': children,
                    'file_count': len([c for c in children if c.get('is_file')])
                })

    return result


@log_viewer_bp.route('/api/log-viewer/temp-folders', methods=['GET'])
def get_temp_folders():
    """获取 temp 目录下所有工作目录列表"""
    try:
        folders = get_all_temp_folders()
        return jsonify({
            'success': True,
            'data': folders
        })
    except Exception as e:
        logger.error(f"获取 temp 目录列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@log_viewer_bp.route('/api/log-viewer/recent-path', methods=['GET'])
def get_recent_path():
    """获取最近一次分析的日志路径"""
    try:
        work_info = get_recent_work_dir()

        if not work_info:
            return jsonify({
                'success': False,
                'error': '没有找到最近的分析记录',
                'data': None
            })

        analysis_type = work_info['analysis_type']

        if analysis_type == 'single_file':
            # 单文件分析：返回日志文件列表
            log_files = work_info['items']
            return jsonify({
                'success': True,
                'data': {
                    'path': work_info['path'],
                    'analysis_type': 'single_file',
                    'display_name': work_info['display_name'],
                    'log_files': [os.path.basename(f) for f in log_files],
                    'log_file_paths': log_files,
                    'files_count': len(log_files)
                }
            })
        elif analysis_type == 'folder_batch':
            # 文件夹分析：返回分析单元列表
            units = work_info['items']
            return jsonify({
                'success': True,
                'data': {
                    'path': work_info['path'],
                    'analysis_type': 'folder_batch',
                    'display_name': work_info['display_name'],
                    'analysis_units': units,
                    'units_count': len(units)
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': '无法确定分析类型',
                'data': None
            })

    except Exception as e:
        logger.error(f"获取最近路径失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@log_viewer_bp.route('/api/log-viewer/validate-path', methods=['POST'])
def validate_path():
    """验证用户输入的路径"""
    try:
        data = request.get_json()
        path = data.get('path', '')

        if not path:
            return jsonify({'success': False, 'error': '路径不能为空'})

        # 处理 URL 编码
        path = urllib.parse.unquote(path)

        # 验证路径安全（防止目录穿越）
        try:
            # 转换为绝对路径
            abs_path = os.path.abspath(path)
        except Exception:
            return jsonify({'success': False, 'error': '路径格式无效'})

        if not os.path.exists(abs_path):
            return jsonify({'success': False, 'error': '路径不存在'})

        if os.path.isfile(abs_path):
            filename = os.path.basename(abs_path)
            is_log = is_valid_log_file(abs_path)

            if not is_log:
                return jsonify({'success': False, 'error': '不是有效的日志文件'})

            return jsonify({
                'success': True,
                'data': {
                    'path': abs_path,
                    'is_folder': False,
                    'filename': filename,
                    'size': os.path.getsize(abs_path)
                }
            })

        elif os.path.isdir(abs_path):
            log_files = find_log_files_in_directory(abs_path)

            return jsonify({
                'success': True,
                'data': {
                    'path': abs_path,
                    'is_folder': True,
                    'folder_name': os.path.basename(abs_path) or 'root',
                    'files_count': len(log_files)
                }
            })

        else:
            return jsonify({'success': False, 'error': '路径类型未知'})

    except Exception as e:
        logger.error(f"验证路径失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@log_viewer_bp.route('/api/log-viewer/file-tree', methods=['GET'])
def get_file_tree():
    """获取目录的文件树结构"""
    try:
        path = request.args.get('path', '')

        if not path:
            return jsonify({'success': False, 'error': '路径不能为空'})

        # 处理 URL 编码
        path = urllib.parse.unquote(path)

        if not os.path.exists(path):
            return jsonify({'success': False, 'error': '路径不存在'})

        if not os.path.isdir(path):
            # 单文件，返回简单结构
            return jsonify({
                'success': True,
                'data': [{
                    'name': os.path.basename(path),
                    'path': path,
                    'is_file': True,
                    'size': os.path.getsize(path)
                }]
            })

        # 构建目录树
        tree = build_file_tree(path, max_depth=3)

        return jsonify({'success': True, 'data': tree})

    except Exception as e:
        logger.error(f"获取文件树失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@log_viewer_bp.route('/api/log-viewer/file-content', methods=['GET'])
def get_file_content():
    """获取日志文件内容（支持时间筛选）"""
    try:
        path = request.args.get('path', '')
        start_time_str = request.args.get('start_time', '')
        end_time_str = request.args.get('end_time', '')
        center_time_str = request.args.get('center_time', '')
        offset_minutes = request.args.get('offset_minutes', '60')
        mode = request.args.get('mode', '')  # quick mode
        max_lines = int(request.args.get('max_lines', '10000'))

        if not path:
            return jsonify({'success': False, 'error': '文件路径不能为空'})

        path = urllib.parse.unquote(path)

        if not os.path.exists(path):
            return jsonify({'success': False, 'error': '文件不存在'})

        if not os.path.isfile(path):
            return jsonify({'success': False, 'error': '路径不是文件'})

        # 检测时间格式
        format_info = detect_time_format(path)

        lines = []
        filter_start_time = None
        filter_end_time = None

        # 快捷模式
        if mode:
            lines, filter_start_time, filter_end_time = filter_log_by_quick_mode(
                path, mode, format_info, max_lines
            )
        # 时间点偏移模式
        elif center_time_str:
            center_time = parse_user_input_time(center_time_str)
            if not center_time:
                return jsonify({'success': False, 'error': f'时间格式无法解析: {center_time_str}'})
            offset = int(offset_minutes)
            lines = filter_log_by_center_time(path, center_time, offset, format_info, max_lines)
            filter_start_time = center_time - timedelta(minutes=offset)
            filter_end_time = center_time + timedelta(minutes=offset)

        # 精确时间范围模式
        elif start_time_str and end_time_str:
            start_time = parse_user_input_time(start_time_str)
            end_time = parse_user_input_time(end_time_str)
            if not start_time or not end_time:
                return jsonify({'success': False, 'error': f'时间格式无法解析: start={start_time_str}, end={end_time_str}'})
            lines = filter_log_by_time(path, start_time, end_time, format_info, max_lines)
            filter_start_time = start_time
            filter_end_time = end_time

        # 无筛选，返回全部内容
        else:
            lines = read_log_lines(path, 0, max_lines)

        # 计算总行数
        total_lines = 0
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for _ in f:
                    total_lines += 1
        except Exception:
            pass

        return jsonify({
            'success': True,
            'data': {
                'lines': lines,
                'total_lines': total_lines,
                'filtered_lines': len(lines),
                'detected_format': format_info.get('format'),
                'format_description': format_info.get('description', '未知格式'),
                'has_year': format_info.get('has_year', False),
                'all_formats': format_info.get('all_formats'),
                'filter_start_time': filter_start_time.strftime('%Y-%m-%d %H:%M:%S') if filter_start_time else None,
                'filter_end_time': filter_end_time.strftime('%Y-%m-%d %H:%M:%S') if filter_end_time else None
            }
        })

    except Exception as e:
        logger.error(f"获取文件内容失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@log_viewer_bp.route('/api/log-viewer/file-time-range', methods=['GET'])
def get_file_time_range():
    """获取日志文件的时间范围"""
    try:
        path = request.args.get('path', '')

        if not path:
            return jsonify({'success': False, 'error': '文件路径不能为空'})

        path = urllib.parse.unquote(path)

        if not os.path.exists(path):
            return jsonify({'success': False, 'error': '文件不存在'})

        if not os.path.isfile(path):
            return jsonify({'success': False, 'error': '路径不是文件'})

        min_time, max_time, format_info = get_file_time_range(path)

        result = {
            'detected_format': format_info.get('format'),
            'format_description': format_info.get('description', '未知格式'),
            'has_year': format_info.get('has_year', False),
            'match_count': format_info.get('match_count', 0),
            'total_lines': format_info.get('total_lines', 0)
        }

        # 如果检测到多种格式，返回所有格式信息
        if format_info.get('all_formats'):
            result['all_formats'] = [
                {'format': f.get('format'), 'description': f.get('description'), 'count': f.get('count')}
                for f in format_info['all_formats']
            ]

        if min_time:
            result['min_time'] = min_time.strftime('%Y-%m-%d %H:%M:%S')
        if max_time:
            result['max_time'] = max_time.strftime('%Y-%m-%d %H:%M:%S')

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        logger.error(f"获取时间范围失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@log_viewer_bp.route('/api/log-viewer/multi-file-content', methods=['GET'])
def get_multi_file_content():
    """获取多个日志文件的内容（同一时间段筛选）"""
    try:
        dir_path = request.args.get('dir_path', '')
        start_time_str = request.args.get('start_time', '')
        end_time_str = request.args.get('end_time', '')
        center_time_str = request.args.get('center_time', '')
        offset_minutes = request.args.get('offset_minutes', '60')
        mode = request.args.get('mode', '')  # quick mode
        max_total_lines = int(request.args.get('max_total_lines', '20000'))

        if not dir_path:
            return jsonify({'success': False, 'error': '目录路径不能为空'})

        dir_path = urllib.parse.unquote(dir_path)

        if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            return jsonify({'success': False, 'error': '路径不存在或不是目录'})

        # 获取目录下所有日志文件
        log_files = find_log_files_in_directory(dir_path)

        if not log_files:
            return jsonify({'success': False, 'error': '目录中没有日志文件'})

        lines = []
        filter_start_time = None
        filter_end_time = None

        # 快捷模式
        if mode:
            lines, filter_start_time, filter_end_time = filter_multi_files_by_quick_mode(
                log_files, mode, max_total_lines=max_total_lines
            )
        # 时间点偏移模式
        elif center_time_str:
            center_time = parse_user_input_time(center_time_str)
            if not center_time:
                return jsonify({'success': False, 'error': f'时间格式无法解析: {center_time_str}'})
            offset = int(offset_minutes)
            lines, filter_start_time, filter_end_time = filter_multi_files_by_center_time(
                log_files, center_time, offset, max_total_lines=max_total_lines
            )

        # 精确时间范围模式
        elif start_time_str and end_time_str:
            start_time = parse_user_input_time(start_time_str)
            end_time = parse_user_input_time(end_time_str)
            if not start_time or not end_time:
                return jsonify({'success': False, 'error': f'时间格式无法解析: start={start_time_str}, end={end_time_str}'})
            lines = filter_multi_files_by_time(
                log_files, start_time, end_time, max_total_lines=max_total_lines
            )
            filter_start_time = start_time
            filter_end_time = end_time

        else:
            return jsonify({'success': False, 'error': '请指定时间筛选参数'})

        # 统计每个文件的行数
        file_stats = {}
        for line in lines:
            source = line.get('source_file', 'unknown')
            if source not in file_stats:
                file_stats[source] = 0
            file_stats[source] += 1

        return jsonify({
            'success': True,
            'data': {
                'lines': lines,
                'filtered_lines': len(lines),
                'file_count': len(log_files),
                'file_stats': file_stats,
                'filter_start_time': filter_start_time.strftime('%Y-%m-%d %H:%M:%S') if filter_start_time else None,
                'filter_end_time': filter_end_time.strftime('%Y-%m-%d %H:%M:%S') if filter_end_time else None
            }
        })

    except Exception as e:
        logger.error(f"多文件筛选失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@log_viewer_bp.route('/api/log-viewer/analysis-unit-info', methods=['GET'])
def get_analysis_unit_info():
    """获取分析单元的日志文件详情（文件夹分析专用）"""
    try:
        path = request.args.get('path', '')

        if not path:
            return jsonify({'success': False, 'error': '路径不能为空'})

        path = urllib.parse.unquote(path)

        if not os.path.exists(path) or not os.path.isdir(path):
            return jsonify({'success': False, 'error': '路径不存在或不是目录'})

        log_files = find_log_files_in_directory(path)

        return jsonify({
            'success': True,
            'data': {
                'path': path,
                'name': os.path.basename(path),
                'log_files': [os.path.basename(f) for f in log_files],
                'log_file_paths': log_files,
                'file_count': len(log_files)
            }
        })

    except Exception as e:
        logger.error(f"获取分析单元信息失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500