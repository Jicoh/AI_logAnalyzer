"""
健壮的JSON解析工具
支持多种AI返回格式：纯JSON、markdown代码块、带说明文本、控制字符、中文标点等
"""

import json
import re
import logging

logger = logging.getLogger('json_parser')


def parse_ai_json_response(response_text: str, required_fields: list = None) -> tuple:
    """
    解析AI返回的JSON响应

    Args:
        response_text: AI返回的文本
        required_fields: 必需字段列表（可选）

    Returns:
        tuple: (解析结果dict或None, 错误信息str或None)
    """
    if not response_text or not response_text.strip():
        return None, "AI响应为空"

    text = response_text.strip()
    errors = []

    # 移除思考标签
    cleaned_text = remove_think_tags(text)
    if cleaned_text != text:
        logger.debug(f"移除思考标签后长度: {len(text)} -> {len(cleaned_text)}")

    # 策略1：尝试直接解析（AI直接返回JSON）
    try:
        result = json.loads(cleaned_text)
        if validate_result(result, required_fields, errors):
            logger.info("JSON直接解析成功")
            return result, None
        else:
            errors.append(f"直接解析成功但验证失败: {errors[-1] if errors else '未知原因'}")
    except json.JSONDecodeError as e:
        error_context = get_error_context(cleaned_text, e.pos)
        errors.append(f"直接解析失败: {str(e)} (位置: {e.pos}, 行: {e.lineno})\n{error_context}")
        logger.debug(f"直接解析失败: {e}")

    # 策略1.5：尝试修复中文标点后解析
    fixed_text = fix_chinese_punctuation(cleaned_text)
    if fixed_text != cleaned_text:
        logger.debug(f"修复中文标点: 原长度{len(cleaned_text)} -> {len(fixed_text)}")
        try:
            result = json.loads(fixed_text)
            if validate_result(result, required_fields, errors):
                logger.info("修复中文标点后解析成功")
                return result, None
        except json.JSONDecodeError as e:
            errors.append(f"修复中文标点后仍失败: {str(e)}")

    # 策略2：尝试提取markdown代码块
    result, code_block_error = try_code_block(cleaned_text, required_fields)
    if result:
        logger.info("从代码块提取JSON成功")
        return result, None
    elif code_block_error:
        errors.append(code_block_error)

    # 策略3：从文本中提取JSON对象（处理JSON前有说明文本的情况）
    result, extract_error = try_extract_json_object(cleaned_text, required_fields)
    if result:
        logger.info("从文本提取JSON对象成功")
        return result, None
    elif extract_error:
        errors.append(extract_error)

    # 汇总所有错误信息
    error_summary = "\n".join(errors)
    preview = cleaned_text[:300] if len(cleaned_text) > 300 else cleaned_text
    final_error = f"JSON解析失败，尝试了所有策略:\n{error_summary}\n\n响应内容预览:\n{preview}"

    logger.error(final_error)
    return None, final_error


def fix_chinese_punctuation(text: str) -> str:
    """修复JSON中的中文标点符号"""
    # 中文逗号 -> 英文逗号（只替换结构位置的逗号，不替换字符串内的）
    # 中文冒号 -> 英文冒号（键名分隔符）
    # 中文引号 -> 英文引号（键名和字符串的边界）
    replacements = [
        ('，', ','),  # 中文逗号
        ('：', ':'),  # 中文冒号
        ('"', '"'),   # 中文左引号
        ('"', '"'),   # 中文右引号
        ('【', '['),  # 中文左方括号
        ('】', ']'),  # 中文右方括号
    ]
    for chinese, english in replacements:
        text = text.replace(chinese, english)
    return text


def remove_think_tags(text: str) -> str:
    """移除思考标签"""
    patterns = [
        r'_Tisijin[\s\S]*?liusijin',
        r'liusijin[\s\S]*?liusijin',
    ]
    for pattern in patterns:
        text = re.sub(pattern, '', text)
    return text.strip()


def validate_result(result: dict, required_fields: list, errors: list = None) -> bool:
    """验证结果是否包含必需字段"""
    if not isinstance(result, dict):
        msg = f"结果不是字典类型: {type(result)}"
        if errors:
            errors.append(msg)
        logger.warning(msg)
        return False
    if required_fields:
        missing = [f for f in required_fields if f not in result]
        if missing:
            msg = f"缺少必需字段: {missing}"
            if errors:
                errors.append(msg)
            logger.warning(msg)
            return False
    return True


def try_code_block(text: str, required_fields: list) -> tuple:
    """尝试从markdown代码块提取JSON"""
    patterns = [
        (r'```json\s*\n?([\s\S]*?)\n?```', '```json代码块'),
        (r'```\s*\n?([\s\S]*?)\n?```', '普通代码块'),
    ]

    for pattern, name in patterns:
        match = re.search(pattern, text)
        if match:
            json_text = match.group(1).strip()
            try:
                result = json.loads(json_text)
                if validate_result(result, required_fields):
                    return result, None
            except json.JSONDecodeError as e:
                # 尝试修复尾部逗号
                result = try_fix_trailing_commas(json_text, required_fields)
                if result:
                    return result, None
                error_context = get_error_context(json_text, e.pos)
                return None, f"{name}解析失败: {str(e)}\n{error_context}\n(内容长度: {len(json_text)})"

    return None, "未找到markdown代码块"


def get_error_context(text: str, error_pos: int, context_range: int = 50) -> str:
    """获取错误位置附近的上下文"""
    if error_pos is None or error_pos < 0:
        return ""

    start = max(0, error_pos - context_range)
    end = min(len(text), error_pos + context_range)

    before = text[start:error_pos]
    after = text[error_pos:end]

    # 标记错误位置
    return f"错误位置附近内容:\n...{before}>>>{after}...\n(箭头>>>标记错误起始位置，字符索引: {error_pos})"


def try_extract_json_object(text: str, required_fields: list) -> tuple:
    """从文本中提取JSON对象（处理JSON前有说明文本）"""
    start_idx = text.find('{')
    if start_idx < 0:
        return None, "未找到JSON起始符'{'"

    end_idx = find_json_end(text, start_idx)
    if end_idx <= start_idx:
        return None, "未找到匹配的JSON结束符'}'，括号匹配失败"

    json_str = text[start_idx:end_idx + 1]

    try:
        result = json.loads(json_str)
        if validate_result(result, required_fields):
            return result, None
    except json.JSONDecodeError as e:
        # 尝试修复尾部逗号和中文标点
        result = try_fix_trailing_commas(json_str, required_fields)
        if result:
            return result, None

        # 显示错误位置附近的内容
        error_context = get_error_context(json_str, e.pos)
        return None, f"提取的JSON解析失败: {str(e)}\n{error_context}\n(提取长度: {len(json_str)}, 原文位置: {start_idx}-{end_idx})"

    return None, "提取JSON对象失败"


def find_json_end(text: str, start_idx: int) -> int:
    """使用括号匹配找到JSON对象的结束位置"""
    brace_count = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(text[start_idx:], start_idx):
        if escape_next:
            escape_next = False
            continue
        if char == '\\' and in_string:
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                return i

    logger.debug(f"括号匹配失败，最终brace_count={brace_count}")
    return -1


def try_fix_trailing_commas(json_str: str, required_fields: list) -> dict:
    """尝试修复尾部逗号和中文标点问题"""
    fixed = json_str
    # 修复尾部逗号
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*]', ']', fixed)
    # 修复中文标点
    fixed = fix_chinese_punctuation(fixed)

    if fixed != json_str:
        logger.debug(f"修复后长度: {len(json_str)} -> {len(fixed)}")
    try:
        result = json.loads(fixed)
        if validate_result(result, required_fields):
            logger.info("修复后解析成功")
            return result
    except json.JSONDecodeError as e:
        logger.debug(f"修复后仍失败: {e}")
        return None