"""
意见反馈 API 路由。
"""

from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user
from src.models.feedback import Feedback
from src.models.user import db
from src.auth.decorators import login_required, admin_required
from src.utils import get_logger

logger = get_logger('feedback_api')

feedback_bp = Blueprint('feedback_api', __name__)


@feedback_bp.route('/api/feedback/submit', methods=['POST'])
@login_required
def submit_feedback():
    """提交意见反馈。"""
    try:
        data = request.get_json()
        content = data.get('content', '').strip()

        if not content:
            return jsonify({'success': False, 'error': '意见内容不能为空'}), 400

        if len(content) > 2000:
            return jsonify({'success': False, 'error': '意见内容不能超过2000字符'}), 400

        feedback = Feedback(
            user_id=current_user.id,
            content=content,
            status='pending'
        )
        db.session.add(feedback)
        db.session.commit()

        logger.info(f"用户 {current_user.employee_id} 提交意见反馈")

        return jsonify({
            'success': True,
            'message': '意见已提交',
            'data': {
                'id': feedback.id,
                'content': feedback.content,
                'status': feedback.status,
                'created_at': feedback.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"提交意见失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@feedback_bp.route('/api/feedback/my', methods=['GET'])
@login_required
def get_my_feedback():
    """获取当前用户的意见列表。"""
    try:
        feedbacks = Feedback.query.filter_by(user_id=current_user.id)\
            .order_by(Feedback.created_at.desc()).all()

        result = []
        for f in feedbacks:
            result.append({
                'id': f.id,
                'content': f.content,
                'status': f.status,
                'admin_reply': f.admin_reply,
                'created_at': f.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'replied_at': f.replied_at.strftime('%Y-%m-%d %H:%M:%S') if f.replied_at else None
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取意见列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@feedback_bp.route('/api/admin/feedback', methods=['GET'])
@admin_required
def list_feedbacks():
    """获取所有意见列表（管理员）。"""
    try:
        feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).all()

        result = []
        for f in feedbacks:
            result.append({
                'id': f.id,
                'user_id': f.user_id,
                'employee_id': f.user.employee_id,
                'content': f.content,
                'status': f.status,
                'admin_reply': f.admin_reply,
                'created_at': f.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'replied_at': f.replied_at.strftime('%Y-%m-%d %H:%M:%S') if f.replied_at else None
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取意见列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@feedback_bp.route('/api/admin/feedback/<int:feedback_id>/reply', methods=['POST'])
@admin_required
def reply_feedback(feedback_id):
    """回复意见（管理员）。"""
    try:
        feedback = Feedback.query.get(feedback_id)
        if not feedback:
            return jsonify({'success': False, 'error': '意见不存在'}), 404

        data = request.get_json()
        reply = data.get('reply', '').strip()

        if not reply:
            return jsonify({'success': False, 'error': '回复内容不能为空'}), 400

        feedback.admin_reply = reply
        feedback.status = 'replied'
        feedback.replied_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"管理员 {current_user.employee_id} 回复意见 {feedback_id}")

        return jsonify({
            'success': True,
            'message': '回复已提交',
            'data': {
                'id': feedback.id,
                'status': feedback.status,
                'replied_at': feedback.replied_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"回复意见失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@feedback_bp.route('/api/admin/feedback/stats', methods=['GET'])
@admin_required
def feedback_stats():
    """获取意见统计（管理员）。"""
    try:
        total = Feedback.query.count()
        pending = Feedback.query.filter_by(status='pending').count()
        replied = Feedback.query.filter_by(status='replied').count()

        return jsonify({
            'success': True,
            'data': {
                'total': total,
                'pending': pending,
                'replied': replied
            }
        })
    except Exception as e:
        logger.error(f"获取意见统计失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500