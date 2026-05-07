"""
认证装饰器。
"""

from functools import wraps
from flask import redirect, url_for, jsonify, request
from flask_login import current_user


def login_required(view_func):
    """
    登录检查装饰器。
    - API路由（/api/*）：返回JSON错误
    - 页面路由：重定向到登录页
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': '请先登录'}), 401
            return redirect(url_for('auth.login'))
        return view_func(*args, **kwargs)
    return wrapped


def admin_required(view_func):
    """
    管理员权限检查装饰器。
    非管理员返回 403 错误。
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': '请先登录'}), 401
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            return jsonify({'success': False, 'error': '需要管理员权限'}), 403
        return view_func(*args, **kwargs)
    return wrapped