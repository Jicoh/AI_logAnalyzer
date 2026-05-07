"""
Web工具函数模块
提供统一的API响应格式
"""

from flask import jsonify


def api_error(message: str, code: str = 'ERROR', status: int = 400):
    """
    统一API错误响应

    Args:
        message: 错误消息
        code: 错误码（用于错误分类）
        status: HTTP状态码

    Returns:
        Flask响应对象
    """
    return jsonify({
        'success': False,
        'error': message,
        'code': code
    }), status


def api_success(data=None, message: str = None):
    """
    统一API成功响应

    Args:
        data: 返回数据
        message: 成功消息（可选）

    Returns:
        Flask响应对象
    """
    response = {'success': True}
    if data is not None:
        response['data'] = data
    if message:
        response['message'] = message
    return jsonify(response)


# 标准错误码定义
class ErrorCode:
    """错误码枚举"""
    # 认证相关
    AUTH_REQUIRED = 'AUTH_REQUIRED'
    AUTH_FAILED = 'AUTH_FAILED'
    PERMISSION_DENIED = 'PERMISSION_DENIED'

    # 资源相关
    NOT_FOUND = 'NOT_FOUND'
    ALREADY_EXISTS = 'ALREADY_EXISTS'

    # 输入相关
    INVALID_INPUT = 'INVALID_INPUT'
    MISSING_PARAM = 'MISSING_PARAM'

    # 文件相关
    FILE_NOT_FOUND = 'FILE_NOT_FOUND'
    FILE_ACCESS_DENIED = 'FILE_ACCESS_DENIED'
    FILE_TYPE_INVALID = 'FILE_TYPE_INVALID'

    # 操作相关
    OPERATION_FAILED = 'OPERATION_FAILED'
    QUOTA_EXCEEDED = 'QUOTA_EXCEEDED'

    # 系统相关
    INTERNAL_ERROR = 'INTERNAL_ERROR'
    SERVICE_UNAVAILABLE = 'SERVICE_UNAVAILABLE'