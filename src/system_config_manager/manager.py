"""
系统配置管理模块
负责系统配置的读取、修改和保存
支持环境变量占位符解析：${VAR_NAME}
"""

import json
import logging
import os
import re
import sys
from src.utils import get_logger

logger = get_logger('system_config_manager')

# 环境变量占位符模式：${VAR_NAME}
ENV_VAR_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')


def resolve_env_vars(value):
    """
    解析环境变量占位符

    Args:
        value: 配置值，可以是字符串或任意类型

    Returns:
        解析后的值，字符串中的 ${VAR_NAME} 会替换为对应的环境变量值
        如果环境变量不存在，保持原值不变
    """
    if isinstance(value, str):
        def replace_env_var(match):
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value is not None:
                logger.debug(f"解析环境变量: {var_name}")
                return env_value
            else:
                logger.warning(f"环境变量不存在: {var_name}")
                return match.group(0)
        return ENV_VAR_PATTERN.sub(replace_env_var, value)
    elif isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_vars(item) for item in value]
    else:
        return value


class SystemConfigManager:
    """系统配置管理器"""

    DEFAULT_SETTINGS = {
        "web": {
            "host": "127.0.0.1",
            "port": 18888,
            "debug": True
        },
        "api": {
            "base_url": "",
            "api_key": "",
            "model": "",
            "temperature": 0.7,
            "max_tokens": 4096
        },
        "orchestrator": {
            "max_rounds": 20,
            "tool_call_limit": 50,
            "compression_retain_rounds": 5,
            "context_limit": 120000,
            "compression_threshold": 0.8
        },
        "agent": {
            "max_tokens": 60000,
            "max_rounds": 10,
            "tool_call_limit": 20
        },
        "mcp_servers": {},
        "knowledge_base": {
            "default_id": "",
            "version": "1.0"
        },
        "bm25": {
            "k1": 1.5,
            "b": 0.75
        },
        "embedding": {
            "enabled": False,
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "text-embedding-3-small",
            "dimension": 1536,
            "batch_size": 100,
            "timeout": 60
        },
        "retrieval": {
            "mode": "bm25",
            "bm25_weight": 0.4,
            "vector_weight": 0.6,
            "top_n_multiplier": 2,
            "rrf_k": 60
        },
        "faiss": {
            "enabled": True,
            "index_type": "auto",
            "nlist": 100,
            "nprobe": 10,
            "use_gpu": False
        }
    }

    def __init__(self, settings_path=None):
        if settings_path is None:
            if getattr(sys, 'frozen', False):
                project_root = os.path.dirname(sys.executable)
            else:
                config_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(os.path.dirname(config_dir))
            new_path = os.path.join(project_root, "config", "system_config.json")
            old_path = os.path.join(project_root, "config", "settings.json")
            if os.path.exists(new_path):
                settings_path = new_path
            elif os.path.exists(old_path):
                logging.getLogger(__name__).warning(
                    "config/settings.json 已弃用，请重命名为 config/system_config.json"
                )
                settings_path = old_path
            else:
                settings_path = new_path
        self.settings_path = settings_path
        self.settings = self.load_settings()

    def load_settings(self):
        """加载设置文件并解析环境变量"""
        if os.path.exists(self.settings_path):
            with open(self.settings_path, 'r', encoding='utf-8') as f:
                raw_settings = json.load(f)
            return resolve_env_vars(raw_settings)
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

        支持点分隔的多层设置获取，如: get("api.base_url")
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

        支持点分隔的多层设置设置，如: set("api.base_url", "https://api.example.com")
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