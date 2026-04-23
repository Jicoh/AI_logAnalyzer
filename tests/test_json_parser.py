from src.utils.json_parser import parse_ai_json_response


def test_pure_json():
    text = '{"files_overview": [], "key_events": []}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None
    assert error is None


def test_json_with_prefix_text():
    text = '这是分析结果：\n{"files_overview": [], "key_events": []}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None


def test_json_with_trailing_comma():
    text = '{"files_overview": [], "key_events": [],}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None


def test_json_in_plain_code_block():
    text = '```\n{"files_overview": [], "key_events": []}\n```'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None


def test_json_in_json_code_block():
    text = '```json\n{"files_overview": [], "key_events": []}\n```'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None


def test_empty_response():
    result, error = parse_ai_json_response('')
    assert result is None


def test_missing_required_fields():
    text = '{"files_overview": []}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is None


def test_nested_json():
    text = '{"files_overview": [{"file": "test.log"}], "key_events": [{"type": "error"}]}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None
    assert len(result['files_overview']) == 1
    assert len(result['key_events']) == 1


def test_json_with_chinese_comma():
    text = '{"files_overview"：[]，"key_events"：[]}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None


def test_json_with_chinese_quotes():
    text = '{"files_overview"：[]，"key_events"：【"test"】}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None
    assert result['key_events'] == ['test']


def test_json_with_chinese_punctuation_in_code_block():
    text = '```json\n{"files_overview"：[]，"key_events"：[]}\n```'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None


def test_unescaped_quotes_in_string():
    """测试字符串内部未转义双引号的修复"""
    text = '{"files_overview": [], "key_events": [{"title": "错误"信息"描述"}]}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None
    assert result['key_events'][0]['title'] == '错误"信息"描述'


def test_unescaped_quotes_nested():
    """测试嵌套结构中未转义双引号的修复"""
    text = '{"files_overview": [], "key_events": [{"search_context": {"keyword": "日志"关键字"}}]}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None
    assert result['key_events'][0]['search_context']['keyword'] == '日志"关键字'


def test_unescaped_quotes_in_array():
    """测试数组元素中未转义双引号的修复"""
    text = '{"files_overview": [], "key_events": ["事件"一", "事件"二"]}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None
    assert result['key_events'] == ['事件"一', '事件"二']


def test_normal_escaped_quotes_not_modified():
    """测试正常的已转义双引号不会被修改"""
    text = '{"files_overview": [], "key_events": [{"title": "正常\\"已转义\\"内容"}]}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None
    assert result['key_events'][0]['title'] == '正常"已转义"内容'


def test_unescaped_quotes_at_end():
    """测试字符串末尾未转义双引号"""
    text = '{"files_overview": [], "key_events": [{"title": "末尾有"引号"}]}'
    result, error = parse_ai_json_response(text, ['files_overview', 'key_events'])
    assert result is not None
    assert result['key_events'][0]['title'] == '末尾有"引号'