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


def create_app():
    """创建并配置 Flask 应用。"""
    # 获取项目根目录（支持打包）
    if getattr(sys, 'frozen', False):
        resource_dir = sys._MEIPASS
        root_dir = os.path.dirname(sys.executable)
    else:
        # 当前文件在 src/web/app.py，项目根目录是上两级
        resource_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        root_dir = resource_dir

    # 创建 Flask 应用，设置模板和静态文件夹
    app = Flask(
        __name__,
        template_folder=os.path.join(resource_dir, 'src', 'web', 'templates'),
        static_folder=os.path.join(resource_dir, 'src', 'web', 'static')
    )

    # 配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ai-log-analyzer-secret-key-change-in-production')

    # 安全检查：检测是否使用默认SECRET_KEY
    if app.config['SECRET_KEY'] == 'ai-log-analyzer-secret-key-change-in-production':
        logger.warning("=" * 60)
        logger.warning("安全警告: 正在使用默认 SECRET_KEY!")
        logger.warning("生产环境请设置环境变量: SECRET_KEY=<your-secret-key>")
        logger.warning("=" * 60)

    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 最大文件大小 50MB

    # 数据库配置
    db_path = os.path.join(root_dir, 'data', 'app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 初始化数据库
    from src.models.user import db
    from src.models.feedback import Feedback  # 确保 Feedback 表被创建
    db.init_app(app)

    # 初始化 Flask-Login
    from src.web.routes.auth_api import init_login_manager
    init_login_manager(app)

    # 初始化 CSRF 保护
    csrf = CSRFProtect(app)

    # 初始化 Flask-Limiter（限流保护）
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"  # 使用内存存储，适合单实例部署
    )
    # 存储limiter实例供其他模块使用
    app.extensions['limiter'] = limiter

    # 配置限流错误响应
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({
            'success': False,
            'error': '请求过于频繁，请稍后再试'
        }), 429

    # 创建数据库表和默认管理员
    with app.app_context():
        db.create_all()
        init_default_admin()

    # 确保数据目录存在
    users_dir = os.path.join(root_dir, 'data', 'users')
    os.makedirs(users_dir, exist_ok=True)

    # 预加载插件
    logger.info("正在预加载插件...")
    from plugins.manager import get_plugin_manager
    custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
    plugin_manager = get_plugin_manager(custom_dirs=[custom_plugins_dir])
    logger.info(f"可用插件: {[p.id for p in plugin_manager.get_all_plugins()]}")

    # 预加载Skill
    logger.info("正在预加载Skill...")
    from src.ai_analyzer.skill_loader import get_skill_loader
    skill_loader = get_skill_loader()
    skills = skill_loader.scan()
    logger.info(f"已加载 {len(skills)} 个Skill: {[s.name for s in skills]}")

    # 注册路由
    register_routes(app)

    # 为认证接口添加额外限流保护
    # 登录接口: 每IP每分钟5次
    limiter.limit("5 per minute")(app.view_functions['auth.do_login'])
    # 注册接口: 每IP每小时10次
    limiter.limit("10 per hour")(app.view_functions['auth.do_register'])

    # CSRF豁免：SSE流式端点无法使用标准CSRF Token
    csrf.exempt(app.view_functions['analyze_api.analyze_stream'])
    csrf.exempt(app.view_functions['analyze_api.analyze_local_stream'])
    csrf.exempt(app.view_functions['analyze_api.analyze_batch_stream'])

    # CSRF豁免：认证端点（使用限流保护）
    csrf.exempt(app.view_functions['auth.do_login'])
    csrf.exempt(app.view_functions['auth.do_register'])
    csrf.exempt(app.view_functions['auth.do_logout'])
    csrf.exempt(app.view_functions['auth.change_password'])

    # CSRF豁免：智能助手API（使用限流+认证保护）
    csrf.exempt(app.view_functions['assistant_api.create_session'])
    csrf.exempt(app.view_functions['assistant_api.delete_session'])
    csrf.exempt(app.view_functions['assistant_api.chat'])
    csrf.exempt(app.view_functions['assistant_api.chat_stream'])
    csrf.exempt(app.view_functions['assistant_api.upload_file'])

    # CSRF豁免：用户配置API（已使用登录保护）
    csrf.exempt(app.view_functions['user_config_api.reload_mcp_servers'])
    csrf.exempt(app.view_functions['user_config_api.toggle_mcp_server'])
    csrf.exempt(app.view_functions['user_config_api.toggle_skill'])

    # CSRF豁免：知识库API
    csrf.exempt(app.view_functions['kb_api.reload_kb'])

    # CSRF豁免：Skill API
    csrf.exempt(app.view_functions['skill_api.reload_skills'])

    # CSRF豁免：日志规则API（已使用登录保护）
    csrf.exempt(app.view_functions['log_metadata_api.create_rule_set'])
    csrf.exempt(app.view_functions['log_metadata_api.import_rule_set'])
    csrf.exempt(app.view_functions['log_metadata_api.update_rule_set'])
    csrf.exempt(app.view_functions['log_metadata_api.delete_rule_set'])
    csrf.exempt(app.view_functions['log_metadata_api.add_rule'])
    csrf.exempt(app.view_functions['log_metadata_api.update_rule'])
    csrf.exempt(app.view_functions['log_metadata_api.delete_rule'])

    # CSRF豁免：分析模板API（已使用登录保护）
    csrf.exempt(app.view_functions['admin_api.create_analysis_template'])
    csrf.exempt(app.view_functions['admin_api.update_user_analysis_template'])
    csrf.exempt(app.view_functions['admin_api.delete_user_analysis_template'])

    # CSRF豁免：缓存清理API（已使用登录保护）
    csrf.exempt(app.view_functions['cache_api.clear_temp'])
    csrf.exempt(app.view_functions['cache_api.clear_results'])

    # CSRF豁免：知识库API（已使用登录保护）
    csrf.exempt(app.view_functions['kb_api.create_kb'])
    csrf.exempt(app.view_functions['kb_api.upload_document'])
    csrf.exempt(app.view_functions['kb_api.reindex_kb'])

    # CSRF豁免：管理员API（已使用登录+管理员权限保护）
    csrf.exempt(app.view_functions['admin_api.update_config'])
    csrf.exempt(app.view_functions['admin_api.test_mcp_server'])
    csrf.exempt(app.view_functions['admin_api.add_mcp_server'])
    csrf.exempt(app.view_functions['admin_api.create_user'])
    csrf.exempt(app.view_functions['admin_api.update_user_quota'])
    csrf.exempt(app.view_functions['admin_api.reset_user_password'])
    csrf.exempt(app.view_functions['admin_api.toggle_user_active'])
    csrf.exempt(app.view_functions['feedback_api.reply_feedback'])

    # CSRF豁免：反馈API（已使用登录保护）
    csrf.exempt(app.view_functions['feedback_api.submit_feedback'])

    # CSRF豁免：历史API（已使用登录保护）
    csrf.exempt(app.view_functions['history_api.download_history'])

    # CSRF豁免：用户配置API（已使用登录保护）
    csrf.exempt(app.view_functions['user_config_api.update_user_config'])

    # CSRF豁免：分析API（已使用登录保护）
    csrf.exempt(app.view_functions['analyze_api.validate_local_path'])

    # CSRF豁免：日志查看API（已使用登录保护）
    csrf.exempt(app.view_functions['log_viewer_api.validate_path'])

    return app


def init_default_admin():
    """初始化默认管理员账号。"""
    from src.models.user import User, db
    from src.auth.password import hash_password

    # 检查是否已存在管理员
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