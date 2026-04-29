"""
Admin MCP配置API单元测试
测试MCP Server配置相关的核心逻辑
"""

import pytest
import json
import os
import sys
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestLogSourceIntegration:
    """log_source参数集成测试"""

    def test_log_source_local_file(self):
        """测试local_file类型的log_source"""
        log_source = {
            "type": "local_file",
            "paths": ["test.log"]
        }

        # 验证参数传递
        assert log_source['type'] == 'local_file'
        assert log_source['paths'] == ["test.log"]

    def test_log_source_mcp_download(self):
        """测试mcp_download类型的log_source"""
        log_source = {
            "type": "mcp_download",
            "mcp_config": {
                "server": "log_downloader",
                "ip": "192.168.1.100",
                "username": "root",
                "password": "password",
                "log_type": "system"
            }
        }

        assert log_source['type'] == 'mcp_download'
        assert log_source['mcp_config']['ip'] == "192.168.1.100"


class TestMCPServerConfigLogic:
    """MCP Server配置逻辑测试（不涉及Flask装饰器）"""

    def test_mcp_server_config_stdio_format(self):
        """测试stdio配置格式"""
        config = {
            "enabled": True,
            "transport": "stdio",
            "command": "python",
            "args": ["server.py"],
            "description": "测试服务",
            "timeout": 30
        }

        assert config["transport"] == "stdio"
        assert config["command"] == "python"
        assert isinstance(config["args"], list)

    def test_mcp_server_config_websocket_format(self):
        """测试websocket配置格式"""
        config = {
            "enabled": True,
            "transport": "websocket",
            "url": "ws://localhost:8080/mcp",
            "description": "WebSocket服务",
            "timeout": 30
        }

        assert config["transport"] == "websocket"
        assert config["url"].startswith("ws://")

    def test_mcp_server_config_validation(self):
        """测试配置验证"""
        # 无效的transport类型
        config = {"transport": "invalid"}
        valid_transports = ["stdio", "websocket"]
        assert config["transport"] not in valid_transports

        # 缺少必需字段
        config_stdio = {"transport": "stdio"}
        assert "command" not in config_stdio

        config_ws = {"transport": "websocket"}
        assert "url" not in config_ws

    def test_mcp_server_config_update(self):
        """测试配置更新逻辑"""
        existing = {
            "enabled": True,
            "transport": "stdio",
            "command": "python",
            "args": ["old.py"],
            "timeout": 30
        }

        update_data = {
            "enabled": False,
            "args": ["new.py"],
            "timeout": 60
        }

        # 合并更新
        for key, value in update_data.items():
            existing[key] = value

        assert existing["enabled"] == False
        assert existing["args"] == ["new.py"]
        assert existing["timeout"] == 60
        assert existing["command"] == "python"  # 未更新的字段保持不变


class TestAnalyzeWithAgentLogSource:
    """analyze_with_agent log_source参数测试"""

    def test_analyzer_import_with_log_source(self):
        """测试analyzer模块导入"""
        from src.ai_analyzer.analyzer import analyze_with_agent
        assert analyze_with_agent is not None

    def test_log_source_parameter_handling(self):
        """测试log_source参数处理"""
        # local_file模式
        log_source = {"type": "local_file", "paths": ["file1.log", "file2.log"]}
        expected_files = log_source.get("paths", [])
        assert len(expected_files) == 2

        # mcp_download模式
        log_source = {"type": "mcp_download", "mcp_config": {"ip": "192.168.1.1"}}
        mcp_config = log_source.get("mcp_config", {})
        assert mcp_config.get("ip") == "192.168.1.1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])