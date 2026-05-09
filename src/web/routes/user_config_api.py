"""
用户配置 API 路由
处理用户级别配置的读取和更新
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from src.user_config_manager.manager import UserConfigManager
from src.system_config_manager.manager import SystemConfigManager
from src.agent.skill_loader import get_skill_loader
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
        if 'selected_kb_ids' in data:
            manager.set('selected_kb_ids', data['selected_kb_ids'])
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
        if 'assistant_settings' in data:
            manager.set('assistant_settings', data['assistant_settings'])

        manager.save()

        return jsonify({'success': True, 'message': '用户配置已更新'})
    except Exception as e:
        logger.error(f"更新用户配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@user_config_bp.route('/api/user/mcp-servers', methods=['GET'])
@login_required
def get_user_mcp_servers():
    """获取所有MCP Server及用户启用状态"""
    try:
        settings_manager = SystemConfigManager()
        mcp_servers = settings_manager.get('mcp_servers', [])

        # 获取用户配置中启用的MCP列表
        manager = get_user_config_manager()
        assistant_settings = manager.get('assistant_settings', {})
        enabled_mcp = assistant_settings.get('enabled_mcp_servers', [])

        # 构建返回数据
        result = []
        for name, server_config in mcp_servers.items():
            result.append({
                'name': name,
                'description': server_config.get('description', ''),
                'transport': server_config.get('transport', 'stdio'),
                'enabled': server_config.get('enabled', True),
                'user_enabled': name in enabled_mcp
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取MCP Server列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@user_config_bp.route('/api/user/mcp-servers/toggle', methods=['POST'])
@login_required
def toggle_mcp_server():
    """启用/禁用指定MCP Server"""
    try:
        data = request.get_json()
        server_name = data.get('name', '')
        enabled = data.get('enabled', True)

        if not server_name:
            return jsonify({'success': False, 'error': 'MCP Server名称不能为空'}), 400

        manager = get_user_config_manager()
        assistant_settings = manager.get('assistant_settings', {})
        enabled_mcp = assistant_settings.get('enabled_mcp_servers', [])

        if enabled:
            if server_name not in enabled_mcp:
                enabled_mcp.append(server_name)
        else:
            if server_name in enabled_mcp:
                enabled_mcp.remove(server_name)

        assistant_settings['enabled_mcp_servers'] = enabled_mcp
        manager.set('assistant_settings', assistant_settings)
        manager.save()

        action = '启用' if enabled else '禁用'
        logger.info(f"用户 {current_user.employee_id} {action} MCP Server: {server_name}")

        return jsonify({'success': True, 'message': f'已{action} MCP Server: {server_name}'})
    except Exception as e:
        logger.error(f"切换MCP Server状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@user_config_bp.route('/api/user/mcp-servers/reload', methods=['POST'])
@login_required
def reload_mcp_servers():
    """重新加载MCP Server列表"""
    try:
        settings_manager = SystemConfigManager()
        settings_manager.reload()
        logger.info(f"用户 {current_user.employee_id} 重新加载MCP Server列表")
        return jsonify({'success': True, 'message': 'MCP Server列表已刷新'})
    except Exception as e:
        logger.error(f"重新加载MCP Server列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@user_config_bp.route('/api/user/skills', methods=['GET'])
@login_required
def get_user_skills():
    """获取所有Skill及用户启用状态"""
    try:
        loader = get_skill_loader()
        loader.scan()
        skills = loader.list_all()

        # 获取用户配置中启用的Skill列表
        manager = get_user_config_manager()
        assistant_settings = manager.get('assistant_settings', {})
        enabled_skills = assistant_settings.get('enabled_skills', [])

        # 构建返回数据
        result = []
        for skill in skills:
            result.append({
                'name': skill.get('name', ''),
                'description': skill.get('description', ''),
                'metadata': skill.get('metadata', {}),
                'user_enabled': skill.get('name') in enabled_skills
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取Skill列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@user_config_bp.route('/api/user/skills/toggle', methods=['POST'])
@login_required
def toggle_skill():
    """启用/禁用指定Skill"""
    try:
        data = request.get_json()
        skill_name = data.get('name', '')
        enabled = data.get('enabled', True)

        if not skill_name:
            return jsonify({'success': False, 'error': 'Skill名称不能为空'}), 400

        manager = get_user_config_manager()
        assistant_settings = manager.get('assistant_settings', {})
        enabled_skills = assistant_settings.get('enabled_skills', [])

        if enabled:
            if skill_name not in enabled_skills:
                enabled_skills.append(skill_name)
        else:
            if skill_name in enabled_skills:
                enabled_skills.remove(skill_name)

        assistant_settings['enabled_skills'] = enabled_skills
        manager.set('assistant_settings', assistant_settings)
        manager.save()

        action = '启用' if enabled else '禁用'
        logger.info(f"用户 {current_user.employee_id} {action} Skill: {skill_name}")

        return jsonify({'success': True, 'message': f'已{action} Skill: {skill_name}'})
    except Exception as e:
        logger.error(f"切换Skill状态失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500