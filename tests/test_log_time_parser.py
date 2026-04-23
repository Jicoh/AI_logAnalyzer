"""
时间解析模块测试
测试 log_time_parser.py 支持的所有时间格式
"""

import os
import tempfile
from datetime import datetime, timedelta
from src.utils.log_time_parser import (
    parse_line_time,
    parse_user_input_time,
    detect_time_format,
    get_file_time_range,
    filter_log_by_quick_mode,
    filter_log_by_time,
    filter_log_by_center_time,
    TIME_FORMATS
)


# ============ parse_line_time 测试 ============

def test_iso_with_timezone_t_separator():
    """ISO格式带时区T分隔 (2025-09-09T17:11:11+8:00)"""
    line = "Log entry at 2025-09-09T17:11:11+8:00 message"
    fmt = TIME_FORMATS[0]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 9
    assert dt.day == 9
    assert dt.hour == 17
    assert dt.minute == 11
    assert dt.second == 11


def test_iso_with_timezone_no_colon():
    """ISO格式带时区无冒号 (2025-09-09T17:11:11+0800)"""
    line = "Log entry at 2025-09-09T17:11:11+0800 message"
    fmt = TIME_FORMATS[1]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2025
    assert dt.hour == 17


def test_iso_space_timezone_hour():
    """ISO格式空格带时区小时 (2025-08-30 15:15:15+08)"""
    line = "Log entry at 2025-08-30 15:15:15+08 message"
    fmt = TIME_FORMATS[2]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 8
    assert dt.day == 30
    assert dt.hour == 15


def test_iso_space_timezone_colon():
    """ISO格式空格带时区冒号 (2025-08-30 15:15:15+8:00)"""
    line = "Log entry at 2025-08-30 15:15:15+8:00 message"
    fmt = TIME_FORMATS[3]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2025
    assert dt.hour == 15


def test_iso_space_timezone_no_colon():
    """ISO格式空格带时区无冒号 (2025-08-30 15:15:15+0800)"""
    line = "Log entry at 2025-08-30 15:15:15+0800 message"
    fmt = TIME_FORMATS[4]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2025
    assert dt.hour == 15


def test_iso_space_no_timezone():
    """ISO格式空格无时区 (2025-08-30 15:15:15)"""
    line = "Log entry at 2025-08-30 15:15:15 message"
    fmt = TIME_FORMATS[5]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 8
    assert dt.day == 30
    assert dt.hour == 15
    assert dt.minute == 15
    assert dt.second == 15


def test_iso_t_separator_no_timezone():
    """ISO格式T分隔无时区 (2026-04-14T09:00:30)"""
    line = "Log entry at 2026-04-14T09:00:30 message"
    fmt = TIME_FORMATS[6]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.day == 14
    assert dt.hour == 9
    assert dt.minute == 0
    assert dt.second == 30


def test_iso_with_ms_space():
    """ISO带毫秒空格分隔 (2026-04-14 09:00:30.123)"""
    line = "Log entry at 2026-04-14 09:00:30.123 message"
    fmt = TIME_FORMATS[7]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2026
    assert dt.hour == 9
    assert dt.minute == 0
    assert dt.second == 30


def test_iso_with_ms_t_separator():
    """ISO带毫秒T分隔 (2026-04-14T09:00:30.123)"""
    line = "Log entry at 2026-04-14T09:00:30.123 message"
    fmt = TIME_FORMATS[8]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2026
    assert dt.second == 30


def test_slash_format():
    """斜杠格式 (2026/04/14 09:00:30)"""
    line = "Log entry at 2026/04/14 09:00:30 message"
    fmt = TIME_FORMATS[9]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.day == 14


def test_english_month_format():
    """英文月份格式 (Sep 19 20:10:33)"""
    line = "Log entry at Sep 19 20:10:33 message"
    fmt = TIME_FORMATS[10]
    dt = parse_line_time(line, fmt, reference_year=2025)
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 9
    assert dt.day == 19
    assert dt.hour == 20
    assert dt.minute == 10
    assert dt.second == 33


def test_compact_format():
    """紧凑格式 (20260414090030)"""
    line = "Log entry at 20260414090030 message"
    fmt = TIME_FORMATS[11]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.day == 14
    assert dt.hour == 9
    assert dt.minute == 0
    assert dt.second == 30


def test_short_format():
    """短格式 (04-14 09:00:30)"""
    line = "Log entry at 04-14 09:00:30 message"
    fmt = TIME_FORMATS[12]
    dt = parse_line_time(line, fmt, reference_year=2026)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.day == 14
    assert dt.hour == 9


def test_bracket_iso_format():
    """方括号ISO格式 [2026-04-14T09:00:30]"""
    line = "Log entry [2026-04-14T09:00:30] message"
    fmt = TIME_FORMATS[13]
    dt = parse_line_time(line, fmt)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.day == 14


def test_bracket_time_format():
    """方括号时间格式 [09:00:30]"""
    line = "Log entry [09:00:30] message"
    fmt = TIME_FORMATS[14]
    dt = parse_line_time(line, fmt, reference_year=2026)
    assert dt is not None
    assert dt.hour == 9
    assert dt.minute == 0
    assert dt.second == 30


def test_only_time_format():
    """仅时间格式 (09:00:30)"""
    line = "Log entry at 09:00:30 message"
    fmt = TIME_FORMATS[15]
    dt = parse_line_time(line, fmt, reference_year=2026)
    assert dt is not None
    assert dt.hour == 9
    assert dt.minute == 0
    assert dt.second == 30


def test_parse_line_time_auto_detect():
    """自动检测格式（不提供 format_info）"""
    line = "2025-08-30 15:15:15 some log message"
    dt = parse_line_time(line, None, reference_year=2025)
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 8
    assert dt.day == 30


def test_parse_line_time_invalid():
    """无效时间格式"""
    line = "No valid timestamp here"
    dt = parse_line_time(line, None)
    assert dt is None


# ============ parse_user_input_time 测试 ============

def test_user_input_datetime_full():
    """用户输入完整日期时间 (2025-09-03 02:01:30)"""
    dt = parse_user_input_time("2025-09-03 02:01:30")
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 9
    assert dt.day == 3
    assert dt.hour == 2
    assert dt.minute == 1
    assert dt.second == 30


def test_user_input_datetime_no_seconds():
    """用户输入日期时间无秒 (2025-09-03 02:01)"""
    dt = parse_user_input_time("2025-09-03 02:01")
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 9
    assert dt.day == 3
    assert dt.hour == 2
    assert dt.minute == 1
    assert dt.second == 0


def test_user_input_iso_t_full():
    """用户输入ISO T分隔完整 (2025-09-03T02:01:30)"""
    dt = parse_user_input_time("2025-09-03T02:01:30")
    assert dt is not None
    assert dt.year == 2025
    assert dt.hour == 2
    assert dt.second == 30


def test_user_input_iso_t_no_seconds():
    """用户输入ISO T分隔无秒 (2025-09-03T02:01)"""
    dt = parse_user_input_time("2025-09-03T02:01")
    assert dt is not None
    assert dt.year == 2025
    assert dt.minute == 1
    assert dt.second == 0


def test_user_input_slash_full():
    """用户输入斜杠格式完整 (2025/09/03 02:01:30)"""
    dt = parse_user_input_time("2025/09/03 02:01:30")
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 9
    assert dt.day == 3
    assert dt.hour == 2


def test_user_input_slash_no_seconds():
    """用户输入斜杠格式无秒 (2025/09/03 02:01)"""
    dt = parse_user_input_time("2025/09/03 02:01")
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 9
    assert dt.minute == 1


def test_user_input_empty():
    """用户输入空字符串"""
    dt = parse_user_input_time("")
    assert dt is None


def test_user_input_invalid():
    """用户输入无效格式"""
    dt = parse_user_input_time("invalid-time-format")
    assert dt is None


def test_user_input_partial_date():
    """用户输入部分日期（不支持）"""
    dt = parse_user_input_time("2025-09-03")
    assert dt is None


# ============ detect_time_format 测试 ============

def test_detect_iso_format():
    """检测ISO格式日志"""
    content = """2025-08-30 15:15:15 INFO message1
2025-08-30 15:15:16 DEBUG message2
2025-08-30 15:15:17 ERROR message3
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        result = detect_time_format(temp_path)
        assert result.get('format') is not None
        assert result.get('has_year') == True
        assert 'ISO' in result.get('description', '')
    finally:
        os.unlink(temp_path)


def test_detect_english_month_format():
    """检测英文月份格式日志"""
    content = """Sep 19 20:10:33 INFO message1
Sep 19 20:10:34 DEBUG message2
Sep 19 20:10:35 ERROR message3
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        result = detect_time_format(temp_path)
        assert result.get('format') is not None
        assert result.get('has_year') == False
        assert '英文月份' in result.get('description', '')
    finally:
        os.unlink(temp_path)


def test_detect_no_time_format():
    """检测无时间格式日志"""
    content = """No timestamp line1
No timestamp line2
No timestamp line3
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        result = detect_time_format(temp_path)
        assert result.get('format') is None
    finally:
        os.unlink(temp_path)


def test_detect_empty_file():
    """检测空文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.flush()
        temp_path = f.name

    try:
        result = detect_time_format(temp_path)
        assert result.get('format') is None
        assert '空文件' in result.get('description', '')
    finally:
        os.unlink(temp_path)


# ============ get_file_time_range 测试 ============

def test_get_time_range():
    """获取文件时间范围"""
    content = """2025-08-30 15:15:15 INFO start
2025-08-30 15:16:20 DEBUG middle
2025-08-30 15:17:30 ERROR end
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        min_time, max_time, format_info = get_file_time_range(temp_path)
        assert min_time is not None
        assert max_time is not None
        assert min_time.hour == 15
        assert min_time.minute == 15
        assert max_time.minute == 17
        assert max_time.second == 30
    finally:
        os.unlink(temp_path)


def test_get_time_range_no_format():
    """无时间格式的文件时间范围"""
    content = """line without time1
line without time2
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        min_time, max_time, format_info = get_file_time_range(temp_path)
        assert min_time is None
        assert max_time is None
    finally:
        os.unlink(temp_path)


# ============ 快捷模式测试 ============

def test_filter_quick_mode_recent_1h():
    """快捷模式：最近1小时"""
    now = datetime.now()
    content = f"""{now.strftime('%Y-%m-%d %H:%M:%S')} INFO recent
{(now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')} INFO old
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        lines, start, end = filter_log_by_quick_mode(temp_path, 'recent_1h')
        assert len(lines) >= 1
        assert 'recent' in lines[0]['content']
    finally:
        os.unlink(temp_path)


def test_filter_quick_mode_recent_24h():
    """快捷模式：最近24小时"""
    now = datetime.now()
    content = f"""{now.strftime('%Y-%m-%d %H:%M:%S')} INFO recent
{(now - timedelta(hours=30)).strftime('%Y-%m-%d %H:%M:%S')} INFO old
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        lines, start, end = filter_log_by_quick_mode(temp_path, 'recent_24h')
        assert len(lines) >= 1
    finally:
        os.unlink(temp_path)


def test_filter_quick_mode_today():
    """快捷模式：今天"""
    now = datetime.now()
    content = f"""{now.strftime('%Y-%m-%d %H:%M:%S')} INFO today
{(now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')} INFO old
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        lines, start, end = filter_log_by_quick_mode(temp_path, 'today')
        assert len(lines) >= 1
    finally:
        os.unlink(temp_path)


def test_filter_quick_mode_recent_7d():
    """快捷模式：最近7天"""
    now = datetime.now()
    content = f"""{now.strftime('%Y-%m-%d %H:%M:%S')} INFO recent
{(now - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S')} INFO old
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        lines, start, end = filter_log_by_quick_mode(temp_path, 'recent_7d')
        assert len(lines) >= 1
    finally:
        os.unlink(temp_path)


def test_filter_quick_mode_unknown():
    """快捷模式：未知模式默认最近1小时"""
    now = datetime.now()
    content = f"""{now.strftime('%Y-%m-%d %H:%M:%S')} INFO recent
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        lines, start, end = filter_log_by_quick_mode(temp_path, 'unknown_mode')
        assert len(lines) >= 1
    finally:
        os.unlink(temp_path)


# ============ 时间筛选测试 ============

def test_filter_by_time_range():
    """按时间范围筛选"""
    content = """2025-08-30 15:15:15 INFO in_range
2025-08-30 15:16:20 DEBUG in_range
2025-08-30 16:00:00 ERROR out_range
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        start = datetime(2025, 8, 30, 15, 0, 0)
        end = datetime(2025, 8, 30, 15, 30, 0)
        lines = filter_log_by_time(temp_path, start, end)
        assert len(lines) == 2
        assert 'in_range' in lines[0]['content']
        assert 'in_range' in lines[1]['content']
    finally:
        os.unlink(temp_path)


def test_filter_by_center_time():
    """按中心时间偏移筛选"""
    content = """2025-08-30 14:00:00 INFO far_before
2025-08-30 15:15:15 INFO near_before
2025-08-30 16:00:00 INFO center
2025-08-30 16:45:15 INFO near_after
2025-08-30 18:00:00 INFO far_after
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        center = datetime(2025, 8, 30, 16, 0, 0)
        lines = filter_log_by_center_time(temp_path, center, offset_minutes=60)
        assert len(lines) == 3
        assert 'near_before' in lines[0]['content']
        assert 'center' in lines[1]['content']
        assert 'near_after' in lines[2]['content']
    finally:
        os.unlink(temp_path)


def test_filter_no_format():
    """无时间格式时返回原始内容"""
    content = """line1 no time
line2 no time
line3 no time
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        start = datetime(2025, 8, 30, 15, 0, 0)
        end = datetime(2025, 8, 30, 16, 0, 0)
        lines = filter_log_by_time(temp_path, start, end)
        assert len(lines) == 3
        assert 'parsed_time' not in lines[0]
    finally:
        os.unlink(temp_path)


# ============ 无效时间格式测试（修复验证） ============

def test_invalid_bracket_hour_not_matched():
    """方括号时间格式：无效小时[31:00:00]不应被匹配"""
    line = "Log entry [31:00:00] message"
    dt = parse_line_time(line, None)
    assert dt is None


def test_invalid_bracket_minute_not_matched():
    """方括号时间格式：无效分钟[09:61:30]不应被匹配"""
    line = "Log entry [09:61:30] message"
    dt = parse_line_time(line, None)
    assert dt is None


def test_time_with_ms_not_matched():
    """仅时间格式：带毫秒的时间31:00:00.018不应被匹配"""
    line = "Log entry 31:00:00.018 message"
    dt = parse_line_time(line, None)
    assert dt is None


def test_invalid_only_time_hour_not_matched():
    """仅时间格式：无效小时31:00:00不应被匹配"""
    line = "Log entry 31:00:00 message"
    dt = parse_line_time(line, None)
    assert dt is None


def test_invalid_compact_year_not_matched():
    """紧凑格式：无效年份90700001000003不应被匹配"""
    line = "Log entry 90700001000003 message"
    dt = parse_line_time(line, None)
    assert dt is None


def test_invalid_compact_month_not_matched():
    """紧凑格式：无效月份20260001000000不应被匹配"""
    line = "Log entry 20260001000000 message"
    dt = parse_line_time(line, None)
    assert dt is None


def test_invalid_short_format_month_not_matched():
    """短格式：无效月份13-14 09:00:30不应被匹配"""
    line = "Log entry 13-14 09:00:30 message"
    dt = parse_line_time(line, None, reference_year=2026)
    assert dt is None


def test_valid_time_with_correct_bounds():
    """有效时间边界测试：[23:59:59]应被正确匹配（使用方括号格式）"""
    line = "Log entry [23:59:59] message"
    dt = parse_line_time(line, None, reference_year=2026)
    assert dt is not None
    assert dt.hour == 23
    assert dt.minute == 59
    assert dt.second == 59


def test_valid_compact_with_year_2000():
    """紧凑格式：年份2000有效"""
    line = "Log entry 20000101000000 message"
    dt = parse_line_time(line, None)
    assert dt is not None
    assert dt.year == 2000
    assert dt.month == 1
    assert dt.day == 1