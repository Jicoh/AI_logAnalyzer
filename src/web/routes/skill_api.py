"""
Skill API路由。
提供Skill列表和详情查询接口。
"""

from flask import Blueprint, jsonify
from src.auth.decorators import login_required, admin_required
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
        skills = loader.list_all()

        # 返回简化信息（名称、描述、版本）
        result = []
        for skill in skills:
            result.append({
                'name': skill.get('name', ''),
                'description': skill.get('description', ''),
                'metadata': skill.get('metadata', {})
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取Skill列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@skill_bp.route('/api/skills/reload', methods=['POST'])
@login_required
def reload_skills():
    """刷新Skill列表。"""
    try:
        loader = get_skill_loader()
        loader.reload()
        return jsonify({'success': True, 'message': 'Skill列表已刷新'})
    except Exception as e:
        logger.error(f"刷新Skill列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500