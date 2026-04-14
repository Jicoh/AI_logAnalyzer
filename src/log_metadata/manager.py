"""
日志文件元数据管理模块
管理日志文件的描述规则，用于 AI 智能选择
"""

import os
import json
import uuid
from typing import Dict, List, Optional, Any


class LogMetadataManager:
    """日志文件元数据管理器"""

    def __init__(self, config_path=None):
        """
        初始化日志元数据管理器

        Args:
            config_path: 配置文件路径，默认为 config/log_metadata.json
        """
        if config_path is None:
            config_path = self.get_default_config_path()
        self.config_path = config_path
        self.config = self.load_config()

        # 规则集管理
        self.rules_config_path = self.get_rules_config_path()
        self.rules_config = self.load_rules_config()

    def get_default_config_path(self):
        """获取默认配置文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'log_metadata.json')

    def get_rules_config_path(self):
        """获取规则集配置文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'log_metadata_rules.json')

    def load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'log_rules': {},
            'file_descriptions': {}
        }

    def load_rules_config(self):
        """加载规则集配置文件"""
        if os.path.exists(self.rules_config_path):
            with open(self.rules_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        # 创建空规则集配置（不再创建默认规则集）
        default_config = {
            'rule_sets': {}
        }
        self.save_rules_config(default_config)
        return default_config

    def save_config(self):
        """保存配置文件"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

    def save_rules_config(self, config=None):
        """保存规则集配置文件"""
        if config is None:
            config = self.rules_config
        os.makedirs(os.path.dirname(self.rules_config_path), exist_ok=True)
        with open(self.rules_config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    # ==================== 规则集管理 ====================

    def list_rule_sets(self) -> List[Dict]:
        """
        列出所有规则集

        Returns:
            list: 规则集列表，每个元素包含 rules_id, name, description, rule_count
        """
        result = []
        for rules_id, rules_set in self.rules_config.get('rule_sets', {}).items():
            result.append({
                'rules_id': rules_id,
                'name': rules_set.get('name', rules_id),
                'description': rules_set.get('description', ''),
                'rule_count': len(rules_set.get('rules', {}))
            })
        return result

    def get_rule_set(self, rules_id: str) -> Optional[Dict]:
        """
        获取指定规则集详情

        Args:
            rules_id: 规则集ID

        Returns:
            dict: 规则集详情，包含 rules_id, name, description, rules, is_active
        """
        rule_sets = self.rules_config.get('rule_sets', {})
        if rules_id not in rule_sets:
            return None

        rules_set = rule_sets[rules_id]
        rules_list = []
        for rule_id, rule in rules_set.get('rules', {}).items():
            rules_list.append({
                'rule_id': rule_id,
                'file_path': rule.get('file_path', ''),
                'description': rule.get('description', ''),
                'keywords': rule.get('keywords', []),
                'suggested_plugins': rule.get('suggested_plugins', [])
            })

        return {
            'rules_id': rules_id,
            'name': rules_set.get('name', rules_id),
            'description': rules_set.get('description', ''),
            'rules': rules_list
        }

    def create_rule_set(self, name: str, description: str = '') -> str:
        """
        创建新规则集

        Args:
            name: 规则集名称
            description: 规则集描述

        Returns:
            str: 新规则集ID
        """
        rules_id = f"custom_{uuid.uuid4().hex[:8]}"
        self.rules_config['rule_sets'][rules_id] = {
            'name': name,
            'description': description,
            'rules': {}
        }
        self.save_rules_config()
        return rules_id

    def update_rule_set(self, rules_id: str, name: str = None, description: str = None) -> bool:
        """
        更新规则集信息

        Args:
            rules_id: 规则集ID
            name: 新名称（可选）
            description: 新描述（可选）

        Returns:
            bool: 是否成功
        """
        if rules_id not in self.rules_config.get('rule_sets', {}):
            return False

        rule_set = self.rules_config['rule_sets'][rules_id]
        if name is not None:
            rule_set['name'] = name
        if description is not None:
            rule_set['description'] = description

        self.save_rules_config()
        return True

    def delete_rule_set(self, rules_id: str) -> bool:
        """
        删除规则集

        Args:
            rules_id: 规则集ID

        Returns:
            bool: 是否成功
        """
        if rules_id not in self.rules_config.get('rule_sets', {}):
            return False

        del self.rules_config['rule_sets'][rules_id]
        self.save_rules_config()
        return True

    # ==================== 规则管理 ====================

    def add_rule_to_set(self, rules_id: str, rule: Dict) -> str:
        """
        向规则集添加规则

        Args:
            rules_id: 规则集ID
            rule: 规则内容，包含 file_path, description, keywords, suggested_plugins

        Returns:
            str: 规则ID
        """
        if rules_id not in self.rules_config.get('rule_sets', {}):
            return None

        file_path = rule.get('file_path', '').strip()
        if not file_path:
            return None

        rule_id = f"rule_{uuid.uuid4().hex[:8]}"
        self.rules_config['rule_sets'][rules_id]['rules'][rule_id] = {
            'file_path': file_path,
            'description': rule.get('description', ''),
            'keywords': rule.get('keywords', []),
            'suggested_plugins': rule.get('suggested_plugins', [])
        }
        self.save_rules_config()
        return rule_id

    def update_rule_in_set(self, rules_id: str, rule_id: str, rule: Dict) -> bool:
        """
        更新规则集中的规则

        Args:
            rules_id: 规则集ID
            rule_id: 规则ID
            rule: 更新的规则内容

        Returns:
            bool: 是否成功
        """
        if rules_id not in self.rules_config.get('rule_sets', {}):
            return False

        rules = self.rules_config['rule_sets'][rules_id].get('rules', {})
        if rule_id not in rules:
            return False

        existing_rule = rules[rule_id]
        if 'file_path' in rule:
            existing_rule['file_path'] = rule['file_path']
        existing_rule['description'] = rule.get('description', existing_rule.get('description', ''))
        existing_rule['keywords'] = rule.get('keywords', existing_rule.get('keywords', []))
        existing_rule['suggested_plugins'] = rule.get('suggested_plugins', existing_rule.get('suggested_plugins', []))

        self.save_rules_config()
        return True

    def remove_rule_from_set(self, rules_id: str, rule_id: str) -> bool:
        """
        从规则集移除规则

        Args:
            rules_id: 规则集ID
            rule_id: 规则ID

        Returns:
            bool: 是否成功
        """
        if rules_id not in self.rules_config.get('rule_sets', {}):
            return False

        rules = self.rules_config['rule_sets'][rules_id].get('rules', {})
        if rule_id not in rules:
            return False

        del rules[rule_id]
        self.save_rules_config()
        return True

    def get_rule_from_set(self, rules_id: str, rule_id: str) -> Optional[Dict]:
        """
        获取规则集中的单个规则

        Args:
            rules_id: 规则集ID
            rule_id: 规则ID

        Returns:
            dict: 规则详情
        """
        if rules_id not in self.rules_config.get('rule_sets', {}):
            return None

        rules = self.rules_config['rule_sets'][rules_id].get('rules', {})
        if rule_id not in rules:
            return None

        rule = rules[rule_id]
        return {
            'rule_id': rule_id,
            'file_path': rule.get('file_path', ''),
            'description': rule.get('description', ''),
            'keywords': rule.get('keywords', []),
            'suggested_plugins': rule.get('suggested_plugins', [])
        }

    # ==================== 文件匹配（使用激活规则集） ====================

    def match_file(self, file_path: str, rules_id: str = None) -> Optional[Dict]:
        """
        匹配文件路径，返回匹配的规则

        Args:
            file_path: 文件路径
            rules_id: 规则集ID（必须指定）

        Returns:
            dict: 匹配的规则信息，若无匹配则返回 None
        """
        if rules_id is None:
            return None

        rule_set = self.rules_config.get('rule_sets', {}).get(rules_id, {})
        rules = rule_set.get('rules', {})

        # 精确匹配路径
        for rule_id, rule in rules.items():
            rule_path = rule.get('file_path', '').strip()
            if rule_path and file_path == rule_path:
                return {
                    'rule_id': rule_id,
                    'file_path': rule_path,
                    'description': rule.get('description', ''),
                    'keywords': rule.get('keywords', []),
                    'suggested_plugins': rule.get('suggested_plugins', [])
                }

        return None

    def get_description_for_file(self, file_path: str, rules_id: str = None) -> Dict:
        """
        获取文件的描述信息

        Args:
            file_path: 文件路径
            rules_id: 规则集ID（可选）

        Returns:
            dict: 文件描述信息
        """
        # 先检查是否有自定义描述
        if file_path in self.config['file_descriptions']:
            return self.config['file_descriptions'][file_path]

        # 再检查规则匹配
        matched_rule = self.match_file(file_path, rules_id)
        if matched_rule:
            return {
                'description': matched_rule['description'],
                'keywords': matched_rule['keywords'],
                'suggested_plugins': matched_rule['suggested_plugins'],
                'source': 'rule',
                'rule_id': matched_rule['rule_id']
            }

        # 无匹配，返回基本信息
        filename = os.path.basename(file_path)
        return {
            'description': f'日志文件: {filename}',
            'keywords': [],
            'suggested_plugins': [],
            'source': 'default'
        }

    def set_description_for_file(self, file_path: str, description: Dict) -> None:
        """
        设置文件的自定义描述

        Args:
            file_path: 文件路径
            description: 描述信息字典
        """
        self.config['file_descriptions'][file_path] = description
        self.save_config()

    def get_file_descriptions(self, file_paths: List[str], rules_id: str = None) -> str:
        """
        获取多个文件的 AI 描述文本

        Args:
            file_paths: 文件路径列表
            rules_id: 规则集ID（可选）

        Returns:
            str: AI 可读的文件描述文本
        """
        descriptions = []
        for file_path in file_paths:
            desc = self.get_description_for_file(file_path, rules_id)
            filename = os.path.basename(file_path)
            desc_text = f"- {filename}\n"
            desc_text += f"  描述: {desc['description']}\n"
            if desc['keywords']:
                desc_text += f"  关键词: {', '.join(desc['keywords'])}\n"
            if desc['suggested_plugins']:
                desc_text += f"  建议插件: {', '.join(desc['suggested_plugins'])}\n"
            descriptions.append(desc_text)

        return "\n".join(descriptions)

    def clear_file_descriptions(self) -> None:
        """清除所有自定义文件描述"""
        self.config['file_descriptions'] = {}
        self.save_config()