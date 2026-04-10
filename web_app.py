#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI Log Analyzer - Web Application Entry Point

Usage:
    python web_app.py                           # Use config file settings
    python web_app.py --port 9000               # Override port
    python web_app.py --host 0.0.0.0 --port 80  # Override host and port
    python web_app.py --no-debug                # Disable debug mode

Access the web interface at: http://127.0.0.1:18888 (default)
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from src.web.routes import register_routes
from src.config_manager.manager import ConfigManager


def get_web_config():
    """Read web configuration from config file."""
    config_manager = ConfigManager()
    return {
        "host": config_manager.get("web.host", "127.0.0.1"),
        "port": config_manager.get("web.port", 18888),
        "debug": config_manager.get("web.debug", True)
    }


def create_app():
    """Create and configure the Flask application."""
    # Get the project root directory
    root_dir = os.path.dirname(os.path.abspath(__file__))

    # Create Flask app with template and static folders
    app = Flask(
        __name__,
        template_folder=os.path.join(root_dir, 'src', 'web', 'templates'),
        static_folder=os.path.join(root_dir, 'src', 'web', 'static')
    )

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ai-log-analyzer-secret-key-change-in-production')
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

    # Ensure upload directory exists
    uploads_dir = os.path.join(root_dir, 'data', 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    # Preload plugins
    print("Preloading plugins...")
    from plugins.manager import get_plugin_manager
    custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
    plugin_manager = get_plugin_manager(custom_dirs=[custom_plugins_dir])
    print(f"Available plugins: {[p.id for p in plugin_manager.get_all_plugins()]}")

    # Register routes
    register_routes(app)

    return app


# Create app instance
app = create_app()


def parse_args():
    """Parse command line arguments."""
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

    print("=" * 50)
    print("AI Log Analyzer - Web Interface")
    print("=" * 50)
    print(f"Access at: http://{host}:{port}")
    print("=" * 50)

    app.run(
        host=host,
        port=port,
        debug=debug
    )