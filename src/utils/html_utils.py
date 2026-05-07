"""
HTML 安全工具函数
防止 XSS 攻击
"""

import html


def escape_html(text: str) -> str:
    """
    安全转义HTML内容，防止XSS攻击

    Args:
        text: 需要转义的文本

    Returns:
        str: 转义后的安全文本
    """
    if text is None:
        return ''
    return html.escape(str(text))


def escape_dict_values(d: dict, keys: list = None) -> dict:
    """
    转义字典中指定键的值

    Args:
        d: 需要处理的字典
        keys: 需要转义的键列表，如果为None则转义所有字符串值

    Returns:
        dict: 值已转义的字典
    """
    result = {}
    for k, v in d.items():
        if keys is None or k in keys:
            result[k] = escape_html(v)
        else:
            result[k] = v
    return result