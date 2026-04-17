"""
AI接口连通性测试
验证配置的AI API是否可以正常连接，打印SSE数据块
"""

import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'src'))
sys.path.insert(0, project_root)

import pytest
from config_manager import ConfigManager
from ai_analyzer.client import AIClient


def test_ai_connection():
    """测试AI接口连通性，打印SSE数据块"""
    config_manager = ConfigManager()
    api_config = config_manager.get('api', {})

    base_url = api_config.get('base_url')
    api_key = api_config.get('api_key')
    model = api_config.get('model')

    if not base_url:
        pytest.fail("缺少 base_url 配置")
    if not api_key:
        pytest.fail("缺少 api_key 配置")
    if not model:
        pytest.fail("缺少 model 配置")

    print(f"\n当前配置:")
    print(f"  Base URL: {base_url}")
    print(f"  Model: {model}")

    client = AIClient(api_config)

    test_message = [{"role": "user", "content": "你好，简短回复"}]

    print("\nSSE数据块:")
    response_parts = []
    try:
        for i, chunk in enumerate(client.chat(test_message, max_tokens=100)):
            response_parts.append(chunk)
            print(f"  chunk {i}: {repr(chunk)}")
            if i > 20:
                print("  ... (已显示前20个块)")
                break
    except Exception as e:
        pytest.fail(f"API连接失败: {str(e)}")

    full_response = ''.join(response_parts)
    assert len(full_response) > 0, "API返回内容为空"

    print(f"\n完整响应: {full_response}")


if '__name__' == '__main__':
    test_ai_connection()