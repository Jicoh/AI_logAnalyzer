"""
Serve 专属二进制集成测试

测试 log_analyze_serve 专属二进制的功能：
- 启动常驻服务进程
- 客户端通信（ping、analyze）
- 平台差异检测（Linux Unix socket / Windows TCP）

需要先运行 python scripts/build_package.py serve 编译二进制文件。
"""

import json
import os
import subprocess
import sys
import time

import pytest

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 二进制路径
if sys.platform == 'win32':
    BINARY_PATH = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer_Serve', 'log_analyze_serve.exe')
else:
    BINARY_PATH = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer_Serve', 'log_analyze_serve')

DIST_DIR = os.path.join(PROJECT_ROOT, 'dist', 'AI_Log_Analyzer_Serve')

# 锁文件路径
LOCK_FILE = os.path.join(DIST_DIR, 'data', '.serve.lock')

# 测试用 Unix socket 路径
TEST_SOCKET_PATH = '/tmp/test_ai_log_analyzer.sock'

# 测试用 TCP 端口
TEST_PORT = 19889


def _is_unix_available():
    """检测是否支持 Unix domain socket。"""
    import socket
    return hasattr(socket, 'AF_UNIX') and sys.platform != 'win32'


def _get_serve_args():
    """根据平台返回 serve 启动参数和客户端连接参数。

    Linux 优先使用 Unix socket，Windows 使用 TCP。
    """
    if _is_unix_available():
        return {
            'serve_args': ['--socket', TEST_SOCKET_PATH],
            'client_kwargs': {'socket_path': TEST_SOCKET_PATH}
        }
    return {
        'serve_args': ['--port', str(TEST_PORT)],
        'client_kwargs': {'port': TEST_PORT}
    }


def _start_serve_process(serve_args=None, client_kwargs=None):
    """启动 serve 进程并等待就绪。

    Args:
        serve_args: 传给 serve 命令的额外参数列表
        client_kwargs: AnalyzeClient 连接参数

    Returns:
        tuple: (进程对象, AnalyzeClient 实例, stderr_content)
    """
    sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))
    from serve.client import AnalyzeClient

    args = [BINARY_PATH, 'serve'] + (serve_args or [])

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(BINARY_PATH)
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
            # 非阻塞读取当前stderr内容（用于诊断）
            stderr_content = ''
            if proc.stderr:
                try:
                    # Linux支持select管道，Windows不支持
                    import select
                    if hasattr(select, 'select') and sys.platform != 'win32':
                        readable, _, _ = select.select([proc.stderr], [], [], 0)
                        if readable:
                            stderr_content = proc.stderr.read().decode('utf-8', errors='ignore')
                except Exception:
                    pass
            return proc, client, stderr_content
        time.sleep(1)

    proc.kill()
    raise RuntimeError("服务启动超时")


def _stop_serve_process(proc):
    """停止 serve 进程并清理资源。"""
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)

    # 清理锁文件
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass

    # 清理 Unix socket 文件
    if os.path.exists(TEST_SOCKET_PATH):
        try:
            os.remove(TEST_SOCKET_PATH)
        except Exception:
            pass


@pytest.mark.skipif(not os.path.exists(BINARY_PATH), reason="serve专属二进制未编译")
class TestServeBinary:
    """serve 专属二进制集成测试。"""

    def test_serve_ping(self):
        """测试心跳检测。"""
        config = _get_serve_args()
        proc, client, _ = _start_serve_process(
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
        proc, client, _ = _start_serve_process(
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
        proc, client, stderr_content = _start_serve_process(
            serve_args=config['serve_args'],
            client_kwargs=config['client_kwargs']
        )

        try:
            # 检查锁文件
            if not os.path.exists(LOCK_FILE):
                # 收集诊断信息
                data_dir = os.path.dirname(LOCK_FILE)
                raise AssertionError(
                    f"锁文件不存在\n"
                    f"期望路径: {LOCK_FILE}\n"
                    f"data目录存在: {os.path.exists(data_dir)}\n"
                    f"data目录内容: {os.listdir(data_dir) if os.path.exists(data_dir) else 'N/A'}\n"
                    f"服务stderr: {stderr_content}"
                )

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

    def test_no_web_command(self):
        """验证不支持 web 命令。"""
        result = subprocess.run(
            [BINARY_PATH, 'web'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0

    def test_no_analyze_command(self):
        """验证不支持 analyze 命令。"""
        result = subprocess.run(
            [BINARY_PATH, 'analyze', '--format', 'cli', '--plugin-id', 'test'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0
