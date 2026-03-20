#!/usr/bin/env python3
"""
AI日志分析器主入口
"""

import argparse
import os
import sys

# 添加src到路径
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.insert(0, src_path)
# 添加项目根目录到路径（用于plugins模块）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from knowledge_base import KnowledgeBaseManager
from ai_analyzer import AIAnalyzer
from utils import read_file, write_json, ensure_dir
from plugins.manager import get_plugin_manager


def cmd_analyze(args):
    """分析日志命令"""
    config_manager = ConfigManager()
    kb_manager = KnowledgeBaseManager(config=config_manager.get_all())

    # 检查日志文件
    if not os.path.exists(args.log):
        print(f"错误: 日志文件不存在: {args.log}")
        return 1

    # 读取日志内容
    log_content = read_file(args.log)

    # 初始化插件管理器
    plugin_manager = get_plugin_manager()

    # 确定要使用的插件
    if args.plugins:
        # 用户指定的插件
        plugin_ids = [p.strip() for p in args.plugins.split(',')]
    else:
        # 使用所有可用插件
        plugin_ids = [p.id for p in plugin_manager.get_all_plugins()]

    if not plugin_ids:
        print("错误: 没有可用的插件")
        return 1

    # 显示可用的插件
    print(f"使用插件: {', '.join(plugin_ids)}")

    # 插件分析
    print(f"正在分析日志: {args.log}")
    try:
        plugin_result = plugin_manager.run_analysis(plugin_ids, args.log)
        result_dict = plugin_result.to_dict()
    except Exception as e:
        print(f"插件分析失败: {e}")
        return 1

    print(f"发现 {result_dict['error_count']} 个错误, {result_dict['warning_count']} 个警告")

    # 保存插件分析结果
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    plugin_output_dir = os.path.join('data', 'plugin_output', timestamp)
    ensure_dir(plugin_output_dir)
    plugin_output = os.path.join(plugin_output_dir, 'plugin_result.json')
    write_json(plugin_output, result_dict)
    print(f"插件分析结果已保存: {plugin_output}")

    # AI分析
    if args.no_ai:
        print("跳过AI分析")
        return 0

    # 检查AI配置
    api_config = config_manager.get('api', {})
    if not api_config.get('base_url') or not api_config.get('api_key'):
        print("警告: AI配置不完整，请先配置API信息")
        print("使用命令: python main.py config set api.base_url <url>")
        print("         python main.py config set api.api_key <key>")
        return 1

    # 获取知识库ID
    kb_id = args.kb
    if not kb_id:
        kb_id = config_manager.get('knowledge_base.default_id')

    if kb_id:
        print(f"使用知识库: {kb_id}")

    # 读取用户提示词
    user_prompt = None
    if args.prompt:
        if os.path.exists(args.prompt):
            user_prompt = read_file(args.prompt)
        else:
            user_prompt = args.prompt

    # 执行AI分析
    print("正在进行AI分析...")
    ai_analyzer = AIAnalyzer(config_manager, kb_manager)

    # 流式输出分析结果
    print("\n" + "="*50)
    print("分析报告")
    print("="*50)

    gen = ai_analyzer.analyze(
        plugin_result=result_dict,
        log_content=log_content,
        kb_id=kb_id,
        user_prompt=user_prompt
    )

    # 收集完整结果并流式输出
    result = None
    try:
        while True:
            chunk = next(gen)
            print(chunk, end='', flush=True)
    except StopIteration as e:
        # 生成器结束，获取返回值
        result = e.value

    print()  # 换行

    if result is None:
        result = {
            'analysis_time': '未知',
            'kb_id': kb_id,
            'plugin_result': plugin_result,
            'analysis': ''
        }

    # 保存AI分析结果
    ai_output = os.path.join('data', 'ai_output', os.path.basename(args.log).replace('.txt', '_ai.json'))
    ensure_dir(os.path.dirname(ai_output))
    ai_analyzer.save_result(result, ai_output)
    print(f"\nAI分析结果已保存: {ai_output}")

    return 0


def cmd_kb(args):
    """知识库管理命令"""
    config_manager = ConfigManager()
    kb_manager = KnowledgeBaseManager(config=config_manager.get_all())

    if args.kb_action == 'create':
        kb_id = kb_manager.create(args.name, args.description or '')
        print(f"知识库创建成功: {kb_id}")
        return 0

    elif args.kb_action == 'delete':
        if kb_manager.delete(args.kb_id):
            print(f"知识库已删除: {args.kb_id}")
            return 0
        else:
            print(f"知识库不存在: {args.kb_id}")
            return 1

    elif args.kb_action == 'list':
        kbs = kb_manager.list()
        if not kbs:
            print("暂无知识库")
            return 0
        print("知识库列表:")
        for kb in kbs:
            print(f"  {kb['kb_id']}: {kb['name']} (文档数: {kb['document_count']})")
        return 0

    elif args.kb_action == 'info':
        kb_info = kb_manager.get(args.kb_id)
        if not kb_info:
            print(f"知识库不存在: {args.kb_id}")
            return 1
        print(f"知识库ID: {kb_info['kb_id']}")
        print(f"名称: {kb_info['name']}")
        print(f"描述: {kb_info.get('description', '无')}")
        print(f"版本: {kb_info['version']}")
        print(f"创建时间: {kb_info['created_at']}")
        print(f"文档数量: {kb_info['document_count']}")
        if kb_info['documents']:
            print("文档列表:")
            for doc in kb_info['documents']:
                print(f"  - {doc['doc_id']}: {doc['file_name']}")
        return 0

    elif args.kb_action == 'add':
        if not os.path.exists(args.file):
            print(f"文件不存在: {args.file}")
            return 1
        doc_id = kb_manager.add_document(args.kb_id, args.file)
        print(f"文档添加成功: {doc_id}")
        return 0

    elif args.kb_action == 'remove':
        if kb_manager.remove_document(args.kb_id, args.doc_id):
            print(f"文档已删除: {args.doc_id}")
            return 0
        else:
            print(f"删除失败")
            return 1

    elif args.kb_action == 'search':
        results = kb_manager.search(args.kb_id, args.query, args.top)
        if not results:
            print("未找到相关内容")
            return 0
        print(f"搜索结果 (共{len(results)}条):")
        for i, r in enumerate(results, 1):
            print(f"\n[{i}] 相关度: {r['score']:.4f}")
            print(f"内容: {r['chunk']['content'][:200]}...")
        return 0

    return 1


def cmd_config(args):
    """配置管理命令"""
    config_manager = ConfigManager()

    if args.config_action == 'get':
        value = config_manager.get(args.key)
        if value is None:
            print(f"配置项不存在: {args.key}")
            return 1
        if isinstance(value, dict):
            import json
            print(json.dumps(value, indent=2, ensure_ascii=False))
        else:
            print(value)
        return 0

    elif args.config_action == 'set':
        config_manager.set(args.key, args.value)
        config_manager.save()
        print(f"配置已更新: {args.key} = {args.value}")
        return 0

    elif args.config_action == 'list':
        import json
        print(json.dumps(config_manager.get_all(), indent=2, ensure_ascii=False))
        return 0

    return 1


def cmd_plugin(args):
    """插件管理命令"""
    plugin_manager = get_plugin_manager()

    if args.plugin_action == 'list':
        plugins = plugin_manager.get_all_plugins()
        if not plugins:
            print("暂无可用插件")
            return 0
        print("可用插件列表:")
        for plugin in plugins:
            info = plugin.get_info()
            print(f"  [{info.id}] {info.name} (v{info.version})")
            print(f"      分类: {info.category.name}")
            print(f"      描述: {info.description}")
            if info.tags:
                print(f"      标签: {', '.join(info.tags)}")
        return 0

    return 1


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='AI日志分析器')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # analyze 命令
    analyze_parser = subparsers.add_parser('analyze', help='分析日志文件')
    analyze_parser.add_argument('--log', '-l', required=True, help='日志文件路径')
    analyze_parser.add_argument('--plugins', help='指定使用的插件ID，多个插件用逗号分隔')
    analyze_parser.add_argument('--kb', '-k', help='知识库ID')
    analyze_parser.add_argument('--prompt', '-p', help='自定义提示词或提示词文件路径')
    analyze_parser.add_argument('--no-ai', action='store_true', help='仅运行插件分析，跳过AI分析')

    # plugin 命令
    plugin_parser = subparsers.add_parser('plugin', help='插件管理')
    plugin_subparsers = plugin_parser.add_subparsers(dest='plugin_action', help='插件操作')

    # plugin list
    plugin_list = plugin_subparsers.add_parser('list', help='列出可用插件')

    # kb 命令
    kb_parser = subparsers.add_parser('kb', help='知识库管理')
    kb_subparsers = kb_parser.add_subparsers(dest='kb_action', help='知识库操作')

    # kb create
    kb_create = kb_subparsers.add_parser('create', help='创建知识库')
    kb_create.add_argument('--name', '-n', required=True, help='知识库名称')
    kb_create.add_argument('--description', '-d', help='知识库描述')

    # kb delete
    kb_delete = kb_subparsers.add_parser('delete', help='删除知识库')
    kb_delete.add_argument('--kb-id', required=True, help='知识库ID')

    # kb list
    kb_list = kb_subparsers.add_parser('list', help='列出知识库')

    # kb info
    kb_info = kb_subparsers.add_parser('info', help='查看知识库详情')
    kb_info.add_argument('--kb-id', required=True, help='知识库ID')

    # kb add
    kb_add = kb_subparsers.add_parser('add', help='添加文档到知识库')
    kb_add.add_argument('--kb-id', required=True, help='知识库ID')
    kb_add.add_argument('--file', '-f', required=True, help='文档文件路径')

    # kb remove
    kb_remove = kb_subparsers.add_parser('remove', help='从知识库移除文档')
    kb_remove.add_argument('--kb-id', required=True, help='知识库ID')
    kb_remove.add_argument('--doc-id', required=True, help='文档ID')

    # kb search
    kb_search = kb_subparsers.add_parser('search', help='在知识库中搜索')
    kb_search.add_argument('--kb-id', required=True, help='知识库ID')
    kb_search.add_argument('--query', '-q', required=True, help='搜索查询')
    kb_search.add_argument('--top', '-t', type=int, default=5, help='返回结果数量')

    # config 命令
    config_parser = subparsers.add_parser('config', help='配置管理')
    config_subparsers = config_parser.add_subparsers(dest='config_action', help='配置操作')

    # config get
    config_get = config_subparsers.add_parser('get', help='获取配置项')
    config_get.add_argument('--key', '-k', required=True, help='配置项键名')

    # config set
    config_set = config_subparsers.add_parser('set', help='设置配置项')
    config_set.add_argument('--key', '-k', required=True, help='配置项键名')
    config_set.add_argument('--value', '-v', required=True, help='配置项值')

    # config list
    config_list = config_subparsers.add_parser('list', help='列出所有配置')

    args = parser.parse_args()

    if args.command == 'analyze':
        return cmd_analyze(args)
    elif args.command == 'plugin':
        return cmd_plugin(args)
    elif args.command == 'kb':
        return cmd_kb(args)
    elif args.command == 'config':
        return cmd_config(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())