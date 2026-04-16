"""
历史记录 API 路由，用于查看过去的分析结果。
"""

import os
import json
import re
from datetime import datetime
from flask import Blueprint, jsonify
from src.utils import get_data_dir

history_bp = Blueprint('history_api', __name__)


def parse_timestamp_folder(folder_name):
    """
    从文件夹名解析时间戳。
    支持两种格式：
    - 旧格式: '20260321_200213'
    - 新格式: '20260321_200213_filename'
    """
    # 使用正则提取时间戳部分（前15个字符）
    match = re.match(r'^(\d{8}_\d{6})', folder_name)
    if match:
        timestamp_str = match.group(1)
        try:
            dt = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
            return dt
        except ValueError:
            return None
    return None


def get_history_list():
    """获取所有分析历史记录列表。"""
    plugin_output_dir = get_data_dir('plugin_output')

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

        # 检查是否为批量分析目录（包含 batch_summary.json）
        batch_summary_path = os.path.join(folder_path, 'batch_summary.json')
        if os.path.exists(batch_summary_path):
            # 批量分析记录
            try:
                with open(batch_summary_path, 'r', encoding='utf-8') as f:
                    batch_summary = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

            # 计算总统计和子文件列表
            total_errors = 0
            total_warnings = 0
            files_list = []

            files_data = batch_summary.get('files', {})
            for filename, file_data in files_data.items():
                # 计算单个文件的错误、警告数和插件数
                file_errors = 0
                file_warnings = 0
                plugin_count = 0
                plugin_result = file_data.get('plugin_result', {})
                for plugin_id, plugin_data in plugin_result.items():
                    if isinstance(plugin_data, dict):
                        plugin_count += 1
                        sections = plugin_data.get('sections', [])
                        for section in sections:
                            if section.get('type') == 'stats' and section.get('items'):
                                for item in section.get('items', []):
                                    severity = item.get('severity', '')
                                    value = item.get('value', 0)
                                    if isinstance(value, (int, float)):
                                        if severity == 'error':
                                            file_errors += int(value)
                                        elif severity == 'warning':
                                            file_warnings += int(value)

                total_errors += file_errors
                total_warnings += file_warnings

                files_list.append({
                    'filename': filename,
                    'output_dir': file_data.get('output_dir', ''),
                    'errors': file_errors,
                    'warnings': file_warnings,
                    'plugin_count': plugin_count,
                    'has_ai_result': file_data.get('ai_result') is not None,
                    'html_path': file_data.get('html_path', '')
                })

            history_records.append({
                'folder_name': folder_name,
                'timestamp': folder_name,
                'formatted_time': dt.strftime('%Y-%m-%d %H:%M:%S'),
                'is_batch': True,
                'total_files': batch_summary.get('total_files', len(files_list)),
                'total_errors': total_errors,
                'total_warnings': total_warnings,
                'files': files_list
            })
            continue

        # 单文件分析记录
        plugin_result_path = os.path.join(folder_path, 'plugin_result.json')
        if not os.path.exists(plugin_result_path):
            continue

        try:
            with open(plugin_result_path, 'r', encoding='utf-8') as f:
                plugin_result = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        # 计算统计信息
        total_errors = 0
        total_warnings = 0
        plugin_count = 0

        for plugin_id, plugin_data in plugin_result.items():
            if isinstance(plugin_data, dict):
                plugin_count += 1
                sections = plugin_data.get('sections', [])
                for section in sections:
                    if section.get('type') == 'stats' and section.get('items'):
                        for item in section.get('items', []):
                            severity = item.get('severity', '')
                            value = item.get('value', 0)
                            if isinstance(value, (int, float)):
                                if severity == 'error':
                                    total_errors += int(value)
                                elif severity == 'warning':
                                    total_warnings += int(value)

        # 检查是否有 HTML 结果文件
        html_path = os.path.join(folder_path, 'plugin_result.html')
        has_html_result = os.path.exists(html_path)

        # 检查是否有 AI 结果（新版：ai_analysis.html，旧版：ai_result.json）
        ai_html_path = os.path.join(folder_path, 'ai_analysis.html')
        ai_json_path = os.path.join(folder_path, 'ai_result.json')
        has_ai_result = os.path.exists(ai_html_path) or os.path.exists(ai_json_path)

        history_records.append({
            'folder_name': folder_name,
            'timestamp': folder_name,
            'formatted_time': dt.strftime('%Y-%m-%d %H:%M:%S'),
            'is_batch': False,
            'total_errors': total_errors,
            'total_warnings': total_warnings,
            'plugin_count': plugin_count,
            'has_html_result': has_html_result,
            'has_ai_result': has_ai_result
        })

    return history_records


def get_history_detail(timestamp):
    """获取特定历史记录的详情。"""
    plugin_output_dir = get_data_dir('plugin_output')
    folder_path = os.path.join(plugin_output_dir, timestamp)

    if not os.path.exists(folder_path):
        return None

    dt = parse_timestamp_folder(timestamp)
    if not dt:
        return None

    result = {
        'folder_name': timestamp,
        'timestamp': timestamp,
        'formatted_time': dt.strftime('%Y-%m-%d %H:%M:%S')
    }

    # 检查 HTML 文件是否存在，返回相对路径用于 iframe
    html_path = os.path.join(folder_path, 'plugin_result.html')
    if os.path.exists(html_path):
        # 计算相对于项目根目录的路径
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        html_relative_path = os.path.relpath(html_path, root_dir)
        result['html_path'] = html_relative_path

    # 如果存在 AI 结果则读取
    # 新版：ai_analysis.html（HTML 格式）
    ai_html_path = os.path.join(folder_path, 'ai_analysis.html')
    if os.path.exists(ai_html_path):
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        ai_html_relative = os.path.relpath(ai_html_path, root_dir)
        result['ai_html_path'] = ai_html_relative
        result['has_ai_html'] = True

    # 旧版：ai_result.json（JSON 格式）
    ai_result_path = os.path.join(folder_path, 'ai_result.json')
    if os.path.exists(ai_result_path):
        try:
            with open(ai_result_path, 'r', encoding='utf-8') as f:
                ai_result = json.load(f)
                result['ai_result'] = ai_result.get('analysis', '')
        except (json.JSONDecodeError, IOError):
            pass

    return result


def get_batch_file_detail(batch_folder, file_output_dir):
    """获取批量记录中单个文件的详情。"""
    plugin_output_dir = get_data_dir('plugin_output')
    folder_path = os.path.join(plugin_output_dir, batch_folder, file_output_dir)

    if not os.path.exists(folder_path):
        return None

    result = {
        'folder_name': file_output_dir,
        'batch_folder': batch_folder
    }

    # 检查 HTML 文件
    html_path = os.path.join(folder_path, 'plugin_result.html')
    if os.path.exists(html_path):
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        html_relative_path = os.path.relpath(html_path, root_dir)
        result['html_path'] = html_relative_path

    # 检查 AI 结果
    # 新版：ai_analysis.html（HTML 格式）
    ai_html_path = os.path.join(folder_path, 'ai_analysis.html')
    if os.path.exists(ai_html_path):
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        ai_html_relative = os.path.relpath(ai_html_path, root_dir)
        result['ai_html_path'] = ai_html_relative
        result['has_ai_html'] = True

    # 旧版：ai_result.json（JSON 格式）
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


@history_bp.route('/api/history/batch/<batch_folder>/<file_output_dir>', methods=['GET'])
def get_batch_file_detail_api(batch_folder, file_output_dir):
    """获取批量记录中单个文件的详情。"""
    try:
        detail = get_batch_file_detail(batch_folder, file_output_dir)
        if detail is None:
            return jsonify({'success': False, 'error': 'Record not found'}), 404
        return jsonify({'success': True, 'data': detail})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500