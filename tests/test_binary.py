"""
主程序二进制文件 CLI 测试

测试打包后的主程序二进制文件是否能正确返回返回值。
需要先运行 python scripts/build_package.py 编译。
"""

import json
import subprocess
import sys
import os
import pytest

# 主程序二进制文件路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    BINARY_PATH = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer', 'ai_log_analyzer.exe')
else:
    BINARY_PATH = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer', 'main')


def run_binary(*args, stdin_data=None):
    """运行二进制文件"""
    result = subprocess.run(
        [BINARY_PATH] + list(args),
        input=stdin_data,
        capture_output=True,
        text=True
    )
    print(f"工具输出: ", result)
    return result


@pytest.mark.skipif(not os.path.exists(BINARY_PATH), reason="二进制文件未编译")
class TestBinaryExists:
    """二进制文件存在性测试"""

    def test_binary_exists(self):
        assert os.path.exists(BINARY_PATH)


@pytest.mark.skipif(not os.path.exists(BINARY_PATH), reason="二进制文件未编译")
class TestBinaryPluginList:
    """plugin list 命令测试"""

    def test_plugin_list_returncode(self):
        result = run_binary('plugin', 'list')
        assert result.returncode == 0

    def test_plugin_list_output_not_empty(self):
        result = run_binary('plugin', 'list')
        assert len(result.stdout.strip()) > 0


@pytest.mark.skipif(not os.path.exists(BINARY_PATH), reason="二进制文件未编译")
class TestBinaryAnalyzeCliFormat:
    """analyze --format cli 命令测试"""

    def test_analyze_returncode_success(self):
        log_content = json.dumps({"system.log": ["INFO ok"]})
        result = run_binary(
            'analyze', '--format', 'cli',
            '--plugin-id', 'CloudBMC_00001',
            '--task-name', 'my_task',
            '--bmc-ip', '192.168.1.1',
            '--date', '2024-01-01',
            stdin_data=log_content)
        assert result.returncode == 0

    def test_analyze_returncode_error(self):
        result = run_binary('analyze', '--format', 'cli', '--plugin-id', 'CloudBMC_00001', stdin_data='not json')
        assert result.returncode == 1
