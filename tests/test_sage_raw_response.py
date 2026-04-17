"""
Sage Agent 分析流程测试
探测max_tokens上限，测试Sage prompt响应
"""

import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'src'))
sys.path.insert(0, project_root)

import pytest
from config_manager import ConfigManager
from ai_analyzer.client import AIClient
from ai_analyzer.sage_agent import SageAgent


def test_probe_max_tokens_and_config():
    """探测AI支持的最大max_tokens，并测试当前配置"""
    config_manager = ConfigManager()
    api_config = config_manager.get('api', {})

    if not api_config.get('base_url'):
        pytest.skip("缺少API配置")

    print(f"\n=== 配置信息 ===")
    print(f"  base_url: {api_config.get('base_url')}")
    print(f"  model: {api_config.get('model')}")
    print(f"  配置的max_tokens: {api_config.get('max_tokens')}")

    client = AIClient(api_config)

    # 探测不同的max_tokens值
    print("\n=== 探测max_tokens上限 ===")
    test_values = [100, 512, 1024, 2048, 4096, 8192, 16384, 32768]
    working_values = []

    for max_tokens in test_values:
        msg = [{"role": "user", "content": "回复OK"}]

        response_parts = []
        try:
            for chunk in client.chat(msg, max_tokens=max_tokens):
                response_parts.append(chunk)
        except Exception as e:
            print(f"  max_tokens={max_tokens}: 错误 - {str(e)[:80]}")
            continue

        full = ''.join(response_parts)
        if len(full) > 0:
            working_values.append(max_tokens)
            print(f"  max_tokens={max_tokens}: 成功，响应={repr(full[:50])}")
        else:
            print(f"  max_tokens={max_tokens}: 返回空内容")

    print(f"\n=== 探测结果 ===")
    print(f"  可用的max_tokens值: {working_values}")
    if working_values:
        recommended = max(working_values)
        print(f"  建议设置: python main.py config set api.max_tokens {recommended}")
    else:
        print(f"  所有测试值都失败，请检查API配置")

    # 测试当前配置的max_tokens
    configured_max_tokens = api_config.get('max_tokens', 4096)
    print(f"\n=== 测试当前配置max_tokens={configured_max_tokens} ===")

    msg = [{"role": "user", "content": "你好"}]
    response_parts = []
    try:
        for i, chunk in enumerate(client.chat(msg)):
            response_parts.append(chunk)
            print(f"  chunk {i}: {repr(chunk)}")
    except Exception as e:
        print(f"  错误: {e}")

    full = ''.join(response_parts)
    print(f"  总长度: {len(full)}, 内容: {full}")


def test_sage_prompt_response():
    """测试Sage Agent的prompt响应"""
    config_manager = ConfigManager()
    api_config = config_manager.get('api', {})

    if not api_config.get('base_url'):
        pytest.skip("缺少API配置")

    sage = SageAgent(config_manager)

    print(f"\n=== Sage Prompt测试 ===")

    # 测试1: Sage默认prompt
    prompt_template = sage.load_prompt()
    print(f"  Prompt模板长度: {len(prompt_template)} 字符")

    formatted_prompt = prompt_template.format(
        machine_info="暂无机器信息",
        plugin_result="测试插件结果",
        log_content="测试日志内容",
        knowledge_content="无知识库内容",
        user_prompt="分析"
    )
    print(f"  格式化后Prompt长度: {len(formatted_prompt)} 字符")

    # 获取响应
    print(f"\n=== 调用AI获取响应 ===")
    response_text, success, error_msg = sage.call_ai(formatted_prompt)

    print(f"  成功: {success}")
    print(f"  错误信息: {error_msg}")
    print(f"  响应长度: {len(response_text)} 字符")
    print(f"  响应内容(前500字): {response_text[:500]}")

    # 解析JSON
    print(f"\n=== 解析JSON ===")
    analysis_data = sage.parse_json_response(response_text)
    print(f"  解析结果:")
    print(f"    machine_info: {analysis_data.get('machine_info', {})}")
    print(f"    summary: {analysis_data.get('summary', {})}")
    print(f"    problems数量: {len(analysis_data.get('problems', []))}")
    print(f"    solutions数量: {len(analysis_data.get('solutions', []))}")


if '__name__' == '__main__':
    test_probe_max_tokens_and_config()
    print("\n" + "="*50 + "\n")
    test_sage_prompt_response()