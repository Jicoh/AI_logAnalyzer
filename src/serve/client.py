"""
轻量客户端 - 供外部程序调用分析服务

无第三方依赖，仅使用标准库 socket/json/struct。
可直接拷贝此文件到调用方项目中使用。

用法:
    from analyze_client import AnalyzeClient

    client = AnalyzeClient(host='127.0.0.1', port=19888)
    # 或 Linux Unix socket:
    # client = AnalyzeClient(socket_path='/tmp/ai_log_analyzer.sock')

    # 心跳检测
    client.ping()  # -> True

    # 执行分析
    result = client.analyze(
        plugin_id='CloudBMC_00001',
        log_content={'system.log': ['ERROR disk failure']}
    )
    # result = [task_name, bmc_ip, status, description, log_detail, date]

    # 关闭服务
    client.shutdown()
"""

import socket
import json
import struct

HEADER_SIZE = 4
MAX_MESSAGE_SIZE = 50 * 1024 * 1024


def _recv_exact(sock, n):
    """精确接收 n 字节。"""
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("连接已关闭")
        data += chunk
    return data


def _send_message(sock, data):
    """编码并发送消息。"""
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    header = struct.pack('!I', len(body))
    sock.sendall(header + body)


def _recv_message(sock):
    """接收并解码一条消息。"""
    header = _recv_exact(sock, HEADER_SIZE)
    body_len = struct.unpack('!I', header)[0]
    if body_len > MAX_MESSAGE_SIZE:
        raise ValueError(f"消息过大: {body_len}")
    body = _recv_exact(sock, body_len)
    return json.loads(body.decode('utf-8'))


class AnalyzeClient:
    """分析服务客户端。"""

    def __init__(self, host='127.0.0.1', port=19888, socket_path=None):
        """
        初始化客户端。

        Args:
            host: TCP 服务地址（默认 127.0.0.1）
            port: TCP 服务端口（默认 19888）
            socket_path: Unix socket 路径（Linux，优先于 TCP）
        """
        self._host = host
        self._port = port
        self._socket_path = socket_path

        import sys as _sys
        self._use_unix = (
            socket_path is not None
            and hasattr(socket, 'AF_UNIX')
            and _sys.platform != 'win32'
        )

    def _connect(self):
        """创建新连接。"""
        if self._use_unix:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self._socket_path)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self._host, self._port))
        sock.settimeout(300)  # 5分钟超时
        return sock

    def _request(self, data):
        """发送请求并获取响应。"""
        sock = self._connect()
        try:
            _send_message(sock, data)
            return _recv_message(sock)
        finally:
            sock.close()

    def ping(self):
        """
        检测服务是否可用。

        Returns:
            bool: 服务是否可用
        """
        try:
            resp = self._request({'action': 'ping'})
            return resp.get('status') == 'ok'
        except Exception:
            return False

    def analyze(self, plugin_id, log_content,
                task_name='', bmc_ip='', date=''):
        """
        执行 cli 格式分析。

        Args:
            plugin_id: 插件ID（如 'CloudBMC_00001'）
            log_content: 日志内容，{"文件名": ["行1", "行2"]} 字典
            task_name: 任务名称
            bmc_ip: BMC IP地址
            date: 日期

        Returns:
            list: CliResult 列表 [task_name, bmc_ip, status, description,
                  log_detail, date]

        Raises:
            RuntimeError: 分析失败
            ConnectionError: 连接失败
        """
        resp = self._request({
            'action': 'analyze',
            'plugin_id': plugin_id,
            'log_content': log_content,
            'task_name': task_name,
            'bmc_ip': bmc_ip,
            'date': date
        })

        if resp.get('status') == 'error':
            raise RuntimeError(resp.get('message', '未知错误'))

        return resp.get('result')

    def shutdown(self):
        """关闭远程服务。"""
        try:
            self._request({'action': 'shutdown'})
        except Exception:
            pass
