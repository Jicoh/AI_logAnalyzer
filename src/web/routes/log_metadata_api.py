"""
Log metadata rules API routes.
"""

from flask import Blueprint, request, jsonify

from src.log_metadata.manager import LogMetadataManager

log_metadata_bp = Blueprint('log_metadata_api', __name__)

# Global instance
log_metadata_manager = None


def get_log_metadata_manager():
    """Get or create LogMetadataManager instance."""
    global log_metadata_manager
    if log_metadata_manager is None:
        log_metadata_manager = LogMetadataManager()
    return log_metadata_manager


# ==================== 规则集管理 ====================

@log_metadata_bp.route('/api/log-rules', methods=['GET'])
def list_rule_sets():
    """列出所有日志规则集"""
    try:
        manager = get_log_metadata_manager()
        rule_sets = manager.list_rule_sets()
        return jsonify({'success': True, 'data': rule_sets})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>', methods=['GET'])
def get_rule_set(rules_id):
    """获取规则集详情"""
    try:
        manager = get_log_metadata_manager()
        rule_set = manager.get_rule_set(rules_id)
        if rule_set is None:
            return jsonify({'success': False, 'error': '规则集不存在'}), 404
        return jsonify({'success': True, 'data': rule_set})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules', methods=['POST'])
def create_rule_set():
    """创建规则集"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return jsonify({'success': False, 'error': '名称不能为空'}), 400

        manager = get_log_metadata_manager()
        rules_id = manager.create_rule_set(name, description)

        return jsonify({
            'success': True,
            'data': {
                'rules_id': rules_id,
                'name': name,
                'description': description
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>', methods=['PUT'])
def update_rule_set(rules_id):
    """更新规则集信息"""
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description')

        manager = get_log_metadata_manager()
        success = manager.update_rule_set(rules_id, name, description)

        if not success:
            return jsonify({'success': False, 'error': '规则集不存在'}), 404

        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>', methods=['DELETE'])
def delete_rule_set(rules_id):
    """删除规则集"""
    try:
        manager = get_log_metadata_manager()
        success = manager.delete_rule_set(rules_id)

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
        rule_set = manager.get_rule_set(rules_id)

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
        rule = manager.get_rule_from_set(rules_id, rule_id)

        if rule is None:
            return jsonify({'success': False, 'error': '规则不存在'}), 404

        return jsonify({'success': True, 'data': rule})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>/rules', methods=['POST'])
def add_rule(rules_id):
    """向规则集添加规则"""
    try:
        data = request.get_json()
        file_path = data.get('file_path', '').strip()
        description = data.get('description', '').strip()
        keywords = data.get('keywords', [])
        suggested_plugins = data.get('suggested_plugins', [])

        if not file_path:
            return jsonify({'success': False, 'error': '文件路径不能为空'}), 400

        manager = get_log_metadata_manager()
        rule_id = manager.add_rule_to_set(rules_id, {
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
def update_rule(rules_id, rule_id):
    """更新规则"""
    try:
        data = request.get_json()
        manager = get_log_metadata_manager()

        success = manager.update_rule_in_set(rules_id, rule_id, data)

        if not success:
            return jsonify({'success': False, 'error': '规则不存在'}), 404

        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@log_metadata_bp.route('/api/log-rules/<rules_id>/rules/<rule_id>', methods=['DELETE'])
def delete_rule(rules_id, rule_id):
    """删除规则"""
    try:
        manager = get_log_metadata_manager()
        success = manager.remove_rule_from_set(rules_id, rule_id)

        if not success:
            return jsonify({'success': False, 'error': '规则不存在'}), 404

        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500