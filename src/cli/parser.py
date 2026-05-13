"""
CLI参数解析器定义
独立模块，不依赖重模块加载，供 main.py 复用
"""

import argparse


def get_parser(include_web=False):
    """返回CLI参数解析器

    Args:
        include_web: 是否包含web子命令（main.py需要）
    """
    parser = argparse.ArgumentParser(description='AI日志分析器')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # analyze 命令
    analyze_parser = subparsers.add_parser('analyze', help='分析日志文件或目录')
    analyze_parser.add_argument('path', nargs='?', help='日志文件或目录路径（cli格式时不需要）')
    analyze_parser.add_argument('--format', choices=['system', 'cli'], default='system',
                                help='输出格式: system=Web格式(默认), cli=脚本集成格式')
    analyze_parser.add_argument('--plugin-id', help='插件ID（cli格式必填）')
    analyze_parser.add_argument('--task-name', default='', help='任务名称（cli格式）')
    analyze_parser.add_argument('--bmc-ip', default='', help='BMC IP地址（cli格式）')
    analyze_parser.add_argument('--date', default='', help='日期（cli格式）')
    analyze_parser.add_argument('--plugins', help='指定插件ID，多个用逗号分隔（system格式）')
    analyze_parser.add_argument('--kb', '-k', help='知识库ID')
    analyze_parser.add_argument('--prompt', '-p', help='用户提示词（配合--ai使用）')
    analyze_parser.add_argument('--ai', action='store_true', help='启用AI分析')
    analyze_parser.add_argument('--log-rules', '-l', help='日志规则集ID')

    # plugin 命令
    plugin_parser = subparsers.add_parser('plugin', help='插件管理')
    plugin_subparsers = plugin_parser.add_subparsers(dest='plugin_action', help='插件操作')

    plugin_subparsers.add_parser('list', help='列出可用插件（显示分类信息）')
    plugin_subparsers.add_parser('categories', help='按分类查看插件列表')

    plugin_select = plugin_subparsers.add_parser('select', help='选择插件（必须指定类别）')
    plugin_select.add_argument('category', nargs='?', help='插件类别名，不指定则显示当前选择')
    plugin_select.add_argument('plugins', nargs='?', help='插件ID列表（逗号分隔），不指定则选择该类别全部插件')

    plugin_subparsers.add_parser('selected', help='显示已选择的插件')

    # kb 命令
    kb_parser = subparsers.add_parser('kb', help='知识库管理')
    kb_subparsers = kb_parser.add_subparsers(dest='kb_action', help='知识库操作')

    kb_create = kb_subparsers.add_parser('create', help='创建知识库')
    kb_create.add_argument('--name', '-n', required=True, help='知识库名称')
    kb_create.add_argument('--description', '-d', help='知识库描述')

    kb_delete = kb_subparsers.add_parser('delete', help='删除知识库')
    kb_delete.add_argument('--kb-id', required=True, help='知识库ID')

    kb_subparsers.add_parser('list', help='列出知识库')

    kb_info = kb_subparsers.add_parser('info', help='查看知识库详情')
    kb_info.add_argument('--kb-id', required=True, help='知识库ID')

    kb_add = kb_subparsers.add_parser('add', help='添加文档到知识库')
    kb_add.add_argument('--kb-id', required=True, help='知识库ID')
    kb_add.add_argument('--file', '-f', required=True, help='文档文件路径')

    kb_remove = kb_subparsers.add_parser('remove', help='从知识库移除文档')
    kb_remove.add_argument('--kb-id', required=True, help='知识库ID')
    kb_remove.add_argument('--doc-id', required=True, help='文档ID')

    kb_search = kb_subparsers.add_parser('search', help='在知识库中搜索')
    kb_search.add_argument('--kb-id', required=True, help='知识库ID')
    kb_search.add_argument('--query', '-q', required=True, help='搜索查询')
    kb_search.add_argument('--top', '-t', type=int, default=5, help='返回结果数量')

    kb_reindex = kb_subparsers.add_parser('reindex', help='重建知识库索引')
    kb_reindex.add_argument('--kb-id', required=True, help='知识库ID')

    # config 命令
    config_parser = subparsers.add_parser('config', help='配置管理')
    config_subparsers = config_parser.add_subparsers(dest='config_action', help='配置操作')

    config_get = config_subparsers.add_parser('get', help='获取配置项')
    config_get.add_argument('--key', '-k', required=True, help='配置项键名')

    config_set = config_subparsers.add_parser('set', help='设置配置项')
    config_set.add_argument('--key', '-k', required=True, help='配置项键名')
    config_set.add_argument('--value', '-v', required=True, help='配置项值')

    config_subparsers.add_parser('list', help='列出所有配置')

    # log-rules 命令
    log_rules_parser = subparsers.add_parser('log-rules', help='日志元数据规则管理')
    log_rules_subparsers = log_rules_parser.add_subparsers(dest='rules_action', help='规则操作')

    log_rules_subparsers.add_parser('list', help='列出所有规则集')

    log_rules_create = log_rules_subparsers.add_parser('create', help='创建规则集')
    log_rules_create.add_argument('--name', '-n', required=True, help='规则集名称')
    log_rules_create.add_argument('--description', '-d', help='规则集描述')

    log_rules_show = log_rules_subparsers.add_parser('show', help='查看规则集详情')
    log_rules_show.add_argument('--rules-id', required=True, help='规则集ID')

    log_rules_delete = log_rules_subparsers.add_parser('delete', help='删除规则集')
    log_rules_delete.add_argument('--rules-id', required=True, help='规则集ID')

    log_rules_add = log_rules_subparsers.add_parser('add', help='添加规则到规则集')
    log_rules_add.add_argument('--rules-id', required=True, help='规则集ID')
    log_rules_add.add_argument('--file-path', '-f', required=True, help='文件路径匹配规则')
    log_rules_add.add_argument('--description', '-d', help='规则描述')
    log_rules_add.add_argument('--keywords', '-k', help='关键词（逗号分隔）')
    log_rules_add.add_argument('--plugins', '-p', help='建议插件（逗号分隔）')

    log_rules_remove = log_rules_subparsers.add_parser('remove', help='从规则集移除规则')
    log_rules_remove.add_argument('--rules-id', required=True, help='规则集ID')
    log_rules_remove.add_argument('--rule-id', required=True, help='规则ID')

    # cache 命令
    cache_parser = subparsers.add_parser('cache', help='缓存管理')
    cache_subparsers = cache_parser.add_subparsers(dest='cache_action', help='缓存操作')

    cache_subparsers.add_parser('stats', help='查看缓存大小')
    cache_subparsers.add_parser('clear-results', help='清理分析结果')
    cache_subparsers.add_parser('clear-temp', help='清理临时文件')

    # web 命令（仅main.py需要）
    if include_web:
        web_parser = subparsers.add_parser('web', help='启动Web界面')
        web_parser.add_argument('--host', type=str, default='127.0.0.1',
                                help='绑定主机地址 (默认: 127.0.0.1)')
        web_parser.add_argument('--port', type=int, default=18888,
                                help='绑定端口 (默认: 18888)')
        web_parser.add_argument('--debug', action='store_true', dest='debug',
                                help='启用调试模式')
        web_parser.add_argument('--no-debug', action='store_false', dest='debug',
                                help='禁用调试模式')
        web_parser.add_argument('--no-browser', action='store_true',
                                help='不自动打开浏览器')

    return parser
