"""
配置管理模块
负责AI配置的读取、修改和保存
"""

import json
import os


class ConfigManager:
    """AI配置管理器"""

    DEFAULT_CONFIG = {
        "api": {
            "base_url": "",
            "api_key": "",
            "model": "",
            "temperature": 0.7,
            "max_tokens": 4096
        },
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

    def __init__(self, config_path=None):
        if config_path is None:
            config_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(config_dir))
            config_path = os.path.join(project_root, "config", "ai_config.json")
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self._create_default_config()

    def _create_default_config(self):
        """创建默认配置"""
        config_dir = os.path.dirname(self.config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        return self.DEFAULT_CONFIG.copy()

    def get(self, key, default=None):
        """
        获取配置项

        支持点分隔的多层配置获取，如: get("api.base_url")
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

        支持点分隔的多层配置设置，如: set("api.base_url", "https://api.example.com")
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
        config_dir = os.path.dirname(self.config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

    def reload(self):
        """重新加载配置文件"""
        self.config = self._load_config()

    def get_all(self):
        """获取所有配置"""
        return self.config.copy()

    def update(self, config_dict):
        """批量更新配置"""
        def deep_update(target, source):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_update(target[key], value)
                else:
                    target[key] = value
        deep_update(self.config, config_dict)