"""
MCP (Model Context Protocol) 客户端
支持stdio和websocket两种transport连接MCP Server
"""

import json
import subprocess
import threading
import queue
import time
import os
from typing import Dict, Any, List, Optional

try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False

from src.utils import get_logger

logger = get_logger('mcp_client')


class MCPTool:
    """MCP工具定义"""

    def __init__(self, name: str, description: str, input_schema: dict):
        self.name = name
        self.description = description
        self.input_schema = input_schema

    def to_openai_format(self) -> dict:
        """转换为OpenAI工具格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema
            }
        }


class MCPServerConnection:
    """MCP Server连接基类"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.connected = False
        self.tools: List[MCPTool] = []
        self.request_id = 0

    def connect(self) -> bool:
        """连接Server"""
        raise NotImplementedError

    def disconnect(self):
        """断开连接"""
        raise NotImplementedError

    def send_request(self, method: str, params: dict = None) -> dict:
        """发送JSON-RPC请求"""
        raise NotImplementedError

    def initialize(self) -> bool:
        """初始化握手"""
        try:
            response = self.send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "ai-log-analyzer",
                    "version": "1.0.0"
                }
            })
            if response.get("result"):
                self.connected = True
                logger.info(f"MCP Server '{self.name}' 初始化成功")
                return True
            else:
                logger.error(f"MCP Server '{self.name}' 初始化失败: {response}")
                return False
        except Exception as e:
            logger.error(f"MCP Server '{self.name}' 初始化异常: {str(e)}")
            return False

    def load_tools(self) -> List[MCPTool]:
        """加载工具列表"""
        if not self.connected:
            return []

        try:
            response = self.send_request("tools/list", {})
            result = response.get("result", {})
            tools_data = result.get("tools", [])

            self.tools = []
            for tool_data in tools_data:
                tool = MCPTool(
                    name=tool_data.get("name", ""),
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {})
                )
                self.tools.append(tool)

            logger.info(f"MCP Server '{self.name}' 提供 {len(self.tools)} 个工具")
            return self.tools
        except Exception as e:
            logger.error(f"获取工具列表失败: {str(e)}")
            return []

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """调用工具"""
        if not self.connected:
            return {"error": "Server未连接"}

        try:
            response = self.send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
            result = response.get("result", {})
            if response.get("error"):
                return {"error": response.get("error", {}).get("message", "未知错误")}
            return result
        except Exception as e:
            logger.error(f"调用工具 {tool_name} 失败: {str(e)}")
            return {"error": str(e)}


class StdioConnection(MCPServerConnection):
    """stdio类型的MCP连接"""

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.process = None
        self.response_queue = queue.Queue()
        self.reader_thread = None
        self.timeout = config.get("timeout", 30)

    def connect(self) -> bool:
        """启动子进程连接"""
        command = self.config.get("command", "python")
        args = self.config.get("args", [])

        # 获取项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))

        # 处理相对路径
        full_args = []
        for arg in args:
            if not os.path.isabs(arg):
                full_args.append(os.path.join(project_root, arg))
            else:
                full_args.append(arg)

        try:
            # 启动子进程
            self.process = subprocess.Popen(
                [command] + full_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                cwd=project_root
            )

            # 启动读取线程
            self.reader_thread = threading.Thread(target=self._read_responses, daemon=True)
            self.reader_thread.start()

            logger.info(f"stdio MCP Server '{self.name}' 进程已启动: {command} {args}")

            # 初始化握手
            return self.initialize()
        except Exception as e:
            logger.error(f"启动stdio进程失败: {str(e)}")
            return False

    def _read_responses(self):
        """读取响应的后台线程"""
        while self.process and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if line:
                    try:
                        response = json.loads(line.decode('utf-8').strip())
                        self.response_queue.put(response)
                    except json.JSONDecodeError:
                        continue
            except Exception:
                break

    def send_request(self, method: str, params: dict = None) -> dict:
        """发送JSON-RPC请求"""
        if not self.process or self.process.poll() is not None:
            return {"error": "进程未运行"}

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        try:
            # 发送请求
            request_str = json.dumps(request) + "\n"
            self.process.stdin.write(request_str.encode('utf-8'))
            self.process.stdin.flush()

            # 等待响应
            try:
                response = self.response_queue.get(timeout=self.timeout)
                return response
            except queue.Empty:
                return {"error": f"响应超时 ({self.timeout}s)"}
        except Exception as e:
            return {"error": str(e)}

    def disconnect(self):
        """终止进程"""
        self.connected = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            self.process = None
        logger.info(f"stdio MCP Server '{self.name}' 已断开")


class WebSocketConnection(MCPServerConnection):
    """websocket类型的MCP连接"""

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.ws = None
        self.url = config.get("url", "")
        self.timeout = config.get("timeout", 30)
        self.response_queue = queue.Queue()

    def connect(self) -> bool:
        """建立WebSocket连接"""
        if not WEBSOCKET_AVAILABLE:
            logger.error("websocket-client库未安装，无法使用websocket transport")
            return False

        try:
            # 创建WebSocket连接
            self.ws = websocket.create_connection(
                self.url,
                timeout=self.timeout
            )

            logger.info(f"websocket MCP Server '{self.name}' 已连接: {self.url}")

            # 初始化握手
            return self.initialize()
        except Exception as e:
            logger.error(f"WebSocket连接失败: {str(e)}")
            return False

    def send_request(self, method: str, params: dict = None) -> dict:
        """发送JSON-RPC请求"""
        if not self.ws:
            return {"error": "WebSocket未连接"}

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        try:
            # 发送请求
            self.ws.send(json.dumps(request))

            # 接收响应
            response_str = self.ws.recv()
            response = json.loads(response_str)
            return response
        except Exception as e:
            logger.error(f"WebSocket发送失败: {str(e)}")
            return {"error": str(e)}

    def disconnect(self):
        """关闭WebSocket连接"""
        self.connected = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        logger.info(f"websocket MCP Server '{self.name}' 已断开")


class MCPClient:
    """MCP协议客户端"""

    def __init__(self, config_manager=None, auto_connect=True):
        """
        初始化MCP客户端

        Args:
            config_manager: 配置管理器
            auto_connect: 是否自动连接配置中的Server
        """
        self.config_manager = config_manager
        self.servers: Dict[str, MCPServerConnection] = {}
        self.all_tools: List[MCPTool] = []
        self.tool_to_server: Dict[str, str] = {}  # tool_name -> server_name

        if config_manager and auto_connect:
            self.load_servers_from_config()

    def load_servers_from_config(self):
        """从配置加载MCP Server"""
        mcp_config = self.config_manager.get('mcp_servers', {})
        if not mcp_config:
            logger.debug("未配置MCP Server")
            return

        for name, server_config in mcp_config.items():
            if not server_config.get('enabled', False):
                logger.debug(f"MCP Server '{name}' 未启用，跳过")
                continue

            self.connect_server(name, server_config)

    def connect_server(self, name: str, config: dict) -> bool:
        """
        连接MCP Server

        Args:
            name: Server名称
            config: Server配置

        Returns:
            bool: 是否连接成功
        """
        transport = config.get('transport', 'stdio')

        if transport == 'stdio':
            connection = StdioConnection(name, config)
        elif transport == 'websocket':
            connection = WebSocketConnection(name, config)
        else:
            logger.error(f"未知transport类型: {transport}")
            return False

        if connection.connect():
            self.servers[name] = connection
            tools = connection.load_tools()
            self.all_tools.extend(tools)
            for tool in tools:
                self.tool_to_server[tool.name] = name
            return True
        else:
            return False

    def list_tools(self) -> List[dict]:
        """
        获取所有MCP Server提供的工具列表（OpenAI格式）

        Returns:
            List[dict]: OpenAI格式的工具定义列表
        """
        return [tool.to_openai_format() for tool in self.all_tools]

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        调用MCP工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            dict: 工具执行结果
        """
        server_name = self.tool_to_server.get(tool_name)
        if not server_name:
            return {"error": f"未找到工具: {tool_name}"}

        server = self.servers.get(server_name)
        if not server:
            return {"error": f"Server '{server_name}' 未连接"}

        logger.debug(f"调用MCP工具: {tool_name} (Server: {server_name})")
        return server.call_tool(tool_name, arguments)

    def disconnect(self, name: str):
        """断开指定Server"""
        server = self.servers.get(name)
        if server:
            server.disconnect()
            # 移除工具
            self.all_tools = [t for t in self.all_tools if self.tool_to_server.get(t.name) != name]
            for tool_name in list(self.tool_to_server.keys()):
                if self.tool_to_server[tool_name] == name:
                    del self.tool_to_server[tool_name]
            del self.servers[name]

    def disconnect_all(self):
        """断开所有Server"""
        for name in list(self.servers.keys()):
            self.disconnect(name)
        self.all_tools.clear()
        self.tool_to_server.clear()

    def get_server_status(self) -> dict:
        """获取所有Server状态"""
        status = {}
        for name, server in self.servers.items():
            status[name] = {
                "connected": server.connected,
                "tools": [t.name for t in server.tools],
                "transport": server.config.get('transport', 'unknown')
            }
        return status