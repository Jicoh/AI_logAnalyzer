"""
认证装饰器。
"""

from functools import wraps
from flask import redirect, url_for, session, jsonify
from flask_login import current_user


def login_required(view_func):
    """
    登录检查装饰器。
    未登录用户重定向到登录页。
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
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
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            return jsonify({'success': False, 'error': '需要管理员权限'}), 403
        return view_func(*args, **kwargs)
    return wrapped