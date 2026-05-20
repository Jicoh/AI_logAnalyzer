"""
工具调用路由器

根据工具名称，将调用分发到：
- 内置工具（get_session_state, save_session_note 等）
- Subagent（log_analyzer 等）
- MCP工具
- 知识库检索
"""

import json
from typing import Dict, Any

from src.utils import get_logger
from src.agent.tools.log_file_tool import upload_log_file as upload_log_file_tool, prepare_log_analyzer as prepare_log_analyzer_tool

logger = get_logger('tool_router')

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
                    "key": {"type": "string", "description": "信息键名"},
                    "value": {"type": "string", "description": "信息内容"}
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
                    "subagent_name": {"type": "string", "description": "Subagent名称，如 log_analyzer"},
                    "request": {"type": "string", "description": "给Subagent的任务描述"},
                    "user_intent": {"type": "string", "description": "用户的具体意图/关注点"}
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
                    "file_path": {"type": "string", "description": "日志文件路径（本地路径或压缩包路径）"}
                },
                "required": ["file_path"]
            }
        }
    }
]

ORCHESTRATOR_TOOL_NAMES = [t["function"]["name"] for t in ORCHESTRATOR_TOOLS]


class ToolRouter:
    """工具调用路由器

    根据工具名称，将调用分发到对应的执行器
    """

    def __init__(self, subagent_registry, mcp_client=None,
                 session_manager=None, session_id=None,
                 session_state=None, work_dir=None, outputs_dir=None,
                 kb_manager=None, get_api_config=None):
        self.subagent_registry = subagent_registry
        self.mcp_client = mcp_client
        self.session_manager = session_manager
        self.session_id = session_id
        self.session_state = session_state or {}
        self.work_dir = work_dir
        self.outputs_dir = outputs_dir
        self.kb_manager = kb_manager
        self.get_api_config = get_api_config

    def get_all_tools(self) -> list:
        """获取所有可用工具列表（内置 + MCP）"""
        tools = ORCHESTRATOR_TOOLS.copy()
        if self.mcp_client:
            mcp_tools = self.mcp_client.list_tools()
            tools.extend(mcp_tools)
        return tools

    def execute(self, tool_name: str, args: Dict) -> Dict:
        """执行工具调用

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            dict: 工具执行结果
        """
        # 内置工具
        if tool_name in ORCHESTRATOR_TOOL_NAMES:
            return self._execute_builtin(tool_name, args)

        # MCP工具
        if self.mcp_client and tool_name in self.mcp_client.tool_to_server:
            return self._execute_mcp(tool_name, args)

        # 未知工具
        return {"error": f"未知工具: {tool_name}"}

    def _execute_builtin(self, tool_name: str, args: Dict) -> Dict:
        """执行内置工具"""
        if tool_name == "get_session_state":
            return {
                "work_dir": self.work_dir,
                "outputs_dir": self.outputs_dir,
                "context_usage": f"{self.session_state.get('context_usage', 0) * 100:.1f}%",
                "uploaded_files": self.session_state.get("uploaded_files", []),
                "notes": self.session_state.get("notes", {}),
                "subagent_calls": self.session_state.get("subagent_calls", 0),
                "tool_calls": self.session_state.get("tool_calls", 0)
            }

        elif tool_name == "save_session_note":
            key = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                notes = self.session_state.setdefault("notes", {})
                notes[key] = value
                if self.session_manager and self.session_id:
                    self.session_manager.update_state(self.session_id, {"notes": notes})
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
            if self.subagent_registry:
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
            return upload_log_file_tool(
                file_path=args.get("file_path", ""),
                work_dir=self.work_dir,
                user_id=self.session_state.get("user_id"),
                session_state=self.session_state,
                session_manager=self.session_manager,
                session_id=self.session_id
            )

        return {"error": f"未实现的内置工具: {tool_name}"}

    def _execute_mcp(self, tool_name: str, args: Dict) -> Dict:
        """执行MCP工具"""
        # MCP下载工具：强制传递工作目录
        if tool_name == "download_bmc_log":
            args["output_dir"] = self.work_dir

        result = self.mcp_client.call_tool(tool_name, args)

        # 处理下载结果
        if tool_name == "download_bmc_log" and not result.get("isError"):
            filename = result.get("filename")
            if filename:
                uploaded_files = self.session_state.setdefault("uploaded_files", [])
                if filename not in uploaded_files:
                    uploaded_files.append(filename)
                if self.session_manager and self.session_id:
                    self.session_manager.update_state(self.session_id, {
                        "uploaded_files": uploaded_files
                    })
                logger.info(f"MCP下载文件已记录: {filename}")

        return result

    def _dispatch_subagent(self, subagent_name: str, request: str, user_intent: str = "") -> Dict:
        """调度Subagent执行任务"""
        if not subagent_name:
            return {"error": "subagent_name不能为空"}
        if not request:
            return {"error": "request不能为空"}

        if not self.subagent_registry or not self.subagent_registry.has(subagent_name):
            available = []
            if self.subagent_registry:
                available = [info["name"] for info in self.subagent_registry.list_all()]
            return {"error": f"Subagent不存在: {subagent_name}", "available": available}

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

        context = {
            "work_dir": temp_work_dir if has_prepare else self.work_dir,
            "outputs_dir": self.outputs_dir,
            "log_files": log_files,
            "kb_ids": self.session_state.get("kb_ids", []),
            "kb_manager": self.kb_manager,
            "api_config": self.get_api_config() if self.get_api_config else {},
            "user_intent": user_intent or request,
            "user_id": self.session_state.get("user_id")
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
