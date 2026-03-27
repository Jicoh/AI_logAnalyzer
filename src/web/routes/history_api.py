"""
History API routes for viewing past analysis results.
"""

import os
import json
from datetime import datetime
from flask import Blueprint, jsonify

history_bp = Blueprint('history_api', __name__)


def get_plugin_output_dir():
    """Get the plugin output directory path."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(root_dir, 'data', 'plugin_output')


def get_ai_output_dir():
    """Get the AI output directory path."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(root_dir, 'data', 'ai_output')


def parse_timestamp_folder(folder_name):
    """Parse timestamp from folder name like '20260321_200213'."""
    try:
        dt = datetime.strptime(folder_name, '%Y%m%d_%H%M%S')
        return dt
    except ValueError:
        return None


def get_history_list():
    """Get list of all analysis history records."""
    plugin_output_dir = get_plugin_output_dir()
    ai_output_dir = get_ai_output_dir()

    history_records = []

    if not os.path.exists(plugin_output_dir):
        return history_records

    # List all timestamp directories
    for folder_name in sorted(os.listdir(plugin_output_dir), reverse=True):
        folder_path = os.path.join(plugin_output_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue

        dt = parse_timestamp_folder(folder_name)
        if not dt:
            continue

        # Read plugin result
        plugin_result_path = os.path.join(folder_path, 'plugin_result.json')
        if not os.path.exists(plugin_result_path):
            continue

        try:
            with open(plugin_result_path, 'r', encoding='utf-8') as f:
                plugin_result = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        # Calculate totals from plugins
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
            # Old format compatibility
            total_errors = plugin_result.get('error_count', 0)
            total_warnings = plugin_result.get('warning_count', 0)
            plugin_count = 1

        # Check for AI result
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
    """Get detail of a specific history record."""
    plugin_output_dir = get_plugin_output_dir()
    folder_path = os.path.join(plugin_output_dir, timestamp)

    if not os.path.exists(folder_path):
        return None

    dt = parse_timestamp_folder(timestamp)
    if not dt:
        return None

    # Read plugin result
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

    # Read AI result if exists
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
    """Get list of all history records."""
    try:
        records = get_history_list()
        return jsonify({'success': True, 'data': records})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@history_bp.route('/api/history/<timestamp>', methods=['GET'])
def get_history(timestamp):
    """Get detail of a specific history record."""
    try:
        detail = get_history_detail(timestamp)
        if detail is None:
            return jsonify({'success': False, 'error': 'Record not found'}), 404
        return jsonify({'success': True, 'data': detail})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500