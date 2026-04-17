"""
AI接口连通性测试
验证配置的AI API是否可以正常连接
"""

import sys
import os

# 添加src到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'src'))
sys.path.insert(0, project_root)

import pytest
from config_manager import ConfigManager
from ai_analyzer.client import AIClient


def test_ai_connection():
    """测试AI接口连通性"""
    # 加载配置
    config_manager = ConfigManager()
    api_config = config_manager.get('api', {})

    # 检查必要配置项
    base_url = api_config.get('base_url')
    api_key = api_config.get('api_key')
    model = api_config.get('model')

    if not base_url:
        pytest.fail("缺少 base_url 配置，请先设置: python main.py config set api.base_url <url>")
    if not api_key:
        pytest.fail("缺少 api_key 配置，请先设置: python main.py config set api.api_key <key>")
    if not model:
        pytest.fail("缺少 model 配置，请先设置: python main.py config set api.model <model_name>")

    # 显示当前配置
    print(f"\n当前配置:")
    print(f"  Base URL: {base_url}")
    print(f"  Model: {model}")

    # 创建客户端
    client = AIClient(api_config)

    # 发送简单测试消息
    test_message = [{"role": "user", "content": "你好，这是一个连通性测试，请简短回复"}]

    # 收集响应
    response_parts = []
    try:
        for chunk in client.chat(test_message, max_tokens=100):
            response_parts.append(chunk)
    except Exception as e:
        pytest.fail(f"API连接失败: {str(e)}")

    # 验证响应
    full_response = ''.join(response_parts)
    assert len(full_response) > 0, "API返回内容为空"

    print(f"\nAPI响应: {full_response}")

if '__name__' == '__main__':
    test_ai_connection()