"""
日志分析模块
对BMC日志进行解析和分析，提取错误、警告等信息
"""

import re
import os
from datetime import datetime
from collections import Counter


class LogAnalyzer:
    """BMC日志分析器"""

    # 常见日志级别
    LOG_LEVELS = ['ERROR', 'WARN', 'WARNING', 'INFO', 'DEBUG', 'CRITICAL', 'FATAL']

    # 常见错误模式
    ERROR_PATTERNS = [
        r'error',
        r'fail',
        r'exception',
        r'critical',
        r'fatal',
        r'fault',
        r'abort',
        r'timeout',
        r'overflow',
        r'underflow',
        r'corrupt'
    ]

    # 常见警告模式
    WARNING_PATTERNS = [
        r'warn',
        r'warning',
        r'degrad',
        r'retry',
        r'unavailable',
        r'threshold',
        r'limit'
    ]

    def __init__(self, config=None):
        self.config = config or {}
        self.results = {
            'analysis_time': '',
            'log_file': '',
            'error_count': 0,
            'warning_count': 0,
            'errors': [],
            'warnings': [],
            'statistics': {}
        }

    def analyze(self, log_file):
        """
        分析日志文件

        Args:
            log_file: 日志文件路径

        Returns:
            dict: 分析结果
        """
        self.results['analysis_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.results['log_file'] = os.path.basename(log_file)

        lines = self.read_log_file(log_file)
        parsed_lines = self.parse_lines(lines)

        self.extract_errors(parsed_lines)
        self.extract_warnings(parsed_lines)
        self.calculate_statistics(lines, parsed_lines)

        return self.results

    def read_log_file(self, log_file):
        """读取日志文件"""
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            return f.readlines()

    def parse_lines(self, lines):
        """解析日志行"""
        parsed = []
        for line_num, line in enumerate(lines, 1):
            parsed_line = self.parse_line(line.strip(), line_num)
            if parsed_line:
                parsed.append(parsed_line)
        return parsed

    def parse_line(self, line, line_num):
        """解析单行日志"""
        if not line:
            return None

        result = {
            'line_number': line_num,
            'raw': line,
            'timestamp': '',
            'level': '',
            'component': '',
            'message': ''
        }

        # 尝试提取时间戳
        timestamp_patterns = [
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
            r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})',
            r'(\d{2}:\d{2}:\d{2})',
            r'\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\]'
        ]

        for pattern in timestamp_patterns:
            match = re.search(pattern, line)
            if match:
                result['timestamp'] = match.group(1)
                break

        # 提取日志级别
        line_upper = line.upper()
        for level in self.LOG_LEVELS:
            if level in line_upper:
                result['level'] = level
                break

        # 提取组件名（方括号中的内容）
        component_match = re.search(r'\[([^\]]+)\]', line)
        if component_match:
            component = component_match.group(1)
            if component and not re.match(r'^\d{4}-\d{2}-\d{2}', component):
                result['component'] = component

        # 提取消息
        result['message'] = line

        return result

    def extract_errors(self, parsed_lines):
        """提取错误信息"""
        errors = []
        error_pattern = re.compile('|'.join(self.ERROR_PATTERNS), re.IGNORECASE)

        for line_info in parsed_lines:
            if line_info['level'] in ['ERROR', 'CRITICAL', 'FATAL']:
                errors.append(self.format_issue(line_info))
            elif error_pattern.search(line_info['message']):
                # 避免重复添加
                if line_info['level'] not in ['WARN', 'WARNING']:
                    errors.append(self.format_issue(line_info))

        self.results['errors'] = errors
        self.results['error_count'] = len(errors)

    def extract_warnings(self, parsed_lines):
        """提取警告信息"""
        warnings = []
        warning_pattern = re.compile('|'.join(self.WARNING_PATTERNS), re.IGNORECASE)

        for line_info in parsed_lines:
            if line_info['level'] in ['WARN', 'WARNING']:
                warnings.append(self.format_issue(line_info))
            elif warning_pattern.search(line_info['message']):
                # 避免重复添加已标记为错误的
                if line_info['level'] not in ['ERROR', 'CRITICAL', 'FATAL']:
                    warnings.append(self.format_issue(line_info))

        self.results['warnings'] = warnings
        self.results['warning_count'] = len(warnings)

    def format_issue(self, line_info):
        """格式化问题信息"""
        return {
            'timestamp': line_info['timestamp'],
            'level': line_info['level'] or 'UNKNOWN',
            'message': line_info['message'],
            'component': line_info['component'],
            'line_number': line_info['line_number']
        }

    def calculate_statistics(self, lines, parsed_lines):
        """计算统计数据"""
        total_lines = len(lines)
        level_counter = Counter()

        for line_info in parsed_lines:
            if line_info['level']:
                level_counter[line_info['level']] += 1

        # 统计组件出现频率
        component_counter = Counter()
        for line_info in parsed_lines:
            if line_info['component']:
                component_counter[line_info['component']] += 1

        self.results['statistics'] = {
            'total_lines': total_lines,
            'error_rate': round(self.results['error_count'] / total_lines, 6) if total_lines > 0 else 0,
            'warning_rate': round(self.results['warning_count'] / total_lines, 6) if total_lines > 0 else 0,
            'level_distribution': dict(level_counter),
            'top_components': dict(component_counter.most_common(10))
        }

    def get_summary(self):
        """获取分析摘要"""
        return {
            'log_file': self.results['log_file'],
            'analysis_time': self.results['analysis_time'],
            'error_count': self.results['error_count'],
            'warning_count': self.results['warning_count'],
            'error_rate': self.results['statistics'].get('error_rate', 0),
            'warning_rate': self.results['statistics'].get('warning_rate', 0)
        }

    def save_results(self, output_file):
        """
        保存分析结果到JSON文件

        Args:
            output_file: 输出文件路径
        """
        import json
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=4, ensure_ascii=False)


def analyze_log(log_file, output_file=None):
    """
    分析日志文件的便捷函数

    Args:
        log_file: 日志文件路径
        output_file: 输出文件路径（可选）

    Returns:
        dict: 分析结果
    """
    analyzer = LogAnalyzer()
    results = analyzer.analyze(log_file)

    if output_file:
        analyzer.save_results(output_file)

    return results