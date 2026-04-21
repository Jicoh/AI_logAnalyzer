"""
通用设置管理模块
负责用户偏好设置的读取、修改和保存
"""

import json
import os
import sys


class SettingsManager:
    """通用设置管理器"""

    DEFAULT_SETTINGS = {
        "log_viewer": {
            "enabled": False,
            "exe_path": ""
        }
    }

    def __init__(self, settings_path=None):
        if settings_path is None:
            if getattr(sys, 'frozen', False):
                project_root = os.path.dirname(sys.executable)
            else:
                config_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(os.path.dirname(config_dir))
            settings_path = os.path.join(project_root, "config", "settings.json")
        self.settings_path = settings_path
        self.settings = self.load_settings()

    def load_settings(self):
        """加载设置文件"""
        if os.path.exists(self.settings_path):
            with open(self.settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self.create_default_settings()

    def create_default_settings(self):
        """创建默认设置"""
        config_dir = os.path.dirname(self.settings_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(self.settings_path, 'w', encoding='utf-8') as f:
            json.dump(self.DEFAULT_SETTINGS, f, indent=4, ensure_ascii=False)
        return self.DEFAULT_SETTINGS.copy()

    def get(self, key, default=None):
        """
        获取设置项

        支持点分隔的多层设置获取，如: get("log_viewer.enabled")
        """
        keys = key.split('.')
        value = self.settings
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key, value):
        """
        设置设置项

        支持点分隔的多层设置设置，如: set("log_viewer.enabled", True)
        """
        keys = key.split('.')
        settings = self.settings
        for k in keys[:-1]:
            if k not in settings:
                settings[k] = {}
            settings = settings[k]
        settings[keys[-1]] = value

    def save(self):
        """保存设置到文件"""
        config_dir = os.path.dirname(self.settings_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(self.settings_path, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=4, ensure_ascii=False)

    def reload(self):
        """重新加载设置文件"""
        self.settings = self.load_settings()

    def get_all(self):
        """获取所有设置"""
        return self.settings.copy()

    def update(self, settings_dict):
        """批量更新设置"""
        def deep_update(target, source):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_update(target[key], value)
                else:
                    target[key] = value
        deep_update(self.settings, settings_dict)