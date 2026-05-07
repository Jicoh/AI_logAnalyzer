"""
Flask 应用工厂

通过 main.py web 启动。
"""

import os
import sys

from flask import Flask
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