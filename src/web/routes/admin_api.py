"""
管理员 API 路由。
处理用户管理、系统配置等功能。
"""

from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user
from src.models.user import User, db
from src.auth.password import hash_password, verify_password
from src.auth.decorators import admin_required
from src.config_manager.manager import ConfigManager
from src.settings_manager.manager import SettingsManager
from src.storage.quota import StorageQuota, format_size, get_dir_size, check_disk_space
from src.utils.file_utils import get_user_data_dir, get_data_dir
from src.utils import get_logger

logger = get_logger('admin_api')

admin_bp = Blueprint('admin_api', __name__)


@admin_bp.route('/api/admin/users', methods=['GET'])
@admin_required
def list_users():
    """获取所有用户列表。"""
    try:
        users = User.query.order_by(User.created_at.desc()).all()

        user_list = []
        for u in users:
            # 计算用户存储使用量
            try:
                user_dir = get_user_data_dir(u.employee_id)
                storage_used = get_dir_size(user_dir)
            except Exception:
                storage_used = 0

            user_list.append({
                'id': u.id,
                'employee_id': u.employee_id,
                'is_admin': u.is_admin,
                'is_active': u.is_active,
                'created_at': u.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'storage_quota': u.storage_quota,
                'storage_quota_formatted': format_size(u.storage_quota),
                'storage_used': storage_used,
                'storage_used_formatted': format_size(storage_used),
                'storage_percent': round(storage_used / u.storage_quota * 100, 1) if u.storage_quota > 0 else 0
            })

        return jsonify({'success': True, 'data': user_list})
    except Exception as e:
        logger.error(f"获取用户列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    """获取单个用户详情。"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404

        # 计算存储使用量
        try:
            user_dir = get_user_data_dir(user.employee_id)
            storage_used = get_dir_size(user_dir)
        except Exception:
            storage_used = 0

        return jsonify({
            'success': True,
            'data': {
                'id': user.id,
                'employee_id': user.employee_id,
                'is_admin': user.is_admin,
                'is_active': user.is_active,
                'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'storage_quota': user.storage_quota,
                'storage_quota_formatted': format_size(user.storage_quota),
                'storage_used': storage_used,
                'storage_used_formatted': format_size(storage_used)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>/quota', methods=['POST'])
@admin_required
def update_user_quota(user_id):
    """修改用户存储配额。"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404

        data = request.get_json()
        quota_mb = data.get('quota_mb')

        if not quota_mb or quota_mb < 10:
            return jsonify({'success': False, 'error': '配额不能小于10MB'})

        user.storage_quota = quota_mb * 1024 * 1024
        db.session.commit()

        logger.info(f"管理员 {current_user.employee_id} 修改用户 {user.employee_id} 配额为 {quota_mb}MB")

        return jsonify({
            'success': True,
            'message': f'配额已修改为 {quota_mb}MB'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>/disable', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    """启用/禁用用户。"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404

        if user.id == current_user.id:
            return jsonify({'success': False, 'error': '不能禁用自己'}), 400

        data = request.get_json()
        is_active = data.get('is_active', True)

        user.is_active = is_active
        db.session.commit()

        action = '启用' if is_active else '禁用'
        logger.info(f"管理员 {current_user.employee_id} {action}用户 {user.employee_id}")

        return jsonify({
            'success': True,
            'message': f'用户已{action}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(user_id):
    """重置用户密码。"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404

        data = request.get_json()
        new_password = data.get('new_password', '123456')  # 默认重置为123456

        if len(new_password) < 6:
            return jsonify({'success': False, 'error': '密码长度不能少于6个字符'})

        user.password_hash = hash_password(new_password)
        db.session.commit()

        logger.info(f"管理员 {current_user.employee_id} 重置用户 {user.employee_id} 密码")

        return jsonify({
            'success': True,
            'message': f'密码已重置为: {new_password}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/users/create', methods=['POST'])
@admin_required
def create_user():
    """创建新用户。"""
    try:
        data = request.get_json()
        employee_id = data.get('employee_id', '').strip()
        password = data.get('password', '123456')
        is_admin = data.get('is_admin', False)

        if not employee_id:
            return jsonify({'success': False, 'error': '工号不能为空'})

        if len(employee_id) > 20:
            return jsonify({'success': False, 'error': '工号长度不能超过20个字符'})

        existing = User.query.filter_by(employee_id=employee_id).first()
        if existing:
            return jsonify({'success': False, 'error': '工号已存在'})

        # 检查服务器存储空间
        space_ok, space_msg = check_disk_space(10)
        if not space_ok:
            return jsonify({
                'success': False,
                'error': f'{space_msg}，无法创建新用户，请联系管理员 w30038012'
            })

        user = User(
            employee_id=employee_id,
            password_hash=hash_password(password),
            is_admin=is_admin
        )
        db.session.add(user)
        db.session.commit()

        logger.info(f"管理员 {current_user.employee_id} 创建用户 {employee_id}")

        return jsonify({
            'success': True,
            'message': f'用户 {employee_id} 已创建，密码: {password}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/stats', methods=['GET'])
@admin_required
def get_stats():
    """获取全局统计信息。"""
    try:
        # 用户统计
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        admin_users = User.query.filter_by(is_admin=True).count()

        # 存储统计
        users_dir = get_data_dir('users')
        total_storage = get_dir_size(users_dir)

        # 全局缓存统计
        temp_dir = get_data_dir('temp')
        analysis_dir = get_data_dir('analysis_output')
        temp_size = get_dir_size(temp_dir)
        analysis_size = get_dir_size(analysis_dir)

        return jsonify({
            'success': True,
            'data': {
                'users': {
                    'total': total_users,
                    'active': active_users,
                    'admins': admin_users
                },
                'storage': {
                    'total_users_storage': total_storage,
                    'total_users_storage_formatted': format_size(total_storage),
                    'global_temp': temp_size,
                    'global_temp_formatted': format_size(temp_size),
                    'global_analysis': analysis_size,
                    'global_analysis_formatted': format_size(analysis_size)
                }
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/config', methods=['GET'])
@admin_required
def get_config():
    """获取系统配置。"""
    try:
        config_manager = ConfigManager()
        config = config_manager.get_all()
        # 添加 log_viewer 配置（从 settings.json 获取）
        settings_manager = SettingsManager()
        config['log_viewer'] = settings_manager.get('log_viewer', {'enabled': False, 'exe_path': ''})
        return jsonify({'success': True, 'data': config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/config', methods=['POST'])
@admin_required
def update_config():
    """更新系统配置。"""
    try:
        data = request.get_json()
        config_manager = ConfigManager()

        # 更新 API 设置
        if 'api' in data:
            api_config = data['api']
            if 'base_url' in api_config:
                config_manager.set('api.base_url', api_config['base_url'])
            if 'api_key' in api_config and api_config['api_key']:
                config_manager.set('api.api_key', api_config['api_key'])
            if 'model' in api_config:
                config_manager.set('api.model', api_config['model'])
            if 'temperature' in api_config:
                config_manager.set('api.temperature', float(api_config['temperature']))
            if 'max_tokens' in api_config:
                config_manager.set('api.max_tokens', int(api_config['max_tokens']))

        # 更新 Embedding 设置
        if 'embedding' in data:
            emb_config = data['embedding']
            if 'enabled' in emb_config:
                config_manager.set('embedding.enabled', emb_config['enabled'])
            if 'provider' in emb_config:
                config_manager.set('embedding.provider', emb_config['provider'])
            if 'base_url' in emb_config:
                config_manager.set('embedding.base_url', emb_config['base_url'])
            if 'api_key' in emb_config:
                config_manager.set('embedding.api_key', emb_config['api_key'])
            if 'model' in emb_config:
                config_manager.set('embedding.model', emb_config['model'])
            if 'dimension' in emb_config:
                config_manager.set('embedding.dimension', int(emb_config['dimension']))
            if 'batch_size' in emb_config:
                config_manager.set('embedding.batch_size', int(emb_config['batch_size']))

        # 更新检索设置
        if 'retrieval' in data:
            ret_config = data['retrieval']
            if 'mode' in ret_config:
                config_manager.set('retrieval.mode', ret_config['mode'])
            if 'bm25_weight' in ret_config:
                config_manager.set('retrieval.bm25_weight', float(ret_config['bm25_weight']))
            if 'vector_weight' in ret_config:
                config_manager.set('retrieval.vector_weight', float(ret_config['vector_weight']))
            if 'rrf_k' in ret_config:
                config_manager.set('retrieval.rrf_k', int(ret_config['rrf_k']))

        config_manager.save()

        # 更新 log_viewer 设置（保存到 settings.json）
        if 'log_viewer' in data:
            lv_config = data['log_viewer']
            settings_manager = SettingsManager()
            if 'enabled' in lv_config:
                settings_manager.set('log_viewer.enabled', lv_config['enabled'])
            if 'exe_path' in lv_config:
                settings_manager.set('log_viewer.exe_path', lv_config['exe_path'])
            settings_manager.save()

        logger.info(f"管理员 {current_user.employee_id} 更新系统配置")

        return jsonify({'success': True, 'message': '配置已更新'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ================= MCP Server 配置 API =================

@admin_bp.route('/api/admin/mcp/servers', methods=['GET'])
@admin_required
def get_mcp_servers():
    """获取MCP Server配置列表"""
    try:
        config_manager = ConfigManager()
        mcp_servers = config_manager.get('mcp_servers', {})

        # 构建返回数据，添加状态信息
        server_list = []
        for name, config in mcp_servers.items():
            server_list.append({
                'name': name,
                'transport': config.get('transport', 'stdio'),
                'enabled': config.get('enabled', False),
                'description': config.get('description', ''),
                'command': config.get('command', ''),
                'args': config.get('args', []),
                'url': config.get('url', ''),
                'timeout': config.get('timeout', 30)
            })

        return jsonify({'success': True, 'data': server_list})
    except Exception as e:
        logger.error(f"获取MCP Server配置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/mcp/servers', methods=['POST'])
@admin_required
def add_mcp_server():
    """新增MCP Server配置"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()

        if not name:
            return jsonify({'success': False, 'error': '名称不能为空'}), 400

        config_manager = ConfigManager()
        mcp_servers = config_manager.get('mcp_servers', {})

        if name in mcp_servers:
            return jsonify({'success': False, 'error': '名称已存在'}), 400

        transport = data.get('transport', 'stdio')
        if transport not in ['stdio', 'websocket']:
            return jsonify({'success': False, 'error': '不支持的transport类型'}), 400

        # 构建配置
        new_config = {
            'enabled': data.get('enabled', True),
            'transport': transport,
            'description': data.get('description', ''),
            'timeout': data.get('timeout', 30)
        }

        if transport == 'stdio':
            command = data.get('command', '').strip()
            if not command:
                return jsonify({'success': False, 'error': 'stdio类型必须填写command'}), 400
            new_config['command'] = command
            new_config['args'] = data.get('args', [])
        elif transport == 'websocket':
            new_config['url'] = data.get('url', '')

        mcp_servers[name] = new_config
        config_manager.set('mcp_servers', mcp_servers)
        config_manager.save()

        logger.info(f"管理员 {current_user.employee_id} 新增MCP Server: {name}")

        return jsonify({'success': True, 'message': f'MCP Server {name} 已添加'})
    except Exception as e:
        logger.error(f"新增MCP Server失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/mcp/servers/<name>', methods=['PUT'])
@admin_required
def update_mcp_server(name):
    """更新MCP Server配置"""
    try:
        config_manager = ConfigManager()
        mcp_servers = config_manager.get('mcp_servers', {})

        if name not in mcp_servers:
            return jsonify({'success': False, 'error': 'MCP Server不存在'}), 404

        data = request.get_json()
        existing = mcp_servers[name]

        # 更新配置
        if 'enabled' in data:
            existing['enabled'] = data['enabled']
        if 'description' in data:
            existing['description'] = data['description']
        if 'timeout' in data:
            existing['timeout'] = data['timeout']

        transport = existing.get('transport', 'stdio')
        if transport == 'stdio':
            if 'command' in data:
                existing['command'] = data['command']
            if 'args' in data:
                existing['args'] = data['args']
        elif transport == 'websocket':
            if 'url' in data:
                existing['url'] = data['url']

        mcp_servers[name] = existing
        config_manager.set('mcp_servers', mcp_servers)
        config_manager.save()

        logger.info(f"管理员 {current_user.employee_id} 更新MCP Server: {name}")

        return jsonify({'success': True, 'message': '配置已更新'})
    except Exception as e:
        logger.error(f"更新MCP Server失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/mcp/servers/<name>', methods=['DELETE'])
@admin_required
def delete_mcp_server(name):
    """删除MCP Server配置"""
    try:
        config_manager = ConfigManager()
        mcp_servers = config_manager.get('mcp_servers', {})

        if name not in mcp_servers:
            return jsonify({'success': False, 'error': 'MCP Server不存在'}), 404

        del mcp_servers[name]
        config_manager.set('mcp_servers', mcp_servers)
        config_manager.save()

        logger.info(f"管理员 {current_user.employee_id} 删除MCP Server: {name}")

        return jsonify({'success': True, 'message': f'MCP Server {name} 已删除'})
    except Exception as e:
        logger.error(f"删除MCP Server失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/admin/mcp/servers/<name>/test', methods=['POST'])
@admin_required
def test_mcp_server(name):
    """测试MCP Server连接"""
    try:
        config_manager = ConfigManager()
        mcp_servers = config_manager.get('mcp_servers', {})

        if name not in mcp_servers:
            return jsonify({'success': False, 'error': 'MCP Server不存在'}), 404

        server_config = mcp_servers[name]

        # 创建临时MCP客户端测试连接
        from src.ai_analyzer.mcp_client import MCPClient

        # 禁用自动连接，手动测试单个Server
        mcp_client = MCPClient(config_manager, auto_connect=False)
        success = mcp_client.connect_server(name, server_config)

        if success:
            tools = mcp_client.servers.get(name)
            tool_names = [t.name for t in tools.tools] if tools else []
            tool_count = len(tool_names)

            # 断开测试连接
            mcp_client.disconnect(name)

            return jsonify({
                'success': True,
                'data': {
                    'connected': True,
                    'tool_count': tool_count,
                    'tools': tool_names
                }
            })
        else:
            return jsonify({
                'success': True,
                'data': {
                    'connected': False,
                    'tool_count': 0,
                    'tools': [],
                    'error': '连接失败'
                }
            })
    except Exception as e:
        logger.error(f"测试MCP Server失败: {str(e)}")
        return jsonify({
            'success': True,
            'data': {
                'connected': False,
                'tool_count': 0,
                'tools': [],
                'error': str(e)
            }
        })


@admin_bp.route('/api/admin/mcp/tools', methods=['GET'])
@admin_required
def get_mcp_tools():
    """获取所有MCP工具列表（预览）"""
    try:
        from src.ai_analyzer.mcp_client import MCPClient

        config_manager = ConfigManager()
        mcp_client = MCPClient(config_manager)

        tools = []
        for tool in mcp_client.all_tools:
            tools.append({
                'name': tool.name,
                'description': tool.description,
                'server': mcp_client.tool_to_server.get(tool.name, 'unknown')
            })

        # 断开连接
        mcp_client.disconnect_all()

        return jsonify({'success': True, 'data': tools})
    except Exception as e:
        logger.error(f"获取MCP工具列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500