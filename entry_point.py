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
import json
import urllib.request
import urllib.parse

# 添加路径
if getattr(sys, 'frozen', False):
    # exe运行时
    exe_dir = os.path.dirname(sys.executable)
    sys.path.insert(0, exe_dir)
else:
    # 源码运行时
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
        print(f"写入锁文件失败: {e}")


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
        pass  # 发送失败不影响打开浏览器


def check_port_in_use(port):
    """检查端口是否被占用。"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', port))
            return result == 0  # 0 表示端口可连接（被占用）
    except Exception:
        return False


def check_existing_server(analyze_path=None):
    """检查是否已有服务运行，复用则返回True。"""
    lock_data = read_lock_file()
    port = lock_data.get('port', 18888) if lock_data else 18888

    # 检查端口是否可连接
    if not check_port_in_use(port):
        # 端口不可连接，清理锁文件
        if lock_data:
            remove_lock_file()
        return False

    # 端口可连接，复用已有服务，不重复打开浏览器
    if analyze_path:
        send_analyze_request(port, analyze_path)
        print(f"已发送分析请求到现有服务 (端口 {port})")
        print("请在已打开的浏览器页面查看分析结果")
    else:
        webbrowser.open(f"http://127.0.0.1:{port}/")
        print(f"已有服务运行，已打开浏览器 (端口 {port})")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='AI日志分析器 - BMC服务器日志分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  ai_log_analyzer.exe                          启动Web界面
  ai_log_analyzer.exe web --port 9000          指定端口启动Web
  ai_log_analyzer.exe web --analyze-path log.zip  启动并自动分析
  ai_log_analyzer.exe analyze log.zip          CLI分析（插件分析）
  ai_log_analyzer.exe analyze log.zip --ai     CLI分析+AI分析
  ai_log_analyzer.exe plugin list              列出可用插件
  ai_log_analyzer.exe plugin select CloudBMC   选择CloudBMC插件类别
  ai_log_analyzer.exe config set api.api_key xxx  配置API密钥
  ai_log_analyzer.exe kb create --name "知识库"  创建知识库
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

    # analyze 子命令
    analyze_parser = subparsers.add_parser('analyze', help='分析日志文件或目录')
    analyze_parser.add_argument('path', help='日志文件或目录路径')
    analyze_parser.add_argument('--plugins', help='指定插件ID，多个用逗号分隔')
    analyze_parser.add_argument('--kb', '-k', help='知识库ID')
    analyze_parser.add_argument('--prompt', '-p', help='用户提示词')
    analyze_parser.add_argument('--ai', action='store_true', help='启用AI分析')
    analyze_parser.add_argument('--ai-select', action='store_true', help='AI智能选择插件')

    # plugin 子命令
    plugin_parser = subparsers.add_parser('plugin', help='插件管理')
    plugin_parser.add_argument('plugin_action', nargs='?', choices=['list', 'select', 'categories', 'selected'],
                               default='list', help='操作: list(列表), select(选择), categories(分类), selected(已选)')

    # config 子命令
    config_parser = subparsers.add_parser('config', help='配置管理')
    config_parser.add_argument('config_action', choices=['get', 'set', 'list'],
                               help='操作: get(获取), set(设置), list(列出)')
    config_parser.add_argument('--key', '-k', help='配置项键名')
    config_parser.add_argument('--value', '-v', help='配置项值')

    # kb 子命令
    kb_parser = subparsers.add_parser('kb', help='知识库管理')
    kb_parser.add_argument('kb_action', choices=['list', 'create', 'info'],
                           default='list', help='操作: list(列表), create(创建), info(详情)')
    kb_parser.add_argument('--name', '-n', help='知识库名称')
    kb_parser.add_argument('--kb-id', help='知识库ID')

    # log-rules 子命令
    log_rules_parser = subparsers.add_parser('log-rules', help='日志规则管理')
    log_rules_parser.add_argument('rules_action', choices=['list', 'show'],
                                  default='list', help='操作: list(列表), show(详情)')

    # cache 子命令
    cache_parser = subparsers.add_parser('cache', help='缓存管理')
    cache_parser.add_argument('cache_action', choices=['stats', 'clear-results', 'clear-temp'],
                              default='stats', help='操作: stats(统计), clear-results(清理结果), clear-temp(清理临时)')

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
    # 获取参数（先不import web_app）
    host = getattr(args, 'host', None) or '127.0.0.1'
    port = getattr(args, 'port', None) or 18888
    no_browser = getattr(args, 'no_browser', False)
    analyze_path = getattr(args, 'analyze_path', None)
    debug = False  # 打包后禁用debug模式

    # 检查是否已有服务运行（在import web_app之前）
    if check_existing_server(analyze_path):
        return

    # 现在才import web_app（避免提前加载插件）
    from web_app import create_app, get_web_config

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
        # 如果指定了analyze-path，添加到URL参数
        if analyze_path:
            # 对路径进行URL编码处理
            encoded_path = urllib.parse.quote(analyze_path)
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
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        # 如果是打包后运行，等待用户按键
        if getattr(sys, 'frozen', False):
            print("\n按任意键退出...")
            try:
                input()
            except:
                pass