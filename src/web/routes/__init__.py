"""
Route blueprints registration.
"""

from flask import Blueprint

def register_routes(app):
    """Register all route blueprints with the Flask app."""
    from src.web.routes.main import main_bp
    from src.web.routes.kb_api import kb_bp
    from src.web.routes.analyze_api import analyze_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(kb_bp)
    app.register_blueprint(analyze_bp)