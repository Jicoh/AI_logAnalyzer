"""
插件选择 API 路由
处理插件选择状态的读取和更新
"""

from flask import Blueprint, request, jsonify

from src.plugin_selection.manager import PluginSelectionManager
from src.utils import get_logger

logger = get_logger('plugin_selection_api')

plugin_selection_bp = Blueprint('plugin_selection_api', __name__)

# 全局实例
plugin_selection_manager = None


def get_plugin_selection_manager():
    """获取或创建 PluginSelectionManager 实例。"""
    global plugin_selection_manager
    if plugin_selection_manager is None:
        plugin_selection_manager = PluginSelectionManager()
    return plugin_selection_manager


@plugin_selection_bp.route('/api/plugin-selection', methods=['GET'])
def get_plugin_selection():
    """获取插件选择和 AI 设置。"""
    try:
        manager = get_plugin_selection_manager()
        manager.reload()
        config = manager.get_all()
        return jsonify({'success': True, 'data': config})
    except Exception as e:
        logger.error(f"获取插件选择状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@plugin_selection_bp.route('/api/plugin-selection', methods=['POST'])
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
        if 'last_selected_category' in data:
            manager.set('last_selected_category', data['last_selected_category'])

        manager.save()

        return jsonify({'success': True, 'message': 'Plugin selection updated'})
    except Exception as e:
        logger.error(f"更新插件选择状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500