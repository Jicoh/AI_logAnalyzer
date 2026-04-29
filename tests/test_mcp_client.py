"""
MCP客户端单元测试
测试stdio连接、工具列表获取、工具调用等功能
"""

import pytest
import json
import os
import sys
import threading
import time
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai_analyzer.mcp_client import (
    MCPClient, MCPTool, MCPServerConnection,
    StdioConnection, WebSocketConnection
)


class TestMCPTool:
    """MCP工具类测试"""

    def test_mcp_tool_creation(self):
        """测试MCP工具创建"""
        tool = MCPTool(
            name="test_tool",
            description="测试工具",
            input_schema={"type": "object", "properties": {}}
        )
        assert tool.name == "test_tool"
        assert tool.description == "测试工具"

    def test_mcp_tool_to_openai_format(self):
        """测试转换为OpenAI格式"""
        tool = MCPTool(
            name="download_bmc_log",
            description="从BMC下载日志",
            input_schema={
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "BMC IP地址"}
                },
                "required": ["ip"]
            }
        )

        openai_format = tool.to_openai_format()
        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "download_bmc_log"
        assert openai_format["function"]["description"] == "从BMC下载日志"
        assert openai_format["function"]["parameters"]["type"] == "object"
        assert "ip" in openai_format["function"]["parameters"]["properties"]


class TestStdioConnection:
    """stdio连接测试"""

    def test_stdio_connection_init(self):
        """测试stdio连接初始化"""
        config = {
            "command": "python",
            "args": ["test_server.py"],
            "timeout": 30
        }
        connection = StdioConnection("test_server", config)
        assert connection.name == "test_server"
        assert connection.timeout == 30
        assert not connection.connected

    def test_stdio_build_tools_list(self):
        """测试工具列表构建（模拟）"""
        connection = StdioConnection("test", {})
        connection.connected = True

        # 模拟工具数据
        mock_response = {
            "result": {
                "tools": [
                    {
                        "name": "tool1",
                        "description": "工具1",
                        "inputSchema": {"type": "object"}
                    },
                    {
                        "name": "tool2",
                        "description": "工具2",
                        "inputSchema": {"type": "object"}
                    }
                ]
            }
        }

        # 手动添加工具
        connection.tools = [
            MCPTool(name="tool1", description="工具1", input_schema={"type": "object"}),
            MCPTool(name="tool2", description="工具2", input_schema={"type": "object"})
        ]

        assert len(connection.tools) == 2
        assert connection.tools[0].name == "tool1"


class TestWebSocketConnection:
    """websocket连接测试"""

    def test_websocket_connection_init(self):
        """测试websocket连接初始化"""
        config = {
            "url": "ws://localhost:8080/mcp",
            "timeout": 30
        }
        connection = WebSocketConnection("test_ws", config)
        assert connection.name == "test_ws"
        assert connection.url == "ws://localhost:8080/mcp"
        assert connection.timeout == 30

    def test_websocket_connection_without_library(self):
        """测试无websocket库时的行为"""
        # 模拟无websocket库
        with patch('src.ai_analyzer.mcp_client.WEBSOCKET_AVAILABLE', False):
            connection = WebSocketConnection("test", {"url": "ws://localhost"})
            result = connection.connect()
            assert result == False


class TestMCPClient:
    """MCP客户端测试"""

    def test_mcp_client_init_without_config(self):
        """测试无配置初始化"""
        client = MCPClient(auto_connect=False)
        assert len(client.servers) == 0
        assert len(client.all_tools) == 0

    def test_mcp_client_with_empty_config(self):
        """测试空配置"""
        mock_config = Mock()
        mock_config.get = Mock(return_value={})

        client = MCPClient(mock_config, auto_connect=False)
        assert len(client.servers) == 0

    def test_mcp_client_list_tools_empty(self):
        """测试空工具列表"""
        client = MCPClient(auto_connect=False)
        tools = client.list_tools()
        assert tools == []

    def test_mcp_client_call_tool_not_found(self):
        """测试调用不存在的工具"""
        client = MCPClient(auto_connect=False)
        result = client.call_tool("unknown_tool", {})
        assert "error" in result
        assert "未找到工具" in result["error"]

    def test_mcp_client_get_status_empty(self):
        """测试空状态获取"""
        client = MCPClient(auto_connect=False)
        status = client.get_server_status()
        assert status == {}

    def test_mcp_client_disconnect_all(self):
        """测试断开所有连接"""
        client = MCPClient(auto_connect=False)
        client.disconnect_all()
        assert len(client.servers) == 0
        assert len(client.all_tools) == 0


class TestMCPClientWithMockServer:
    """带模拟Server的MCP客户端测试"""

    def test_mcp_client_with_mock_connection(self):
        """测试带模拟连接的客户端"""
        # 创建模拟连接
        mock_connection = Mock(spec=MCPServerConnection)
        mock_connection.connected = True
        mock_connection.tools = [
            MCPTool("tool1", "工具1", {"type": "object"}),
            MCPTool("tool2", "工具2", {"type": "object"})
        ]
        mock_connection.config = {"transport": "stdio"}
        mock_connection.call_tool = Mock(return_value={"result": "success"})

        # 创建客户端并添加模拟连接
        client = MCPClient(auto_connect=False)
        client.servers["mock_server"] = mock_connection
        client.all_tools = mock_connection.tools
        for tool in mock_connection.tools:
            client.tool_to_server[tool.name] = "mock_server"

        # 测试工具列表
        tools = client.list_tools()
        assert len(tools) == 2
        assert tools[0]["function"]["name"] == "tool1"

        # 测试工具调用
        result = client.call_tool("tool1", {"arg": "value"})
        assert result == {"result": "success"}

        # 测试状态
        status = client.get_server_status()
        assert "mock_server" in status
        assert status["mock_server"]["connected"] == True

    def test_mcp_client_disconnect_specific_server(self):
        """测试断开特定Server"""
        # 创建模拟连接
        mock_connection1 = Mock(spec=MCPServerConnection)
        mock_connection1.connected = True
        mock_connection1.tools = [MCPTool("tool1", "工具1", {"type": "object"})]
        mock_connection1.disconnect = Mock()

        mock_connection2 = Mock(spec=MCPServerConnection)
        mock_connection2.connected = True
        mock_connection2.tools = [MCPTool("tool2", "工具2", {"type": "object"})]
        mock_connection2.disconnect = Mock()

        client = MCPClient(auto_connect=False)
        client.servers["server1"] = mock_connection1
        client.servers["server2"] = mock_connection2
        client.all_tools = mock_connection1.tools + mock_connection2.tools
        client.tool_to_server["tool1"] = "server1"
        client.tool_to_server["tool2"] = "server2"

        # 断开server1
        client.disconnect("server1")

        assert "server1" not in client.servers
        assert "server2" in client.servers
        mock_connection1.disconnect.assert_called_once()


class TestMCPIntegration:
    """MCP集成测试（需要实际Server）"""

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'mcp_servers', 'log_downloader', 'server.py')),
        reason="示例MCP Server不存在"
    )
    def test_real_stdio_connection(self):
        """测试真实的stdio连接"""
        from src.config_manager.manager import ConfigManager

        config_manager = ConfigManager()
        client = MCPClient(config_manager)

        if len(client.servers) == 0:
            pytest.skip("未配置MCP Server")

        # 检查连接状态
        status = client.get_server_status()
        assert len(status) > 0

        for server_name, server_status in status.items():
            assert server_status["connected"] == True
            assert len(server_status["tools"]) > 0

        # 测试工具调用
        if client.all_tools:
            tool_name = client.all_tools[0].name
            result = client.call_tool(tool_name, {})
            assert result is not None

        client.disconnect_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])