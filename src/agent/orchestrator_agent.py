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
from .subagents import SubagentRegistry, get_registry
from .mcp_client import MCPClient
from .skill_loader import get_skill_loader
from .tools.log_file_tool import upload_log_file as upload_log_file_tool, prepare_log_analyzer as prepare_log_analyzer_tool
from src.session_manager.manager import SessionManager
from src.system_config_manager.manager import SystemConfigManager
from src.knowledge_base.manager import KnowledgeBaseManager

# 数据库模型为可选依赖，仅Web模式需要
try:
    from src.models.user import User, db
    from src.models.token_usage import TokenUsage
    DB_MODELS_AVAILABLE = True
except ImportError:
    DB_MODELS_AVAILABLE = False
    User = None
    db = None
    TokenUsage = None

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
        settings_manager: SystemConfigManager = None,
        kb_manager: KnowledgeBaseManager = None,
        mcp_client: MCPClient = None,
        log_metadata_manager=None,
        plugin_manager=None
    ):
        """
        初始化OrchestratorAgent

        Args:
            user_id: 用户ID
            session_id: 会话ID
            settings_manager: 配置管理器
            kb_manager: 知识库管理器
            mcp_client: MCP客户端
            log_metadata_manager: 日志元数据管理器
            plugin_manager: 插件管理器
        """
        self.user_id = user_id
        self.session_id = session_id

        # 配置管理器
        if settings_manager is None:
            settings_manager = SystemConfigManager()
        self.settings_manager = settings_manager

        # 加载Orchestrator配置
        self.load_config()

        # 初始化AI客户端（Orchestrator专用）
        orchestrator_api_config = self.get_orchestrator_api_config()
        self.client = AIClient(orchestrator_api_config)

        # Subagent注册表
        self.subagent_registry = get_registry()

        # 知识库管理器
        self.kb_manager = kb_manager

        # MCP客户端
        self.mcp_client = mcp_client

        # 日志元数据管理器
        self.log_metadata_manager = log_metadata_manager

        # 插件管理器
        self.plugin_manager = plugin_manager

        # 注册 LogAnalyzerSubagent
        from .subagents.log_analyzer import register_log_analyzer_subagent
        register_log_analyzer_subagent(
            self.subagent_registry,
            config_manager=self.settings_manager,
            kb_manager=self.kb_manager,
            mcp_client=self.mcp_client,
            log_metadata_manager=self.log_metadata_manager,
            plugin_manager=self.plugin_manager
        )

        # Skill加载器
        self.skill_loader = get_skill_loader()
        self.skill_loader.scan()

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
        self.tools = self.build_tools()

        # 知识库上下文（用于增强对话）
        self.kb_context = ""

        # Prompt路径
        self.prompt_path = self.get_prompt_path()

        logger.info(f"OrchestratorAgent初始化完成: user={user_id}, session={session_id}")

    def record_token_usage(self, tokens: int):
        """
        记录token使用量

        Args:
            tokens: 使用的token数量
        """
        if not DB_MODELS_AVAILABLE:
            # 非Web模式跳过数据库记录
            return

        try:
            user = User.query.filter_by(employee_id=self.user_id).first()
            if user:
                usage = TokenUsage(
                    user_id=user.id,
                    tokens_used=tokens
                )
                db.session.add(usage)
                db.session.commit()
                logger.debug(f"记录token使用: user={self.user_id}, tokens={tokens}")
        except Exception as e:
            db.session.rollback()
            logger.warning(f"记录token使用失败: {str(e)}")

    def load_config(self):
        """加载Orchestrator配置"""
        orchestrator_config = self.settings_manager.get('orchestrator', {})
        self.max_rounds = orchestrator_config.get('max_rounds', 20)
        self.tool_call_limit = orchestrator_config.get('tool_call_limit', 50)
        self.compression_retain_rounds = orchestrator_config.get('compression_retain_rounds', 5)

        # 上下文限制（从orchestrator配置块读取）
        self.context_limit = orchestrator_config.get('context_limit', 120000)
        self.compression_threshold = orchestrator_config.get('compression_threshold', 0.8)

    def get_orchestrator_api_config(self) -> Dict:
        """获取Orchestrator API配置 - 直接使用api配置"""
        return self.settings_manager.get('api', {})

    def get_prompt_path(self) -> str:
        """获取prompt文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, 'prompts', 'orchestrator_prompt.txt')

    def build_tools(self) -> List[Dict]:
        """构建工具列表（内置 + MCP）"""
        tools = ORCHESTRATOR_TOOLS.copy()

        if self.mcp_client:
            mcp_tools = self.mcp_client.list_tools()
            tools.extend(mcp_tools)
            logger.debug(f"已加载 {len(mcp_tools)} 个MCP工具")

        return tools

    def load_prompt(self) -> str:
        """加载prompt模板"""
        if os.path.exists(self.prompt_path):
            with open(self.prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        return self.default_prompt()

    def default_prompt(self) -> str:
        """默认prompt"""
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

    def build_system_prompt(self) -> str:
        """构建系统提示"""
        prompt_template = self.load_prompt()

        # 获取可用Skill列表
        available_skills = []
        for skill in self.skill_loader.list_all():
            skill_name = skill.get('name', '')
            skill_desc = skill.get('description', '')
            skill_content = skill.get('content', '')

            # 格式化Skill信息
            skill_info = f"## {skill_name}\n{skill_desc}\n"
            if skill_content:
                skill_info += f"\n{skill_content}\n"
            available_skills.append(skill_info)

        # 同时列出Subagent作为工具参考
        subagent_list = []
        for info in self.subagent_registry.list_all():
            subagent_desc = f"- {info['name']}: {info['description']}"
            if info.get('capabilities'):
                subagent_desc += f" (能力: {', '.join(info['capabilities'])})"
            subagent_list.append(subagent_desc)

        # 知识库上下文部分
        kb_context_section = ""
        if self.kb_context:
            kb_context_section = f"\n# 相关知识库内容\n\n{self.kb_context}\n"

        # 填充模板
        prompt_data = {
            'available_skills': '\n'.join(available_skills) if available_skills else '暂无可用技能',
            'available_subagents': '\n'.join(subagent_list) if subagent_list else '暂无可用Subagent',
            'work_dir': self.work_dir,
            'context_usage': f"{self.context_state.usage_ratio * 100:.1f}",
            'uploaded_files': ', '.join(self.session_state.get('uploaded_files', [])) or '无',
            'notes': json.dumps(self.session_state.get('notes', {}), ensure_ascii=False) or '{}',
            'kb_context': kb_context_section
        }

        # 转义花括号
        def escape_braces(text):
            if not text:
                return ""
            return text.replace('{', '{{').replace('}', '}}')

        return prompt_template.format(**{k: escape_braces(v) for k, v in prompt_data.items()})

    def calculate_context_usage(self, messages: List[Dict]) -> int:
        """计算上下文使用量"""
        return self.client.count_tokens(messages, self.tools)

    def compress_context(self, messages: List[Dict]) -> List[Dict]:
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
            new_tokens = self.calculate_context_usage(new_messages)
            logger.info(f"压缩完成: {len(messages)} -> {len(new_messages)} 条消息, "
                       f"tokens: {self.calculate_context_usage(messages)} -> {new_tokens}")

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
        messages = self._build_chat_messages(user_input)

        # 计算上下文使用率并压缩
        messages = self._check_and_compress_context(messages)

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
                if response.usage and response.usage.get('total_tokens'):
                    self.record_token_usage(response.usage['total_tokens'])
            except Exception as e:
                logger.error(f"AI调用失败: {str(e)}")
                final_response = f"AI调用失败: {str(e)}"
                break

            if response.has_tool_calls():
                messages.append(response.to_message())
                for tool_call in response.tool_calls:
                    tool_call_count += 1
                    result, interaction = self._process_tool_call(tool_call)
                    interactions.append(interaction)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get('id', ''),
                        "content": json.dumps(result, ensure_ascii=False)
                    })
            else:
                final_response = response.content or ""
                interactions.append({"response": final_response})
                break

        # 更新对话历史
        self._update_conversation_history(user_input, messages)

        # 保存会话
        self._save_chat_session(user_input, final_response, tool_call_count)

        # 返回响应和元数据
        metadata = {
            "round_count": round_count,
            "tool_call_count": tool_call_count,
            "context_usage": self.context_state.usage_ratio,
            "interactions": interactions
        }

        logger.debug(f"对话完成: {round_count}轮, {tool_call_count}次工具调用")
        return final_response, metadata

    def _build_chat_messages(self, user_input: str) -> List[Dict]:
        """构建对话消息列表。"""
        messages = []
        system_prompt = self.build_system_prompt()
        messages.append({"role": "system", "content": system_prompt})
        messages.extend(self.conversation_history)
        if user_input:
            messages.append({"role": "user", "content": user_input})
        return messages

    def _check_and_compress_context(self, messages: List[Dict]) -> List[Dict]:
        """检查上下文使用率并按需压缩。"""
        current_tokens = self.calculate_context_usage(messages)
        self.context_state.update(current_tokens)

        if self.context_state.needs_compression:
            messages = self.compress_context(messages)
            current_tokens = self.calculate_context_usage(messages)
            self.context_state.update(current_tokens)

        return messages

    def _process_tool_call(self, tool_call: Dict) -> Tuple[Dict, Dict]:
        """
        处理单个工具调用。

        Returns:
            tuple: (工具执行结果, 交互记录)
        """
        tool_name = tool_call.get('function', {}).get('name', '')
        args_str = tool_call.get('function', {}).get('arguments', '{}')

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}

        logger.debug(f"执行工具: {tool_name}")
        result = self.execute_tool_call(tool_name, args)

        interaction = {
            "tool": tool_name,
            "args": args,
            "result": result
        }
        return result, interaction

    def _update_conversation_history(self, user_input: str, messages: List[Dict]):
        """更新对话历史。"""
        if user_input:
            self.conversation_history.append({"role": "user", "content": user_input})

        # 保存本轮新增的消息
        history_len = len(self.conversation_history)
        new_messages_start = 1 + history_len + 1  # 跳过system、旧历史、user

        for msg in messages[new_messages_start:]:
            role = msg.get('role')
            if role == 'assistant':
                self.conversation_history.append({
                    "role": "assistant",
                    "content": msg.get('content', ''),
                    "tool_calls": msg.get('tool_calls')
                })
            elif role == 'tool':
                content = msg.get('content', '')
                if len(content) > 500:
                    content = content[:500] + "...(已截断)"
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": msg.get('tool_call_id', ''),
                    "content": content
                })

    def _save_chat_session(self, user_input: str, final_response: str, tool_call_count: int):
        """保存对话会话状态。"""
        if user_input:
            self.session_manager.save_message(self.session_id, "user", user_input)
        if final_response:
            self.session_manager.save_message(self.session_id, "assistant", final_response)

        self.session_state["tool_calls"] = self.session_state.get("tool_calls", 0) + tool_call_count
        self.session_state["subagent_calls"] = self.session_state.get("subagent_calls", 0)
        self.session_manager.update_state(self.session_id, {
            "context_usage": self.context_state.usage_ratio,
            "tool_calls": self.session_state["tool_calls"],
            "subagent_calls": self.session_state["subagent_calls"]
        })

    def chat_stream(self, user_input: str):
        """
        流式对话接口（无工具调用）
        用于AI助手聊天，实时显示AI响应

        Args:
            user_input: 用户输入

        Yields:
            str: AI响应的文本片段
        """
        logger.debug(f"流式对话开始: {user_input[:100]}...")

        # 构建消息
        messages = []
        system_prompt = self.build_system_prompt()
        messages.append({"role": "system", "content": system_prompt})
        messages.extend(self.conversation_history)
        if user_input:
            messages.append({"role": "user", "content": user_input})

        # 收集完整响应
        full_response = ""

        # 流式调用AI
        try:
            for chunk in self.client.chat(messages):
                full_response += chunk
                yield chunk
        except Exception as e:
            logger.error(f"流式对话失败: {str(e)}")
            yield f"[错误: {str(e)}]"
            return

        # 更新对话历史
        if user_input:
            self.conversation_history.append({"role": "user", "content": user_input})
        if full_response:
            self.conversation_history.append({"role": "assistant", "content": full_response})

        # 保存消息到会话
        if user_input:
            self.session_manager.save_message(self.session_id, "user", user_input)
        if full_response:
            self.session_manager.save_message(self.session_id, "assistant", full_response)

        logger.debug(f"流式对话完成: 响应长度={len(full_response)}")

    def execute_tool_call(self, tool_name: str, args: Dict) -> Dict:
        """执行工具调用"""

        # 内置工具
        if tool_name in ORCHESTRATOR_TOOL_NAMES:
            return self.execute_builtin_tool(tool_name, args)

        # MCP工具
        if self.mcp_client and tool_name in self.mcp_client.tool_to_server:
            # MCP下载工具：强制传递工作目录
            if tool_name == "download_bmc_log":
                args["output_dir"] = self.work_dir

            result = self.mcp_client.call_tool(tool_name, args)

            # 处理下载结果
            if tool_name == "download_bmc_log" and not result.get("isError"):
                filename = result.get("filename")
                if filename:
                    uploaded_files = self.session_state.get("uploaded_files", [])
                    if filename not in uploaded_files:
                        uploaded_files.append(filename)
                    self.session_state["uploaded_files"] = uploaded_files
                    self.session_manager.update_state(self.session_id, {
                        "uploaded_files": uploaded_files
                    })
                    logger.info(f"MCP下载文件已记录: {filename}")

            return result

        # 未知工具
        return {"error": f"未知工具: {tool_name}"}

    def execute_builtin_tool(self, tool_name: str, args: Dict) -> Dict:
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
            return self.dispatch_subagent(
                args.get("subagent_name", ""),
                args.get("request", ""),
                args.get("user_intent", "")
            )

        elif tool_name == "upload_log_file":
            return upload_log_file_tool(
                file_path=args.get("file_path", ""),
                work_dir=self.work_dir,
                user_id=self.user_id,
                session_state=self.session_state,
                session_manager=self.session_manager,
                session_id=self.session_id
            )

        return {"error": f"未实现的内置工具: {tool_name}"}

    def dispatch_subagent(self, subagent_name: str, request: str, user_intent: str = "") -> Dict:
        """调度Subagent执行任务"""
        if not subagent_name:
            return {"error": "subagent_name不能为空"}

        if not request:
            return {"error": "request不能为空"}

        # 统一通过注册表调用
        if not self.subagent_registry.has(subagent_name):
            return {"error": f"Subagent不存在: {subagent_name}",
                    "available": [info["name"] for info in self.subagent_registry.list_all()]}

        # 执行对应的准备函数
        log_files = []
        temp_work_dir = ""
        has_prepare = False
        if subagent_name == "log_analyzer":
            has_prepare = True
            prepare_result = prepare_log_analyzer_tool(self.session_state)
            if "error" in prepare_result:
                return prepare_result
            temp_work_dir = prepare_result.get("temp_work_dir", "")
            log_files = prepare_result.get("log_files", [])

        # 构建执行上下文
        context = {
            "work_dir": temp_work_dir if has_prepare else self.work_dir,
            "outputs_dir": self.outputs_dir,
            "log_files": log_files,
            "kb_ids": self.session_state.get("kb_ids", []),
            "kb_manager": self.kb_manager,
            "api_config": self.get_orchestrator_api_config(),
            "user_intent": user_intent or request,
            "user_id": self.user_id
        }

        try:
            logger.info(f"调度Subagent: {subagent_name}")
            result = self.subagent_registry.execute(
                subagent_name,
                request,
                context,
                temp_work_dir if has_prepare else self.work_dir
            )

            if result is None:
                return {"error": f"Subagent执行返回空结果: {subagent_name}"}

            self.session_state["subagent_calls"] = self.session_state.get("subagent_calls", 0) + 1
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

    def set_kb_ids(self, kb_ids: List[str]):
        """设置当前使用的知识库ID列表"""
        self.session_state["kb_ids"] = kb_ids
        self.session_manager.update_state(self.session_id, {"kb_ids": kb_ids})
        logger.info(f"设置知识库列表: {kb_ids}")

    def set_kb_context(self, kb_context: str):
        """
        设置知识库检索上下文

        Args:
            kb_context: 从知识库检索的相关内容
        """
        self.kb_context = kb_context
        logger.debug(f"设置知识库上下文: {len(kb_context)}字符")

    def get_context_state(self) -> ContextState:
        """获取当前上下文状态"""
        return self.context_state