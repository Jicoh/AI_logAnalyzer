#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI日志分析器统一入口点
支持CLI子命令和Web模式

用法：
    ai_log_analyzer.exe                    # 启动Web界面（自动打开浏览器）
    ai_log_analyzer.exe web --port 9000    # 指定端口启动Web
    ai_log_analyzer.exe web --no-browser   # 启动Web但不打开浏览器
    ai_log_analyzer.exe web --analyze-path <path>  # 启动并自动分析指定路径
    ai_log_analyzer.exe analyze <path>     # CLI分析
    ai_log_analyzer.exe config set api.api_key <key>  # 配置
"""

import argparse
import sys
import os
import webbrowser
import threading
import time

# 添加路径
if getattr(sys, 'frozen', False):
    # exe运行时
    exe_dir = os.path.dirname(sys.executable)
    sys.path.insert(0, exe_dir)
else:
    # 源码运行时
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(
        description='AI日志分析器 - BMC服务器日志分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  ai_log_analyzer.exe                    启动Web界面
  ai_log_analyzer.exe web --port 9000    指定端口启动Web
  ai_log_analyzer.exe web --analyze-path /path/to/log.zip  启动并自动分析
  ai_log_analyzer.exe analyze /path/to/log  CLI分析
  ai_log_analyzer.exe config set api.api_key xxx  配置API
'''
    )
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # web 子命令
    web_parser = subparsers.add_parser('web', help='启动Web界面')
    web_parser.add_argument('--host', type=str, default='127.0.0.1',
                            help='绑定主机地址 (默认: 127.0.0.1)')
    web_parser.add_argument('--port', type=int, default=18888,
                            help='绑定端口 (默认: 18888)')
    web_parser.add_argument('--no-browser', action='store_true',
                            help='不自动打开浏览器')
    web_parser.add_argument('--analyze-path', type=str,
                            help='启动后自动分析指定路径')

    # 其他子命令通过main.py处理
    args = parser.parse_args()

    if args.command == 'web' or args.command is None:
        run_web(args)
    else:
        # 其他子命令交给main.py处理
        import main
        # 保留原始命令行参数，但替换argv[0]
        original_argv0 = sys.argv[0]
        sys.argv[0] = 'main.py'
        try:
            sys.exit(main.main())
        finally:
            sys.argv[0] = original_argv0


def run_web(args):
    """启动Web服务"""
    from web_app import create_app, get_web_config

    # 获取配置
    config = get_web_config()
    host = args.host or config.get('host', '127.0.0.1')
    port = args.port or config.get('port', 18888)
    debug = False  # 打包后禁用debug模式

    # 创建应用
    app = create_app()

    # 自动打开浏览器
    if not args.no_browser:
        url = f"http://{host}:{port}"
        # 如果指定了analyze-path，添加到URL参数
        if args.analyze_path:
            # 对路径进行URL编码处理
            import urllib.parse
            encoded_path = urllib.parse.quote(args.analyze_path)
            url += f"/?auto_analyze={encoded_path}"

        def open_browser():
            time.sleep(1.5)  # 等待服务启动
            try:
                webbrowser.open(url)
            except Exception as e:
                print(f"打开浏览器失败: {e}")

        threading.Thread(target=open_browser, daemon=True).start()

    print("=" * 50)
    print("AI Log Analyzer - Web Interface")
    print("=" * 50)
    print(f"访问地址: http://{host}:{port}")
    if args.analyze_path:
        print(f"自动分析路径: {args.analyze_path}")
    print("=" * 50)
    print("按 Ctrl+C 退出")

    try:
        app.run(host=host, port=port, debug=debug, threaded=True)
    except KeyboardInterrupt:
        print("\n服务已停止")


if __name__ == '__main__':
    main()