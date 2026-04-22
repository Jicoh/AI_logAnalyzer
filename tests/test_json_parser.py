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