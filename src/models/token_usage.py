"""
Token 使用记录模型。
"""

from datetime import datetime
from src.models.user import db


class TokenUsage(db.Model):
    """Token 使用记录模型。"""
    __tablename__ = 'token_usage'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tokens_used = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('token_usages', lazy='dynamic'))

    def __repr__(self):
        return f'<TokenUsage {self.id} by User {self.user_id}: {self.tokens_used}>'
