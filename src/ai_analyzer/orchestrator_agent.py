"""
Orchestrator Agent - 主Agent编排器
理解用户意图，调度Subagent/MCP工具，管理对话上下文
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from .client import AIClient, AIResponse
from .subagent_registry import SubagentRegistry, get_registry
from .mcp_client import MCPClient
from src.session_manager.manager import SessionManager
from src.config_manager.manager import ConfigManager
from src.knowledge_base.manager import KnowledgeBaseManager
from src.utils import get_logger

logger = get_logger('orchestrator_agent')


@dataclass
class ContextState:
    """上下文状态"""
    total_limit: int = 120000
    used_tokens: int = 0
    available_tokens: int = 0
    usage_ratio: float = 0.0
    needs_compression: bool = False

    def update(self, used: int):
        """更新状态"""
        self.used_tokens = used
        self.available_tokens = self.total_limit - used
        self.usage_ratio = used / self.total_limit if self.total_limit > 0 else 0
        self.needs_compression = self.usage_ratio >= 0.8


# Orchestrator内置工具定义
ORCHESTRATOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_session_state",
            "description": "获取当前会话的状态信息，包括工作目录、上下文使用率、已执行操作等。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_session_note",
            "description": "保存重要信息到会话状态，供后续查询使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "信息键名"
                    },
                    "value": {
                        "type": "string",
                        "description": "信息内容"
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_tools",
            "description": "列出所有可用的工具，包括内置工具、MCP工具和Subagent。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_subagent",
            "description": "调用指定的Subagent执行专业任务。必须传递user_intent参数，包含用户的具体关注点，确保分析报告能针对性回答用户问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_name": {
                        "type": "string",
                        "description": "Subagent名称，如 log_analyzer"
                    },
                    "request": {
                        "type": "string",
                        "description": "给Subagent的任务描述"
                    },
                    "user_intent": {
                        "type": "string",
                        "description": "用户的具体意图/关注点。例如：用户问'为什么重启'，user_intent应为'分析重启事件及其原因'"
                    }
                },
                "required": ["subagent_name", "request"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "upload_log_file",
            "description": "上传日志文件到会话工作目录，准备进行分析。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "日志文件路径（本地路径或压缩包路径）"
                    }
                },
                "required": ["file_path"]
            }
        }
    }
]

ORCHESTRATOR_TOOL_NAMES = [t["function"]["name"] for t in ORCHESTRATOR_TOOLS]


class OrchestratorAgent:
    """主Agent编排器"""

    def __init__(
        self,
        user_id: str,
        session_id: str,
        config_manager: ConfigManager = None,
        kb_manager: KnowledgeBaseManager = None,
        mcp_client: MCPClient = None
    ):
        """
        初始化OrchestratorAgent

        Args:
            user_id: 用户ID
            session_id: 会话ID
            config_manager: 配置管理器
            kb_manager: 知识库管理器
            mcp_client: MCP客户端
        """
        self.user_id = user_id
        self.session_id = session_id

        # 配置管理器
        if config_manager is None:
            config_manager = ConfigManager()
        self.config_manager = config_manager

        # 加载Orchestrator配置
        self._load_config()

        # 初始化AI客户端（Orchestrator专用）
        orchestrator_api_config = self._get_orchestrator_api_config()
        self.client = AIClient(orchestrator_api_config)

        # Subagent注册表
        self.subagent_registry = get_registry()

        # 知识库管理器
        self.kb_manager = kb_manager

        # MCP客户端
        self.mcp_client = mcp_client

        # 会话管理
        self.session_manager = SessionManager(user_id)
        self.session = self.session_manager.get_session(session_id)

        if not self.session:
            raise ValueError(f"会话不存在: {session_id}")

        # 工作目录
        self.work_dir = self.session.work_dir
        self.outputs_dir = self.session.outputs_dir

        # 对话历史（从会话加载）
        self.conversation_history: List[Dict] = []
        for msg in self.session.conversation:
            self.conversation_history.append({
                "role": msg.role,
                "content": msg.content
            })

        # 上下文状态
        self.context_state = ContextState(total_limit=self.context_limit)

        # 会话状态
        self.session_state = self.session.state.copy()
        self.session_state.setdefault("notes", {})
        self.session_state.setdefault("uploaded_files", [])
        self.session_state.setdefault("subagent_calls", 0)
        self.session_state.setdefault("tool_calls", 0)

        # 工具列表（内置 + MCP）
        self.tools = self._build_tools()

        # Prompt路径
        self.prompt_path = self._get_prompt_path()

        logger.info(f"OrchestratorAgent初始化完成: user={user_id}, session={session_id}")

    def _load_config(self):
        """加载Orchestrator配置"""
        orchestrator_config = self.config_manager.get('orchestrator', {})
        self.max_rounds = orchestrator_config.get('max_rounds', 20)
        self.tool_call_limit = orchestrator_config.get('tool_call_limit', 50)
        self.enable_mcp_tools = orchestrator_config.get('enable_mcp_tools', True)
        self.compression_retain_rounds = orchestrator_config.get('compression_retain_rounds', 5)

        # 上下文限制（从orchestrator配置块读取）
        self.context_limit = orchestrator_config.get('context_limit', 120000)
        self.compression_threshold = orchestrator_config.get('compression_threshold', 0.8)

    def _get_orchestrator_api_config(self) -> Dict:
        """获取Orchestrator API配置 - 直接使用api配置"""
        return self.config_manager.get('api', {})

    def _get_subagent_api_config(self, subagent_name: str = None) -> Dict:
        """
        获取Subagent API配置

        Args:
            subagent_name: Subagent名称，如 'log_analyzer'

        Returns:
            Dict: API配置，按名称查找，没配置则回退到api
        """
        if subagent_name:
            subagent_apis = self.config_manager.get('subagent_api', {})
            specific_config = subagent_apis.get(subagent_name, {})

            # 检查是否有有效配置（至少有base_url和api_key）
            if specific_config.get('base_url') and specific_config.get('api_key'):
                return {
                    'base_url': specific_config.get('base_url'),
                    'api_key': specific_config.get('api_key'),
                    'model': specific_config.get('model'),
                    'temperature': specific_config.get('temperature', 0.1),
                    'max_tokens': specific_config.get('max_tokens', 60000)
                }

        # 回退到默认api配置
        return self.config_manager.get('api', {})

    def _get_prompt_path(self) -> str:
        """获取prompt文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'orchestrator_prompt.txt')

    def _build_tools(self) -> List[Dict]:
        """构建工具列表（内置 + MCP）"""
        tools = ORCHESTRATOR_TOOLS.copy()

        if self.enable_mcp_tools and self.mcp_client:
            mcp_tools = self.mcp_client.list_tools()
            tools.extend(mcp_tools)
            logger.debug(f"已加载 {len(mcp_tools)} 个MCP工具")

        return tools

    def _load_prompt(self) -> str:
        """加载prompt模板"""
        if os.path.exists(self.prompt_path):
            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        return self._default_prompt()

    def _default_prompt(self) -> str:
        """默认prompt"""
        return """你是智能助手的编排器，负责理解用户意图并协调各种专业技能完成复杂任务。

# 角色定位

你是用户与专业技能之间的桥梁，职责包括:
1. 理解用户意图，判断任务类型
2. 选择合适的技能(Subagent)来执行专业任务
3. 可直接调用MCP工具处理简单请求
4. 维护对话上下文，确保沟通连贯

# 可用技能

{available_skills}

# 当前会话状态

- 工作目录: {work_dir}
- 上下文使用率: {context_usage}%

# 工作原则

1. 简单请求直接处理，复杂任务调度Subagent
2. 关注上下文使用率，必要时主动压缩
3. 将专业结果整合为用户友好的回复"""

    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        prompt_template = self._load_prompt()

        # 获取可用Subagent列表
        available_skills = []
        for info in self.subagent_registry.list_all():
            skill_desc = f"- {info['name']}: {info['description']}"
            if info.get('capabilities'):
                skill_desc += f" (能力: {', '.join(info['capabilities'])})"
            available_skills.append(skill_desc)

        # 填充模板
        prompt_data = {
            'available_skills': '\n'.join(available_skills) if available_skills else '暂无可用技能',
            'work_dir': self.work_dir,
            'context_usage': f"{self.context_state.usage_ratio * 100:.1f}",
            'uploaded_files': ', '.join(self.session_state.get('uploaded_files', [])) or '无',
            'notes': json.dumps(self.session_state.get('notes', {}), ensure_ascii=False) or '{}'
        }

        # 转义花括号
        def escape_braces(text):
            if not text:
                return ""
            return text.replace('{', '{{').replace('}', '}}')

        return prompt_template.format(**{k: escape_braces(v) for k, v in prompt_data.items()})

    def _calculate_context_usage(self, messages: List[Dict]) -> int:
        """计算上下文使用量"""
        return self.client.count_tokens(messages)

    def _compress_context(self, messages: List[Dict]) -> List[Dict]:
        """压缩上下文"""
        if len(messages) <= 2:
            return messages

        logger.info("开始压缩上下文...")

        # 保留system消息和最近N轮对话
        retain_rounds = self.compression_retain_rounds * 2  # 每轮包含user+assistant
        system_message = messages[0] if messages and messages[0].get('role') == 'system' else None

        # 分离要压缩的内容
        if system_message:
            recent_messages = messages[-retain_rounds:] if len(messages) > retain_rounds + 1 else messages[1:]
            to_compress = messages[1:-retain_rounds] if len(messages) > retain_rounds + 1 else []
        else:
            recent_messages = messages[-retain_rounds:] if len(messages) > retain_rounds else messages
            to_compress = messages[:-retain_rounds] if len(messages) > retain_rounds else []

        if not to_compress:
            return messages

        # 生成压缩摘要
        compression_prompt = f"""请将以下对话历史压缩为简洁摘要，保留关键信息。

# 对话历史
{json.dumps(to_compress, ensure_ascii=False, indent=2)}

# 输出要求
1. 保留关键决策和结论
2. 保留用户的重要需求
3. 记录已执行的操作
4. 格式：几条关键要点，每条不超过50字

请输出摘要："""

        try:
            summary_response = self.client.chat_with_tools([
                {"role": "user", "content": compression_prompt}
            ])
            summary = summary_response.content or "对话历史已压缩"

            # 构建新消息列表
            new_messages = []
            if system_message:
                new_messages.append(system_message)

            # 添加摘要消息
            new_messages.append({
                "role": "user",
                "content": f"[历史摘要] {summary}"
            })
            new_messages.append({
                "role": "assistant",
                "content": "我已了解之前的对话内容，继续为您服务。"
            })

            # 添加最近的对话
            new_messages.extend(recent_messages)

            # 验证压缩效果
            new_tokens = self._calculate_context_usage(new_messages)
            logger.info(f"压缩完成: {len(messages)} -> {len(new_messages)} 条消息, "
                       f"tokens: {self._calculate_context_usage(messages)} -> {new_tokens}")

            return new_messages

        except Exception as e:
            logger.error(f"上下文压缩失败: {str(e)}")
            return messages

    def chat(self, user_input: str) -> Tuple[str, Dict[str, Any]]:
        """
        主对话接口

        Args:
            user_input: 用户输入

        Returns:
            Tuple: (响应内容, 元数据)
        """
        logger.debug(f"收到用户输入: {user_input[:100]}...")

        # 构建消息
        messages = []
        system_prompt = self._build_system_prompt()
        messages.append({"role": "system", "content": system_prompt})

        # 添加对话历史
        messages.extend(self.conversation_history)

        # 添加用户输入
        if user_input:
            messages.append({"role": "user", "content": user_input})

        # 计算上下文使用率
        current_tokens = self._calculate_context_usage(messages)
        self.context_state.update(current_tokens)

        # 检查是否需要压缩
        if self.context_state.needs_compression:
            messages = self._compress_context(messages)
            current_tokens = self._calculate_context_usage(messages)
            self.context_state.update(current_tokens)

        # 多轮交互
        round_count = 0
        tool_call_count = 0
        final_response = ""
        interactions = []

        while round_count < self.max_rounds and tool_call_count < self.tool_call_limit:
            round_count += 1
            logger.debug(f"第{round_count}轮交互开始")

            try:
                response = self.client.chat_with_tools(messages, self.tools, "auto")
            except Exception as e:
                logger.error(f"AI调用失败: {str(e)}")
                final_response = f"AI调用失败: {str(e)}"
                break

            if response.has_tool_calls():
                # 执行工具调用
                messages.append(response.to_message())

                for tool_call in response.tool_calls:
                    tool_call_count += 1
                    tool_name = tool_call.get('function', {}).get('name', '')
                    args_str = tool_call.get('function', {}).get('arguments', '{}')

                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}

                    logger.debug(f"执行工具: {tool_name}")

                    # 执行工具
                    result = self._execute_tool_call(tool_name, args)

                    interactions.append({
                        "tool": tool_name,
                        "args": args,
                        "result": result
                    })

                    # 添加工具结果
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get('id', ''),
                        "content": json.dumps(result, ensure_ascii=False)
                    })

            else:
                # 最终响应
                final_response = response.content or ""
                interactions.append({
                    "response": final_response
                })
                break

        # 更新对话历史（只保留user/assistant消息）
        if user_input:
            self.conversation_history.append({"role": "user", "content": user_input})
        if final_response:
            self.conversation_history.append({"role": "assistant", "content": final_response})

        # 保存消息到会话
        if user_input:
            self.session_manager.save_message(self.session_id, "user", user_input)
        if final_response:
            self.session_manager.save_message(self.session_id, "assistant", final_response)

        # 更新会话状态
        self.session_state["tool_calls"] = self.session_state.get("tool_calls", 0) + tool_call_count
        self.session_state["subagent_calls"] = self.session_state.get("subagent_calls", 0)
        self.session_manager.update_state(self.session_id, {
            "context_usage": self.context_state.usage_ratio,
            "tool_calls": self.session_state["tool_calls"],
            "subagent_calls": self.session_state["subagent_calls"]
        })

        # 返回响应和元数据
        metadata = {
            "round_count": round_count,
            "tool_call_count": tool_call_count,
            "context_usage": self.context_state.usage_ratio,
            "interactions": interactions
        }

        logger.debug(f"对话完成: {round_count}轮, {tool_call_count}次工具调用")
        return final_response, metadata

    def _execute_tool_call(self, tool_name: str, args: Dict) -> Dict:
        """执行工具调用"""

        # 内置工具
        if tool_name in ORCHESTRATOR_TOOL_NAMES:
            return self._execute_builtin_tool(tool_name, args)

        # MCP工具
        if self.mcp_client and tool_name in self.mcp_client.tool_to_server:
            return self.mcp_client.call_tool(tool_name, args)

        # 未知工具
        return {"error": f"未知工具: {tool_name}"}

    def _execute_builtin_tool(self, tool_name: str, args: Dict) -> Dict:
        """执行内置工具"""

        if tool_name == "get_session_state":
            return {
                "work_dir": self.work_dir,
                "outputs_dir": self.outputs_dir,
                "context_usage": f"{self.context_state.usage_ratio * 100:.1f}%",
                "uploaded_files": self.session_state.get("uploaded_files", []),
                "notes": self.session_state.get("notes", {}),
                "subagent_calls": self.session_state.get("subagent_calls", 0),
                "tool_calls": self.session_state.get("tool_calls", 0)
            }

        elif tool_name == "save_session_note":
            key = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                self.session_state["notes"][key] = value
                self.session_manager.update_state(self.session_id, {
                    "notes": self.session_state["notes"]
                })
                return {"success": True, "message": f"已保存: {key}"}
            return {"error": "key和value不能为空"}

        elif tool_name == "list_available_tools":
            tools_info = []
            for tool in ORCHESTRATOR_TOOLS:
                tools_info.append({
                    "name": tool["function"]["name"],
                    "type": "builtin",
                    "description": tool["function"]["description"]
                })
            if self.mcp_client:
                for tool in self.mcp_client.all_tools:
                    tools_info.append({
                        "name": tool.name,
                        "type": "mcp",
                        "server": self.mcp_client.tool_to_server.get(tool.name, ""),
                        "description": tool.description
                    })
            for info in self.subagent_registry.list_all():
                tools_info.append({
                    "name": info["name"],
                    "type": "subagent",
                    "description": info["description"],
                    "capabilities": info.get("capabilities", [])
                })
            return {"tools": tools_info}

        elif tool_name == "dispatch_subagent":
            return self._dispatch_subagent(
                args.get("subagent_name", ""),
                args.get("request", ""),
                args.get("user_intent", "")
            )

        elif tool_name == "upload_log_file":
            return self._upload_log_file(args.get("file_path", ""))

        return {"error": f"未实现的内置工具: {tool_name}"}

    def _dispatch_subagent(self, subagent_name: str, request: str, user_intent: str = "") -> Dict:
        """调度Subagent执行任务"""
        if not subagent_name:
            return {"error": "subagent_name不能为空"}

        if not request:
            return {"error": "request不能为空"}

        # 检查Subagent是否存在
        if not self.subagent_registry.has(subagent_name):
            return {"error": f"Subagent不存在: {subagent_name}",
                    "available": [info["name"] for info in self.subagent_registry.list_all()]}

        # 构建执行上下文，包含user_intent
        context = {
            "work_dir": self.work_dir,
            "outputs_dir": self.outputs_dir,
            "session_notes": self.session_state.get("notes", {}),
            "uploaded_files": self.session_state.get("uploaded_files", []),
            "kb_id": self.session_state.get("kb_id"),
            "subagent_api_config": self._get_subagent_api_config(subagent_name),
            "user_intent": user_intent or request  # 如果未提供user_intent，使用request
        }

        # 如果有知识库管理器，添加相关信息
        if self.kb_manager:
            kb_id = self.session_state.get("kb_id")
            if kb_id:
                context["kb_manager"] = self.kb_manager

        # 执行Subagent
        try:
            logger.info(f"调度Subagent: {subagent_name}")
            result = self.subagent_registry.execute(
                subagent_name,
                request,
                context,
                self.work_dir
            )

            if result is None:
                return {"error": f"Subagent执行返回空结果: {subagent_name}"}

            # 更新调用计数
            self.session_state["subagent_calls"] = self.session_state.get("subagent_calls", 0) + 1

            # 提取intent_response
            intent_response = result.data.get("intent_response", "") if result.data else ""

            return {
                "success": result.success,
                "subagent": subagent_name,
                "content": result.content,
                "intent_response": intent_response,
                "data": result.data,
                "error": result.error,
                "metadata": result.metadata
            }

        except Exception as e:
            logger.error(f"Subagent执行失败: {subagent_name}, {str(e)}")
            return {"error": f"Subagent执行失败: {str(e)}"}

    def _upload_log_file(self, file_path: str) -> Dict:
        """处理日志文件上传"""
        if not file_path:
            return {"error": "file_path不能为空"}

        if not os.path.exists(file_path):
            return {"error": f"文件不存在: {file_path}"}

        # 复制文件到工作目录
        import shutil
        filename = os.path.basename(file_path)
        dest_path = os.path.join(self.work_dir, filename)

        try:
            shutil.copy2(file_path, dest_path)
            self.session_state["uploaded_files"].append(filename)
            self.session_manager.update_state(self.session_id, {
                "uploaded_files": self.session_state["uploaded_files"]
            })
            logger.info(f"上传日志文件: {filename}")
            return {
                "success": True,
                "filename": filename,
                "work_dir_path": dest_path,
                "message": f"文件已上传到工作目录: {filename}"
            }
        except Exception as e:
            logger.error(f"文件上传失败: {str(e)}")
            return {"error": f"文件上传失败: {str(e)}"}

    def set_kb_id(self, kb_id: str):
        """设置当前使用的知识库ID"""
        self.session_state["kb_id"] = kb_id
        self.session_manager.update_state(self.session_id, {"kb_id": kb_id})
        logger.info(f"设置知识库: {kb_id}")

    def get_context_state(self) -> ContextState:
        """获取当前上下文状态"""
        return self.context_state