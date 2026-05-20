"""
请求处理器，调用预加载的 PluginManager 执行分析
"""

from src.utils import get_logger
from src.agent import AgentService
from plugins.base import CliResult

logger = get_logger('serve_handler')


class RequestHandler:
    """处理客户端请求。"""

    def __init__(self):
        self._agent_service = None
        self._server = None

    def set_server(self, server):
        """设置 server 引用，用于 shutdown 操作。"""
        self._server = server

    def _ensure_agent_service(self):
        """延迟初始化 AgentService。"""
        if self._agent_service is None:
            import os
            import sys

            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
            if getattr(sys, 'frozen', False):
                root_dir = os.path.dirname(sys.executable)

            custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
            self._agent_service = AgentService()
            # 延迟初始化 plugin_manager 以加载自定义插件
            _ = self._agent_service.plugin_manager
            logger.info(f"插件已加载: "
                        f"{[p.id for p in self._agent_service.plugin_manager.get_all_plugins()]}")

    def handle(self, request: dict) -> dict:
        """处理请求，返回响应字典。"""
        action = request.get('action', '')

        if action == 'ping':
            return {'status': 'ok', 'message': 'pong'}

        if action == 'shutdown':
            if self._server:
                self._server.request_shutdown()
            return {'status': 'ok', 'message': 'shutting down'}

        if action == 'analyze':
            return self._handle_analyze(request)

        return {'status': 'error', 'message': f'未知操作: {action}'}

    def _handle_analyze(self, request: dict) -> dict:
        """处理分析请求。"""
        self._ensure_agent_service()

        plugin_id = request.get('plugin_id', '')
        log_content = request.get('log_content')
        task_name = request.get('task_name', '')
        bmc_ip = request.get('bmc_ip', '')
        date = request.get('date', '')

        if not plugin_id:
            return {'status': 'error', 'message': '缺少 plugin_id'}

        if log_content is None:
            return {'status': 'error', 'message': '缺少 log_content'}

        # 验证插件存在
        plugin = self._agent_service.plugin_manager.get_plugin(plugin_id)
        if not plugin:
            available = [p.id for p in self._agent_service.plugin_manager.get_all_plugins()]
            return {
                'status': 'error',
                'message': f'插件不存在: {plugin_id}，可用插件: {available}'
            }

        try:
            result = self._agent_service.run_plugin_only(
                source='cli',
                plugin_ids=[plugin_id],
                log_content=log_content,
                task_name=task_name,
                bmc_ip=bmc_ip,
                date=date
            )
            return {'status': 'ok', 'result': result}
        except Exception as e:
            logger.error(f"分析失败: {e}")
            return {'status': 'error', 'message': str(e)}
