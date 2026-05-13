"""
JSON-over-socket 通信协议

消息格式: 4字节 big-endian 长度头 + JSON body
"""

import struct
import json


HEADER_SIZE = 4
MAX_MESSAGE_SIZE = 50 * 1024 * 1024  # 50MB


def encode_message(data: dict) -> bytes:
    """将字典编码为长度头+JSON的消息。"""
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    header = struct.pack('!I', len(body))
    return header + body


def recv_exact(sock, n: int) -> bytes:
    """从 socket 精确接收 n 字节。"""
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("连接已关闭")
        data += chunk
    return data


def decode_message(sock) -> dict:
    """从 socket 读取一条完整消息并解码为字典。"""
    header = recv_exact(sock, HEADER_SIZE)
    body_len = struct.unpack('!I', header)[0]

    if body_len > MAX_MESSAGE_SIZE:
        raise ValueError(f"消息过大: {body_len} 字节 (最大 {MAX_MESSAGE_SIZE})")

    body = recv_exact(sock, body_len)
    return json.loads(body.decode('utf-8'))


def send_message(sock, data: dict):
    """编码并发送一条消息。"""
    msg = encode_message(data)
    sock.sendall(msg)
