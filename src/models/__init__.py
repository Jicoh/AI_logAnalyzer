"""
数据模型模块。
"""

from src.models.user import User, db
from src.models.feedback import Feedback

__all__ = ['User', 'Feedback', 'db']