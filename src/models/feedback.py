"""
意见反馈模型。
"""

from datetime import datetime
from src.models.user import db


class Feedback(db.Model):
    """意见反馈模型。"""
    __tablename__ = 'feedbacks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    admin_reply = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    replied_at = db.Column(db.DateTime)

    # 关联用户
    user = db.relationship('User', backref=db.backref('feedbacks', lazy='dynamic'))

    def __repr__(self):
        return f'<Feedback {self.id} by User {self.user_id}>'