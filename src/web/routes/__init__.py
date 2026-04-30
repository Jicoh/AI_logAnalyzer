"""
Route blueprints registration.
"""

from flask import Blueprint

def register_routes(app):
    """Register all route blueprints with the Flask app."""
    from src.web.routes.main import main_bp
    from src.web.routes.kb_api import kb_bp
    from src.web.routes.analyze_api import analyze_bp
    from src.web.routes.history_api import history_bp
    from src.web.routes.log_metadata_api import log_metadata_bp
    from src.web.routes.cache_api import cache_bp
    from src.web.routes.log_viewer_api import log_viewer_bp
    from src.web.routes.auth_api import auth_bp
    from src.web.routes.admin_api import admin_bp
    from src.web.routes.feedback_api import feedback_bp
    from src.web.routes.skill_api import skill_bp
    from src.web.routes.assistant_api import assistant_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(kb_bp)
    app.register_blueprint(analyze_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(log_metadata_bp)
    app.register_blueprint(cache_bp)
    app.register_blueprint(log_viewer_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(skill_bp)
    app.register_blueprint(assistant_bp)