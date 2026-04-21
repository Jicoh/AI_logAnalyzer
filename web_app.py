#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI 日志分析器 - Web 应用入口

用法：
    python web_app.py                           # 使用配置文件设置
    python web_app.py --port 9000               # 覆盖端口
    python web_app.py --host 0.0.0.0 --port 80  # 覆盖主机和端口
    python web_app.py --no-debug                # 禁用调试模式

访问 Web 界面: http://127.0.0.1:18888（默认）
"""

import argparse
import os
import sys

# 将项目根目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from src.web.routes import register_routes
from src.config_manager.manager import ConfigManager
from src.utils import get_logger

logger = get_logger('web_app')


def get_web_config():
    """从配置文件读取 Web 配置。"""
    config_manager = ConfigManager()
    return {
        "host": config_manager.get("web.host", "127.0.0.1"),
        "port": config_manager.get("web.port", 18888),
        "debug": config_manager.get("web.debug", True)
    }


def create_app():
    """创建并配置 Flask 应用。"""
    # 获取项目根目录（支持打包）
    if getattr(sys, 'frozen', False):
        # exe运行时，资源文件在 sys._MEIPASS 目录下
        resource_dir = sys._MEIPASS
        # exe所在目录用于外部文件（配置、日志等）
        root_dir = os.path.dirname(sys.executable)
    else:
        resource_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = resource_dir

    # 创建 Flask 应用，设置模板和静态文件夹
    app = Flask(
        __name__,
        template_folder=os.path.join(resource_dir, 'src', 'web', 'templates'),
        static_folder=os.path.join(resource_dir, 'src', 'web', 'static')
    )

    # 配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ai-log-analyzer-secret-key-change-in-production')
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 最大文件大小 50MB

    # 确保上传目录存在
    uploads_dir = os.path.join(root_dir, 'data', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    # 预加载插件
    logger.info("正在预加载插件...")
    from plugins.manager import get_plugin_manager
    custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
    plugin_manager = get_plugin_manager(custom_dirs=[custom_plugins_dir])
    logger.info(f"可用插件: {[p.id for p in plugin_manager.get_all_plugins()]}")

    # 注册路由
    register_routes(app)

    return app


# 创建应用实例
app = create_app()


def parse_args():
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description='AI Log Analyzer Web Application')
    parser.add_argument('--host', type=str, help='Host to bind to (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, help='Port to bind to (default: 18888)')
    parser.add_argument('--debug', action='store_true', dest='debug', help='Enable debug mode')
    parser.add_argument('--no-debug', action='store_false', dest='debug', help='Disable debug mode')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    config = get_web_config()

    host = args.host if args.host else config['host']
    port = args.port if args.port else config['port']
    debug = args.debug if args.debug is not None else config['debug']

    logger.info("=" * 50)
    logger.info("AI Log Analyzer - Web Interface")
    logger.info("=" * 50)
    logger.info(f"Access at: http://{host}:{port}")
    logger.info("=" * 50)

    app.run(
        host=host,
        port=port,
        debug=debug
    )