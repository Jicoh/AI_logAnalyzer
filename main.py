#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI日志分析器统一入口点
支持CLI子命令和Web模式

用法：
    python main.py                    # 启动Web界面（自动打开浏览器）
    python main.py web --port 9000    # 指定端口启动Web
    python main.py web --no-browser   # 启动Web但不打开浏览器
    python main.py web --analyze-path <path>  # 启动并自动分析指定路径
    python main.py analyze <path>     # CLI分析
    python main.py config set api.api_key <key>  # 配置
"""

import sys
import os
import webbrowser
import threading
import time
import json
import urllib.request
import urllib.parse

# 添加路径
if getattr(sys, 'frozen', False):
    exe_dir = os.path.dirname(sys.executable)
    sys.path.insert(0, exe_dir)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils import get_logger
from src.cli import get_parser

logger = get_logger('main')

# 锁文件路径
LOCK_FILE_NAME = '.web_server.lock'


def get_lock_file_path():
    """获取锁文件路径。"""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'data', LOCK_FILE_NAME)


def read_lock_file():
    """读取锁文件内容。"""
    lock_path = get_lock_file_path()
    if not os.path.exists(lock_path):
        return None
    try:
        with open(lock_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def write_lock_file(port, pid):
    """写入锁文件。"""
    lock_path = get_lock_file_path()
    lock_dir = os.path.dirname(lock_path)
    if not os.path.exists(lock_dir):
        os.makedirs(lock_dir, exist_ok=True)
    try:
        with open(lock_path, 'w', encoding='utf-8') as f:
            json.dump({
                'port': port,
                'pid': pid,
                'timestamp': time.time()
            }, f)
    except Exception as e:
        logger.warning(f"写入锁文件失败: {e}")


def remove_lock_file():
    """删除锁文件。"""
    lock_path = get_lock_file_path()
    if os.path.exists(lock_path):
        try:
            os.remove(lock_path)
        except Exception:
            pass


def send_analyze_request(port, path):
    """向已运行的服务发送分析请求。"""
    try:
        url = f"http://127.0.0.1:{port}/api/trigger-analysis"
        data = json.dumps({'path': path}).encode('utf-8')
        req = urllib.request.Request(url, data=data,
                                     headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def check_port_in_use(port):
    """检查端口是否被占用。"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', port))
            return result == 0
    except Exception:
        return False


def check_existing_server(port=None, analyze_path=None):
    """检查是否已有服务运行，复用则返回True。

    Args:
        port: 用户指定的端口，如果指定则只检查该端口
        analyze_path: 分析路径，用于发送分析请求
    """
    lock_data = read_lock_file()
    lock_port = lock_data.get('port', 18888) if lock_data else 18888

    # 如果用户指定了端口，只检查该端口
    check_port = port if port is not None else lock_port

    if not check_port_in_use(check_port):
        if lock_data and check_port == lock_port:
            remove_lock_file()
        return False

    # 端口被占用，复用现有服务
    if analyze_path:
        send_analyze_request(check_port, analyze_path)
        print(f"已发送分析请求到现有服务 (端口 {check_port})")
        print("请在已打开的浏览器页面查看分析结果")
    else:
        webbrowser.open(f"http://127.0.0.1:{check_port}/")
        print(f"已有服务运行，已打开浏览器 (端口 {check_port})")
    return True


def main():
    # 包含web子命令的完整解析器
    parser = get_parser(include_web=True)
    args = parser.parse_args()

    if args.command == 'web' or args.command is None:
        run_web(args)
    else:
        # 延迟导入，避免触发main.py的重模块加载
        from src.cli import handle_command
        sys.exit(handle_command(args))


def run_web(args):
    """启动Web服务"""
    host = getattr(args, 'host', None) or '127.0.0.1'
    port = getattr(args, 'port', None) or 18888
    no_browser = getattr(args, 'no_browser', False)
    analyze_path = getattr(args, 'analyze_path', None)
    # --debug/--no-debug 参数，打包后默认禁用
    if getattr(sys, 'frozen', False):
        debug = False
    else:
        debug = getattr(args, 'debug', None)
        if debug is None:
            debug = False  # 默认禁用

    # 检查是否已有服务运行（在import src.web之前）
    if check_existing_server(port, analyze_path):
        return

    # 现在才import src.web（避免提前加载插件）
    from src.web import create_app, get_web_config

    # 获取配置（覆盖默认值）
    config = get_web_config()
    host = getattr(args, 'host', None) or config.get('host', '127.0.0.1')
    port = getattr(args, 'port', None) or config.get('port', 18888)

    # 写入锁文件
    write_lock_file(port, os.getpid())

    # 创建应用
    app = create_app()

    # 注册退出清理
    import atexit
    atexit.register(remove_lock_file)

    # 自动打开浏览器
    if not no_browser:
        url = f"http://{host}:{port}"
        if analyze_path:
            encoded_path = urllib.parse.quote(analyze_path)
            url += f"/?auto_analyze={encoded_path}"

        def open_browser():
            time.sleep(1.5)
            try:
                webbrowser.open(url)
            except Exception as e:
                logger.warning(f"打开浏览器失败: {e}")

        threading.Thread(target=open_browser, daemon=True).start()

    print("=" * 50)
    print("AI Log Analyzer - Web Interface")
    print("=" * 50)
    print(f"访问地址: http://{host}:{port}")
    if analyze_path:
        print(f"自动分析路径: {analyze_path}")
    print("=" * 50)
    print("按 Ctrl+C 退出")

    try:
        app.run(host=host, port=port, debug=debug, threaded=True)
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        remove_lock_file()


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
            except:
                pass
