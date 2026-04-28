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
from src.storage.quota import StorageQuota, format_size, get_dir_size
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

        logger.info(f"管理员 {current_user.employee_id} 更新系统配置")

        return jsonify({'success': True, 'message': '配置已更新'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500