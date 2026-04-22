"""
Main page routes.
"""

from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Analyzer page (default home)."""
    return render_template('analyzer.html', active_page='analyzer')


@main_bp.route('/log-viewer')
def log_viewer():
    """Log viewer page."""
    return render_template('log_viewer.html', active_page='log_viewer')


@main_bp.route('/knowledge-base')
def knowledge_base():
    """Knowledge base management page."""
    return render_template('knowledge_base.html', active_page='kb')


@main_bp.route('/log-metadata')
def log_metadata():
    """Log metadata rules management page."""
    return render_template('log_metadata.html', active_page='log_metadata')


@main_bp.route('/history')
def history():
    """History records page."""
    return render_template('history.html', active_page='history')


@main_bp.route('/settings')
def settings():
    """Settings page."""
    return render_template('settings.html', active_page='settings')