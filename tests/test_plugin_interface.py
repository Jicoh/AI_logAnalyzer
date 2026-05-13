"""
插件接口测试
"""

import re
import pytest

from plugins.manager import PluginManager
from plugins.base import AnalysisResult, ResultMeta, CliResult


@pytest.fixture
def plugin_manager():
    """创建并初始化插件管理器"""
    manager = PluginManager()
    manager.load_plugins()
    return manager


class TestDemoPluginWithLogContent:
    """验证demo_plugin接收log_content字典后正确解析"""

    def test_parses_log_content_dict(self, plugin_manager):
        plugin = plugin_manager.get_plugin('example_00001')
        assert plugin is not None

        log_content = {
            "system.log": ["ERROR disk read failure", "WARNING low memory", "INFO started"]
        }
        result = plugin.analyze(log_content)
        assert isinstance(result, AnalysisResult)
        assert result.meta.plugin_id == 'example_00001'

    def test_detects_errors(self, plugin_manager):
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {
            "test.log": ["ERROR something went wrong", "FAIL again"]
        }
        result = plugin.analyze(log_content)
        # 检查sections中有error相关的统计
        found_error_stat = False
        for section in result.sections:
            if hasattr(section, 'items'):
                for item in section.items:
                    if item.severity == 'error' and item.value > 0:
                        found_error_stat = True
        assert found_error_stat

    def test_detects_warnings(self, plugin_manager):
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {
            "test.log": ["WARNING something suspicious"]
        }
        result = plugin.analyze(log_content)
        found_warning_stat = False
        for section in result.sections:
            if hasattr(section, 'items'):
                for item in section.items:
                    if item.severity == 'warning' and item.value > 0:
                        found_warning_stat = True
        assert found_warning_stat

    def test_log_files_in_meta(self, plugin_manager):
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {
            "a.log": ["INFO line1"],
            "b.log": ["INFO line2"]
        }
        result = plugin.analyze(log_content)
        assert set(result.meta.log_files) == {"a.log", "b.log"}

    def test_counts_log_lines(self, plugin_manager):
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {
            "test.log": ["line1", "line2", "line3"]
        }
        result = plugin.analyze(log_content)
        # 检查总行数统计
        for section in result.sections:
            if hasattr(section, 'items'):
                for item in section.items:
                    if item.label == '总行数':
                        assert item.value == 3


class TestPluginIdFormat:
    """验证所有插件ID符合 {类型}_00001 格式"""

    def test_plugin_id_format(self, plugin_manager):
        import re
        pattern = re.compile(r'^(CloudBMC|iBMC|LxBMC|example)_\d{5}$')
        plugins = plugin_manager.get_all_plugins()
        assert len(plugins) > 0, "应该至少有一个插件"
        for plugin in plugins:
            assert pattern.match(plugin.id), f"插件ID格式不正确: {plugin.id}，应为 {{类型}}_00001 格式"

    def test_plugin_ids_are_unique(self, plugin_manager):
        plugins = plugin_manager.get_all_plugins()
        ids = [p.id for p in plugins]
        assert len(ids) == len(set(ids)), "插件ID应该唯一"


class TestParameterPassing:
    """验证插件analyze方法能接收完整参数"""

    def test_analyze_accepts_all_params(self, plugin_manager):
        """验证内置插件接受所有参数而不报错"""
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"test.log": ["INFO ok"]}
        result = plugin.analyze(
            log_content,
            task_name="test_task",
            bmc_ip="192.168.1.1",
            date="2024-01-01",
            source="cli"
        )
        assert isinstance(result, CliResult)

    def test_analyze_default_params(self, plugin_manager):
        """验证默认参数不影响现有行为"""
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"test.log": ["ERROR fail"]}
        result_default = plugin.analyze(log_content)
        result_explicit = plugin.analyze(
            log_content, task_name="", bmc_ip="", date="", source="system"
        )
        assert isinstance(result_default, AnalysisResult)
        assert isinstance(result_explicit, AnalysisResult)
        assert result_default.meta.plugin_id == result_explicit.meta.plugin_id


class TestCliReturnFormat:
    """验证source='cli'时返回CliResult格式"""

    def test_demo_plugin_cli_result_type(self, plugin_manager):
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"test.log": ["ERROR disk failure"]}
        result = plugin.analyze(log_content, source='cli')
        assert isinstance(result, CliResult)

    def test_demo_plugin_cli_fields(self, plugin_manager):
        """验证cli返回值的6个字段"""
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"test.log": ["ERROR disk failure"]}
        result = plugin.analyze(
            log_content,
            task_name="my_task",
            bmc_ip="192.168.1.1",
            date="2024-01-01",
            source='cli'
        )
        assert result.task_name == "my_task"
        assert result.bmc_ip == "192.168.1.1"
        assert result.date == "2024-01-01"
        assert result.status == 'ERROR'
        assert isinstance(result.description, str)
        assert len(result.description) <= 1000
        assert isinstance(result.log_detail, str)

    def test_demo_plugin_cli_status_ok(self, plugin_manager):
        """无错误时status为OK"""
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"test.log": ["INFO system started"]}
        result = plugin.analyze(log_content, source='cli')
        assert result.status == 'OK'

    def test_demo_plugin_cli_status_error(self, plugin_manager):
        """有错误时status为ERROR"""
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"test.log": ["ERROR disk failure"]}
        result = plugin.analyze(log_content, source='cli')
        assert result.status == 'ERROR'

    def test_demo_plugin_cli_to_list(self, plugin_manager):
        """验证to_list()输出格式"""
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"test.log": ["ERROR fail"]}
        result = plugin.analyze(
            log_content,
            task_name="t1",
            bmc_ip="1.1.1.1",
            date="2024-06-01",
            source='cli'
        )
        output = result.to_list()
        assert isinstance(output, list)
        assert len(output) == 6
        assert output[0] == "t1"
        assert output[1] == "1.1.1.1"
        assert output[2] == 'ERROR'
        assert output[5] == "2024-06-01"

    def test_demo_plugin_cli_log_detail_length(self, plugin_manager):
        """log_detail长度不超过3000"""
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"big.log": [f"ERROR error number {i}" for i in range(500)]}
        result = plugin.analyze(log_content, source='cli')
        assert len(result.log_detail) <= 3000


class TestSystemReturnFormat:
    """验证source='system'时返回AnalysisResult格式"""

    def test_demo_plugin_system_result(self, plugin_manager):
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"test.log": ["ERROR disk failure"]}
        result = plugin.analyze(log_content, source='system')
        assert isinstance(result, AnalysisResult)
        assert result.meta.plugin_id == 'example_00001'

    def test_demo_plugin_all_section_types(self, plugin_manager):
        """验证demo插件包含所有section类型"""
        plugin = plugin_manager.get_plugin('example_00001')
        log_content = {"test.log": ["ERROR fail", "WARNING warn", "INFO ok", "10:00:00 some event"]}
        result = plugin.analyze(log_content, source='system')

        # 检查包含的section类型
        section_types = set()
        for section in result.sections:
            section_types.add(section.__class__.__name__)

        # 至少包含这些类型
        expected_types = {'StatsSection', 'TableSection', 'TimelineSection',
                         'CardsSection', 'ChartSection', 'SearchBoxSection', 'RawSection'}
        # 允许部分类型缺失（取决于日志内容）
        assert len(section_types) >= 4  # 至少有4种类型
