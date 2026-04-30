"""
Skill加载器模块
扫描和解析SKILL.md文件，提供Skill信息查询接口
"""

import os
import yaml
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from src.utils import get_logger

logger = get_logger('skill_loader')


@dataclass
class SkillInfo:
    """Skill信息"""
    name: str
    description: str
    allowed_tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    content: str = ""
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "allowed_tools": self.allowed_tools,
            "metadata": self.metadata,
            "content": self.content,
            "path": self.path
        }


class SkillLoader:
    """Skill加载器"""

    def __init__(self, skills_dir: str = None):
        """
        初始化SkillLoader

        Args:
            skills_dir: Skill目录路径，默认为项目根目录下的config/skills
        """
        if skills_dir is None:
            # 获取项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            skills_dir = os.path.join(project_root, 'config', 'skills')

        self.skills_dir = skills_dir
        self._skills: Dict[str, SkillInfo] = {}
        self._loaded = False

    def _parse_frontmatter(self, content: str) -> tuple:
        """
        解析YAML frontmatter

        Args:
            content: 文件内容

        Returns:
            tuple: (frontmatter_dict, markdown_content)
        """
        # 检查是否以---开头
        if not content.strip().startswith('---'):
            return {}, content

        # 找到第二个---
        lines = content.split('\n')
        end_index = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                end_index = i
                break

        if end_index == -1:
            return {}, content

        # 解析YAML
        yaml_content = '\n'.join(lines[1:end_index])
        try:
            frontmatter = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError as e:
            logger.warning(f"YAML解析失败: {str(e)}")
            frontmatter = {}

        # 剩余内容是Markdown正文
        markdown_content = '\n'.join(lines[end_index + 1:])

        return frontmatter, markdown_content

    def _load_skill_file(self, file_path: str) -> Optional[SkillInfo]:
        """
        加载单个SKILL.md文件

        Args:
            file_path: 文件路径

        Returns:
            SkillInfo: Skill信息，解析失败时返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            frontmatter, markdown_content = self._parse_frontmatter(content)

            # 提取必要字段
            name = frontmatter.get('name', '')
            if not name:
                logger.warning(f"Skill缺少name字段: {file_path}")
                return None

            description = frontmatter.get('description', '')
            allowed_tools = frontmatter.get('allowed-tools', [])
            if isinstance(allowed_tools, str):
                allowed_tools = allowed_tools.split()
            metadata = frontmatter.get('metadata', {})

            return SkillInfo(
                name=name,
                description=description,
                allowed_tools=allowed_tools,
                metadata=metadata,
                content=markdown_content.strip(),
                path=file_path
            )

        except Exception as e:
            logger.error(f"加载Skill文件失败: {file_path}, {str(e)}")
            return None

    def scan(self) -> List[SkillInfo]:
        """
        扫描所有SKILL.md文件

        Returns:
            List[SkillInfo]: Skill信息列表
        """
        if not os.path.exists(self.skills_dir):
            logger.warning(f"Skill目录不存在: {self.skills_dir}")
            return []

        skills = []

        # 遍历子目录
        for item in os.listdir(self.skills_dir):
            item_path = os.path.join(self.skills_dir, item)
            if not os.path.isdir(item_path):
                continue

            # 查找SKILL.md文件
            skill_file = os.path.join(item_path, 'SKILL.md')
            if not os.path.exists(skill_file):
                continue

            skill_info = self._load_skill_file(skill_file)
            if skill_info:
                skills.append(skill_info)
                self._skills[skill_info.name] = skill_info
                logger.debug(f"加载Skill: {skill_info.name}")

        self._loaded = True
        logger.info(f"扫描完成，共加载 {len(skills)} 个Skill")
        return skills

    def get(self, name: str) -> Optional[SkillInfo]:
        """
        获取单个Skill信息

        Args:
            name: Skill名称

        Returns:
            SkillInfo: Skill信息，不存在时返回None
        """
        # 如果未加载过，先扫描
        if not self._loaded:
            self.scan()

        return self._skills.get(name)

    def list_all(self) -> List[Dict[str, Any]]:
        """
        获取所有Skill信息（字典格式）

        Returns:
            List[Dict]: Skill信息列表
        """
        # 如果未加载过，先扫描
        if not self._loaded:
            self.scan()

        return [skill.to_dict() for skill in self._skills.values()]

    def reload(self) -> List[SkillInfo]:
        """
        强制重新扫描

        Returns:
            List[SkillInfo]: Skill信息列表
        """
        self._skills.clear()
        self._loaded = False
        return self.scan()

    def has(self, name: str) -> bool:
        """
        检查Skill是否存在

        Args:
            name: Skill名称

        Returns:
            bool: 是否存在
        """
        if not self._loaded:
            self.scan()
        return name in self._skills


# 全局SkillLoader实例
_loader = None


def get_skill_loader() -> SkillLoader:
    """获取全局SkillLoader实例"""
    global _loader
    if _loader is None:
        _loader = SkillLoader()
    return _loader