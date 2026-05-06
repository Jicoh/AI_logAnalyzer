"""
Log Analyzer Subagent
日志分析Subagent，支持主流程和分析流程两种调用模式
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from jinja2 import Template

from .base import SubagentBase, SubagentResult
from src.ai_analyzer.client import AIClient
from src.utils import get_logger

logger = get_logger('log_analyzer_subagent')


# 内置工具定义（OpenAI格式）
BUILTIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_log_by_keyword",
            "description": "在指定日志文件中搜索关键词，返回匹配位置前后若干行的内容。用于深入分析特定问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "日志文件名（不含路径）"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词或短语"
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "上下文行数（前后各取这么多行），默认20",
                        "default": 20
                    }
                },
                "required": ["file", "keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_log_by_range",
            "description": "读取指定日志文件的指定行号范围。用于查看特定时间段的日志。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "日志文件名（不含路径）"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从1开始）"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号"
                    }
                },
                "required": ["file", "start_line", "end_line"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_log_file_info",
            "description": "获取所有日志文件的信息，包括文件名、大小、行数。用于了解可分析的日志范围。",
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
            "name": "search_knowledge_base",
            "description": "在知识库中搜索相关内容，用于深入了解特定问题的解决方案或相关知识。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询词"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

BUILTIN_TOOL_NAMES = [t["function"]["name"] for t in BUILTIN_TOOLS]


class ToolExecutor:
    """工具执行器"""

    def __init__(self, log_files: List[str], kb_manager=None, kb_id: str = None):
        """
        初始化工具执行器

        Args:
            log_files: 日志文件完整路径列表
            kb_manager: 知识库管理器实例
            kb_id: 知识库ID
        """
        self.file_map = {}
        for f in log_files:
            basename = os.path.basename(f)
            self.file_map[basename] = f
            if '.' in basename:
                name_without_ext = basename.rsplit('.', 1)[0]
                self.file_map[name_without_ext] = f

        self.kb_manager = kb_manager
        self.kb_id = kb_id
        self.file_info_cache = None

    def execute(self, tool_name: str, args: dict) -> dict:
        """执行工具调用"""
        if tool_name not in BUILTIN_TOOL_NAMES:
            return {"error": f"未知工具: {tool_name}"}

        try:
            if tool_name == "read_log_by_keyword":
                return self.read_by_keyword(args)
            elif tool_name == "read_log_by_range":
                return self.read_by_range(args)
            elif tool_name == "get_log_file_info":
                return self.get_file_info()
            elif tool_name == "search_knowledge_base":
                return self.search_kb(args)
        except Exception as e:
            logger.error(f"工具执行失败: {tool_name}, {str(e)}")
            return {"error": str(e)}

    def find_file(self, file_name: str) -> Optional[str]:
        """查找文件完整路径"""
        if file_name in self.file_map:
            return self.file_map[file_name]
        for name, path in self.file_map.items():
            if file_name in name or name in file_name:
                return path
        return None

    def read_by_keyword(self, args: dict) -> dict:
        """按关键词读取日志"""
        file_name = args.get('file', '')
        keyword = args.get('keyword', '')
        context_lines = args.get('context_lines', 20)

        file_path = self.find_file(file_name)
        if not file_path:
            return {"error": f"未找到文件: {file_name}", "available_files": list(self.file_map.keys())[:10]}

        if not os.path.exists(file_path):
            return {"error": f"文件不存在: {file_path}"}

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            return {"error": f"读取文件失败: {str(e)}"}

        matches = []
        for i, line in enumerate(lines):
            if keyword in line:
                matches.append(i)

        if not matches:
            return {
                "found": False,
                "keyword": keyword,
                "file": file_name,
                "message": f"未找到关键词: {keyword}"
            }

        target_idx = matches[0]
        start = max(0, target_idx - context_lines)
        end = min(len(lines), target_idx + context_lines + 1)

        content_lines = []
        for i in range(start, end):
            marker = ">>>" if i == target_idx else "   "
            content_lines.append(f"{marker} [{i+1}] {lines[i].rstrip()}")

        return {
            "found": True,
            "keyword": keyword,
            "file": file_name,
            "matched_line": target_idx + 1,
            "total_matches": len(matches),
            "content": '\n'.join(content_lines)
        }

    def read_by_range(self, args: dict) -> dict:
        """按行号范围读取日志"""
        file_name = args.get('file', '')
        start_line = args.get('start_line', 1)
        end_line = args.get('end_line', 100)

        file_path = self.find_file(file_name)
        if not file_path:
            return {"error": f"未找到文件: {file_name}"}

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            return {"error": f"读取文件失败: {str(e)}"}

        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)

        content_lines = []
        for i in range(start_idx, end_idx):
            content_lines.append(f"[{i+1}] {lines[i].rstrip()}")

        return {
            "file": file_name,
            "start_line": start_idx + 1,
            "end_line": end_idx,
            "total_lines": len(lines),
            "content": '\n'.join(content_lines)
        }

    def get_file_info(self) -> dict:
        """获取所有日志文件信息"""
        if self.file_info_cache:
            return self.file_info_cache

        files_info = []
        for basename, path in self.file_map.items():
            if not os.path.exists(path):
                continue
            try:
                size = os.path.getsize(path)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    line_count = sum(1 for _ in f)
                files_info.append({
                    "name": basename,
                    "path": path,
                    "size_bytes": size,
                    "size_kb": round(size / 1024, 2),
                    "line_count": line_count
                })
            except Exception:
                continue

        files_info.sort(key=lambda x: x['size_bytes'], reverse=True)

        self.file_info_cache = {
            "total_files": len(files_info),
            "files": files_info
        }
        return self.file_info_cache

    def search_kb(self, args: dict) -> dict:
        """搜索知识库"""
        query = args.get('query', '')

        if not self.kb_manager or not self.kb_id:
            return {"error": "知识库未配置", "available": False}

        try:
            results = self.kb_manager.search(self.kb_id, query, top_k=3)
            chunks = []
            for r in results:
                chunk = r.get('chunk', {})
                content = chunk.get('content', '')
                if content:
                    chunks.append({
                        "content": content[:500],
                        "source": chunk.get('source', '未知')
                    })
            return {
                "query": query,
                "found": len(chunks) > 0,
                "results": chunks
            }
        except Exception as e:
            return {"error": f"知识库搜索失败: {str(e)}"}


class LogAnalyzerSubagent(SubagentBase):
    """日志分析Subagent，支持主流程和分析流程两种调用模式"""

    name = "log_analyzer"
    description = "BMC服务器日志分析，识别问题并提供解决方案"
    capabilities = [
        "日志文件分析",
        "问题识别",
        "风险评估",
        "解决方案推荐",
        "知识库检索",
        "智能选择插件和文件"
    ]

    # 智能选择提示词
    SELECTION_PROMPT = """
你是一个预处理Agent，负责根据用户请求选择合适的插件和日志文件进行分析。

## 可用插件
{plugin_descriptions}

## 日志文件
{file_descriptions}

## 用户请求
{user_prompt}

请根据用户请求，选择最适合的插件和日志文件进行分析。

返回JSON格式结果（仅返回JSON，不要包含其他内容）：
```json
{
    "selected_plugins": ["plugin_id_1", "plugin_id_2"],
    "selected_files": ["file_1.log", "file_2.log"],
    "fallback": false,
    "reason": "选择原因的简要说明"
}
```

判断规则：
1. 如果用户请求与特定关键词匹配，选择相关插件和文件
2. 如果用户请求模糊或无明确分析目标，设置fallback=true，表示需要全量分析
3. 如果用户请求与任何插件能力或文件关键词都不匹配，设置fallback=true
4. fallback=true时，selected_plugins和selected_files包含所有插件和文件
5. 优先选择能解决用户问题的最精简组合，避免冗余分析
"""

    def __init__(self, config_manager=None, kb_manager=None, mcp_client=None,
                 log_metadata_manager=None, plugin_manager=None):
        super().__init__(config_manager, kb_manager, mcp_client)
        self.log_metadata_manager = log_metadata_manager
        self.plugin_manager = plugin_manager
        self.client = None
        self.html_template = None
        self.prompt_path = None
        self.template_path = None
        self.max_tokens = 60000
        self.max_rounds = 10

    def _init_client(self, api_config: Dict = None):
        """延迟初始化AI客户端"""
        if self.client is None:
            if api_config:
                self.client = AIClient(api_config)
            elif self.config_manager:
                api_config = self.config_manager.get('api', {})
                self.client = AIClient(api_config)

            # 加载配置
            if self.config_manager:
                agent_config = self.config_manager.get('agent', {})
                self.max_tokens = agent_config.get('max_tokens', 60000)
                self.max_rounds = agent_config.get('max_rounds', 10)

            # 加载模板
            self._load_template()
            self._get_prompt_path()

    def _get_prompt_path(self) -> str:
        """获取prompt文件路径"""
        if self.prompt_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            self.prompt_path = os.path.join(project_root, 'config', 'agent_prompt.txt')
        return self.prompt_path

    def _get_template_path(self) -> str:
        """获取HTML模板路径"""
        if self.template_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            self.template_path = os.path.join(project_root, 'src', 'ai_analyzer', 'templates', 'ai_report_template.html')
        return self.template_path

    def _load_template(self):
        """加载HTML模板"""
        if self.html_template is None:
            template_path = self._get_template_path()
            if os.path.exists(template_path):
                with open(template_path, 'r', encoding='utf-8') as f:
                    self.html_template = Template(f.read())

    def _load_prompt(self) -> str:
        """加载prompt模板"""
        prompt_path = self._get_prompt_path()
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        return self._default_prompt()

    def _default_prompt(self) -> str:
        """默认prompt"""
        return """你是BMC服务器日志分析专家。

# 核心原则
1. 有理有据：每条结论必须引用具体日志内容
2. 因果分析：不只列现象，要分析根因和逻辑链
3. 潜在风险：发现任何可疑迹象都要输出，但要说明依据
4. 简洁精确：禁止emoji，禁止废话，禁止无依据的免责声明

# 分析数据
{analysis_data}

# 输出要求
输出合法JSON，包含: machine_info, analysis_summary, problems, potential_risks, solutions, risk_assessment, analysis_coverage

直接输出JSON对象，不要包裹在代码块中。"""

    def _build_tools(self) -> list:
        """构建完整工具列表（内置工具 + MCP工具）"""
        tools = BUILTIN_TOOLS.copy()
        if self.mcp_client:
            mcp_tools = self.mcp_client.list_tools()
            tools.extend(mcp_tools)
            logger.debug(f"已加载 {len(mcp_tools)} 个MCP工具")
        return tools

    def analyze(
        self,
        log_files: List[str],
        plugin_result: Dict = None,
        machine_info: Dict = None,
        knowledge_content: str = None,
        log_rules: str = None,
        analysis_templates: str = None,
        kb_id: str = None,
        user_prompt: str = None,
        user_intent: str = None,
        api_config: Dict = None
    ) -> Dict[str, Any]:
        """
        统一分析接口

        Args:
            log_files: 日志文件路径列表
            plugin_result: 插件分析结果（分析流程传入）
            machine_info: 机器信息（分析流程传入）
            knowledge_content: 知识库内容（分析流程传入）
            log_rules: 日志规则描述
            analysis_templates: 分析模板
            kb_id: 知识库ID
            user_prompt: 用户提示词
            user_intent: 用户意图（主流程传入）
            api_config: API配置（可选）

        Returns:
            dict: {'html': str, 'interaction_record': dict, 'intent_response': str}
        """
        self._init_client(api_config)

        if self.client is None:
            return {
                'html': self._generate_error_html("初始化失败", "AI客户端未初始化"),
                'interaction_record': {'error': 'AI客户端未初始化'},
                'intent_response': ''
            }

        if not log_files:
            return {
                'html': self._generate_error_html("无日志文件", "没有可分析的日志文件"),
                'interaction_record': {'error': '无日志文件'},
                'intent_response': ''
            }

        return self._run_ai_analysis(
            log_files=log_files,
            plugin_result=plugin_result or {},
            machine_info=machine_info or {},
            knowledge_content=knowledge_content or "",
            log_rules=log_rules or "无日志规则",
            analysis_templates=analysis_templates or "",
            user_prompt=user_prompt or "",
            kb_id=kb_id,
            user_intent=user_intent
        )

    def execute(
        self,
        request: str,
        context: Dict[str, Any],
        work_dir: str
    ) -> SubagentResult:
        """
        SubagentBase 接口实现（供 OrchestratorAgent 调用）
        主流程路径：自动选择插件并执行分析
        """
        log_files = context.get('log_files', [])
        kb_id = context.get('kb_id')
        user_intent = context.get('user_intent', request)
        api_config = context.get('subagent_api_config')

        self._init_client(api_config)

        if self.client is None:
            return SubagentResult(
                success=False,
                content="",
                error="AI客户端未初始化"
            )

        if not log_files:
            return SubagentResult(
                success=False,
                content="",
                error="缺少日志文件"
            )

        # 主流程：自动选择插件并执行
        plugin_result = {}
        machine_info = {}
        knowledge_content = ""
        log_rules = ""
        analysis_templates = ""

        # 智能选择插件（如果组件可用）
        if self.plugin_manager and user_intent:
            selection = self._smart_select(log_files, user_intent)
            if not selection.get('fallback', True):
                # 执行选择的插件
                plugin_result = self._run_plugin_analysis(
                    selection['selected_plugins'],
                    selection['selected_files']
                )
                # 更新 log_files 为选中的文件
                log_files = selection['selected_files']

        # 提取机器信息
        if plugin_result:
            machine_info = self._extract_machine_info(plugin_result)

        # 获取日志规则
        if self.log_metadata_manager and log_files:
            log_rules = self._get_log_rules(log_files)

        # 检索知识库
        if kb_id and self.kb_manager and plugin_result:
            knowledge_content = self._retrieve_knowledge(kb_id, plugin_result)

        # 加载分析模板
        analysis_templates = self._load_analysis_templates()

        # 执行AI分析
        result = self._run_ai_analysis(
            log_files=log_files,
            plugin_result=plugin_result,
            machine_info=machine_info,
            knowledge_content=knowledge_content,
            log_rules=log_rules,
            analysis_templates=analysis_templates,
            user_prompt=request,
            kb_id=kb_id,
            user_intent=user_intent
        )

        html = result.get('html', '')
        interaction_record = result.get('interaction_record', {})
        intent_response = result.get('intent_response', '')

        return SubagentResult(
            success=True,
            content=intent_response or "分析完成，请查看详细报告",
            data={
                "html": html,
                "interaction_record": interaction_record,
                "intent_response": intent_response
            },
            metadata={
                "analysis_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "log_files": [os.path.basename(f) for f in log_files],
                "kb_used": bool(knowledge_content),
                "user_intent": user_intent
            }
        )

    def _smart_select(
        self,
        log_files: List[str],
        user_prompt: str,
        rules_id: str = None
    ) -> Dict[str, Any]:
        """
        智能选择插件和文件

        Args:
            log_files: 日志文件路径列表
            user_prompt: 用户提示词
            rules_id: 规则集ID

        Returns:
            dict: 选择结果，包含selected_plugins, selected_files, fallback, reason
        """
        if not self.log_metadata_manager or not self.plugin_manager:
            logger.warning("缺少log_metadata_manager或plugin_manager，执行全量分析")
            return self._fallback_result(log_files, "缺少必要组件")

        if not user_prompt or not user_prompt.strip():
            logger.debug("无用户提示词，执行全量分析")
            return self._fallback_result(log_files, "无用户提示词")

        api_config = {}
        if self.config_manager:
            api_config = self.config_manager.get('api', {})

        if not api_config.get('base_url') or not api_config.get('api_key'):
            logger.warning("API配置不完整，执行全量分析")
            return self._fallback_result(log_files, "API配置不完整")

        plugin_descriptions = self.plugin_manager.get_plugins_ai_description()
        file_descriptions = self.log_metadata_manager.get_file_descriptions(log_files, rules_id)

        prompt = self.SELECTION_PROMPT.format(
            plugin_descriptions=plugin_descriptions,
            file_descriptions=file_descriptions,
            user_prompt=user_prompt
        )

        try:
            logger.debug(f"智能选择开始，日志文件数: {len(log_files)}")
            ai_client = AIClient(api_config)
            messages = [{"role": "user", "content": prompt}]

            response_text = ""
            for chunk in ai_client.chat(messages):
                response_text += chunk

            result = self._parse_selection_response(response_text, log_files)
            logger.debug(f"智能选择完成，结果: {result.get('reason', '未知')}")
            return result

        except Exception as e:
            logger.error(f"智能选择失败: {str(e)}", exc_info=True)
            return self._fallback_result(log_files, f"智能选择失败: {str(e)}")

    def _parse_selection_response(self, response_text: str, log_files: List[str]) -> Dict[str, Any]:
        """解析智能选择响应"""
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            json_text = json_match.group(1)
        else:
            json_text = response_text

        try:
            result = json.loads(json_text.strip())

            if not isinstance(result, dict):
                return self._fallback_result(log_files, "响应格式错误")

            if result.get('fallback', False):
                return self._fallback_result(log_files, result.get('reason', '用户请求不明确'))

            selected_plugins = result.get('selected_plugins', [])
            all_plugin_ids = [p.id for p in self.plugin_manager.get_all_plugins()]
            valid_plugins = [p for p in selected_plugins if p in all_plugin_ids]

            if not valid_plugins:
                return self._fallback_result(log_files, "未选择有效插件")

            selected_files = result.get('selected_files', [])
            valid_files = []
            for selected_file in selected_files:
                for log_file in log_files:
                    if selected_file in log_file or os.path.basename(log_file) == selected_file:
                        valid_files.append(log_file)
                        break

            if not valid_files:
                return self._fallback_result(log_files, "未选择有效文件")

            return {
                'selected_plugins': valid_plugins,
                'selected_files': valid_files,
                'fallback': False,
                'reason': result.get('reason', '智能选择完成')
            }

        except json.JSONDecodeError:
            return self._fallback_result(log_files, "JSON解析失败")

    def _fallback_result(self, log_files: List[str], reason: str) -> Dict[str, Any]:
        """生成fallback结果"""
        all_plugin_ids = [p.id for p in self.plugin_manager.get_all_plugins()] if self.plugin_manager else []
        return {
            'selected_plugins': all_plugin_ids,
            'selected_files': log_files,
            'fallback': True,
            'reason': reason
        }

    def _run_plugin_analysis(self, plugin_ids: List[str], log_files: List[str]) -> Dict[str, Any]:
        """执行插件分析"""
        if not self.plugin_manager:
            return {}

        result = {}
        for plugin_id in plugin_ids:
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if plugin:
                try:
                    analysis = plugin.analyze(log_files)
                    result[plugin_id] = analysis.to_dict()
                except Exception as e:
                    logger.error(f"插件 {plugin_id} 分析失败: {str(e)}")

        return result

    def _extract_machine_info(self, plugin_result: Dict) -> Dict[str, Any]:
        """从插件结果中提取机器信息"""
        machine_info = {
            'serial_number': '未知',
            'model': '未知',
            'product_name': '未知',
            'board_type': '未知',
            'bmc_version': '未知',
            'bios_version': '未知',
            'firmware_version': '未知',
            'bmc_ip_address': '未知'
        }

        info_plugin_ids = ['bmc_info', 'system_info', 'machine_info', 'hardware_info']

        for plugin_id, plugin_data in plugin_result.items():
            if plugin_id in info_plugin_ids or 'info' in plugin_id.lower():
                sections = plugin_data.get('sections', [])
                for section in sections:
                    if section.get('type') == 'stats':
                        for item in section.get('items', []):
                            label = item.get('label', '')
                            value = item.get('value', '')

                            if isinstance(value, str):
                                if '序列号' in label or 'Serial' in label:
                                    machine_info['serial_number'] = value
                                elif '型号' in label or 'Model' in label or '机型' in label:
                                    machine_info['model'] = value
                                elif '产品' in label or 'Product' in label:
                                    machine_info['product_name'] = value
                                elif '主板' in label or 'Board' in label:
                                    machine_info['board_type'] = value
                                elif 'BMC' in label and '版本' in label:
                                    machine_info['bmc_version'] = value
                                elif 'BIOS' in label:
                                    machine_info['bios_version'] = value
                                elif '固件' in label or 'Firmware' in label:
                                    machine_info['firmware_version'] = value
                                elif 'IP' in label and 'BMC' in label:
                                    machine_info['bmc_ip_address'] = value

                    if section.get('type') == 'cards':
                        for card in section.get('cards', []):
                            card_title = card.get('title', '')
                            content = card.get('content', {})

                            if '机器' in card_title or '系统' in card_title or 'BMC' in card_title:
                                metrics = content.get('metrics', {})
                                for key, val in metrics.items():
                                    if isinstance(val, str):
                                        if '序列号' in key or 'Serial' in key:
                                            machine_info['serial_number'] = val
                                        elif '型号' in key or 'Model' in key:
                                            machine_info['model'] = val
                                        elif 'BMC' in key and '版本' in key:
                                            machine_info['bmc_version'] = val

        return machine_info

    def _get_log_rules(self, log_files: List[str], rules_id: str = None) -> str:
        """获取日志规则描述"""
        if not self.log_metadata_manager:
            return "无日志规则"

        try:
            plugin_log_files = [os.path.basename(f) for f in log_files]
            return self.log_metadata_manager.get_file_descriptions(plugin_log_files, rules_id)
        except Exception as e:
            logger.warning(f"获取日志规则失败: {str(e)}")
            return "无文件描述规则"

    def _retrieve_knowledge(self, kb_id: str, plugin_result: Dict) -> str:
        """检索知识库内容"""
        if not self.kb_manager or not kb_id:
            return ""

        queries = []
        for plugin_id, plugin_data in plugin_result.items():
            sections = plugin_data.get('sections', [])
            for section in sections:
                if section.get('type') == 'table':
                    severity = section.get('severity', '')
                    if severity in ['error', 'warning']:
                        for row in section.get('rows', [])[:3]:
                            message = row.get('message', '')
                            if message:
                                queries.append(message[:100])

        if not queries:
            return ""

        try:
            results = []
            for query in queries[:5]:
                search_results = self.kb_manager.search(kb_id, query, 2)
                results.extend(search_results)

            seen = set()
            content_parts = []
            for result in results:
                chunk = result.get('chunk', {})
                content = chunk.get('content', '')
                if content and content not in seen:
                    seen.add(content)
                    content_parts.append(content[:500])

            return '\n\n'.join(content_parts)
        except Exception as e:
            logger.warning(f"知识库检索失败: {str(e)}")
            return ""

    def _load_analysis_templates(self) -> str:
        """加载分析模板配置"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        template_path = os.path.join(project_root, 'config', 'analysis_templates.json')

        if not os.path.exists(template_path):
            return ""

        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            templates = data.get('templates', [])
            lines = []
            for t in templates:
                lines.append(f"### {t.get('problem_type', '未知类型')}")
                keywords = t.get('keywords', [])
                if keywords:
                    lines.append(f"关键词: {', '.join(keywords)}")
                logic = t.get('analysis_logic', [])
                if logic:
                    lines.append("分析步骤:")
                    for step in logic:
                        lines.append(f"  {step}")
                causes = t.get('typical_causes', [])
                if causes:
                    lines.append(f"典型原因: {', '.join(causes)}")
                lines.append("")

            return '\n'.join(lines)
        except Exception as e:
            logger.warning(f"加载分析模板失败: {str(e)}")
            return ""

    def _run_ai_analysis(
        self,
        log_files: List[str],
        plugin_result: Dict,
        machine_info: Dict,
        knowledge_content: str,
        log_rules: str,
        analysis_templates: str,
        user_prompt: str,
        kb_id: str = None,
        user_intent: str = None
    ) -> Dict[str, Any]:
        """执行AI分析"""
        logger.info(f"开始分析，日志文件数: {len(log_files)}")

        tool_executor = ToolExecutor(log_files, self.kb_manager, kb_id)
        tools = self._build_tools()

        prompt_data = {
            'plugin_result': self._format_plugin_result(plugin_result),
            'machine_info': self._format_machine_info(machine_info),
            'knowledge_content': knowledge_content or "无知识库内容",
            'log_rules': log_rules or "无日志规则",
            'log_files_overview': self._format_log_files(log_files),
            'analysis_templates': analysis_templates or "无分析模板",
            'user_prompt': user_prompt or "无用户提示词"
        }

        prompt_template = self._load_prompt()
        system_prompt = prompt_template.format(**{k: self._escape_braces(v) for k, v in prompt_data.items()})

        enhanced_prompt = self._build_enhanced_prompt(user_prompt, user_intent)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": enhanced_prompt or "请开始分析日志，输出JSON结果。"}
        ]

        interactions = []
        round_count = 0
        total_tokens = 0
        final_response = None
        validation_errors = []

        while round_count < self.max_rounds and total_tokens < self.max_tokens:
            round_count += 1
            logger.debug(f"第{round_count}轮交互开始")

            try:
                response = self.client.chat_with_tools(messages, tools, "auto")
            except Exception as e:
                logger.error(f"AI调用失败: {str(e)}")
                validation_errors.append(f"AI调用失败: {str(e)}")
                break

            round_record = {
                "round": round_count,
                "token_estimate": self.client.count_tokens(messages)
            }

            if response.has_tool_calls():
                tool_results = []
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get('function', {}).get('name', '')
                    args_str = tool_call.get('function', {}).get('arguments', '{}')
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}

                    if tool_name in BUILTIN_TOOL_NAMES:
                        result = tool_executor.execute(tool_name, args)
                    elif self.mcp_client:
                        result = self.mcp_client.call_tool(tool_name, args)
                    else:
                        result = {"error": f"未知工具: {tool_name}"}

                    tool_results.append({
                        "tool_call_id": tool_call.get('id', ''),
                        "name": tool_name,
                        "args": args,
                        "result": result
                    })

                round_record["tool_calls"] = tool_results

                messages.append(response.to_message())
                for tr in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": json.dumps(tr["result"], ensure_ascii=False)
                    })

                interactions.append(round_record)
                total_tokens += round_record["token_estimate"]

                logger.debug(f"执行工具: {len(tool_results)}个")

            else:
                round_record["response"] = response.content
                interactions.append(round_record)
                final_response = response.content

                data, errors = self._validate_output(final_response)
                if not errors:
                    html = self._render_html(data)
                    logger.info(f"分析完成，共{round_count}轮交互")
                    return {
                        'html': html,
                        'interaction_record': self._build_interaction_record(
                            system_prompt, prompt_data, interactions, data, True, []
                        ),
                        'intent_response': self._extract_intent_response(data, user_intent)
                    }

                validation_errors = errors
                logger.warning(f"验证失败: {errors}")

                if round_count < 2:
                    retry_prompt = self._build_retry_prompt(errors, final_response)
                    messages.append(response.to_message())
                    messages.append({"role": "user", "content": retry_prompt})
                    continue
                else:
                    break

        logger.warning("验证重试失败，启用降级HTML生成")
        html, fallback_interaction = self._generate_html_fallback(
            prompt_data, final_response, validation_errors
        )

        return {
            'html': html,
            'interaction_record': self._build_interaction_record(
                system_prompt, prompt_data, interactions, None, False, validation_errors,
                fallback_interaction
            ),
            'intent_response': ""
        }

    def _build_enhanced_prompt(self, user_prompt: str, user_intent: str) -> str:
        """构建增强的用户提示词"""
        if user_intent and user_intent != user_prompt:
            return f"【用户关注点】{user_intent}\n\n【分析请求】{user_prompt or '请开始分析'}"
        return user_prompt or "请开始分析日志，输出JSON结果。"

    def _validate_output(self, response_text: str) -> tuple:
        """验证AI输出"""
        if not response_text:
            return None, ["AI返回空内容"]

        json_text = self._extract_json(response_text)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            return None, [f"JSON格式错误: {str(e)}"]

        required_fields = ['machine_info', 'analysis_summary', 'problems',
                          'potential_risks', 'solutions', 'risk_assessment']
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"缺少必需字段: {field}")

        problems = data.get('problems', [])
        potential_risks = data.get('potential_risks', [])
        if not problems and not potential_risks:
            summary = data.get('analysis_summary', '')
            if '无异常' not in summary and '正常' not in summary:
                errors.append("未发现任何问题或风险，请确认是否真的无异常")

        if errors:
            return None, errors

        return data, []

    def _extract_json(self, text: str) -> str:
        """从响应中提取JSON"""
        text = text.strip()

        match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
        if match:
            return match.group(1).strip()

        start = text.find('{')
        if start >= 0:
            brace_count = 0
            end = start
            for i, c in enumerate(text[start:]):
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = start + i + 1
                        break
            return text[start:end]

        return text

    def _build_retry_prompt(self, errors: List[str], failed_response: str) -> str:
        """构建重试提示词"""
        error_preview = failed_response[:1000] if failed_response else ""
        return f"""你之前的JSON输出验证失败，请修正后重新输出。

## 验证错误
{chr(10).join(errors)}

## 你之前的输出（有错误）
{error_preview}

## 修正要求
1. 确保输出完整的JSON对象
2. 包含所有必需字段: machine_info, analysis_summary, problems, potential_risks, solutions, risk_assessment
3. 如果确实未发现问题，请在analysis_summary中明确说明"无异常"或"正常"

请直接输出修正后的JSON，不要包含其他内容。"""

    def _generate_html_fallback(
        self,
        prompt_data: dict,
        original_response: str,
        validation_errors: List[str]
    ) -> tuple:
        """降级生成HTML"""
        fallback_prompt = f"""由于JSON格式验证失败，请直接生成HTML报告。

## 插件分析结果
{prompt_data.get('plugin_result', '无')}

## 机器信息
{prompt_data.get('machine_info', '无')}

## 日志文件
{prompt_data.get('log_files_overview', '无')}

## 用户请求
{prompt_data.get('user_prompt', '无')}

## 输出要求
1. 输出完整HTML，从<!DOCTYPE html>开始
2. 每个问题必须包含分析逻辑说明
3. 简洁精确，禁止emoji
4. 直接输出HTML代码，不要包裹在代码块中"""

        messages = [{"role": "user", "content": fallback_prompt}]

        try:
            response = self.client.chat_with_tools(messages)
            html = self._extract_html(response.content)
            fallback_record = {
                "prompt": fallback_prompt,
                "response": response.content[:2000],
                "success": True
            }
        except Exception as e:
            html = self._generate_error_html("降级HTML生成失败", str(e))
            fallback_record = {
                "success": False,
                "error": str(e)
            }

        return html, fallback_record

    def _extract_html(self, text: str) -> str:
        """从响应中提取HTML"""
        text = text.strip()

        match = re.search(r'```(?:html)?\s*\n?([\s\S]*?)\n?```', text)
        if match:
            return match.group(1).strip()

        if '<!DOCTYPE' in text or '<html' in text.lower():
            return text

        html_start = text.find('<')
        if html_start >= 0:
            return text[html_start:]

        return self._generate_simple_html(text)

    def _generate_simple_html(self, content: str) -> str:
        """生成简单HTML"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>AI分析报告</title></head>
<body style="font-family:sans-serif;padding:20px;">
<div style="background:white;padding:20px;margin:20px;border-radius:8px;">
<h2>AI分析结果</h2>
<pre style="white-space:pre-wrap;">{content}</pre>
</div>
</body></html>"""

    def _render_html(self, data: dict) -> str:
        """渲染HTML报告"""
        problems = data.get('problems', [])
        summary = {
            'errors': sum(1 for p in problems if p.get('severity') == 'error'),
            'warnings': sum(1 for p in problems if p.get('severity') == 'warning'),
            'info': sum(1 for p in problems if p.get('severity') == 'info')
        }

        if self.html_template:
            return self.html_template.render(
                machine_info=data.get('machine_info', {}),
                analysis_summary=data.get('analysis_summary', ''),
                summary=summary,
                problems=problems,
                potential_risks=data.get('potential_risks', []),
                solutions=data.get('solutions', []),
                risk_assessment=data.get('risk_assessment', {}),
                analysis_coverage=data.get('analysis_coverage', {}),
                analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
        return self._generate_fallback_html(data)

    def _generate_fallback_html(self, data: dict) -> str:
        """生成备用HTML"""
        html_parts = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">']
        html_parts.append('<title>AI日志分析报告</title>')
        html_parts.append('<style>')
        html_parts.append('body{font-family:sans-serif;padding:20px;background:#f8f9fa;}')
        html_parts.append('.card{background:white;padding:20px;margin:20px auto;border-radius:8px;max-width:800px;}')
        html_parts.append('.error{border-left:4px solid #dc3545;}')
        html_parts.append('.warning{border-left:4px solid #ffc107;}')
        html_parts.append('.info{border-left:4px solid #0dcaf0;}')
        html_parts.append('</style></head><body>')

        machine_info = data.get('machine_info', {})
        html_parts.append('<div class="card"><h2>机器信息</h2>')
        for k, v in machine_info.items():
            html_parts.append(f'<p><strong>{k}</strong>: {v}</p>')
        html_parts.append('</div>')

        html_parts.append('<div class="card"><h2>分析摘要</h2>')
        html_parts.append(f'<p>{data.get("analysis_summary", "无摘要")}</p>')
        html_parts.append('</div>')

        problems = data.get('problems', [])
        if problems:
            html_parts.append('<div class="card"><h2>发现的问题</h2>')
            for p in problems:
                sev = p.get('severity', 'info')
                html_parts.append(f'<div class="{sev}" style="padding:10px;margin:10px 0;">')
                html_parts.append(f'<h3>{p.get("title", "")}</h3>')
                html_parts.append(f'<p><strong>严重程度</strong>: {sev}</p>')
                if p.get('description'):
                    html_parts.append(f'<p>{p["description"]}</p>')
                if p.get('analysis_logic'):
                    html_parts.append(f'<p><strong>分析逻辑</strong>: {p["analysis_logic"]}</p>')
                if p.get('log_reference'):
                    html_parts.append(f'<pre style="background:#f5f5f5;padding:10px;">{p["log_reference"]}</pre>')
                html_parts.append('</div>')
            html_parts.append('</div>')

        risks = data.get('potential_risks', [])
        if risks:
            html_parts.append('<div class="card"><h2>潜在风险</h2>')
            for r in risks:
                html_parts.append('<div style="border-left:4px solid #ffc107;padding:10px;margin:10px 0;">')
                html_parts.append(f'<h3>{r.get("title", "")}</h3>')
                if r.get('reasoning'):
                    html_parts.append(f'<p><strong>推理依据</strong>: {r["reasoning"]}</p>')
                if r.get('recommendation'):
                    html_parts.append(f'<p><strong>建议</strong>: {r["recommendation"]}</p>')
                html_parts.append('</div>')
            html_parts.append('</div>')

        solutions = data.get('solutions', [])
        if solutions:
            html_parts.append('<div class="card"><h2>解决方案</h2>')
            for s in solutions:
                html_parts.append(f'<h3>{s.get("title", "")}</h3>')
                if s.get('description'):
                    html_parts.append(f'<p>{s["description"]}</p>')
                if s.get('steps'):
                    html_parts.append('<ul>')
                    for step in s['steps']:
                        html_parts.append(f'<li>{step}</li>')
                    html_parts.append('</ul>')
            html_parts.append('</div>')

        risk_assessment = data.get('risk_assessment', {})
        html_parts.append('<div class="card"><h2>风险评估</h2>')
        html_parts.append(f'<p><strong>等级</strong>: {risk_assessment.get("level", "未知")}</p>')
        if risk_assessment.get('description'):
            html_parts.append(f'<p>{risk_assessment["description"]}</p>')
        html_parts.append('</div>')

        coverage = data.get('analysis_coverage', {})
        if coverage:
            html_parts.append('<div class="card"><h2>分析覆盖范围</h2>')
            html_parts.append(f'<p><strong>深度</strong>: {coverage.get("analysis_depth", "未知")}</p>')
            if coverage.get('files_analyzed'):
                html_parts.append('<p><strong>已分析文件</strong>: ' + ', '.join(coverage['files_analyzed']) + '</p>')
            html_parts.append('</div>')

        html_parts.append('</body></html>')
        return ''.join(html_parts)

    def _generate_error_html(self, title: str, detail: str) -> str:
        """生成错误HTML"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>分析错误</title></head>
<body style="font-family:sans-serif;padding:20px;">
<div style="background:white;padding:20px;margin:20px;border-radius:8px;border:1px solid #dc3545;">
<h2 style="color:#dc3545;">{title}</h2>
<p>{detail}</p>
</div>
</body></html>"""

    def _build_interaction_record(
        self,
        system_prompt: str,
        prompt_data: dict,
        interactions: List,
        final_output: Optional[dict],
        validation_passed: bool,
        validation_errors: List[str],
        fallback: Optional[dict] = None
    ) -> dict:
        """构建交互记录"""
        return {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "agent": {
                "system_prompt": system_prompt[:2000],
                "analysis_data": {
                    "plugin_result_summary": prompt_data.get('plugin_result', '')[:500],
                    "log_files": list(prompt_data.keys()),
                    "knowledge_used": bool(prompt_data.get('knowledge_content'))
                },
                "interactions": interactions,
                "total_rounds": len(interactions),
                "final_output": final_output,
                "validation": {
                    "passed": validation_passed,
                    "errors": validation_errors
                },
                "fallback": fallback
            }
        }

    def _extract_intent_response(self, data: dict, user_intent: str) -> str:
        """从分析结果中提取针对用户意图的回应"""
        if not user_intent:
            return ""

        if data:
            summary = data.get('analysis_summary', '')
            if summary:
                return summary

        return ""

    def _escape_braces(self, text: str) -> str:
        """转义花括号"""
        if not text:
            return ""
        return text.replace('{', '{{').replace('}', '}}')

    def _format_plugin_result(self, plugin_result: Dict) -> str:
        """格式化插件结果"""
        lines = []
        for plugin_id, plugin_data in plugin_result.items():
            meta = plugin_data.get('meta', {})
            lines.append(f"### {meta.get('plugin_name', plugin_id)}")
            lines.append(f"- 分析文件: {meta.get('log_files', [])}")

            sections = plugin_data.get('sections', [])
            for section in sections:
                if section.get('type') == 'stats':
                    lines.append("\n统计概览:")
                    for item in section.get('items', []):
                        label = item.get('label', '')
                        value = item.get('value', '')
                        severity = item.get('severity', 'info')
                        lines.append(f"  - {label}: {value} [{severity}]")

                elif section.get('type') == 'table':
                    title = section.get('title', '表格')
                    rows = section.get('rows', [])
                    severity = section.get('severity', '')
                    lines.append(f"\n{title}: {len(rows)} 条记录 [{severity}]")

                    for i, row in enumerate(rows[:10]):
                        msg = row.get('message', row.get('content', ''))
                        if len(msg) > 80:
                            msg = msg[:80] + '...'
                        lines.append(f"  {i+1}: {msg}")

                    if len(rows) > 10:
                        lines.append(f"  ... 省略 {len(rows) - 10} 行")

        return '\n'.join(lines)

    def _format_machine_info(self, machine_info: Dict) -> str:
        """格式化机器信息"""
        if not machine_info:
            return "暂无机器信息"
        lines = []
        for k, v in machine_info.items():
            lines.append(f"- {k}: {v}")
        return '\n'.join(lines)

    def _format_log_files(self, log_files: List[str]) -> str:
        """格式化日志文件列表"""
        if not log_files:
            return "无日志文件"

        lines = ["可用日志文件:"]
        for f in log_files:
            basename = os.path.basename(f)
            try:
                size = os.path.getsize(f)
                size_kb = round(size / 1024, 2)
                lines.append(f"  - {basename} ({size_kb} KB)")
            except Exception:
                lines.append(f"  - {basename}")

        return '\n'.join(lines)

    def validate_context(self, context: Dict[str, Any]) -> bool:
        """验证上下文"""
        return 'log_files' in context and len(context.get('log_files', [])) > 0


def register_log_analyzer_subagent(registry, config_manager=None, kb_manager=None,
                                    mcp_client=None, log_metadata_manager=None,
                                    plugin_manager=None):
    """
    注册日志分析Subagent

    Args:
        registry: Subagent注册表
        config_manager: 配置管理器
        kb_manager: 知识库管理器
        mcp_client: MCP客户端
        log_metadata_manager: 日志元数据管理器
        plugin_manager: 插件管理器
    """
    subagent = LogAnalyzerSubagent(
        config_manager, kb_manager, mcp_client,
        log_metadata_manager, plugin_manager
    )
    registry.register(subagent)