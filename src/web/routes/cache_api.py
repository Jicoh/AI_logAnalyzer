"""
缓存清理 API 路由。
"""

import os
import stat
import errno
import time
import shutil
from flask import Blueprint, jsonify
from src.utils import get_data_dir

cache_bp = Blueprint('cache_api', __name__)


def format_size(size_bytes):
    """格式化大小显示。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def handle_readonly(func, path, excinfo):
    """处理只读文件删除失败，用于 shutil.rmtree 的 onerror 回调。"""
    if func in (os.rmdir, os.remove):
        exc = excinfo[1]
        if hasattr(exc, 'errno') and exc.errno in (errno.EACCES, errno.EPERM):
            try:
                os.chmod(path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
                func(path)
            except OSError:
                pass


def delete_with_retry(path, is_dir=False, max_retries=3, delay=0.1):
    """带重试和权限处理的删除。"""
    for attempt in range(max_retries):
        try:
            if is_dir:
                shutil.rmtree(path, onerror=handle_readonly)
            else:
                if not os.access(path, os.W_OK):
                    os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
                os.remove(path)
            return True
        except OSError:
            if attempt == max_retries - 1:
                return False
            time.sleep(delay)
    return False


def clear_dir_contents(path):
    """清空目录内容但保留目录本身，返回统计信息。"""
    if not os.path.exists(path):
        return {'deleted': 0, 'failed': 0, 'failed_files': []}

    stats = {'deleted': 0, 'failed': 0, 'failed_files': []}

    for entry in os.scandir(path):
        is_dir = entry.is_dir()
        if delete_with_retry(entry.path, is_dir=is_dir):
            stats['deleted'] += 1
        else:
            stats['failed'] += 1
            stats['failed_files'].append(entry.path)

    return stats


@cache_bp.route('/api/cache/stats', methods=['GET'])
def get_cache_stats():
    """获取缓存目录大小统计。"""
    try:
        temp_dir = get_data_dir('temp')
        plugin_output_dir = get_data_dir('plugin_output')

        temp_size = get_dir_size(temp_dir)
        plugin_output_size = get_dir_size(plugin_output_dir)

        return jsonify({
            'success': True,
            'data': {
                'temp': {
                    'path': temp_dir,
                    'size_bytes': temp_size,
                    'size_formatted': format_size(temp_size)
                },
                'plugin_output': {
                    'path': plugin_output_dir,
                    'size_bytes': plugin_output_size,
                    'size_formatted': format_size(plugin_output_size)
                },
                'total': {
                    'size_bytes': temp_size + plugin_output_size,
                    'size_formatted': format_size(temp_size + plugin_output_size)
                }
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@cache_bp.route('/api/cache/clear-results', methods=['POST'])
def clear_results():
    """清理分析结果目录。"""
    try:
        plugin_output_dir = get_data_dir('plugin_output')
        stats = clear_dir_contents(plugin_output_dir)

        message = f"清理完成：删除 {stats['deleted']} 个文件"
        if stats['failed'] > 0:
            message += f"，{stats['failed']} 个文件删除失败"

        return jsonify({
            'success': True,
            'message': message,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@cache_bp.route('/api/cache/clear-temp', methods=['POST'])
def clear_temp():
    """清理临时文件目录。"""
    try:
        temp_dir = get_data_dir('temp')
        stats = clear_dir_contents(temp_dir)

        message = f"清理完成：删除 {stats['deleted']} 个文件"
        if stats['failed'] > 0:
            message += f"，{stats['failed']} 个文件删除失败"

        return jsonify({
            'success': True,
            'message': message,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def get_dir_size(path):
    """计算目录大小（字节）。"""
    if not os.path.exists(path):
        return 0
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    except OSError:
        pass
    return total