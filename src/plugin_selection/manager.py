"""
插件选择状态管理模块
负责插件选择和AI设置的读取、修改和保存
"""

import json
import os


class PluginSelectionManager:
    """插件选择和AI设置管理器"""

    DEFAULT_CONFIG = {
        "selected_plugins": ["log_parser"],
        "selected_kb_id": "",
        "selected_log_rules_id": "",
        "enable_ai": True,
        "ai_selection_mode": False
    }

    def __init__(self, config_path=None):
        if config_path is None:
            config_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(config_dir))
            config_path = os.path.join(project_root, "config", "plugin_selection.json")
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self.create_default_config()

    def create_default_config(self):
        """创建默认配置"""
        config_dir = os.path.dirname(self.config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        return self.DEFAULT_CONFIG.copy()

    def get(self, key, default=None):
        """获取配置项"""
        if key in self.config:
            return self.config[key]
        return default

    def set(self, key, value):
        """设置配置项"""
        self.config[key] = value

    def save(self):
        """保存配置到文件"""
        config_dir = os.path.dirname(self.config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

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