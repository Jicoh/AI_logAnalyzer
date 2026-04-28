"""
认证 API 路由。
处理用户注册、登录、登出、修改密码等。
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from flask_login import login_user, logout_user, current_user, LoginManager
from src.models.user import User, db
from src.auth.password import hash_password, verify_password
from src.storage.quota import check_disk_space
from src.utils import get_logger

logger = get_logger('auth_api')

auth_bp = Blueprint('auth', __name__)

# Flask-Login 配置（在 web_app.py 中初始化）
login_manager = None


def init_login_manager(app):
    """初始化 Flask-Login 管理器。"""
    global login_manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    return login_manager


@auth_bp.route('/login', methods=['GET'])
def login():
    """登录页面。"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET'])
def register():
    """注册页面。"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    return render_template('register.html')


@auth_bp.route('/api/auth/login', methods=['POST'])
def do_login():
    """登录 API。"""
    try:
        data = request.get_json()
        employee_id = data.get('employee_id', '').strip()
        password = data.get('password', '')

        if not employee_id or not password:
            return jsonify({'success': False, 'error': '工号和密码不能为空'})

        user = User.query.filter_by(employee_id=employee_id).first()
        if not user:
            return jsonify({'success': False, 'error': '工号不存在'})

        if not user.is_active:
            return jsonify({'success': False, 'error': '账号已被禁用，请联系管理员'})

        if not verify_password(password, user.password_hash):
            return jsonify({'success': False, 'error': '密码错误'})

        login_user(user)
        logger.info(f"用户登录成功: {employee_id}")

        return jsonify({
            'success': True,
            'message': '登录成功',
            'user': {
                'employee_id': user.employee_id,
                'is_admin': user.is_admin
            }
        })
    except Exception as e:
        logger.error(f"登录失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})


@auth_bp.route('/api/auth/register', methods=['POST'])
def do_register():
    """注册 API。"""
    try:
        data = request.get_json()
        employee_id = data.get('employee_id', '').strip()
        password = data.get('password', '')

        if not employee_id or not password:
            return jsonify({'success': False, 'error': '工号和密码不能为空'})

        if len(employee_id) > 20:
            return jsonify({'success': False, 'error': '工号长度不能超过20个字符'})

        if len(password) < 6:
            return jsonify({'success': False, 'error': '密码长度不能少于6个字符'})

        # 检查工号是否已存在
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

        # 创建用户
        password_hash = hash_password(password)
        user = User(
            employee_id=employee_id,
            password_hash=password_hash
        )
        db.session.add(user)
        db.session.commit()

        logger.info(f"用户注册成功: {employee_id}")

        return jsonify({
            'success': True,
            'message': '注册成功'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"注册失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})


@auth_bp.route('/api/auth/logout', methods=['POST'])
def do_logout():
    """登出 API。"""
    try:
        logout_user()
        return jsonify({'success': True, 'message': '已退出登录'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@auth_bp.route('/api/auth/me', methods=['GET'])
def get_me():
    """获取当前用户信息。"""
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': '未登录'})

    return jsonify({
        'success': True,
        'data': {
            'employee_id': current_user.employee_id,
            'is_admin': current_user.is_admin,
            'created_at': current_user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'storage_quota': current_user.storage_quota
        }
    })


@auth_bp.route('/api/auth/change-password', methods=['POST'])
def change_password():
    """修改密码 API。"""
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': '未登录'})

    try:
        data = request.get_json()
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')

        if not old_password or not new_password:
            return jsonify({'success': False, 'error': '请填写完整信息'})

        if len(new_password) < 6:
            return jsonify({'success': False, 'error': '新密码长度不能少于6个字符'})

        # 验证旧密码
        if not verify_password(old_password, current_user.password_hash):
            return jsonify({'success': False, 'error': '旧密码错误'})

        # 更新密码
        current_user.password_hash = hash_password(new_password)
        db.session.commit()

        logger.info(f"用户修改密码: {current_user.employee_id}")

        return jsonify({'success': True, 'message': '密码修改成功'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"修改密码失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})