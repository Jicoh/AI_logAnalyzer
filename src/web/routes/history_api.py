"""
历史记录 API 路由，用于查看过去的分析结果。
"""

import os
import json
from datetime import datetime
from flask import Blueprint, jsonify

history_bp = Blueprint('history_api', __name__)


def get_plugin_output_dir():
    """获取插件输出目录路径。"""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(root_dir, 'data', 'plugin_output')


def get_ai_output_dir():
    """获取 AI 输出目录路径。"""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(root_dir, 'data', 'ai_output')


def parse_timestamp_folder(folder_name):
    """从文件夹名解析时间戳，如 '20260321_200213'。"""
    try:
        dt = datetime.strptime(folder_name, '%Y%m%d_%H%M%S')
        return dt
    except ValueError:
        return None


def get_history_list():
    """获取所有分析历史记录列表。"""
    plugin_output_dir = get_plugin_output_dir()
    ai_output_dir = get_ai_output_dir()

    history_records = []

    if not os.path.exists(plugin_output_dir):
        return history_records

    # 列出所有时间戳目录
    for folder_name in sorted(os.listdir(plugin_output_dir), reverse=True):
        folder_path = os.path.join(plugin_output_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue

        dt = parse_timestamp_folder(folder_name)
        if not dt:
            continue

        # 读取插件结果
        plugin_result_path = os.path.join(folder_path, 'plugin_result.json')
        if not os.path.exists(plugin_result_path):
            continue

        try:
            with open(plugin_result_path, 'r', encoding='utf-8') as f:
                plugin_result = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        # 计算插件总数
        total_errors = 0
        total_warnings = 0
        plugin_count = 0
        log_file = plugin_result.get('log_file', 'Unknown')

        plugins = plugin_result.get('plugins', {})
        if plugins:
            plugin_count = len(plugins)
            for plugin_data in plugins.values():
                total_errors += plugin_data.get('error_count', 0)
                total_warnings += plugin_data.get('warning_count', 0)
        else:
            # 兼容旧格式
            total_errors = plugin_result.get('error_count', 0)
            total_warnings = plugin_result.get('warning_count', 0)
            plugin_count = 1

        # 检查是否有 AI 结果
        ai_result_path = os.path.join(folder_path, 'ai_result.json')
        has_ai_result = os.path.exists(ai_result_path)

        history_records.append({
            'timestamp': folder_name,
            'formatted_time': dt.strftime('%Y-%m-%d %H:%M:%S'),
            'log_file': log_file,
            'total_errors': total_errors,
            'total_warnings': total_warnings,
            'plugin_count': plugin_count,
            'has_ai_result': has_ai_result
        })

    return history_records


def get_history_detail(timestamp):
    """获取特定历史记录的详情。"""
    plugin_output_dir = get_plugin_output_dir()
    folder_path = os.path.join(plugin_output_dir, timestamp)

    if not os.path.exists(folder_path):
        return None

    dt = parse_timestamp_folder(timestamp)
    if not dt:
        return None

    # 读取插件结果
    plugin_result_path = os.path.join(folder_path, 'plugin_result.json')
    if not os.path.exists(plugin_result_path):
        return None

    try:
        with open(plugin_result_path, 'r', encoding='utf-8') as f:
            plugin_result = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    result = {
        'timestamp': timestamp,
        'formatted_time': dt.strftime('%Y-%m-%d %H:%M:%S'),
        'plugin_result': plugin_result
    }

    # 如果存在 AI 结果则读取
    ai_result_path = os.path.join(folder_path, 'ai_result.json')
    if os.path.exists(ai_result_path):
        try:
            with open(ai_result_path, 'r', encoding='utf-8') as f:
                ai_result = json.load(f)
                result['ai_result'] = ai_result.get('analysis', '')
        except (json.JSONDecodeError, IOError):
            pass

    return result


@history_bp.route('/api/history', methods=['GET'])
def list_history():
    """获取所有历史记录列表。"""
    try:
        records = get_history_list()
        return jsonify({'success': True, 'data': records})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@history_bp.route('/api/history/<timestamp>', methods=['GET'])
def get_history(timestamp):
    """获取特定历史记录的详情。"""
    try:
        detail = get_history_detail(timestamp)
        if detail is None:
            return jsonify({'success': False, 'error': 'Record not found'}), 404
        return jsonify({'success': True, 'data': detail})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500