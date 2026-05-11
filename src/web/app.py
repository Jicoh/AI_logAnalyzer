"""
Flask 应用工厂

通过 main.py web 启动。
"""

import os
import sys

from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from src.web.routes import register_routes
from src.system_config_manager.manager import SystemConfigManager
from src.utils import get_logger

logger = get_logger('web')


def get_web_config():
    """从配置文件读取 Web 配置。"""
    settings_manager = SystemConfigManager()
    return {
        "host": settings_manager.get("web.host", "0.0.0.0"),
        "port": settings_manager.get("web.port", 18888),
        "debug": settings_manager.get("web.debug", False)
    }


def _get_app_dirs():
    """获取应用目录路径（支持打包）。"""
    if getattr(sys, 'frozen', False):
        resource_dir = sys._MEIPASS
        root_dir = os.path.dirname(sys.executable)
    else:
        resource_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        root_dir = resource_dir
    return resource_dir, root_dir


def _create_flask_app(resource_dir):
    """创建 Flask 应用实例。"""
    app = Flask(
        __name__,
        template_folder=os.path.join(resource_dir, 'src', 'web', 'templates'),
        static_folder=os.path.join(resource_dir, 'src', 'web', 'static')
    )

    # 基础配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ai-log-analyzer-secret-key-change-in-production')

    # 安全检查：检测是否使用默认SECRET_KEY
    if app.config['SECRET_KEY'] == 'ai-log-analyzer-secret-key-change-in-production':
        logger.warning("=" * 60)
        logger.warning("安全警告: 正在使用默认 SECRET_KEY!")
        logger.warning("生产环境请设置环境变量: SECRET_KEY=<your-secret-key>")
        logger.warning("=" * 60)

    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 最大文件大小 50MB
    return app


def _init_database(app, root_dir):
    """初始化数据库。"""
    db_path = os.path.join(root_dir, 'data', 'app.db')
    # 确保data目录存在
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    from src.models.user import db
    from src.models.feedback import Feedback
    from src.models.token_usage import TokenUsage
    db.init_app(app)

    from src.web.routes.auth_api import init_login_manager
    init_login_manager(app)

    return db


def _init_security(app):
    """初始化安全组件（CSRF和限流）。"""
    csrf = CSRFProtect(app)

    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
    app.extensions['limiter'] = limiter

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({
            'success': False,
            'error': '请求过于频繁，请稍后再试'
        }), 429

    return csrf, limiter


def _preload_components(root_dir):
    """预加载插件和Skill。"""
    logger.info("正在预加载插件...")
    from plugins.manager import get_plugin_manager
    custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
    plugin_manager = get_plugin_manager(custom_dirs=[custom_plugins_dir])
    logger.info(f"可用插件: {[p.id for p in plugin_manager.get_all_plugins()]}")

    logger.info("正在预加载Skill...")
    from src.agent.skill_loader import get_skill_loader
    skill_loader = get_skill_loader()
    skills = skill_loader.scan()
    logger.info(f"已加载 {len(skills)} 个Skill: {[s.name for s in skills]}")


def _configure_rate_limits(app, limiter):
    """配置限流规则。"""
    # 认证接口限流
    limiter.limit("5 per minute")(app.view_functions['auth.do_login'])
    limiter.limit("10 per hour")(app.view_functions['auth.do_register'])

    # 用户信息接口放宽限流（页面加载时必调用）
    limiter.limit("200 per minute")(app.view_functions['auth.get_me'])

    # 缓存统计接口放宽限流
    limiter.limit("200 per minute")(app.view_functions['cache_api.get_cache_stats'])


def _configure_csrf_exemptions(app, csrf):
    """配置CSRF豁免。"""
    # SSE流式端点
    csrf.exempt(app.view_functions['analyze_api.analyze_stream'])
    csrf.exempt(app.view_functions['analyze_api.analyze_local_stream'])
    csrf.exempt(app.view_functions['analyze_api.analyze_batch_stream'])

    # 认证端点
    csrf.exempt(app.view_functions['auth.do_login'])
    csrf.exempt(app.view_functions['auth.do_register'])
    csrf.exempt(app.view_functions['auth.do_logout'])
    csrf.exempt(app.view_functions['auth.change_password'])

    # 智能助手API
    csrf.exempt(app.view_functions['assistant_api.create_session'])
    csrf.exempt(app.view_functions['assistant_api.delete_session'])
    csrf.exempt(app.view_functions['assistant_api.chat'])
    csrf.exempt(app.view_functions['assistant_api.chat_stream'])
    csrf.exempt(app.view_functions['assistant_api.upload_file'])
    csrf.exempt(app.view_functions['assistant_api.download_selected_files'])
    csrf.exempt(app.view_functions['assistant_api.delete_files'])

    # 用户配置API
    csrf.exempt(app.view_functions['user_config_api.reload_mcp_servers'])
    csrf.exempt(app.view_functions['user_config_api.toggle_mcp_server'])
    csrf.exempt(app.view_functions['user_config_api.toggle_skill'])
    csrf.exempt(app.view_functions['user_config_api.update_user_config'])

    # 知识库API
    csrf.exempt(app.view_functions['kb_api.reload_kb'])
    csrf.exempt(app.view_functions['kb_api.create_kb'])
    csrf.exempt(app.view_functions['kb_api.upload_document'])
    csrf.exempt(app.view_functions['kb_api.reindex_kb'])

    # Skill API
    csrf.exempt(app.view_functions['skill_api.reload_skills'])

    # 日志规则API
    csrf.exempt(app.view_functions['log_metadata_api.create_rule_set'])
    csrf.exempt(app.view_functions['log_metadata_api.import_rule_set'])
    csrf.exempt(app.view_functions['log_metadata_api.update_rule_set'])
    csrf.exempt(app.view_functions['log_metadata_api.delete_rule_set'])
    csrf.exempt(app.view_functions['log_metadata_api.add_rule'])
    csrf.exempt(app.view_functions['log_metadata_api.update_rule'])
    csrf.exempt(app.view_functions['log_metadata_api.delete_rule'])

    # 分析模板API
    csrf.exempt(app.view_functions['admin_api.create_analysis_template'])
    csrf.exempt(app.view_functions['admin_api.update_user_analysis_template'])
    csrf.exempt(app.view_functions['admin_api.delete_user_analysis_template'])

    # 缓存清理API
    csrf.exempt(app.view_functions['cache_api.clear_temp'])
    csrf.exempt(app.view_functions['cache_api.clear_results'])

    # 管理员API
    csrf.exempt(app.view_functions['admin_api.update_config'])
    csrf.exempt(app.view_functions['admin_api.test_mcp_server'])
    csrf.exempt(app.view_functions['admin_api.add_mcp_server'])
    csrf.exempt(app.view_functions['admin_api.create_user'])
    csrf.exempt(app.view_functions['admin_api.update_user_quota'])
    csrf.exempt(app.view_functions['admin_api.reset_user_password'])
    csrf.exempt(app.view_functions['admin_api.toggle_user_active'])
    csrf.exempt(app.view_functions['admin_api.delete_user'])
    csrf.exempt(app.view_functions['feedback_api.reply_feedback'])

    # 反馈API
    csrf.exempt(app.view_functions['feedback_api.submit_feedback'])

    # 历史API
    csrf.exempt(app.view_functions['history_api.download_history'])

    # 分析API
    csrf.exempt(app.view_functions['analyze_api.validate_local_path'])

    # 日志查看API
    csrf.exempt(app.view_functions['log_viewer_api.validate_path'])


def create_app():
    """创建并配置 Flask 应用。"""
    resource_dir, root_dir = _get_app_dirs()

    # 创建 Flask 应用
    app = _create_flask_app(resource_dir)

    # 初始化数据库
    db = _init_database(app, root_dir)

    # 初始化安全组件
    csrf, limiter = _init_security(app)

    # 创建数据库表和默认管理员
    with app.app_context():
        db.create_all()
        init_default_admin()

    # 确保数据目录存在
    users_dir = os.path.join(root_dir, 'data', 'users')
    os.makedirs(users_dir, exist_ok=True)

    # 预加载组件
    _preload_components(root_dir)

    # 注册路由
    register_routes(app)

    # 配置限流规则
    _configure_rate_limits(app, limiter)

    # 配置CSRF豁免
    _configure_csrf_exemptions(app, csrf)

    return app


def init_default_admin():
    """初始化默认管理员账号。"""
    from src.models.user import User, db
    from src.auth.password import hash_password

    admin = User.query.filter_by(employee_id='Administrator').first()
    if not admin:
        admin = User(
            employee_id='Administrator',
            password_hash=hash_password('Admin@9000'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        logger.info("创建默认管理员账号: Administrator / Admin@9000")


# 创建应用实例
app = create_app()
