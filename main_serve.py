#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI日志分析器 - 常驻分析服务入口点

仅支持 serve 命令，用于后台常驻进程场景。

用法：
    python main_serve.py                          # 默认启动 serve
    python main_serve.py serve                    # 显式指定 serve
    python main_serve.py serve --port 9000        # 自定义端口
    python main_serve.py serve --socket /tmp/xxx  # Unix socket
"""

import sys
import os
import argparse

# 添加路径
if getattr(sys, 'frozen', False):
    exe_dir = os.path.dirname(sys.executable)
    sys.path.insert(0, exe_dir)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.serve.server import AnalyzeServer
from src.utils import get_logger

logger = get_logger('main_serve')


def main():
    parser = argparse.ArgumentParser(
        description='AI日志分析器 - 常驻分析服务'
    )
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # serve 命令
    serve_parser = subparsers.add_parser('serve', help='启动常驻分析服务')
    serve_parser.add_argument('--host', type=str, default='127.0.0.1',
                              help='TCP绑定地址 (默认: 127.0.0.1)')
    serve_parser.add_argument('--port', type=int, default=19888,
                              help='TCP绑定端口 (默认: 19888)')
    serve_parser.add_argument('--socket', type=str, default=None,
                              help='Unix socket路径 (仅Linux，优先于TCP)')

    args = parser.parse_args()

    # 默认启动 serve（后台进程最常见用法）
    if args.command is None:
        args.command = 'serve'
        args.host = '127.0.0.1'
        args.port = 19888
        args.socket = None

    if args.command == 'serve':
        server = AnalyzeServer(
            host=args.host,
            port=args.port,
            socket_path=args.socket
        )
        server.start()
    else:
        parser.print_help()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        if getattr(sys, 'frozen', False):
            print("\n按任意键退出...")
            try:
                input()
            except Exception:
                pass
