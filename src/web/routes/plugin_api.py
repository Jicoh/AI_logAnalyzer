"""
插件 API 路由
处理插件列表获取和插件结果HTML展示
"""

import os
from flask import Blueprint, request, jsonify, send_from_directory

from src.utils.file_utils import get_project_root, get_data_dir, is_safe_path
from src.utils import get_logger
from plugins.manager import get_plugin_manager

logger = get_logger('plugin_api')

plugin_bp = Blueprint('plugin_api', __name__)


def get_plugin_manager_with_custom():
    """获取包含自定义插件目录的插件管理器。"""
    root_dir = get_project_root()
    custom_dir = os.path.join(root_dir, 'custom_plugins')
    return get_plugin_manager(custom_dirs=[custom_dir])


@plugin_bp.route('/api/analyze/plugins', methods=['GET'])
def get_plugins():
    """获取可用的分析插件。"""
    try:
        manager = get_plugin_manager_with_custom()
        plugins = manager.get_plugins_info()
        return jsonify({'success': True, 'data': plugins})
    except Exception as e:
        logger.error(f"获取插件列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@plugin_bp.route('/api/analyze/plugins/categories', methods=['GET'])
def get_plugins_categories():
    """获取按分类组织的插件列表。"""
    try:
        manager = get_plugin_manager_with_custom()
        categories = manager.get_plugins_categories()
        return jsonify({'success': True, 'data': categories})
    except Exception as e:
        logger.error(f"获取插件分类失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@plugin_bp.route('/api/plugin-result/html/<path:html_path>')
def get_plugin_result_html(html_path):
    """获取插件分析结果的HTML文件。"""
    root_dir = get_project_root()
    full_path = os.path.join(root_dir, html_path)

    # 安全验证：路径必须在data目录下
    data_dir = get_data_dir()
    if not is_safe_path(full_path, data_dir):
        logger.warning(f"非法路径访问尝试: {html_path}")
        return '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>访问被拒绝</title>
    <link rel="stylesheet" href="/static/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background: #f8f9fa;
            font-family: system-ui, -apple-system, sans-serif;
        }
    </style>
</head>
<body>
    <div style="text-align: center; padding: 40px;">
        <i class="bi bi-shield-exclamation" style="font-size: 64px; color: #dc3545;"></i>
        <p style="margin-top: 24px; color: #495057; font-size: 18px; font-weight: 500;">访问被拒绝</p>
        <p style="color: #6c757d; font-size: 14px; margin-top: 8px;">路径不在允许范围内</p>
    </div>
</body>
</html>''', 403

    if not os.path.exists(full_path):
        return '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>结果已清理</title>
    <link rel="stylesheet" href="/static/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background: #f8f9fa;
            font-family: system-ui, -apple-system, sans-serif;
        }
    </style>
</head>
<body>
    <div style="text-align: center; padding: 40px;">
        <i class="bi bi-trash3" style="font-size: 64px; color: #6c757d;"></i>
        <p style="margin-top: 24px; color: #495057; font-size: 18px; font-weight: 500;">分析结果已被清理</p>
        <p style="color: #6c757d; font-size: 14px; margin-top: 8px;">请重新上传日志文件进行分析</p>
    </div>
</body>
</html>''', 200

    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    return send_from_directory(directory, filename)