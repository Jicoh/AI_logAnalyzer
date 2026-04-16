"""
缓存清理 API 路由。
"""

import os
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


def clear_dir_contents(path):
    """清空目录内容但保留目录本身。"""
    if not os.path.exists(path):
        return
    for entry in os.scandir(path):
        try:
            if entry.is_dir():
                shutil.rmtree(entry.path)
            else:
                os.remove(entry.path)
        except OSError:
            pass


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
        clear_dir_contents(plugin_output_dir)

        return jsonify({
            'success': True,
            'message': '分析结果已清理'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@cache_bp.route('/api/cache/clear-temp', methods=['POST'])
def clear_temp():
    """清理临时文件目录。"""
    try:
        temp_dir = get_data_dir('temp')
        clear_dir_contents(temp_dir)

        return jsonify({
            'success': True,
            'message': '缓存文件已清理'
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