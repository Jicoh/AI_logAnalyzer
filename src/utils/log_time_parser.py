"""
日志时间解析模块
自动检测日志时间格式，支持多种常见格式的时间戳提取和解析
"""

import os
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict
from src.utils import get_logger

logger = get_logger('log_time_parser')

# 警告打印计数器（避免刷屏）
_warning_print_count = 0
MAX_WARNING_PRINTS = 5  # 最多打印5次警告


# 时间格式定义：正则表达式 + strftime格式 + 描述
TIME_FORMATS = [
    # ISO格式（空格分隔）
    {
        'regex': r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
        'format': '%Y-%m-%d %H:%M:%S',
        'description': 'ISO格式空格 (2026-04-14 09:00:30)',
        'has_year': True
    },
    # ISO格式（T分隔）
    {
        'regex': r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
        'format': '%Y-%m-%dT%H:%M:%S',
        'description': 'ISO格式T分隔 (2026-04-14T09:00:30)',
        'has_year': True
    },
    # ISO带毫秒（空格分隔）
    {
        'regex': r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)',
        'format': '%Y-%m-%d %H:%M:%S',
        'description': 'ISO格式带毫秒 (2026-04-14 09:00:30.123)',
        'has_year': True,
        'strip_ms': True
    },
    # ISO带毫秒（T分隔）
    {
        'regex': r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)',
        'format': '%Y-%m-%dT%H:%M:%S',
        'description': 'ISO格式T分隔带毫秒 (2026-04-14T09:00:30.123)',
        'has_year': True,
        'strip_ms': True
    },
    # 斜杠格式
    {
        'regex': r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})',
        'format': '%Y/%m/%d %H:%M:%S',
        'description': '斜杠格式 (2026/04/14 09:00:30)',
        'has_year': True
    },
    # 英文月份格式
    {
        'regex': r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}',
        'format': '%b %d %H:%M:%S',
        'description': '英文月份格式 (Apr 14 09:00:30)',
        'has_year': False
    },
    # 紧凑格式
    {
        'regex': r'(\d{14})',
        'format': '%Y%m%d%H%M%S',
        'description': '紧凑格式 (20260414090030)',
        'has_year': True
    },
    # 短格式（月-日 时间）
    {
        'regex': r'(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
        'format': '%m-%d %H:%M:%S',
        'description': '短格式 (04-14 09:00:30)',
        'has_year': False
    },
    # 方括号ISO格式
    {
        'regex': r'\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\]',
        'format': '%Y-%m-%dT%H:%M:%S',
        'description': '方括号ISO格式 [2026-04-14T09:00:30]',
        'has_year': True
    },
    # 方括号时间格式
    {
        'regex': r'\[(\d{2}:\d{2}:\d{2})\]',
        'format': '%H:%M:%S',
        'description': '方括号时间格式 [09:00:30]',
        'has_year': False
    },
    # 仅时间格式（放在最后，优先级最低）
    {
        'regex': r'(\d{2}:\d{2}:\d{2})',
        'format': '%H:%M:%S',
        'description': '仅时间格式 (09:00:30)',
        'has_year': False,
        'low_priority': True
    }
]


def detect_time_format(file_path: str, sample_lines: int = 100) -> Dict:
    """
    检测日志文件的时间格式

    Args:
        file_path: 日志文件路径
        sample_lines: 采样行数

    Returns:
        dict: 包含 format, description, has_year, regex 等信息
        如果检测到多种格式，返回主要格式和所有检测到的格式列表
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = []
            for i, line in enumerate(f):
                if i >= sample_lines:
                    break
                lines.append(line.strip())
    except Exception as e:
        logger.warning(f"读取文件失败: {e}")
        return {'format': None, 'description': '未知格式', 'has_year': False}

    if not lines:
        return {'format': None, 'description': '空文件', 'has_year': False}

    # 统计每种格式的匹配次数
    format_counts = {}

    for line in lines:
        for fmt_def in TIME_FORMATS:
            # 低优先级格式跳过，除非其他格式都不匹配
            if fmt_def.get('low_priority') and format_counts:
                continue

            match = re.search(fmt_def['regex'], line)
            if match:
                key = fmt_def['format']
                if key not in format_counts:
                    format_counts[key] = {
                        'count': 0,
                        'definition': fmt_def
                    }
                format_counts[key]['count'] += 1

    if not format_counts:
        return {'format': None, 'description': '未检测到时间格式', 'has_year': False}

    # 选择匹配次数最多的格式作为主要格式
    best_format = max(format_counts.items(), key=lambda x: x[1]['count'])
    result = best_format[1]['definition'].copy()
    result['match_count'] = best_format[1]['count']
    result['total_lines'] = len(lines)

    # 如果检测到多种格式，记录所有格式
    if len(format_counts) > 1:
        all_formats = []
        for fmt_key, fmt_data in sorted(format_counts.items(), key=lambda x: -x[1]['count']):
            fmt_info = fmt_data['definition'].copy()
            fmt_info['count'] = fmt_data['count']
            all_formats.append(fmt_info)
        result['all_formats'] = all_formats
        # 更新描述，提示有多种格式
        result['description'] = f"{result['description']} (检测到 {len(format_counts)} 种格式)"

    return result


def parse_line_time(line: str, format_info: Dict, reference_year: int = None) -> Optional[datetime]:
    """
    解析单行日志的时间戳

    Args:
        line: 日志行内容
        format_info: 格式信息（包含 regex, format 等）
        reference_year: 参考年份（用于无年份格式）

    Returns:
        datetime: 解析后的时间，如果解析失败返回 None
    """
    if not format_info:
        return None

    # 获取所有可尝试的格式（主要格式 + 其他格式）
    formats_to_try = []
    if format_info.get('regex'):
        formats_to_try.append(format_info)
    # 如果有多种格式，依次尝试
    if format_info.get('all_formats'):
        for fmt in format_info['all_formats']:
            if fmt.get('regex') and fmt not in formats_to_try:
                formats_to_try.append(fmt)

    time_str = None  # 初始化，避免 regex 都不匹配时报错

    for fmt_info in formats_to_try:
        match = re.search(fmt_info['regex'], line)
        if not match:
            continue

        time_str = match.group(1)

        # 处理毫秒（去掉）
        if fmt_info.get('strip_ms'):
            time_str = time_str.split('.')[0]

        try:
            dt = datetime.strptime(time_str, fmt_info['format'])

            # 对于无年份格式，补充年份
            if not fmt_info.get('has_year') and reference_year:
                dt = dt.replace(year=reference_year)

            return dt
        except ValueError as e:
            logger.debug(f"时间解析尝试失败: '{time_str}' - {e}")
            continue

    # 所有格式都失败时打印 warning，最多打印5次避免刷屏
    global _warning_print_count
    if time_str and _warning_print_count < MAX_WARNING_PRINTS:
        _warning_print_count += 1
        logger.warning(f"日志时间格式不支持: '{time_str}'，请检查 TIME_FORMATS 配置")

    return None


def get_file_time_range(file_path: str, sample_lines: int = 1000) -> Tuple[Optional[datetime], Optional[datetime], Dict]:
    """
    获取日志文件的时间范围

    Args:
        file_path: 日志文件路径
        sample_lines: 采样行数（用于检测格式）

    Returns:
        tuple: (min_time, max_time, format_info)
    """
    format_info = detect_time_format(file_path, sample_lines)

    if not format_info.get('format'):
        return None, None, format_info

    # 获取参考年份
    reference_year = datetime.now().year

    min_time = None
    max_time = None

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                dt = parse_line_time(line, format_info, reference_year)
                if dt:
                    if min_time is None or dt < min_time:
                        min_time = dt
                    if max_time is None or dt > max_time:
                        max_time = dt
    except Exception as e:
        logger.warning(f"读取文件失败: {e}")

    return min_time, max_time, format_info


def get_line_severity(line: str) -> str:
    """
    判断日志行的严重程度

    Args:
        line: 日志行内容

    Returns:
        str: 'error', 'warning', 'info'
    """
    upper_line = line.upper()

    # ERROR关键词
    error_keywords = ['ERROR', 'FATAL', 'CRITICAL', 'CRIT', 'EMERG', 'EXCEPTION', 'FAIL']
    for keyword in error_keywords:
        if keyword in upper_line:
            return 'error'

    # WARNING关键词
    warning_keywords = ['WARN', 'WARNING', 'ALERT']
    for keyword in warning_keywords:
        if keyword in upper_line:
            return 'warning'

    return 'info'


def read_log_lines(file_path: str, start_line: int = 0, max_lines: int = 10000) -> List[Dict]:
    """
    读取日志文件的指定行

    Args:
        file_path: 日志文件路径
        start_line: 开始行号（从0开始）
        max_lines: 最大读取行数

    Returns:
        list: [{line_num, content, time_str, severity}]
    """
    lines = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            current_line = 0
            for line in f:
                if current_line < start_line:
                    current_line += 1
                    continue

                if len(lines) >= max_lines:
                    break

                content = line.rstrip('\n\r')

                # 提取时间字符串（用于显示）
                time_match = re.search(r'(\d{2}:\d{2}:\d{2})', content)
                time_str = time_match.group(1) if time_match else ''

                lines.append({
                    'line_num': current_line + 1,
                    'content': content,
                    'time_str': time_str,
                    'severity': get_line_severity(content)
                })

                current_line += 1
    except Exception as e:
        logger.error(f"读取日志文件失败: {e}")

    return lines


def filter_log_by_time(file_path: str, start_time: datetime, end_time: datetime,
                       format_info: Dict = None, max_lines: int = 10000) -> List[Dict]:
    """
    按时间范围筛选日志

    Args:
        file_path: 日志文件路径
        start_time: 开始时间
        end_time: 结束时间
        format_info: 时间格式信息（可选，不提供则自动检测）
        max_lines: 最大返回行数

    Returns:
        list: [{line_num, content, time_str, severity, parsed_time}]
    """
    if not format_info:
        format_info = detect_time_format(file_path)

    if not format_info.get('format'):
        # 无法解析时间，返回原始内容
        return read_log_lines(file_path, 0, max_lines)

    reference_year = start_time.year if start_time else datetime.now().year

    lines = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            line_num = 1
            for line in f:
                if len(lines) >= max_lines:
                    break

                content = line.rstrip('\n\r')
                dt = parse_line_time(content, format_info, reference_year)

                if dt and start_time <= dt <= end_time:
                    time_str = dt.strftime('%H:%M:%S') if dt else ''
                    lines.append({
                        'line_num': line_num,
                        'content': content,
                        'time_str': time_str,
                        'severity': get_line_severity(content),
                        'parsed_time': dt.strftime('%Y-%m-%d %H:%M:%S')
                    })

                line_num += 1
    except Exception as e:
        logger.error(f"筛选日志失败: {e}")

    return lines


def filter_log_by_center_time(file_path: str, center_time: datetime,
                              offset_minutes: int = 60, format_info: Dict = None,
                              max_lines: int = 10000) -> List[Dict]:
    """
    按时间点和偏移量筛选日志

    Args:
        file_path: 日志文件路径
        center_time: 中心时间点
        offset_minutes: 前后偏移分钟数
        format_info: 时间格式信息
        max_lines: 最大返回行数

    Returns:
        list: [{line_num, content, time_str, severity, parsed_time}]
    """
    start_time = center_time - timedelta(minutes=offset_minutes)
    end_time = center_time + timedelta(minutes=offset_minutes)

    return filter_log_by_time(file_path, start_time, end_time, format_info, max_lines)


def filter_log_by_quick_mode(file_path: str, mode: str, format_info: Dict = None,
                             max_lines: int = 10000) -> Tuple[List[Dict], datetime, datetime]:
    """
    按快捷模式筛选日志

    Args:
        file_path: 日志文件路径
        mode: 快捷模式名称 (recent_1h, recent_24h, today, recent_7d)
        format_info: 时间格式信息
        max_lines: 最大返回行数

    Returns:
        tuple: (lines, start_time, end_time)
    """
    now = datetime.now()

    if mode == 'recent_1h':
        start_time = now - timedelta(hours=1)
        end_time = now
    elif mode == 'recent_24h':
        start_time = now - timedelta(hours=24)
        end_time = now
    elif mode == 'today':
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now
    elif mode == 'recent_7d':
        start_time = now - timedelta(days=7)
        end_time = now
    else:
        # 默认返回最近1小时
        start_time = now - timedelta(hours=1)
        end_time = now

    lines = filter_log_by_time(file_path, start_time, end_time, format_info, max_lines)
    return lines, start_time, end_time


def filter_multi_files_by_time(file_paths: List[str], start_time: datetime, end_time: datetime,
                               max_lines_per_file: int = 5000, max_total_lines: int = 20000) -> List[Dict]:
    """
    从多个文件中筛选同一时间段的日志

    Args:
        file_paths: 多个日志文件路径列表
        start_time: 开始时间
        end_time: 结束时间
        max_lines_per_file: 每个文件最大返回行数
        max_total_lines: 总最大返回行数

    Returns:
        list: [{line_num, content, time_str, severity, parsed_time, source_file}]
    """
    all_lines = []

    for file_path in file_paths:
        # 每个文件独立检测格式
        format_info = detect_time_format(file_path)
        reference_year = start_time.year if start_time else datetime.now().year

        if not format_info.get('format'):
            continue

        file_name = os.path.basename(file_path)
        file_lines_count = 0

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                line_num = 1
                for line in f:
                    if len(all_lines) >= max_total_lines:
                        break
                    if file_lines_count >= max_lines_per_file:
                        break

                    content = line.rstrip('\n\r')
                    dt = parse_line_time(content, format_info, reference_year)

                    if dt and start_time <= dt <= end_time:
                        all_lines.append({
                            'line_num': line_num,
                            'content': content,
                            'time_str': dt.strftime('%H:%M:%S'),
                            'severity': get_line_severity(content),
                            'parsed_time': dt.strftime('%Y-%m-%d %H:%M:%S'),
                            'source_file': file_name,
                            'datetime': dt  # 用于排序
                        })
                        file_lines_count += 1

                    line_num += 1
        except Exception as e:
            logger.warning(f"读取文件失败: {file_path} - {e}")

    # 按时间排序
    all_lines.sort(key=lambda x: x['datetime'])

    # 移除 datetime 对象（JSON无法序列化）
    for line in all_lines:
        del line['datetime']

    return all_lines


def filter_multi_files_by_center_time(file_paths: List[str], center_time: datetime,
                                       offset_minutes: int = 60,
                                       max_lines_per_file: int = 5000,
                                       max_total_lines: int = 20000) -> Tuple[List[Dict], datetime, datetime]:
    """
    从多个文件中按时间点偏移筛选日志

    Args:
        file_paths: 多个日志文件路径列表
        center_time: 中心时间点
        offset_minutes: 前后偏移分钟数
        max_lines_per_file: 每个文件最大返回行数
        max_total_lines: 总最大返回行数

    Returns:
        tuple: (lines, start_time, end_time)
    """
    start_time = center_time - timedelta(minutes=offset_minutes)
    end_time = center_time + timedelta(minutes=offset_minutes)

    lines = filter_multi_files_by_time(file_paths, start_time, end_time,
                                       max_lines_per_file, max_total_lines)
    return lines, start_time, end_time


def filter_multi_files_by_quick_mode(file_paths: List[str], mode: str,
                                      max_lines_per_file: int = 5000,
                                      max_total_lines: int = 20000) -> Tuple[List[Dict], datetime, datetime]:
    """
    从多个文件中按快捷模式筛选日志

    Args:
        file_paths: 多个日志文件路径列表
        mode: 快捷模式名称
        max_lines_per_file: 每个文件最大返回行数
        max_total_lines: 总最大返回行数

    Returns:
        tuple: (lines, start_time, end_time)
    """
    now = datetime.now()

    if mode == 'recent_1h':
        start_time = now - timedelta(hours=1)
        end_time = now
    elif mode == 'recent_24h':
        start_time = now - timedelta(hours=24)
        end_time = now
    elif mode == 'today':
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now
    elif mode == 'recent_7d':
        start_time = now - timedelta(days=7)
        end_time = now
    else:
        start_time = now - timedelta(hours=1)
        end_time = now

    lines = filter_multi_files_by_time(file_paths, start_time, end_time,
                                       max_lines_per_file, max_total_lines)
    return lines, start_time, end_time


# 用户输入时间格式定义（用于时间筛选界面）
USER_INPUT_TIME_FORMATS = [
    '%Y-%m-%d %H:%M:%S',  # 2025-09-03 02:01:30
    '%Y-%m-%d %H:%M',     # 2025-09-03 02:01
    '%Y-%m-%dT%H:%M:%S',  # 2025-09-03T02:01:30
    '%Y-%m-%dT%H:%M',     # 2025-09-03T02:01
    '%Y/%m/%d %H:%M:%S',  # 2025/09/03 02:01:30
    '%Y/%m/%d %H:%M',     # 2025/09/03 02:01
]


def parse_user_input_time(time_str: str) -> Optional[datetime]:
    """
    解析用户输入的时间字符串，自动适配多种格式

    Args:
        time_str: 用户输入的时间字符串

    Returns:
        datetime: 解析后的时间，如果解析失败返回 None
    """
    if not time_str:
        return None

    for fmt in USER_INPUT_TIME_FORMATS:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue

    logger.warning(f"用户输入时间格式不支持: '{time_str}'，支持的格式: {USER_INPUT_TIME_FORMATS}")
    return None