#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI Log Analyzer - Web Application Entry Point

Usage:
    python web_app.py

Access the web interface at: http://127.0.0.1:18888
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from src.web.routes import register_routes


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

    # Register routes
    register_routes(app)

    return app


# Create app instance
app = create_app()


if __name__ == '__main__':
    print("=" * 50)
    print("AI Log Analyzer - Web Interface")
    print("=" * 50)
    print(f"Access at: http://127.0.0.1:18888")
    print("=" * 50)

    app.run(
        host='127.0.0.1',
        port=18888,
        debug=True
    )