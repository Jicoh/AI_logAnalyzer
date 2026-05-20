"""
系统提示构建器

根据当前可用的skill、subagent、mcp工具、知识库信息，动态构建系统提示词
"""

import json
import os
from typing import Dict, Any, List

from src.utils import get_logger

logger = get_logger('prompt_builder')


class SystemPromptBuilder:
    """系统提示构建器

    根据当前可用的skill、subagent、mcp工具、知识库信息，
    动态构建系统提示词
    """

    def __init__(self, skill_loader, subagent_registry, prompt_path: str = None):
        self.skill_loader = skill_loader
        self.subagent_registry = subagent_registry
        self.prompt_path = prompt_path or self._default_prompt_path()

    def _default_prompt_path(self) -> str:
        """获取默认prompt文件路径"""
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(current_dir, 'prompts', 'orchestrator_prompt.txt')

    def load_template(self) -> str:
        """加载prompt模板"""
        if os.path.exists(self.prompt_path):
            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        return self._default_template()

    def _default_template(self) -> str:
        """默认prompt模板"""
        return """你是智能助手的编排器，负责理解用户意图并协调各种专业技能完成复杂任务。

# 角色定位

你是用户与专业技能之间的桥梁，职责包括:
1. 理解用户意图，判断任务类型
2. 根据需要选择合适的技能(Skill)来处理请求
3. 可直接调用MCP工具处理简单请求
4. 维护对话上下文，确保沟通连贯

# 可用技能

{available_skills}

# 可用Subagent

{available_subagents}

# 当前会话状态

- 工作目录: {work_dir}
- 上下文使用率: {context_usage}%

# 工作原则

1. 简单请求直接处理，复杂任务调度Subagent
2. 关注上下文使用率，必要时主动压缩
3. 将专业结果整合为用户友好的回复"""

    def build(self, session_context: Dict) -> str:
        """构建系统提示

        Args:
            session_context: 会话上下文，包含:
                - work_dir: 工作目录
                - context_usage_ratio: 上下文使用率(0-1)
                - kb_context: 知识库上下文(可选)
                - uploaded_files: 已上传文件列表
                - notes: 会话笔记

        Returns:
            str: 构建好的系统提示词
        """
        template = self.load_template()

        # 获取可用Skill列表
        available_skills = []
        if self.skill_loader:
            for skill in self.skill_loader.list_all():
                skill_name = skill.get('name', '')
                skill_desc = skill.get('description', '')
                skill_content = skill.get('content', '')
                skill_info = f"## {skill_name}\n{skill_desc}\n"
                if skill_content:
                    skill_info += f"\n{skill_content}\n"
                available_skills.append(skill_info)

        # 获取可用Subagent列表
        subagent_list = []
        if self.subagent_registry:
            for info in self.subagent_registry.list_all():
                subagent_desc = f"- {info['name']}: {info['description']}"
                if info.get('capabilities'):
                    subagent_desc += f" (能力: {', '.join(info['capabilities'])})"
                subagent_list.append(subagent_desc)

        # 知识库上下文
        kb_context_section = ""
        kb_context = session_context.get('kb_context', '')
        if kb_context:
            kb_context_section = f"\n# 相关知识库内容\n\n{kb_context}\n"

        uploaded_files = session_context.get('uploaded_files', [])
        notes = session_context.get('notes', {})
        context_usage = session_context.get('context_usage_ratio', 0.0)

        prompt_data = {
            'available_skills': '\n'.join(available_skills) if available_skills else '暂无可用技能',
            'available_subagents': '\n'.join(subagent_list) if subagent_list else '暂无可用Subagent',
            'work_dir': session_context.get('work_dir', ''),
            'context_usage': f"{context_usage * 100:.1f}",
            'uploaded_files': ', '.join(uploaded_files) or '无',
            'notes': json.dumps(notes, ensure_ascii=False) or '{}',
            'kb_context': kb_context_section
        }

        def _escape_braces(text):
            if not text:
                return ""
            return text.replace('{', '{{').replace('}', '}}')

        return template.format(**{k: _escape_braces(v) for k, v in prompt_data.items()})
