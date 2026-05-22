"""
TCP/Unix socket 常驻分析服务

Linux 优先 Unix domain socket，Windows 使用 TCP 端口。
"""

import os
import sys
import json
import time
import socket
import signal
import threading

from src.serve.protocol import decode_message, send_message
from src.serve.handler import RequestHandler
from src.utils import get_logger

logger = get_logger('serve')

# 默认配置
DEFAULT_TCP_PORT = 19888
DEFAULT_TCP_HOST = '127.0.0.1'
DEFAULT_SOCKET_PATH = '/tmp/ai_log_analyzer.sock'
LOCK_FILE_NAME = '.serve.lock'


def _is_unix_available():
    """检测 Unix domain socket 是否可用。"""
    return hasattr(socket, 'AF_UNIX') and sys.platform != 'win32'


class AnalyzeServer:
    """常驻分析服务，支持 TCP 和 Unix domain socket。"""

    def __init__(self, host=None, port=None, socket_path=None):
        self._host = host or DEFAULT_TCP_HOST
        self._port = port or DEFAULT_TCP_PORT
        self._socket_path = socket_path
        self._handler = RequestHandler()
        self._handler.set_server(self)
        self._shutdown_event = threading.Event()
        self._server_socket = None
        self._lock_file = self._get_lock_file_path()

    def _get_lock_file_path(self):
        """获取锁文件路径。"""
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_dir, 'data', LOCK_FILE_NAME)

    def _read_lock_file(self):
        """读取锁文件。"""
        if not os.path.exists(self._lock_file):
            return None
        try:
            with open(self._lock_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _write_lock_file(self, address_info: dict):
        """写入锁文件。"""
        lock_dir = os.path.dirname(self._lock_file)
        if not os.path.exists(lock_dir):
            os.makedirs(lock_dir, exist_ok=True)
        info = {
            'pid': os.getpid(),
            'timestamp': time.time(),
            **address_info
        }
        with open(self._lock_file, 'w', encoding='utf-8') as f:
            json.dump(info, f, indent=2)

    def _remove_lock_file(self):
        """删除锁文件。"""
        if os.path.exists(self._lock_file):
            try:
                os.remove(self._lock_file)
            except Exception:
                pass

    def _check_existing(self, address_info: dict):
        """检查是否已有实例运行。"""
        lock_data = self._read_lock_file()
        if not lock_data:
            return False

        pid = lock_data.get('pid')
        if pid and self._is_process_alive(pid):
            # 进程还在运行
            addr_type = lock_data.get('type', 'tcp')
            if addr_type == 'unix':
                addr = lock_data.get('socket_path', '')
                print(f"已有服务运行 (PID {pid}, Unix socket: {addr})")
            else:
                host = lock_data.get('host', '127.0.0.1')
                port = lock_data.get('port', DEFAULT_TCP_PORT)
                print(f"已有服务运行 (PID {pid}, {host}:{port})")
            return True

        # 进程已退出，清理锁文件
        self._remove_lock_file()
        return False

    @staticmethod
    def _is_process_alive(pid):
        """检测进程是否存活。"""
        try:
            if sys.platform == 'win32':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x100000, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, ProcessLookupError):
            return False

    def _create_server_socket(self):
        """根据平台创建服务端 socket。"""
        if self._use_unix:
            sock_path = self._socket_path or DEFAULT_SOCKET_PATH
            # 清理旧 socket 文件
            if os.path.exists(sock_path):
                os.remove(sock_path)

            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(sock_path)
            os.chmod(sock_path, 0o666)
            self._address = sock_path
            return sock

        # TCP 模式
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._host, self._port))
        self._address = (self._host, self._port)
        return sock

    def _get_address_info(self):
        """获取当前地址信息用于锁文件。"""
        if self._address_type == 'unix':
            return {
                'type': 'unix',
                'socket_path': self._socket_path or DEFAULT_SOCKET_PATH
            }
        return {
            'type': 'tcp',
            'host': self._host,
            'port': self._port
        }

    def _handle_client(self, client_sock, addr):
        """处理单个客户端连接。"""
        try:
            while not self._shutdown_event.is_set():
                try:
                    request = decode_message(client_sock)
                except ConnectionError:
                    break
                except Exception as e:
                    logger.error(f"消息解码失败: {e}")
                    break

                response = self._handler.handle(request)
                try:
                    send_message(client_sock, response)
                except ConnectionError:
                    break

                # shutdown 命令后关闭连接
                if request.get('action') == 'shutdown':
                    break
        except Exception as e:
            logger.error(f"客户端处理异常: {e}")
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def request_shutdown(self):
        """请求关闭服务。"""
        self._shutdown_event.set()

    def start(self):
        """启动服务。"""
        # 确定监听方式
        self._use_unix = _is_unix_available() and (
            self._socket_path or not self._host)
        if self._use_unix:
            self._address_type = 'unix'
        else:
            self._address_type = 'tcp'

        # 检查已有实例
        address_info = self._get_address_info()
        if self._check_existing(address_info):
            return

        # 创建 socket
        self._server_socket = self._create_server_socket()
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)

        # 写入锁文件
        self._write_lock_file(address_info)

        # 预加载插件
        self._handler._ensure_agent_service()

        # 注册信号处理
        def signal_handler(signum, frame):
            self.request_shutdown()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # 打印启动信息
        self._print_startup_info()

        # 主循环
        try:
            while not self._shutdown_event.is_set():
                try:
                    client_sock, addr = self._server_socket.accept()
                    client_sock.settimeout(300)  # 5分钟超时
                    t = threading.Thread(
                        target=self._handle_client,
                        args=(client_sock, addr),
                        daemon=True
                    )
                    t.start()
                except socket.timeout:
                    continue
                except OSError:
                    if self._shutdown_event.is_set():
                        break
                    raise
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    def _print_startup_info(self):
        """打印启动信息。"""
        print("=" * 50)
        print("AI Log Analyzer - 分析服务")
        print("=" * 50)
        if self._address_type == 'unix':
            print(f"监听: Unix socket {self._address}")
        else:
            print(f"监听: {self._host}:{self._port}")
        print(f"PID: {os.getpid()}")
        print("=" * 50)
        print("按 Ctrl+C 退出")

    def _cleanup(self):
        """清理资源。"""
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass

        # 清理 Unix socket 文件
        if self._address_type == 'unix' and os.path.exists(self._address):
            try:
                os.remove(self._address)
            except Exception:
                pass

        self._remove_lock_file()
        print("\n服务已停止")
