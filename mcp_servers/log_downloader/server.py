"""
日志下载MCP Server示例
提供download_bmc_log和list_remote_logs两个工具
"""

import sys
import json
import os
import threading
import queue
from typing import Dict, Any

# 获取项目根目录
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SERVER_DIR))


class LogDownloaderServer:
    """日志下载MCP Server"""

    def __init__(self):
        self.tools = [
            {
                "name": "download_bmc_log",
                "description": "从BMC服务器下载日志文件。下载后返回本地文件路径，可用于后续分析。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ip": {
                            "type": "string",
                            "description": "BMC服务器IP地址"
                        },
                        "username": {
                            "type": "string",
                            "description": "登录用户名，默认为root"
                        },
                        "password": {
                            "type": "string",
                            "description": "登录密码"
                        },
                        "log_type": {
                            "type": "string",
                            "description": "日志类型: system(系统日志)/audit(审计日志)/sel(系统事件日志)",
                            "enum": ["system", "audit", "sel"]
                        }
                    },
                    "required": ["ip"]
                }
            },
            {
                "name": "list_remote_logs",
                "description": "列出远程BMC服务器上的可用日志文件，返回文件名和大小信息。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ip": {
                            "type": "string",
                            "description": "BMC服务器IP地址"
                        },
                        "username": {
                            "type": "string",
                            "description": "登录用户名"
                        },
                        "password": {
                            "type": "string",
                            "description": "登录密码"
                        }
                    },
                    "required": ["ip"]
                }
            },
            {
                "name": "get_machine_info",
                "description": "获取远程BMC服务器的机器信息，包括序列号、型号、版本等。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ip": {
                            "type": "string",
                            "description": "BMC服务器IP地址"
                        },
                        "username": {
                            "type": "string",
                            "description": "登录用户名"
                        },
                        "password": {
                            "type": "string",
                            "description": "登录密码"
                        }
                    },
                    "required": ["ip"]
                }
            }
        ]
        self.protocol_version = "2024-11-05"

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理JSON-RPC请求"""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        result = None
        error = None

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "initialized":
                # 通知事件，无需响应
                result = {}
            elif method == "tools/list":
                result = self._handle_tools_list()
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            elif method == "resources/list":
                result = {"resources": []}
            elif method == "ping":
                result = {}
            else:
                error = {
                    "code": -32601,
                    "message": f"方法不存在: {method}"
                }
        except Exception as e:
            error = {
                "code": -32603,
                "message": str(e)
            }

        response = {"jsonrpc": "2.0", "id": request_id}
        if error:
            response["error"] = error
        else:
            response["result"] = result

        return response

    def _handle_initialize(self, params: dict) -> dict:
        """处理initialize请求"""
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {
                "tools": {},
                "resources": {}
            },
            "serverInfo": {
                "name": "log_downloader",
                "version": "1.0.0"
            }
        }

    def _handle_tools_list(self) -> dict:
        """处理tools/list请求"""
        return {"tools": self.tools}

    def _handle_tools_call(self, params: dict) -> dict:
        """处理tools/call请求"""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "download_bmc_log":
            return self._execute_download(arguments)
        elif tool_name == "list_remote_logs":
            return self._execute_list_logs(arguments)
        elif tool_name == "get_machine_info":
            return self._execute_get_machine_info(arguments)
        else:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"未知工具: {tool_name}"}]
            }

    def _execute_download(self, args: dict) -> dict:
        """执行下载工具（模拟实现）"""
        ip = args.get("ip", "")
        log_type = args.get("log_type", "system")

        if not ip:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "缺少必需参数: ip"}]
            }

        # 模拟下载 - 实际实现需要SSH或Redfish API
        temp_dir = os.path.join(PROJECT_ROOT, "data", "temp")
        os.makedirs(temp_dir, exist_ok=True)

        # 创建模拟日志文件
        filename = f"downloaded_{ip.replace('.', '_')}_{log_type}.log"
        filepath = os.path.join(temp_dir, filename)

        # 写入模拟内容
        mock_content = f"""# BMC日志下载模拟
# 来源: {ip}
# 类型: {log_type}
# 时间: {self._get_timestamp()}

[INFO] BMC系统启动完成
[INFO] 网络配置: IP={ip}
[INFO] 服务状态: 正常运行
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(mock_content)

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"已成功从 {ip} 下载 {log_type} 日志\n"
                            f"本地路径: {filepath}\n"
                            f"文件大小: {len(mock_content)} 字节"
                }
            ],
            "isError": False,
            "local_path": filepath,
            "ip": ip,
            "log_type": log_type
        }

    def _execute_list_logs(self, args: dict) -> dict:
        """执行列出日志工具（模拟实现）"""
        ip = args.get("ip", "")

        if not ip:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "缺少必需参数: ip"}]
            }

        # 模拟返回日志列表
        logs = [
            {"name": "system.log", "size_kb": 512, "description": "系统日志"},
            {"name": "audit.log", "size_kb": 256, "description": "审计日志"},
            {"name": "sel.log", "size_kb": 128, "description": "系统事件日志"},
            {"name": "ipmi.log", "size_kb": 64, "description": "IPMI日志"},
            {"name": "sensor.log", "size_kb": 32, "description": "传感器日志"}
        ]

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"BMC服务器 {ip} 可用日志文件:\n" +
                            "\n".join([f"- {log['name']} ({log['size_kb']}KB): {log['description']}"
                                      for log in logs])
                }
            ],
            "isError": False,
            "logs": logs,
            "ip": ip
        }

    def _execute_get_machine_info(self, args: dict) -> dict:
        """执行获取机器信息工具（模拟实现）"""
        ip = args.get("ip", "")

        if not ip:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "缺少必需参数: ip"}]
            }

        # 模拟机器信息
        machine_info = {
            "serial_number": f"SN{ip.replace('.', '')}",
            "product_name": "ProServer R440",
            "board_type": "BMC-Board-V3",
            "bmc_version": "5.20.20240101",
            "bios_version": "2.15.01",
            "bmc_ip_address": ip
        }

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"BMC服务器 {ip} 机器信息:\n" +
                            "\n".join([f"- {k}: {v}" for k, v in machine_info.items()])
                }
            ],
            "isError": False,
            "machine_info": machine_info,
            "ip": ip
        }

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def run_server():
    """运行Server主循环"""
    server = LogDownloaderServer()

    # 使用stdin/stdout通信
    while True:
        try:
            # 读取一行请求
            line = sys.stdin.readline()
            if not line:
                break

            # 解析请求
            line = line.strip()
            if not line:
                continue

            request = json.loads(line)

            # 处理请求
            response = server.handle_request(request)

            # 发送响应
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"JSON解析错误: {str(e)}"}
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"内部错误: {str(e)}"}
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_server()