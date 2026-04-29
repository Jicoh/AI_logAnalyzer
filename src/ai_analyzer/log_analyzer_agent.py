"""
Log Analyzer Agent - BMC日志分析Agent
支持多轮交互和工具调用
"""

import os
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from jinja2 import Template

from .client import AIClient, AIResponse
from src.utils import get_logger
from src.utils.json_parser import parse_ai_json_response

logger = get_logger('log_analyzer_agent')


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
            # 也支持部分匹配
            if '.' in basename:
                name_without_ext = basename.rsplit('.', 1)[0]
                self.file_map[name_without_ext] = f

        self.kb_manager = kb_manager
        self.kb_id = kb_id
        self.file_info_cache = None

    def execute(self, tool_name: str, args: dict) -> dict:
        """
        执行工具调用

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            dict: 工具执行结果
        """
        if tool_name not in BUILTIN_TOOL_NAMES:
            return {"error": f"未知工具: {tool_name}"}

        try:
            if tool_name == "read_log_by_keyword":
                return self._read_by_keyword(args)
            elif tool_name == "read_log_by_range":
                return self._read_by_range(args)
            elif tool_name == "get_log_file_info":
                return self._get_file_info()
            elif tool_name == "search_knowledge_base":
                return self._search_kb(args)
        except Exception as e:
            logger.error(f"工具执行失败: {tool_name}, {str(e)}")
            return {"error": str(e)}

    def _find_file(self, file_name: str) -> Optional[str]:
        """查找文件完整路径"""
        if file_name in self.file_map:
            return self.file_map[file_name]
        # 部分匹配
        for name, path in self.file_map.items():
            if file_name in name or name in file_name:
                return path
        return None

    def _read_by_keyword(self, args: dict) -> dict:
        """按关键词读取日志"""
        file_name = args.get('file', '')
        keyword = args.get('keyword', '')
        context_lines = args.get('context_lines', 20)

        file_path = self._find_file(file_name)
        if not file_path:
            return {"error": f"未找到文件: {file_name}", "available_files": list(self.file_map.keys())[:10]}

        if not os.path.exists(file_path):
            return {"error": f"文件不存在: {file_path}"}

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            return {"error": f"读取文件失败: {str(e)}"}

        # 搜索关键词
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

        # 取第一个匹配位置
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

    def _read_by_range(self, args: dict) -> dict:
        """按行号范围读取日志"""
        file_name = args.get('file', '')
        start_line = args.get('start_line', 1)
        end_line = args.get('end_line', 100)

        file_path = self._find_file(file_name)
        if not file_path:
            return {"error": f"未找到文件: {file_name}"}

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            return {"error": f"读取文件失败: {str(e)}"}

        # 转换为0-based索引
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

    def _get_file_info(self) -> dict:
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

        # 按大小排序
        files_info.sort(key=lambda x: x['size_bytes'], reverse=True)

        self.file_info_cache = {
            "total_files": len(files_info),
            "files": files_info
        }
        return self.file_info_cache

    def _search_kb(self, args: dict) -> dict:
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


class LogAnalyzerAgent:
    """BMC日志分析Agent"""

    def __init__(self, config_manager, kb_manager=None, mcp_client=None):
        """
        初始化Agent

        Args:
            config_manager: 配置管理器实例
            kb_manager: 知识库管理器实例
            mcp_client: MCP客户端实例（可选）
        """
        self.config_manager = config_manager
        self.kb_manager = kb_manager
        self.mcp_client = mcp_client

        api_config = config_manager.get('api', {})
        self.client = AIClient(api_config)

        agent_config = config_manager.get('agent', {})
        self.max_tokens = agent_config.get('max_tokens', 60000)
        self.max_rounds = agent_config.get('max_rounds', 10)

        self.prompt_path = self._get_prompt_path()
        self.template_path = self._get_template_path()
        self.html_template = self._load_template()

        # 构建工具列表（内置工具 + MCP工具）
        self.tools = self._build_tools()

    def _get_prompt_path(self) -> str:
        """获取prompt文件路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'config', 'agent_prompt.txt')

    def _get_template_path(self) -> str:
        """获取HTML模板路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, 'templates', 'ai_report_template.html')

    def _load_template(self) -> Optional[Template]:
        """加载HTML模板"""
        if os.path.exists(self.template_path):
            with open(self.template_path, 'r', encoding='utf-8') as f:
                return Template(f.read())
        return None

    def _build_tools(self) -> list:
        """构建完整工具列表（内置工具 + MCP工具）"""
        tools = BUILTIN_TOOLS.copy()
        if self.mcp_client:
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

    def _escape_braces(self, text: str) -> str:
        """转义花括号"""
        if not text:
            return ""
        return text.replace('{', '{{').replace('}', '}}')

    def run_analysis(
        self,
        plugin_result: Dict,
        log_files: List[str],
        machine_info: Dict,
        knowledge_content: str,
        log_rules: str,
        analysis_templates: str,
        user_prompt: str,
        kb_id: str = None
    ) -> Dict[str, Any]:
        """
        执行分析任务

        Args:
            plugin_result: 插件分析结果
            log_files: 日志文件路径列表
            machine_info: 机器信息
            knowledge_content: 知识库内容
            log_rules: 日志规则描述
            analysis_templates: 分析模板
            user_prompt: 用户提示词
            kb_id: 知识库ID

        Returns:
            dict: 包含html和interaction_record的结果
        """
        logger.info(f"开始分析，日志文件数: {len(log_files)}")

        # 初始化工具执行器
        tool_executor = ToolExecutor(log_files, self.kb_manager, kb_id)

        # 构建初始prompt
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

        # 构建初始消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请开始分析日志，输出JSON结果。"}
        ]

        # 多轮交互
        interactions = []
        round_count = 0
        total_tokens = 0
        final_response = None
        validation_errors = []

        while round_count < self.max_rounds and total_tokens < self.max_tokens:
            round_count += 1
            logger.debug(f"第{round_count}轮交互开始")

            # 调用AI（使用完整工具列表）
            try:
                response = self.client.chat_with_tools(messages, self.tools, "auto")
            except Exception as e:
                logger.error(f"AI调用失败: {str(e)}")
                validation_errors.append(f"AI调用失败: {str(e)}")
                break

            # 记录本轮交互
            round_record = {
                "round": round_count,
                "token_estimate": self.client.count_tokens(messages)
            }

            if response.has_tool_calls():
                # 执行工具调用
                tool_results = []
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get('function', {}).get('name', '')
                    args_str = tool_call.get('function', {}).get('arguments', '{}')
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}

                    # 区分内置工具和MCP工具
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

                # 将工具结果加入消息历史
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
                # 模型输出最终结果
                round_record["response"] = response.content
                interactions.append(round_record)
                final_response = response.content

                # 验证输出
                data, errors = self._validate_output(final_response)
                if not errors:
                    # 验证通过，渲染HTML
                    html = self._render_html(data)
                    logger.info(f"分析完成，共{round_count}轮交互")
                    return {
                        'html': html,
                        'interaction_record': self._build_interaction_record(
                            system_prompt, prompt_data, interactions, data, True, []
                        )
                    }

                # 验证失败，尝试重试一次
                validation_errors = errors
                logger.warning(f"验证失败: {errors}")

                if round_count < 2:  # 只重试一次
                    retry_prompt = self._build_retry_prompt(errors, final_response)
                    messages.append(response.to_message())
                    messages.append({"role": "user", "content": retry_prompt})
                    continue
                else:
                    break

        # 重试失败，启用降级方案
        logger.warning("验证重试失败，启用降级HTML生成")
        html, fallback_interaction = self._generate_html_fallback(
            prompt_data, final_response, validation_errors
        )

        return {
            'html': html,
            'interaction_record': self._build_interaction_record(
                system_prompt, prompt_data, interactions, None, False, validation_errors,
                fallback_interaction
            )
        }

    def _validate_output(self, response_text: str) -> tuple:
        """
        验证AI输出

        Returns:
            tuple: (data, errors)
        """
        if not response_text:
            return None, ["AI返回空内容"]

        # 提取JSON
        json_text = self._extract_json(response_text)

        # JSON格式验证
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            return None, [f"JSON格式错误: {str(e)}"]

        # Schema验证
        required_fields = ['machine_info', 'analysis_summary', 'problems',
                          'potential_risks', 'solutions', 'risk_assessment']
        errors = []
        for field in required_fields:
            if field not in data:
                errors.append(f"缺少必需字段: {field}")

        # 内容质量验证
        problems = data.get('problems', [])
        potential_risks = data.get('potential_risks', [])
        if not problems and not potential_risks:
            # 检查是否有明确的"无问题"声明
            summary = data.get('analysis_summary', '')
            if '无异常' not in summary and '正常' not in summary:
                errors.append("未发现任何问题或风险，请确认是否真的无异常")

        if errors:
            return None, errors

        return data, []

    def _extract_json(self, text: str) -> str:
        """从响应中提取JSON"""
        text = text.strip()

        # 尝试从代码块提取
        match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
        if match:
            return match.group(1).strip()

        # 尝试直接解析
        start = text.find('{')
        if start >= 0:
            # 找到最后一个匹配的}
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

        # 从代码块提取
        match = re.search(r'```(?:html)?\s*\n?([\s\S]*?)\n?```', text)
        if match:
            return match.group(1).strip()

        # 包含DOCTYPE或html标签
        if '<!DOCTYPE' in text or '<html' in text.lower():
            return text

        # 查找第一个HTML标签
        html_start = text.find('<')
        if html_start >= 0:
            return text[html_start:]

        # 生成简单HTML包装
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
        # 计算问题摘要统计
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

        # 机器信息
        machine_info = data.get('machine_info', {})
        html_parts.append('<div class="card"><h2>机器信息</h2>')
        for k, v in machine_info.items():
            html_parts.append(f'<p><strong>{k}</strong>: {v}</p>')
        html_parts.append('</div>')

        # 分析摘要
        html_parts.append('<div class="card"><h2>分析摘要</h2>')
        html_parts.append(f'<p>{data.get("analysis_summary", "无摘要")}</p>')
        html_parts.append('</div>')

        # 问题列表
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

        # 潜在风险
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

        # 解决方案
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

        # 风险评估
        risk_assessment = data.get('risk_assessment', {})
        html_parts.append('<div class="card"><h2>风险评估</h2>')
        html_parts.append(f'<p><strong>等级</strong>: {risk_assessment.get("level", "未知")}</p>')
        if risk_assessment.get('description'):
            html_parts.append(f'<p>{risk_assessment["description"]}</p>')
        html_parts.append('</div>')

        # 分析覆盖
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

                    # 显示前10行
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