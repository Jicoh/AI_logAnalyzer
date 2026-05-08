"""
Log metadata rules API routes.
"""

from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required

from src.log_metadata.manager import LogMetadataManager
from src.auth.decorators import admin_required

log_metadata_bp = Blueprint('log_metadata_api', __name__)

# Global instance
log_metadata_manager = None


def get_log_metadata_manager():
    """Get or create LogMetadataManager instance."""
    global log_metadata_manager
    if log_metadata_manager is None:
        log_metadata_manager = LogMetadataManager()
    return log_metadata_manager


def get_current_user_id():
    """获取当前用户ID，未登录返回None"""
    if current_user.is_authenticated:
        return current_user.employee_id
    return None


# ==================== 规则集管理 ====================

@log_metadata_bp.route('/api/log-rules', methods=['GET'])
def list_rule_sets():
    """列出所有日志规则集（全局+用户私有）"""
    try:
        manager = get_log_metadata_manager()
        user_id = get_current_user_id()
        rule_sets = manager.list_all_rule_sets(user_id)
        return jsonify({'success': True, 'data': rule_sets})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>', methods=['GET'])
def get_rule_set(rules_id):
    """获取规则集详情"""
    try:
        manager = get_log_metadata_manager()
        user_id = get_current_user_id()
        rule_set = manager.get_rule_set_with_source(rules_id, user_id)
        if rule_set is None:
            return jsonify({'success': False, 'error': '规则集不存在'}), 404
        return jsonify({'success': True, 'data': rule_set})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules', methods=['POST'])
@login_required
def create_rule_set():
    """创建规则集（管理员创建全局规则，普通用户创建私有规则）"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return jsonify({'success': False, 'error': '名称不能为空'}), 400

        manager = get_log_metadata_manager()
        user_id = get_current_user_id()

        # 管理员创建全局规则，普通用户创建私有规则
        if current_user.is_admin:
            rules_id = manager.create_rule_set(name, description)
            return jsonify({
                'success': True,
                'data': {
                    'rules_id': rules_id,
                    'name': name,
                    'description': description,
                    'source': 'global'
                }
            })
        else:
            if not user_id:
                return jsonify({'success': False, 'error': '请先登录'}), 401
            rules_id = manager.create_user_rule_set(user_id, name, description)
            return jsonify({
                'success': True,
                'data': {
                    'rules_id': rules_id,
                    'name': name,
                    'description': description,
                    'source': 'private'
                }
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/import', methods=['POST'])
@admin_required
def import_rule_set():
    """通过 JSON 导入完整规则集（仅管理员，导入全局规则）"""
    try:
        data = request.get_json()
        manager = get_log_metadata_manager()
        rules_id = manager.import_rule_set(data)

        rule_set = manager.get_rule_set(rules_id)
        return jsonify({
            'success': True,
            'data': {
                'rules_id': rules_id,
                'name': rule_set.get('name'),
                'rule_count': len(rule_set.get('rules', [])),
                'source': 'global'
            }
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>', methods=['PUT'])
@login_required
def update_rule_set(rules_id):
    """更新规则集信息（只能更新自己创建的规则）"""
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description')

        manager = get_log_metadata_manager()
        user_id = get_current_user_id()

        # 检查规则集来源
        if manager.is_global_rule_set(rules_id):
            # 全局规则仅管理员可修改
            if not current_user.is_admin:
                return jsonify({'success': False, 'error': '需要管理员权限'}), 403
            success = manager.update_rule_set(rules_id, name, description)
        else:
            # 私有规则只能由创建者修改
            if not user_id:
                return jsonify({'success': False, 'error': '请先登录'}), 401
            if not manager.is_user_rule_set(user_id, rules_id):
                return jsonify({'success': False, 'error': '无权修改此规则集'}), 403
            # 更新用户私有规则集
            user_config = manager.load_user_rules_config(user_id)
            if rules_id in user_config.get('rule_sets', {}):
                if name is not None:
                    user_config['rule_sets'][rules_id]['name'] = name
                if description is not None:
                    user_config['rule_sets'][rules_id]['description'] = description
                manager.save_user_rules_config(user_id, user_config)
                success = True
            else:
                success = False

        if not success:
            return jsonify({'success': False, 'error': '规则集不存在'}), 404

        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>', methods=['DELETE'])
@login_required
def delete_rule_set(rules_id):
    """删除规则集（只能删除自己创建的规则）"""
    try:
        manager = get_log_metadata_manager()
        user_id = get_current_user_id()

        # 检查规则集来源
        if manager.is_global_rule_set(rules_id):
            # 全局规则仅管理员可删除
            if not current_user.is_admin:
                return jsonify({'success': False, 'error': '需要管理员权限'}), 403
            success = manager.delete_rule_set(rules_id)
        else:
            # 私有规则只能由创建者删除
            if not user_id:
                return jsonify({'success': False, 'error': '请先登录'}), 401
            success = manager.delete_user_rule_set(user_id, rules_id)

        if not success:
            return jsonify({'success': False, 'error': '规则集不存在'}), 404

        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 规则管理 ====================

@log_metadata_bp.route('/api/log-rules/<rules_id>/rules', methods=['GET'])
def list_rules(rules_id):
    """获取规则集中的所有规则"""
    try:
        manager = get_log_metadata_manager()
        user_id = get_current_user_id()
        rule_set = manager.get_rule_set_with_source(rules_id, user_id)

        if rule_set is None:
            return jsonify({'success': False, 'error': '规则集不存在'}), 404

        return jsonify({'success': True, 'data': rule_set.get('rules', [])})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>/rules/<rule_id>', methods=['GET'])
def get_rule(rules_id, rule_id):
    """获取单个规则详情"""
    try:
        manager = get_log_metadata_manager()
        user_id = get_current_user_id()
        rule_set = manager.get_rule_set_with_source(rules_id, user_id)

        if rule_set is None:
            return jsonify({'success': False, 'error': '规则集不存在'}), 404

        # 在规则集中查找规则
        for rule in rule_set.get('rules', []):
            if rule.get('rule_id') == rule_id:
                return jsonify({'success': True, 'data': rule})

        return jsonify({'success': False, 'error': '规则不存在'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>/rules', methods=['POST'])
@login_required
def add_rule(rules_id):
    """向规则集添加规则（只能向自己创建的规则集添加）"""
    try:
        data = request.get_json()
        file_path = data.get('file_path', '').strip()
        description = data.get('description', '').strip()
        keywords = data.get('keywords', [])
        suggested_plugins = data.get('suggested_plugins', [])

        if not file_path:
            return jsonify({'success': False, 'error': '文件路径不能为空'}), 400

        manager = get_log_metadata_manager()
        user_id = get_current_user_id()

        # 检查规则集来源
        if manager.is_global_rule_set(rules_id):
            # 全局规则仅管理员可添加
            if not current_user.is_admin:
                return jsonify({'success': False, 'error': '需要管理员权限'}), 403
            rule_id = manager.add_rule_to_set(rules_id, {
                'file_path': file_path,
                'description': description,
                'keywords': keywords,
                'suggested_plugins': suggested_plugins
            })
        else:
            # 私有规则只能由创建者添加
            if not user_id:
                return jsonify({'success': False, 'error': '请先登录'}), 401
            rule_id = manager.add_rule_to_user_set(user_id, rules_id, {
                'file_path': file_path,
                'description': description,
                'keywords': keywords,
                'suggested_plugins': suggested_plugins
            })

        if rule_id is None:
            return jsonify({'success': False, 'error': '规则集不存在'}), 404

        return jsonify({
            'success': True,
            'data': {
                'rule_id': rule_id,
                'file_path': file_path
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>/rules/<rule_id>', methods=['PUT'])
@login_required
def update_rule(rules_id, rule_id):
    """更新规则（只能修改自己创建的规则集中的规则）"""
    try:
        data = request.get_json()
        manager = get_log_metadata_manager()
        user_id = get_current_user_id()

        # 检查规则集来源
        if manager.is_global_rule_set(rules_id):
            # 全局规则仅管理员可修改
            if not current_user.is_admin:
                return jsonify({'success': False, 'error': '需要管理员权限'}), 403
            success = manager.update_rule_in_set(rules_id, rule_id, data)
        else:
            # 私有规则只能由创建者修改
            if not user_id:
                return jsonify({'success': False, 'error': '请先登录'}), 401
            success = manager.update_rule_in_user_set(user_id, rules_id, rule_id, data)

        if not success:
            return jsonify({'success': False, 'error': '规则不存在'}), 404

        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>/rules/<rule_id>', methods=['DELETE'])
@login_required
def delete_rule(rules_id, rule_id):
    """删除规则（只能删除自己创建的规则集中的规则）"""
    try:
        manager = get_log_metadata_manager()
        user_id = get_current_user_id()

        # 检查规则集来源
        if manager.is_global_rule_set(rules_id):
            # 全局规则仅管理员可删除
            if not current_user.is_admin:
                return jsonify({'success': False, 'error': '需要管理员权限'}), 403
            success = manager.remove_rule_from_set(rules_id, rule_id)
        else:
            # 私有规则只能由创建者删除
            if not user_id:
                return jsonify({'success': False, 'error': '请先登录'}), 401
            success = manager.remove_rule_from_user_set(user_id, rules_id, rule_id)

        if not success:
            return jsonify({'success': False, 'error': '规则不存在'}), 404

        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500