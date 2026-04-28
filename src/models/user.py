"""
用户模型。
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(db.Model, UserMixin):
    """用户模型。"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False)  # 工号
    password_hash = db.Column(db.String(128), nullable=False)  # 密码哈希
    is_admin = db.Column(db.Boolean, default=False)  # 管理员标识
    is_active = db.Column(db.Boolean, default=True)  # 账号是否激活
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # 注册时间
    storage_quota = db.Column(db.Integer, default=300 * 1024 * 1024)  # 配额 300MB

    def get_id(self):
        """Flask-Login 要求的方法，返回用户唯一标识。"""
        return str(self.id)

    def __repr__(self):
        return f'<User {self.employee_id}>'