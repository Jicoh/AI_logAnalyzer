"""
Log Analyzer Agent 单元测试
测试 ToolExecutor、LogAnalyzerAgent、验证机制、降级HTML生成
"""

import os
import json
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# 项目路径设置
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'src'))
sys.path.insert(0, project_root)

from ai_analyzer.log_analyzer_agent import (
    ToolExecutor, LogAnalyzerAgent, BUILTIN_TOOLS, BUILTIN_TOOL_NAMES
)
from ai_analyzer.client import AIResponse


# ==================== ToolExecutor 测试 ====================

class TestToolExecutor:
    """工具执行器测试"""

    def setup_method(self):
        """每个测试方法前创建临时目录和文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, 'test.log')

        # 创建测试日志文件
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("""[2024-01-01 10:00:00] INFO: System started
[2024-01-01 10:01:00] ERROR: Connection failed
[2024-01-01 10:02:00] WARNING: Temperature high
[2024-01-01 10:03:00] ERROR: Disk error detected
[2024-01-01 10:04:00] INFO: Service recovered
""")

        self.executor = ToolExecutor([self.log_file])

    def teardown_method(self):
        """清理临时文件"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_read_log_by_keyword_found(self):
        """测试关键词搜索找到匹配"""
        result = self.executor.execute("read_log_by_keyword", {
            "file": "test.log",
            "keyword": "ERROR",
            "context_lines": 2
        })

        assert result["found"] is True
        assert result["keyword"] == "ERROR"
        assert result["matched_line"] == 2  # 第一个ERROR在第2行（从1开始）
        assert result["total_matches"] == 2
        assert "content" in result
        assert ">>>" in result["content"]  # 标记匹配行

    def test_read_log_by_keyword_not_found(self):
        """测试关键词搜索未找到"""
        result = self.executor.execute("read_log_by_keyword", {
            "file": "test.log",
            "keyword": "NOTEXIST"
        })

        assert result["found"] is False
        assert "未找到关键词" in result["message"]

    def test_read_log_by_keyword_file_not_exists(self):
        """测试文件不存在"""
        result = self.executor.execute("read_log_by_keyword", {
            "file": "notexist.log",
            "keyword": "test"
        })

        assert "error" in result
        assert "未找到文件" in result["error"]

    def test_read_log_by_range(self):
        """测试按行号范围读取"""
        result = self.executor.execute("read_log_by_range", {
            "file": "test.log",
            "start_line": 2,
            "end_line": 4
        })

        assert result["start_line"] == 2
        assert result["end_line"] == 4
        assert result["total_lines"] == 5
        assert "content" in result
        # 检查内容包含3行
        lines = result["content"].split('\n')
        assert len([l for l in lines if l.strip()]) == 3

    def test_read_log_by_range_out_of_bounds(self):
        """测试行号超出范围"""
        result = self.executor.execute("read_log_by_range", {
            "file": "test.log",
            "start_line": 100,
            "end_line": 200
        })

        # 应返回空内容，但不报错
        assert result["start_line"] == 100
        assert result["end_line"] == 5  # 被截断到实际行数

    def test_get_log_file_info(self):
        """测试获取文件信息"""
        result = self.executor.execute("get_log_file_info", {})

        # 注意：file_map可能包含重复映射（basename和name_without_ext）
        # 所以total_files可能是2，但实际文件只有一个路径
        assert result["total_files"] >= 1
        # 检查是否有test.log
        file_names = [f["name"] for f in result["files"]]
        assert "test.log" in file_names
        # 验证基本信息
        file_info = result["files"][0]
        assert file_info["line_count"] == 5
        assert file_info["size_bytes"] > 0

    def test_unknown_tool(self):
        """测试未知工具"""
        result = self.executor.execute("unknown_tool", {})
        assert "error" in result
        assert "未知工具" in result["error"]

    def test_search_knowledge_base_without_kb_manager(self):
        """测试无知识库管理器时的搜索"""
        result = self.executor.execute("search_knowledge_base", {
            "query": "BMC error"
        })

        assert "error" in result
        assert "知识库未配置" in result["error"]

    def test_search_knowledge_base_with_mock(self):
        """测试有mock知识库管理器的搜索"""
        mock_kb_manager = Mock()
        mock_kb_manager.search.return_value = [
            {"chunk": {"content": "BMC重启解决方案...", "source": "doc1.txt"}}
        ]

        executor = ToolExecutor([self.log_file], kb_manager=mock_kb_manager, kb_id="kb001")
        result = executor.execute("search_knowledge_base", {"query": "BMC error"})

        assert result["found"] is True
        assert len(result["results"]) == 1
        mock_kb_manager.search.assert_called_once_with("kb001", "BMC error", top_k=3)


# ==================== AIResponse 测试 ====================

class TestAIResponse:
    """AI响应封装类测试"""

    def test_has_tool_calls_true(self):
        """测试有工具调用"""
        response = AIResponse(
            content="",
            tool_calls=[{"id": "1", "function": {"name": "test"}}]
        )
        assert response.has_tool_calls() is True

    def test_has_tool_calls_false(self):
        """测试无工具调用"""
        response = AIResponse(content="Hello")
        assert response.has_tool_calls() is False

    def test_to_message_with_content(self):
        """测试消息格式转换（纯内容）"""
        response = AIResponse(content="Hello")
        msg = response.to_message()
        assert msg["role"] == "assistant"
        assert msg["content"] == "Hello"
        assert "tool_calls" not in msg

    def test_to_message_with_tool_calls(self):
        """测试消息格式转换（工具调用）"""
        response = AIResponse(
            content=None,
            tool_calls=[{"id": "call1", "function": {"name": "read_log"}}]
        )
        msg = response.to_message()
        assert msg["role"] == "assistant"
        assert "content" not in msg
        assert msg["tool_calls"] == [{"id": "call1", "function": {"name": "read_log"}}]


# ==================== LogAnalyzerAgent 验证机制测试 ====================

class TestLogAnalyzerAgentValidation:
    """LogAnalyzerAgent验证机制测试"""

    def setup_method(self):
        """创建mock配置管理器"""
        self.mock_config_manager = Mock()
        self.mock_config_manager.get.side_effect = lambda key, default=None: {
            'api': {'base_url': 'http://test', 'api_key': 'test', 'model': 'test'},
            'agent': {'max_tokens': 60000, 'max_rounds': 10}
        }.get(key, default)

        # 使用patch避免加载实际模板
        with patch.object(LogAnalyzerAgent, '_load_template', return_value=Mock()):
            with patch.object(LogAnalyzerAgent, '_load_prompt', return_value="test prompt"):
                self.agent = LogAnalyzerAgent(self.mock_config_manager)

    def test_extract_json_from_code_block(self):
        """测试从代码块提取JSON"""
        text = """```json
{"machine_info": {}, "analysis_summary": "test"}
```"""
        result = self.agent._extract_json(text)
        assert result.startswith("{")
        assert result.endswith("}")

    def test_extract_json_from_plain_code_block(self):
        """测试从普通代码块提取JSON"""
        text = """```
{"machine_info": {}, "analysis_summary": "test"}
```"""
        result = self.agent._extract_json(text)
        assert result.startswith("{")

    def test_extract_json_with_nested_braces(self):
        """测试嵌套花括号"""
        text = '{"outer": {"inner": {"deep": "value"}}}'
        result = self.agent._extract_json(text)
        parsed = json.loads(result)
        assert parsed["outer"]["inner"]["deep"] == "value"

    def test_extract_json_with_prefix_text(self):
        """测试有前缀文本的JSON"""
        text = "这是分析结果：\n{\"summary\": \"test\"}"
        result = self.agent._extract_json(text)
        assert result.startswith("{")

    def test_validate_output_valid_json(self):
        """测试合法JSON验证"""
        valid_json = json.dumps({
            "machine_info": {"serial_number": "SN001"},
            "analysis_summary": "发现2个问题",
            "problems": [{"title": "问题1", "severity": "error"}],
            "potential_risks": [],
            "solutions": [],
            "risk_assessment": {"level": "中"}
        })
        data, errors = self.agent._validate_output(valid_json)
        assert data is not None
        assert len(errors) == 0

    def test_validate_output_invalid_json(self):
        """测试非法JSON验证"""
        invalid_json = "{invalid json}"
        data, errors = self.agent._validate_output(invalid_json)
        assert data is None
        assert len(errors) > 0
        assert "JSON格式错误" in errors[0]

    def test_validate_output_missing_required_fields(self):
        """测试缺少必需字段"""
        incomplete_json = json.dumps({
            "machine_info": {},
            "problems": []
        })
        data, errors = self.agent._validate_output(incomplete_json)
        assert data is None
        assert "缺少必需字段" in errors[0]

    def test_validate_output_no_problems_with_normal_statement(self):
        """测试无问题但有'正常'声明"""
        normal_json = json.dumps({
            "machine_info": {},
            "analysis_summary": "系统运行正常，无异常发现",
            "problems": [],
            "potential_risks": [],
            "solutions": [],
            "risk_assessment": {"level": "低"}
        })
        data, errors = self.agent._validate_output(normal_json)
        assert data is not None
        assert len(errors) == 0

    def test_validate_output_no_problems_no_statement(self):
        """测试无问题且无'正常'声明"""
        empty_json = json.dumps({
            "machine_info": {},
            "analysis_summary": "分析完成",
            "problems": [],
            "potential_risks": [],
            "solutions": [],
            "risk_assessment": {"level": "低"}
        })
        data, errors = self.agent._validate_output(empty_json)
        # 应触发警告
        assert len(errors) > 0
        assert "未发现任何问题或风险" in errors[0]

    def test_validate_output_empty_response(self):
        """测试空响应"""
        data, errors = self.agent._validate_output("")
        assert data is None
        assert "AI返回空内容" in errors[0]


# ==================== LogAnalyzerAgent HTML生成测试 ====================

class TestLogAnalyzerAgentHTMLGeneration:
    """HTML生成测试"""

    def setup_method(self):
        """创建mock配置"""
        self.mock_config_manager = Mock()
        self.mock_config_manager.get.side_effect = lambda key, default=None: {
            'api': {'base_url': 'http://test', 'api_key': 'test', 'model': 'test'},
            'agent': {'max_tokens': 60000, 'max_rounds': 10}
        }.get(key, default)

        # 创建agent，不加载模板（使用备用HTML）
        with patch.object(LogAnalyzerAgent, '_load_template', return_value=None):
            with patch.object(LogAnalyzerAgent, '_load_prompt', return_value="test"):
                self.agent = LogAnalyzerAgent(self.mock_config_manager)

    def test_generate_fallback_html(self):
        """测试备用HTML生成"""
        data = {
            "machine_info": {"serial_number": "SN001", "model": "TestModel"},
            "analysis_summary": "发现1个问题",
            "problems": [
                {"title": "测试问题", "severity": "error", "description": "描述",
                 "analysis_logic": "分析逻辑", "log_reference": "日志引用"}
            ],
            "potential_risks": [],
            "solutions": [{"title": "解决方案", "steps": ["步骤1", "步骤2"]}],
            "risk_assessment": {"level": "中", "description": "风险描述"},
            "analysis_coverage": {"analysis_depth": "全面", "files_analyzed": ["test.log"]}
        }
        html = self.agent._generate_fallback_html(data)

        assert "<!DOCTYPE html>" in html
        assert "机器信息" in html
        assert "SN001" in html
        assert "发现的问题" in html
        assert "测试问题" in html
        assert "分析逻辑" in html
        assert "解决方案" in html
        assert "风险评估" in html
        assert "中" in html

    def test_generate_error_html(self):
        """测试错误HTML生成"""
        html = self.agent._generate_error_html("分析失败", "API连接超时")
        assert "<!DOCTYPE html>" in html
        assert "分析失败" in html
        assert "API连接超时" in html

    def test_extract_html_from_code_block(self):
        """测试从代码块提取HTML"""
        text = """```html
<!DOCTYPE html><html><body>Test</body></html>
```"""
        html = self.agent._extract_html(text)
        assert "<!DOCTYPE html>" in html

    def test_extract_html_direct(self):
        """测试直接提取HTML"""
        text = "<!DOCTYPE html><html><body>Test</body></html>"
        html = self.agent._extract_html(text)
        assert html == text

    def test_generate_simple_html(self):
        """测试简单HTML包装"""
        html = self.agent._generate_simple_html("原始内容")
        assert "<!DOCTYPE html>" in html
        assert "原始内容" in html


# ==================== LogAnalyzerAgent 多轮交互测试 ====================

class TestLogAnalyzerAgentInteraction:
    """多轮交互测试（需要mock AIClient）"""

    def setup_method(self):
        """创建mock配置"""
        self.mock_config_manager = Mock()
        self.mock_config_manager.get.side_effect = lambda key, default=None: {
            'api': {'base_url': 'http://test', 'api_key': 'test', 'model': 'test'},
            'agent': {'max_tokens': 60000, 'max_rounds': 10}
        }.get(key, default)

    def test_run_analysis_direct_output(self):
        """测试直接输出结果（无工具调用）"""
        # 创建临时日志文件
        temp_dir = tempfile.mkdtemp()
        log_file = os.path.join(temp_dir, 'test.log')
        with open(log_file, 'w') as f:
            f.write("test log content")

        try:
            agent = LogAnalyzerAgent(self.mock_config_manager)

            # mock prompt加载方法返回简单模板
            agent._load_prompt = Mock(return_value="{plugin_result}\n{machine_info}\n{knowledge_content}\n{log_rules}\n{log_files_overview}\n{analysis_templates}\n{user_prompt}")

            # 直接mock agent的client方法
            valid_json = json.dumps({
                "machine_info": {"serial_number": "SN001"},
                "analysis_summary": "发现1个问题",
                "problems": [{"title": "问题1", "severity": "error"}],
                "potential_risks": [],
                "solutions": [],
                "risk_assessment": {"level": "中"}
            })
            agent.client.chat_with_tools = Mock(return_value=AIResponse(content=valid_json))

            result = agent.run_analysis(
                plugin_result={},
                log_files=[log_file],
                machine_info={"serial_number": "SN001"},
                knowledge_content="",
                log_rules="",
                analysis_templates="",
                user_prompt=""
            )

            assert "html" in result
            assert "<!DOCTYPE html>" in result["html"]
            assert "interaction_record" in result
            assert result["interaction_record"]["agent"]["validation"]["passed"] is True
        finally:
            import shutil
            shutil.rmtree(temp_dir)

    def test_run_analysis_with_tool_call(self):
        """测试工具调用流程"""
        temp_dir = tempfile.mkdtemp()
        log_file = os.path.join(temp_dir, 'test.log')
        with open(log_file, 'w') as f:
            f.write("test log")

        try:
            agent = LogAnalyzerAgent(self.mock_config_manager)

            # mock prompt加载方法
            agent._load_prompt = Mock(return_value="{plugin_result}\n{machine_info}\n{knowledge_content}\n{log_rules}\n{log_files_overview}\n{analysis_templates}\n{user_prompt}")

            # 第一轮返回tool_call，第二轮返回JSON
            tool_call_response = AIResponse(
                content=None,
                tool_calls=[{
                    "id": "call1",
                    "function": {"name": "get_log_file_info", "arguments": "{}"}
                }]
            )

            valid_json = json.dumps({
                "machine_info": {},
                "analysis_summary": "分析完成",
                "problems": [],
                "potential_risks": [],
                "solutions": [],
                "risk_assessment": {"level": "低"}
            })
            final_response = AIResponse(content=valid_json)

            agent.client.chat_with_tools = Mock(side_effect=[tool_call_response, final_response])

            result = agent.run_analysis(
                plugin_result={},
                log_files=[log_file],
                machine_info={},
                knowledge_content="",
                log_rules="",
                analysis_templates="",
                user_prompt=""
            )

            assert "html" in result
            # 验证进行了2轮交互
            interactions = result["interaction_record"]["agent"]["interactions"]
            assert len(interactions) == 2
            # 第一轮应有tool_calls
            assert "tool_calls" in interactions[0]
        finally:
            import shutil
            shutil.rmtree(temp_dir)

    def test_run_analysis_validation_retry(self):
        """测试验证失败触发重试"""
        temp_dir = tempfile.mkdtemp()
        log_file = os.path.join(temp_dir, 'test.log')
        with open(log_file, 'w') as f:
            f.write("test")

        try:
            agent = LogAnalyzerAgent(self.mock_config_manager)

            # mock prompt加载方法
            agent._load_prompt = Mock(return_value="{plugin_result}\n{machine_info}\n{knowledge_content}\n{log_rules}\n{log_files_overview}\n{analysis_templates}\n{user_prompt}")

            # 第一轮返回非法JSON，第二轮返回合法JSON
            invalid_response = AIResponse(content="{invalid json}")
            valid_json = json.dumps({
                "machine_info": {},
                "analysis_summary": "正常",
                "problems": [],
                "potential_risks": [],
                "solutions": [],
                "risk_assessment": {"level": "低"}
            })
            valid_response = AIResponse(content=valid_json)

            agent.client.chat_with_tools = Mock(side_effect=[invalid_response, valid_response])

            result = agent.run_analysis(
                plugin_result={},
                log_files=[log_file],
                machine_info={},
                knowledge_content="",
                log_rules="",
                analysis_templates="",
                user_prompt=""
            )

            # 验证最终成功
            assert "html" in result
            assert result["interaction_record"]["agent"]["validation"]["passed"] is True
        finally:
            import shutil
            shutil.rmtree(temp_dir)

    def test_run_analysis_fallback(self):
        """测试所有验证失败后降级HTML生成"""
        temp_dir = tempfile.mkdtemp()
        log_file = os.path.join(temp_dir, 'test.log')
        with open(log_file, 'w') as f:
            f.write("test")

        try:
            agent = LogAnalyzerAgent(self.mock_config_manager)

            # mock prompt加载方法
            agent._load_prompt = Mock(return_value="{plugin_result}\n{machine_info}\n{knowledge_content}\n{log_rules}\n{log_files_overview}\n{analysis_templates}\n{user_prompt}")

            # 所有轮次都返回非法JSON
            invalid_response = AIResponse(content="{invalid json}")
            # 降级HTML生成时返回有效HTML
            fallback_html_response = AIResponse(content="<html><body>Fallback</body></html>")

            agent.client.chat_with_tools = Mock(side_effect=[
                invalid_response, invalid_response, fallback_html_response
            ])

            result = agent.run_analysis(
                plugin_result={},
                log_files=[log_file],
                machine_info={},
                knowledge_content="",
                log_rules="",
                analysis_templates="",
                user_prompt=""
            )

            assert "html" in result
            # 验证降级模式
            assert result["interaction_record"]["agent"]["validation"]["passed"] is False
        finally:
            import shutil
            shutil.rmtree(temp_dir)


# ==================== 交互记录结构测试 ====================

class TestInteractionRecord:
    """ai_temp记录结构测试"""

    def test_build_interaction_record_structure(self):
        """测试交互记录结构"""
        mock_config_manager = Mock()
        mock_config_manager.get.side_effect = lambda key, default=None: {
            'api': {'base_url': 'http://test', 'api_key': 'test', 'model': 'test'},
            'agent': {'max_tokens': 60000, 'max_rounds': 10}
        }.get(key, default)

        with patch.object(LogAnalyzerAgent, '_load_template', return_value=None):
            with patch.object(LogAnalyzerAgent, '_load_prompt', return_value="test"):
                agent = LogAnalyzerAgent(mock_config_manager)

        record = agent._build_interaction_record(
            system_prompt="system prompt content",
            prompt_data={"plugin_result": "test", "knowledge_content": "kb content"},
            interactions=[{"round": 1, "response": "test"}],
            final_output={"machine_info": {}, "problems": []},
            validation_passed=True,
            validation_errors=[]
        )

        # 验证结构
        assert "timestamp" in record
        assert "agent" in record
        assert "system_prompt" in record["agent"]
        assert "analysis_data" in record["agent"]
        assert "interactions" in record["agent"]
        assert "validation" in record["agent"]
        assert record["agent"]["validation"]["passed"] is True
        assert record["agent"]["total_rounds"] == 1


# ==================== 格式化辅助函数测试 ====================

class TestFormattingHelpers:
    """格式化辅助函数测试"""

    def setup_method(self):
        mock_config_manager = Mock()
        mock_config_manager.get.side_effect = lambda key, default=None: {
            'api': {},
            'agent': {}
        }.get(key, default)

        with patch.object(LogAnalyzerAgent, '_load_template', return_value=None):
            with patch.object(LogAnalyzerAgent, '_load_prompt', return_value=""):
                self.agent = LogAnalyzerAgent(mock_config_manager)

    def test_format_plugin_result(self):
        """测试插件结果格式化"""
        plugin_result = {
            "bmc_info": {
                "meta": {"plugin_name": "BMC信息", "log_files": ["bmc.log"]},
                "sections": [
                    {"type": "stats", "items": [
                        {"label": "序列号", "value": "SN001", "severity": "info"}
                    ]},
                    {"type": "table", "title": "错误列表", "rows": [
                        {"message": "Error 1"}, {"message": "Error 2"}
                    ], "severity": "error"}
                ]
            }
        }
        result = self.agent._format_plugin_result(plugin_result)
        assert "BMC信息" in result
        assert "序列号" in result
        assert "SN001" in result
        assert "错误列表" in result
        assert "Error 1" in result

    def test_format_machine_info(self):
        """测试机器信息格式化"""
        machine_info = {"serial_number": "SN001", "model": "ModelX"}
        result = self.agent._format_machine_info(machine_info)
        assert "serial_number" in result
        assert "SN001" in result

    def test_format_log_files(self):
        """测试日志文件列表格式化"""
        temp_dir = tempfile.mkdtemp()
        log_file = os.path.join(temp_dir, 'test.log')
        with open(log_file, 'w') as f:
            f.write("test content\n")

        try:
            result = self.agent._format_log_files([log_file])
            assert "test.log" in result
            assert "KB" in result  # 包含大小信息
        finally:
            import shutil
            shutil.rmtree(temp_dir)

    def test_format_log_files_empty(self):
        """测试空文件列表"""
        result = self.agent._format_log_files([])
        assert "无日志文件" in result


# ==================== 工具定义验证测试 ====================

class TestToolDefinitions:
    """工具定义格式验证"""

    def test_builtin_tools_format(self):
        """测试内置工具定义格式"""
        for tool in BUILTIN_TOOLS:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]
            assert "properties" in tool["function"]["parameters"]
            assert "required" in tool["function"]["parameters"]

    def test_builtin_tool_names_count(self):
        """测试工具名称数量"""
        assert len(BUILTIN_TOOL_NAMES) == 4
        assert "read_log_by_keyword" in BUILTIN_TOOL_NAMES
        assert "read_log_by_range" in BUILTIN_TOOL_NAMES
        assert "get_log_file_info" in BUILTIN_TOOL_NAMES
        assert "search_knowledge_base" in BUILTIN_TOOL_NAMES


if __name__ == '__main__':
    pytest.main([__file__, '-v'])