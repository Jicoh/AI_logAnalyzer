"""
用户配置管理模块
负责用户级别配置的读取、修改和保存
配置文件存储在用户工作空间：data/users/{employee_id}/user_config.json
"""

import json
import os
from src.utils.file_utils import get_user_data_dir
from src.utils import get_logger

logger = get_logger('user_config')


class UserConfigManager:
    """用户配置管理器"""

    DEFAULT_CONFIG = {
        "selected_plugins": [],
        "selected_kb_id": "",
        "selected_log_rules_id": "",
        "default_kb_id": "",
        "default_log_rules_id": "",
        "enable_ai": True,
        "ai_selection_mode": False,
        "last_selected_category": "CloudBMC"
    }

    def __init__(self, user_id: str):
        self.user_id = user_id
        user_dir = get_user_data_dir(user_id)
        self.config_path = os.path.join(user_dir, "user_config.json")
        self.config = self.load_config()

    def load_config(self):
        """加载用户配置文件"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 合并缺失的默认字段
                for key, value in self.DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                return config
            except Exception as e:
                logger.error(f"加载用户配置失败: {self.user_id}, {str(e)}")
                return self.create_default_config()
        return self.create_default_config()

    def create_default_config(self):
        """创建默认配置"""
        # 尝试从模板加载
        template_path = self._get_template_path()
        if os.path.exists(template_path):
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    template = json.load(f)
                logger.info(f"从模板创建用户配置: {self.user_id}")
                self._save_config(template)
                return template
            except Exception as e:
                logger.warning(f"加载模板失败: {str(e)}")

        # 使用默认配置
        logger.info(f"创建默认用户配置: {self.user_id}")
        self._save_config(self.DEFAULT_CONFIG)
        return self.DEFAULT_CONFIG.copy()

    def _get_template_path(self):
        """获取模板文件路径"""
        from src.utils.file_utils import get_project_root
        return os.path.join(get_project_root(), "config", "user_config_template.json")

    def _save_config(self, config):
        """保存配置到文件"""
        config_dir = os.path.dirname(self.config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    def get(self, key, default=None):
        """
        获取配置项

        支持点分隔的多层配置获取，如: get("selected_kb_id")
        """
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key, value):
        """
        设置配置项

        支持点分隔的多层配置设置
        """
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def save(self):
        """保存配置到文件"""
        self._save_config(self.config)

    def reload(self):
        """重新加载配置文件"""
        self.config = self.load_config()

    def get_all(self):
        """获取所有配置"""
        return self.config.copy()

    def update(self, config_dict):
        """批量更新配置"""
        for key, value in config_dict.items():
            if key in self.DEFAULT_CONFIG:
                self.config[key] = value