"""
Serve 命令集成测试

测试打包后的二进制文件 serve 命令功能：
- 启动常驻服务进程
- 客户端通信（ping、analyze）
- 平台差异检测（Linux Unix socket / Windows TCP）

同时测试 log_analyze_serve 专属二进制的基本功能。

需要先运行 python scripts/build_package.py 编译二进制文件。
"""

import json
import os
import subprocess
import sys
import time

import pytest

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 全功能二进制路径
if sys.platform == 'win32':
    BINARY_PATH = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer', 'ai_log_analyzer.exe')
else:
    BINARY_PATH = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer', 'ai_log_analyzer')

DIST_DIR = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer')

# serve 专属二进制路径
if sys.platform == 'win32':
    SERVE_BINARY_PATH = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer_Serve', 'log_analyze_serve.exe')
else:
    SERVE_BINARY_PATH = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer_Serve', 'log_analyze_serve')

SERVE_DIST_DIR = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer_Serve')

# 锁文件路径
LOCK_FILE = os.path.join(DIST_DIR, 'data', '.serve.lock')
SERVE_LOCK_FILE = os.path.join(SERVE_DIST_DIR, 'data', '.serve.lock')

# 默认 Unix socket 路径
DEFAULT_SOCKET_PATH = '/tmp/ai_log_analyzer.sock'

# 测试用 Unix socket 路径（避免与已运行服务冲突）
TEST_SOCKET_PATH = '/tmp/test_ai_log_analyzer.sock'

# 默认 TCP 端口
DEFAULT_PORT = 19888

# 测试用 TCP 端口（避免与已运行服务冲突）
TEST_PORT = 19889

# serve 专属二进制测试用端口（避免与全功能二进制测试冲突）
SERVE_TEST_PORT = 19890
SERVE_TEST_SOCKET_PATH = '/tmp/test_serve_binary.sock'


def _is_unix_available():
    """检测是否支持 Unix domain socket。"""
    import socket
    return hasattr(socket, 'AF_UNIX') and sys.platform != 'win32'


def _get_serve_args(test_socket_path=TEST_SOCKET_PATH, test_port=TEST_PORT):
    """根据平台返回 serve 启动参数和客户端连接参数。

    Linux 优先使用 Unix socket，Windows 使用 TCP。
    使用非默认端口/socket路径避免与已运行服务冲突。
    """
    if _is_unix_available():
        return {
            'serve_args': ['--socket', test_socket_path],
            'client_kwargs': {'socket_path': test_socket_path}
        }
    return {
        'serve_args': ['--port', str(test_port)],
        'client_kwargs': {'port': test_port}
    }


def _start_serve_process(binary_path, serve_args=None, client_kwargs=None):
    """启动 serve 进程并等待就绪。

    Args:
        binary_path: 二进制文件路径
        serve_args: 传给 serve 命令的额外参数列表
        client_kwargs: AnalyzeClient 连接参数

    Returns:
        tuple: (进程对象, AnalyzeClient 实例)
    """
    sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))
    from serve.client import AnalyzeClient

    args = [binary_path, 'serve'] + (serve_args or [])

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(binary_path)
    )

    client = AnalyzeClient(**(client_kwargs or {}))

    # 等待服务就绪，最多 30 秒
    for _ in range(30):
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            raise RuntimeError(
                f"服务进程意外退出 (code={proc.returncode})\n"
                f"stdout: {stdout.decode('utf-8', errors='ignore')}\n"
                f"stderr: {stderr.decode('utf-8', errors='ignore')}"
            )
        if client.ping():
            return proc, client
        time.sleep(1)

    proc.kill()
    raise RuntimeError("服务启动超时")


def _stop_serve_process(proc, lock_file=LOCK_FILE):
    """停止 serve 进程并清理资源。"""
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)

    # 清理锁文件
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except Exception:
            pass

    # 清理 Unix socket 文件
    for sock_path in [DEFAULT_SOCKET_PATH, TEST_SOCKET_PATH, SERVE_TEST_SOCKET_PATH]:
        if os.path.exists(sock_path):
            try:
                os.remove(sock_path)
            except Exception:
                pass


@pytest.mark.skipif(not os.path.exists(BINARY_PATH), reason="二进制文件未编译")
class TestBinaryServe:
    """全功能二进制 Serve 命令集成测试。"""

    def test_serve_ping(self):
        """测试心跳检测。"""
        config = _get_serve_args()
        proc, client = _start_serve_process(
            BINARY_PATH,
            serve_args=config['serve_args'],
            client_kwargs=config['client_kwargs']
        )

        try:
            assert client.ping() is True
        finally:
            _stop_serve_process(proc)

    def test_serve_analyze(self):
        """测试分析功能。"""
        config = _get_serve_args()
        proc, client = _start_serve_process(
            BINARY_PATH,
            serve_args=config['serve_args'],
            client_kwargs=config['client_kwargs']
        )

        try:
            result = client.analyze(
                plugin_id='CloudBMC_00001',
                log_content={'system.log': ['INFO test message']},
                task_name='test_task',
                bmc_ip='192.168.1.1',
                date='2024-01-01'
            )

            # 验证返回格式: [task_name, bmc_ip, status, description, log_detail, date]
            assert isinstance(result, list)
            assert len(result) == 6
            assert result[0] == 'test_task'
            assert result[1] == '192.168.1.1'
            assert isinstance(result[2], str)
            assert isinstance(result[3], str)
        finally:
            _stop_serve_process(proc)

    def test_platform_detection(self):
        """测试平台差异：Linux 使用 Unix socket，Windows 使用 TCP。"""
        config = _get_serve_args()
        proc, client = _start_serve_process(
            BINARY_PATH,
            serve_args=config['serve_args'],
            client_kwargs=config['client_kwargs']
        )

        try:
            # 检查锁文件
            assert os.path.exists(LOCK_FILE), "锁文件不存在"

            with open(LOCK_FILE, 'r', encoding='utf-8') as f:
                lock_data = json.load(f)

            if _is_unix_available():
                # Linux --socket 模式：锁文件记录 unix 类型
                assert lock_data.get('type') == 'unix', "Linux --socket 应使用 unix 模式"
                assert lock_data.get('socket_path') == TEST_SOCKET_PATH
            else:
                # Windows：锁文件记录 tcp 类型
                assert lock_data.get('type') == 'tcp', "Windows 应使用 tcp 模式"
                assert lock_data.get('port') == TEST_PORT
        finally:
            _stop_serve_process(proc)


@pytest.mark.skipif(not os.path.exists(SERVE_BINARY_PATH), reason="serve专属二进制未编译")
class TestServeBinary:
    """serve 专属二进制集成测试。"""

    def test_serve_ping(self):
        """测试心跳检测。"""
        config = _get_serve_args(
            test_socket_path=SERVE_TEST_SOCKET_PATH,
            test_port=SERVE_TEST_PORT
        )
        proc, client = _start_serve_process(
            SERVE_BINARY_PATH,
            serve_args=config['serve_args'],
            client_kwargs=config['client_kwargs']
        )

        try:
            assert client.ping() is True
        finally:
            _stop_serve_process(proc, lock_file=SERVE_LOCK_FILE)

    def test_serve_analyze(self):
        """测试分析功能。"""
        config = _get_serve_args(
            test_socket_path=SERVE_TEST_SOCKET_PATH,
            test_port=SERVE_TEST_PORT
        )
        proc, client = _start_serve_process(
            SERVE_BINARY_PATH,
            serve_args=config['serve_args'],
            client_kwargs=config['client_kwargs']
        )

        try:
            result = client.analyze(
                plugin_id='CloudBMC_00001',
                log_content={'system.log': ['INFO test message']},
                task_name='test_task',
                bmc_ip='192.168.1.1',
                date='2024-01-01'
            )

            assert isinstance(result, list)
            assert len(result) == 6
            assert result[0] == 'test_task'
            assert result[1] == '192.168.1.1'
        finally:
            _stop_serve_process(proc, lock_file=SERVE_LOCK_FILE)

    def test_no_web_command(self):
        """验证不支持 web 命令。"""
        result = subprocess.run(
            [SERVE_BINARY_PATH, 'web'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0

    def test_no_analyze_command(self):
        """验证不支持 analyze 命令。"""
        result = subprocess.run(
            [SERVE_BINARY_PATH, 'analyze', '--format', 'cli', '--plugin-id', 'test'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0
