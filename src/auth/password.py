"""
密码处理模块。
使用 bcrypt 进行密码加密和验证。
"""

import bcrypt


def hash_password(password: str) -> str:
    """
    使用 bcrypt 加密密码。

    Args:
        password: 原始密码

    Returns:
        加密后的密码哈希字符串
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    验证密码是否匹配哈希值。

    Args:
        password: 待验证的原始密码
        password_hash: 存储的密码哈希

    Returns:
        是否匹配
    """
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            password_hash.encode('utf-8')
        )
    except Exception:
        return False