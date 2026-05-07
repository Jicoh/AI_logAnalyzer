"""
用户配置 API 路由
处理用户级别配置的读取和更新
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from src.user_config_manager.manager import UserConfigManager
from src.utils import get_logger

logger = get_logger('user_config_api')

user_config_bp = Blueprint('user_config_api', __name__)


def get_user_config_manager():
    """获取当前用户的配置管理器"""
    return UserConfigManager(current_user.employee_id)


@user_config_bp.route('/api/user/config', methods=['GET'])
@login_required
def get_user_config():
    """获取当前用户配置"""
    try:
        manager = get_user_config_manager()
        manager.reload()
        config = manager.get_all()
        return jsonify({'success': True, 'data': config})
    except Exception as e:
        logger.error(f"获取用户配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@user_config_bp.route('/api/user/config', methods=['POST'])
@login_required
def update_user_config():
    """更新当前用户配置"""
    try:
        data = request.get_json()
        manager = get_user_config_manager()

        if 'selected_plugins' in data:
            manager.set('selected_plugins', data['selected_plugins'])
        if 'selected_kb_id' in data:
            manager.set('selected_kb_id', data['selected_kb_id'])
        if 'selected_log_rules_id' in data:
            manager.set('selected_log_rules_id', data['selected_log_rules_id'])
        if 'default_kb_id' in data:
            manager.set('default_kb_id', data['default_kb_id'])
        if 'default_log_rules_id' in data:
            manager.set('default_log_rules_id', data['default_log_rules_id'])
        if 'enable_ai' in data:
            manager.set('enable_ai', data['enable_ai'])
        if 'ai_selection_mode' in data:
            manager.set('ai_selection_mode', data['ai_selection_mode'])
        if 'last_selected_category' in data:
            manager.set('last_selected_category', data['last_selected_category'])

        manager.save()

        return jsonify({'success': True, 'message': '用户配置已更新'})
    except Exception as e:
        logger.error(f"更新用户配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500