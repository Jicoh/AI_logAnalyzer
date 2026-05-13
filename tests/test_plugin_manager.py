"""
Manager接口测试
"""

import json
import pytest
from unittest.mock import MagicMock

from plugins.manager import PluginManager
from plugins.base import AnalysisResult, ResultMeta, StatsItem, CliResult, count_severity


@pytest.fixture
def plugin_manager():
    """创建并初始化插件管理器"""
    manager = PluginManager()
    manager.load_plugins()
    return manager


@pytest.fixture
def sample_log_content():
    """示例日志内容"""
    return {
        "system.log": [
            "2024-01-01 10:00:00 ERROR disk read failure",
            "2024-01-01 10:01:00 WARNING low memory",
            "2024-01-01 10:02:00 INFO system started"
        ],
        "app.log": [
            "2024-01-01 11:00:00 INFO application started",
            "2024-01-01 11:01:00 ERROR connection failed"
        ]
    }


@pytest.fixture
def clean_log_content():
    """无错误日志内容"""
    return {
        "system.log": [
            "2024-01-01 10:00:00 INFO system started",
            "2024-01-01 10:01:00 INFO service running"
        ]
    }


class TestRunAnalysisSystemFormat:
    """source='system' 返回原格式"""

    def test_returns_dict_with_plugin_id_key(self, plugin_manager, sample_log_content):
        result = plugin_manager.run_analysis(
            'system', ['example_00001'], sample_log_content
        )
        assert isinstance(result, dict)
        assert 'example_00001' in result

    def test_result_has_meta_and_sections(self, plugin_manager, sample_log_content):
        result = plugin_manager.run_analysis(
            'system', ['example_00001'], sample_log_content
        )
        plugin_data = result['example_00001']
        assert 'meta' in plugin_data
        assert 'sections' in plugin_data

    def test_meta_contains_required_fields(self, plugin_manager, sample_log_content):
        result = plugin_manager.run_analysis(
            'system', ['example_00001'], sample_log_content
        )
        meta = result['example_00001']['meta']
        assert meta['plugin_id'] == 'example_00001'
        assert meta['plugin_name'] == 'Demo Plugin'
        assert 'analysis_time' in meta


class TestRunAnalysisCliFormat:
    """source='cli' 返回 [task_name, bmc_ip, status, description, log_detail, date]"""

    def test_returns_list_with_six_elements(self, plugin_manager, sample_log_content):
        result = plugin_manager.run_analysis(
            'cli', ['example_00001'], sample_log_content,
            task_name='test_task', bmc_ip='192.168.1.1', date='2024-01-01'
        )
        assert isinstance(result, list)
        assert len(result) == 6

    def test_cli_format_fields(self, plugin_manager, sample_log_content):
        result = plugin_manager.run_analysis(
            'cli', ['example_00001'], sample_log_content,
            task_name='test_task', bmc_ip='192.168.1.1', date='2024-01-01'
        )
        task_name, bmc_ip, status, description, log_detail, date = result
        assert task_name == 'test_task'
        assert bmc_ip == '192.168.1.1'
        assert date == '2024-01-01'
        assert status in ('ERROR', 'OK')
        assert isinstance(description, str)
        assert isinstance(log_detail, str) or log_detail == ""

    def test_cli_status_error_when_errors(self, plugin_manager, sample_log_content):
        result = plugin_manager.run_analysis(
            'cli', ['example_00001'], sample_log_content
        )
        status = result[2]
        assert status == 'ERROR'

    def test_cli_status_ok_when_no_errors(self, plugin_manager, clean_log_content):
        result = plugin_manager.run_analysis(
            'cli', ['example_00001'], clean_log_content
        )
        status = result[2]
        assert status == 'OK'

    def test_cli_default_optional_params(self, plugin_manager, sample_log_content):
        result = plugin_manager.run_analysis(
            'cli', ['example_00001'], sample_log_content
        )
        task_name, bmc_ip, status, description, log_detail, date = result
        assert task_name == ""
        assert bmc_ip == ""
        assert date == ""

    def test_cli_description_length_limit(self, plugin_manager):
        """description长度不超过1000"""
        log_content = {
            "big.log": [f"ERROR error number {i} with long description" for i in range(200)]
        }
        result = plugin_manager.run_analysis(
            'cli', ['example_00001'], log_content
        )
        description = result[3]
        assert len(description) <= 1000

    def test_cli_log_detail_length_limit(self, plugin_manager):
        """log_detail长度不超过3000"""
        log_content = {
            "big.log": [f"ERROR error number {i}" for i in range(500)]
        }
        result = plugin_manager.run_analysis(
            'cli', ['example_00001'], log_content
        )
        log_detail = result[4]
        assert len(log_detail) <= 3000


class TestRunAnalysisErrors:
    """错误处理"""

    def test_empty_plugin_ids_raises(self, plugin_manager, sample_log_content):
        with pytest.raises(ValueError, match="未指定要分析的插件"):
            plugin_manager.run_analysis('system', [], sample_log_content)

    def test_nonexistent_plugin_id(self, plugin_manager, sample_log_content):
        with pytest.raises(RuntimeError, match="没有插件成功执行"):
            plugin_manager.run_analysis('system', ['nonexistent_plugin'], sample_log_content)


def _make_mock_plugin(return_value, plugin_id='mock_plugin'):
    """创建一个记录调用参数的mock插件"""
    mock_plugin = MagicMock()
    mock_plugin.id = plugin_id
    mock_plugin.analyze.return_value = return_value
    return mock_plugin


class TestParameterChain:
    """验证参数从run_analysis传递到plugin.analyze"""

    def test_run_analysis_passes_task_name(self):
        mock_result = AnalysisResult(
            meta=ResultMeta(plugin_id='mock', plugin_name='Mock',
                            version='1.0', analysis_time='2024-01-01 00:00:00')
        )
        mock_plugin = _make_mock_plugin(mock_result)
        manager = PluginManager(plugin_dirs=[])
        manager._plugins['mock'] = mock_plugin

        manager.run_analysis('system', ['mock'],
                             {"test.log": ["INFO ok"]},
                             task_name='my_task')

        mock_plugin.analyze.assert_called_once()
        call_kwargs = mock_plugin.analyze.call_args.kwargs
        assert call_kwargs.get('task_name') == 'my_task'

    def test_run_analysis_passes_all_cli_params(self):
        mock_cli_result = CliResult(
            task_name='t1', bmc_ip='10.0.0.1', date='2024-06-01',
            status='OK', description='', log_detail=""
        )
        mock_plugin = _make_mock_plugin(mock_cli_result)
        manager = PluginManager(plugin_dirs=[])
        manager._plugins['mock'] = mock_plugin

        manager.run_analysis('cli', ['mock'],
                             {"test.log": ["INFO ok"]},
                             task_name='t1', bmc_ip='10.0.0.1',
                             date='2024-06-01')

        call_kwargs = mock_plugin.analyze.call_args.kwargs
        assert call_kwargs.get('task_name') == 't1'
        assert call_kwargs.get('bmc_ip') == '10.0.0.1'
        assert call_kwargs.get('date') == '2024-06-01'
        assert call_kwargs.get('source') == 'cli'

    def test_run_analysis_passes_source_system(self):
        mock_result = AnalysisResult(
            meta=ResultMeta(plugin_id='mock', plugin_name='Mock',
                            version='1.0', analysis_time='2024-01-01 00:00:00')
        )
        mock_plugin = _make_mock_plugin(mock_result)
        manager = PluginManager(plugin_dirs=[])
        manager._plugins['mock'] = mock_plugin

        manager.run_analysis('system', ['mock'],
                             {"test.log": ["INFO ok"]})

        call_kwargs = mock_plugin.analyze.call_args.kwargs
        assert call_kwargs.get('source') == 'system'

    def test_run_analysis_default_params(self):
        mock_result = AnalysisResult(
            meta=ResultMeta(plugin_id='mock', plugin_name='Mock',
                            version='1.0', analysis_time='2024-01-01 00:00:00')
        )
        mock_plugin = _make_mock_plugin(mock_result)
        manager = PluginManager(plugin_dirs=[])
        manager._plugins['mock'] = mock_plugin

        manager.run_analysis('system', ['mock'],
                             {"test.log": ["INFO ok"]})

        call_kwargs = mock_plugin.analyze.call_args.kwargs
        assert call_kwargs.get('task_name') == ''
        assert call_kwargs.get('bmc_ip') == ''
        assert call_kwargs.get('date') == ''

    def test_run_analysis_passes_log_callback(self):
        mock_result = AnalysisResult(
            meta=ResultMeta(plugin_id='mock', plugin_name='Mock',
                            version='1.0', analysis_time='2024-01-01 00:00:00')
        )
        mock_plugin = _make_mock_plugin(mock_result)
        mock_plugin.set_log_callback = MagicMock()
        manager = PluginManager(plugin_dirs=[])
        manager._plugins['mock'] = mock_plugin

        callback = lambda msg, level: None
        manager.run_analysis('system', ['mock'],
                             {"test.log": ["INFO ok"]},
                             log_callback=callback)

        mock_plugin.set_log_callback.assert_called_once_with(callback)
