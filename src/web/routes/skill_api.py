"""
Skill API路由。
提供Skill列表和详情查询接口。
"""

from flask import Blueprint, jsonify
from src.auth.decorators import login_required
from src.ai_analyzer.skill_loader import get_skill_loader
from src.utils import get_logger

logger = get_logger('skill_api')

skill_bp = Blueprint('skill_api', __name__)


@skill_bp.route('/api/skills', methods=['GET'])
@login_required
def list_skills():
    """获取所有Skill列表。"""
    try:
        loader = get_skill_loader()
        # 每次请求都重新扫描，确保数据最新
        loader.reload()
        skills = loader.list_all()

        # 返回简化信息（不含content）
        result = []
        for skill in skills:
            result.append({
                'name': skill.get('name', ''),
                'description': skill.get('description', ''),
                'allowed_tools': skill.get('allowed_tools', []),
                'metadata': skill.get('metadata', {}),
                'path': skill.get('path', '')
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取Skill列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@skill_bp.route('/api/skills/<name>', methods=['GET'])
@login_required
def get_skill(name):
    """获取单个Skill详情。"""
    try:
        loader = get_skill_loader()
        skill = loader.get(name)

        if not skill:
            return jsonify({'success': False, 'error': f'Skill不存在: {name}'}), 404

        return jsonify({'success': True, 'data': skill.to_dict()})
    except Exception as e:
        logger.error(f"获取Skill详情失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500