"""
Main page routes.
"""

from flask import Blueprint, render_template
from flask_login import current_user
from src.auth.decorators import login_required

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    """Analyzer page (default home)."""
    return render_template('analyzer.html', active_page='analyzer')


@main_bp.route('/log-viewer')
@login_required
def log_viewer():
    """Log viewer page."""
    return render_template('log_viewer.html', active_page='log_viewer')


@main_bp.route('/knowledge-base')
@login_required
def knowledge_base():
    """Knowledge base management page."""
    return render_template('knowledge_base.html', active_page='kb')


@main_bp.route('/log-metadata')
@login_required
def log_metadata():
    """Log metadata rules management page."""
    return render_template('log_metadata.html', active_page='log_metadata')


@main_bp.route('/history')
@login_required
def history():
    """History records page."""
    return render_template('history.html', active_page='history')


@main_bp.route('/settings')
@login_required
def settings():
    """Settings page."""
    return render_template('settings.html', active_page='settings')


@main_bp.route('/profile')
@login_required
def profile():
    """Profile page (change password, quota info)."""
    return render_template('profile.html', active_page='profile')


@main_bp.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard page."""
    if not current_user.is_admin:
        return render_template('profile.html', active_page='profile'), 403
    return render_template('admin/dashboard.html', active_page='admin')