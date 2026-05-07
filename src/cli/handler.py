"""
CLI 子命令处理
"""

import os
import sys
from typing import Dict

# 项目根目录（当前文件在 src/cli/handler.py）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cli.parser import get_parser

from src.system_config_manager import SystemConfigManager
from src.knowledge_base import KnowledgeBaseManager
from src.ai_analyzer.analyzer import analyze_with_agent
from src.log_metadata import LogMetadataManager
from src.utils import read_file, write_json, ensure_dir, get_logger
from src.utils.file_utils import (
    is_archive_file, is_valid_log_file, extract_archive_recursive,
    create_single_log_output_dir, get_data_dir, find_log_files_in_directory, clean_filename
)
from plugins.manager import get_plugin_manager
from plugins import render_html
from plugins.base import count_severity

logger = get_logger('cli')


def log_callback(message: str, level: str = "info"):
    """日志回调适配函数，根据级别调用不同的日志方法。"""
    # success 映射为 info
    log_level = level if level in ['info', 'warning', 'error'] else 'info'
    log_method = getattr(logger, log_level, logger.info)
    log_method(message)


def display_plugin_result(result: Dict):
    """在 CLI 显示插件分析结果。"""
    print("\n" + "="*50)
    print("插件分析结果")
    print("="*50)

    for section in result.get('sections', []):
        section_type = section.get('type')
        title = section.get('title', '')

        if section_type == 'stats':
            print(f"\n【{title}】")
            for item in section.get('items', []):
                label = item.get('label')
                value = item.get('value')
                unit = item.get('unit', '')
                print(f"  {label}: {value} {unit}")

        elif section_type == 'table':
            print(f"\n【{title}】")
            columns = section.get('columns', [])
            rows = section.get('rows', [])
            if rows:
                # 打印表头
                headers = [c.get('label', c.get('key')) for c in columns]
                print("  " + " | ".join(headers))
                print("  " + "-" * (len(headers) * 10))
                # 打印行
                for row in rows[:10]:
                    values = [str(row.get(c.get('key'), ''))[:20] for c in columns]
                    print("  " + " | ".join(values))
                if len(rows) > 10:
                    print(f"  ... 共 {len(rows)} 行")

        elif section_type == 'chart':
            print(f"\n【{title}】({section.get('chart_type', 'bar')} 图)")
            data = section.get('data', {})
            labels = data.get('labels', [])
            values = data.get('values', [])
            for label, value in zip(labels, values):
                print(f"  {label}: {value}")


def cmd_analyze(args):
    """分析日志命令"""
    logger.debug(f"开始分析日志: {args.path}")

    settings_manager = SystemConfigManager()
    kb_manager = KnowledgeBaseManager(config=settings_manager.get_all())

    # 检查日志文件
    if not os.path.exists(args.path):
        logger.error(f"日志文件不存在: {args.path}")
        print(f"错误: 日志文件不存在: {args.path}")
        return 1

    # 初始化插件管理器
    root_dir = PROJECT_ROOT
    custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
    plugin_manager = get_plugin_manager(custom_dirs=[custom_plugins_dir])

    # 处理文件类型：压缩包需要解压
    analysis_path = args.path  # 用于插件分析的路径
    log_file_paths = [args.path]  # 用于AI智能选择的日志文件列表

    if is_archive_file(args.path):
        # 压缩包：解压到临时目录
        from datetime import datetime
        temp_base = get_data_dir('temp')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.basename(args.path)
        clean_name = filename
        for ext in ['.tar.gz', '.tgz', '.tar', '.zip']:
            if clean_name.lower().endswith(ext):
                clean_name = clean_name[:-len(ext)]
                break
        work_dir_name = f"{timestamp}_{clean_name}"
        work_dir = os.path.join(temp_base, work_dir_name)
        ensure_dir(work_dir)

        print(f"解压压缩包到: {work_dir}")
        extract_archive_recursive(args.path, work_dir)

        # 查找解压后的日志文件
        log_file_paths = find_log_files_in_directory(work_dir)
        if not log_file_paths:
            print(f"错误: 压缩包中没有找到日志文件")
            return 1

        print(f"找到 {len(log_file_paths)} 个日志文件")
        # 插件分析使用解压后的目录
        analysis_path = work_dir

    # CLI 使用用户指定的插件或默认插件
    if args.plugins:
        plugin_ids = [p.strip() for p in args.plugins.split(',')]
    else:
        # 默认使用 log_parser 插件
        plugin_ids = ['log_parser']

    if not plugin_ids:
        logger.error("没有可用的插件")
        print("错误: 没有可用的插件")
        return 1

    print(f"使用插件: {', '.join(plugin_ids)}")

    # 插件分析
    print(f"正在分析日志: {analysis_path}")
    try:
        # 使用日志回调函数，支持不同日志级别
        result_dict = plugin_manager.run_analysis(plugin_ids, analysis_path, log_callback=log_callback)
        logger.debug("插件分析完成")
    except Exception as e:
        logger.error(f"插件分析失败: {e}")
        print(f"插件分析失败: {e}")
        return 1

    # 统计错误和警告数量
    sections = result_dict.get('sections', [])
    counts = count_severity(sections)
    total_errors = counts['errors']
    total_warnings = counts['warnings']

    print(f"发现 {total_errors} 个错误, {total_warnings} 个警告")

    # 保存插件分析结果
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # 使用日志文件名（去除扩展名）
    log_filename = os.path.basename(args.path)
    clean_name = clean_filename(log_filename)
    dir_name = f"{timestamp}_{clean_name}"
    analysis_output_dir = os.path.join('data', 'analysis_output', dir_name)
    ensure_dir(analysis_output_dir)
    plugin_output_file = os.path.join(analysis_output_dir, 'plugin_result.json')
    write_json(plugin_output_file, result_dict)
    print(f"插件分析结果已保存: {plugin_output_file}")

    # 显示结果概览
    display_plugin_result(result_dict)

    # AI分析
    if not args.ai:
        print("跳过AI分析")
        return 0

    # 检查AI配置
    api_config = settings_manager.get('api', {})
    if not api_config.get('base_url') or not api_config.get('api_key'):
        print("警告: AI配置不完整，请先配置API信息")
        print("使用命令: python main.py config set api.base_url <url>")
        print("         python main.py config set api.api_key <key>")
        return 1

    # 获取知识库ID
    kb_id = args.kb
    if not kb_id:
        kb_id = settings_manager.get('knowledge_base.default_id')

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

    try:
        log_metadata_manager = LogMetadataManager()
        log_rules_id = getattr(args, 'log_rules', None)
        if log_rules_id:
            log_metadata_manager.set_active_rules(log_rules_id)

        result = analyze_with_agent(
            settings_manager=settings_manager,
            kb_manager=kb_manager,
            log_metadata_manager=log_metadata_manager,
            plugin_result=result_dict,
            log_source={'type': 'local_file', 'paths': log_file_paths},
            kb_id=kb_id,
            user_prompt=user_prompt,
            log_rules_id=log_rules_id
        )
        html_result = result.get('html', '')

        # 保存AI分析HTML结果（与Web界面一致）
        ai_html_file = os.path.join(analysis_output_dir, 'ai_analysis.html')
        with open(ai_html_file, 'w', encoding='utf-8') as f:
            f.write(html_result)

        # 生成插件HTML
        render_html(plugin_output_file)

        print(f"\nAI分析完成")
        print(f"插件报告: {plugin_output_file.replace('.json', '.html')}")
        print(f"AI报告: {ai_html_file}")

    except Exception as e:
        logger.error(f"AI分析失败: {e}")
        print(f"AI分析失败: {e}")
        return 1

    return 0


def cmd_kb(args):
    """知识库管理命令"""
    settings_manager = SystemConfigManager()
    kb_manager = KnowledgeBaseManager(config=settings_manager.get_all())

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

    elif args.kb_action == 'reindex':
        result = kb_manager.reindex(args.kb_id)
        if result['status'] == 'success':
            print(f"索引重建成功")
            print(f"  文档数量: {result['indexed_count']}")
            vector_status = '已构建' if result['vector_index'] else '未构建 (embedding未启用)'
            print(f"  向量索引: {vector_status}")
            return 0
        else:
            print(f"索引重建失败: {result['message']}")
            return 1

    return 1


def cmd_config(args):
    """配置管理命令"""
    settings_manager = SystemConfigManager()

    if args.config_action == 'get':
        value = settings_manager.get(args.key)
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
        settings_manager.set(args.key, args.value)
        settings_manager.save()
        print(f"配置已更新: {args.key} = {args.value}")
        return 0

    elif args.config_action == 'list':
        import json
        print(json.dumps(settings_manager.get_all(), indent=2, ensure_ascii=False))
        return 0

    return 1


def cmd_plugin(args):
    """插件管理命令"""
    root_dir = PROJECT_ROOT
    custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
    plugin_manager = get_plugin_manager(custom_dirs=[custom_plugins_dir])

    if args.plugin_action == 'list':
        plugins = plugin_manager.get_all_plugins()
        if not plugins:
            print("暂无可用插件")
            return 0
        print("可用插件列表:")
        for plugin in plugins:
            plugin_type = plugin.get_plugin_type()
            print(f"  [{plugin_type}] {plugin.id}: {plugin.get_chinese_description()} (v{plugin.get_version()})")
        return 0

    if args.plugin_action == 'categories':
        categories = plugin_manager.get_plugins_categories()
        if not categories:
            print("暂无可用插件分类")
            return 0
        print("插件分类列表:")
        for category_name, category_data in categories.items():
            plugins = category_data.get('plugins', [])
            if plugins:
                print(f"  [{category_name}] ({len(plugins)}个)")
                for p in plugins:
                    print(f"    - {p['id']}: {p['description']}")
        return 0

    if args.plugin_action == 'select':
        categories = plugin_manager.get_plugins_categories()

        if not args.category:
            # 显示可用类别和提示
            print("可用插件类别:")
            for category_name in categories.keys():
                plugins = categories[category_name].get('plugins', [])
                print(f"  [{category_name}] ({len(plugins)}个插件)")
            print("\n提示: 请通过 Web 界面设置默认插件")
            return 0

        # 显示指定类别的可用插件
        if args.category not in categories:
            print(f"错误: 类别 '{args.category}' 不存在")
            print(f"可用类别: {', '.join(categories.keys())}")
            return 1

        category_plugins = categories[args.category].get('plugins', [])
        if not category_plugins:
            print(f"错误: 类别 '{args.category}' 下没有插件")
            return 1

        print(f"类别 '{args.category}' 可用插件:")
        for p in category_plugins:
            print(f"  - {p['id']}: {p['description']}")
        print("\n提示: 请通过 Web 界面设置默认插件，或在 analyze 命令中使用 --plugins 参数指定插件")
        return 0

    if args.plugin_action == 'selected':
        print("提示: CLI 不存储用户配置，请通过 Web 界面查看已选择的插件")
        print("如需在 CLI 中指定插件，请使用 analyze 命令的 --plugins 参数")
        return 0

    return 1


def cmd_analyze_batch(args):
    """批量分析日志目录"""
    from datetime import datetime

    logger.debug(f"开始批量分析: {args.path}")
    settings_manager = SystemConfigManager()
    kb_manager = KnowledgeBaseManager(config=settings_manager.get_all())

    # 检查目录是否存在
    if not os.path.exists(args.path):
        logger.error(f"目录不存在: {args.path}")
        print(f"错误: 目录不存在: {args.path}")
        return 1

    if not os.path.isdir(args.path):
        logger.error(f"路径不是目录: {args.path}")
        print(f"错误: 路径不是目录: {args.path}")
        return 1

    # 初始化插件管理器
    root_dir = PROJECT_ROOT
    custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
    plugin_manager = get_plugin_manager(custom_dirs=[custom_plugins_dir])

    # 确定要使用的插件
    if args.plugins:
        plugin_ids = [p.strip() for p in args.plugins.split(',')]
    else:
        # CLI 默认使用 log_parser 插件
        plugin_ids = ['log_parser']

    if not plugin_ids:
        logger.error("没有可用的插件")
        print("错误: 没有可用的插件")
        return 1

    # 构建分析单元列表
    # 每个分析单元是一个路径（目录或文件）
    analysis_units = []
    for item in os.listdir(args.path):
        item_path = os.path.join(args.path, item)
        if os.path.isfile(item_path) and is_valid_log_file(item_path):
            # 单个日志文件
            analysis_units.append({
                'path': item_path,
                'name': item,
                'is_archive': False
            })
        elif os.path.isfile(item_path) and is_archive_file(item_path):
            # 压缩文件：解压
            temp_base = get_data_dir('temp')
            extract_dir = os.path.join(temp_base, f"extract_{item}")
            # 处理扩展名
            extract_name = item
            if item.lower().endswith('.tar.gz'):
                extract_name = item[:-7]
            elif item.lower().endswith('.tgz'):
                extract_name = item[:-4]
            elif item.lower().endswith('.tar') or item.lower().endswith('.zip'):
                extract_name = os.path.splitext(item)[0]
            extract_dir = os.path.join(temp_base, f"extract_{extract_name}")
            ensure_dir(extract_dir)
            extract_archive_recursive(item_path, extract_dir)
            analysis_units.append({
                'path': extract_dir,
                'name': extract_name,
                'is_archive': True
            })

    if not analysis_units:
        logger.error(f"目录中没有找到日志文件: {args.path}")
        print(f"错误: 目录中没有找到日志文件: {args.path}")
        return 1

    print(f"发现 {len(analysis_units)} 个分析单元")
    print(f"使用插件: {', '.join(plugin_ids)}")

    # 创建批量输出目录
    analysis_output_base = get_data_dir('analysis_output')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dir_name = os.path.basename(args.path)
    clean_name = dir_name
    for ext in ['.tar.gz', '.tgz', '.tar', '.zip']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break
    batch_dir_name = f"{timestamp}_{clean_name}"
    batch_output_dir = os.path.join(analysis_output_base, batch_dir_name)
    ensure_dir(batch_output_dir)

    # 获取知识库ID
    kb_id = args.kb
    if not kb_id:
        kb_id = settings_manager.get('knowledge_base.default_id')

    log_rules_id = getattr(args, 'log_rules', None)

    # 获取用户提示词
    user_prompt = None
    if args.prompt:
        if os.path.exists(args.prompt):
            user_prompt = read_file(args.prompt)
        else:
            user_prompt = args.prompt

    # 批量分析每个单元
    batch_results = {}
    total_errors = 0
    total_warnings = 0

    for idx, unit in enumerate(analysis_units, 1):
        unit_name = unit['name']
        unit_path = unit['path']

        print(f"\n[{idx}/{len(analysis_units)}] 分析: {unit_name}")

        # 创建单个单元的输出目录
        single_output_dir = create_single_log_output_dir(batch_output_dir, unit_name)

        # 确定当前单元使用的插件
        current_plugin_ids = plugin_ids
        current_log_files = find_log_files_in_directory(unit_path) if os.path.isdir(unit_path) else [unit_path]

        try:
            # 使用主程序的 logger 作为回调，保持日志一致性
            plugin_result = plugin_manager.run_analysis(
                current_plugin_ids, unit_path,
                log_callback=log_callback
            )

            # 保存插件结果
            plugin_output_file = os.path.join(single_output_dir, 'plugin_result.json')
            write_json(plugin_output_file, plugin_result)

            # 生成HTML
            render_html(plugin_output_file)

            # 计算错误和警告数
            unit_errors = 0
            unit_warnings = 0
            for plugin_id, plugin_data in plugin_result.items():
                if isinstance(plugin_data, dict):
                    sections = plugin_data.get('sections', [])
                    counts = count_severity(sections)
                    unit_errors += counts['errors']
                    unit_warnings += counts['warnings']

            total_errors += unit_errors
            total_warnings += unit_warnings

            # AI分析（如果启用）
            ai_result = None
            if args.ai:
                print(f"  AI分析中...")
                # 检查AI配置
                api_config = settings_manager.get('api', {})
                if not api_config.get('base_url') or not api_config.get('api_key'):
                    print(f"  警告: AI配置不完整，跳过AI分析")
                else:
                    try:
                        # 初始化 log_metadata_manager（如果尚未初始化）
                        if 'log_metadata_manager' not in dir() or log_metadata_manager is None:
                            log_metadata_manager = LogMetadataManager()
                            if log_rules_id:
                                log_metadata_manager.set_active_rules(log_rules_id)

                        result = analyze_with_agent(
                            settings_manager=settings_manager,
                            kb_manager=kb_manager,
                            log_metadata_manager=log_metadata_manager,
                            plugin_result=plugin_result,
                            log_source={'type': 'local_file', 'paths': current_log_files},
                            kb_id=kb_id,
                            user_prompt=user_prompt,
                            log_rules_id=log_rules_id
                        )
                        html_result = result.get('html', '')
                        ai_html_file = os.path.join(single_output_dir, 'ai_analysis.html')
                        with open(ai_html_file, 'w', encoding='utf-8') as f:
                            f.write(html_result)
                        ai_result = {'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        print(f"  AI分析完成")
                    except Exception as e:
                        print(f"  AI分析失败: {e}")

            batch_results[unit_name] = {
                'output_dir': os.path.basename(single_output_dir),
                'plugin_result': plugin_result,
                'errors': unit_errors,
                'warnings': unit_warnings,
                'ai_result': ai_result
            }
            print(f"  完成: {unit_errors}个错误, {unit_warnings}个警告")

        except Exception as e:
            logger.error(f"分析失败: {unit_name}, 错误: {e}")
            print(f"  分析失败: {e}")
            batch_results[unit_name] = {'error': str(e)}

    # 生成汇总JSON
    batch_summary_file = os.path.join(batch_output_dir, 'batch_summary.json')
    summary_data = {
        'batch_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'directory': args.path,
        'total_files': len(analysis_units),
        'total_errors': total_errors,
        'total_warnings': total_warnings,
        'files': batch_results
    }
    write_json(batch_summary_file, summary_data)

    # 生成汇总HTML
    from plugins.renderer.html_renderer import render_batch_html
    batch_html_path = render_batch_html(batch_summary_file)

    print("\n" + "=" * 50)
    print("批量分析完成")
    print("=" * 50)
    print(f"总单元数: {len(analysis_units)}")
    print(f"总错误数: {total_errors}")
    print(f"总警告数: {total_warnings}")
    print(f"汇总报告: {batch_html_path}")

    return 0


def cmd_log_rules(args):
    """日志元数据规则管理命令"""
    log_metadata_manager = LogMetadataManager()

    if args.rules_action == 'list':
        rule_sets = log_metadata_manager.list_rule_sets()
        if not rule_sets:
            print("暂无规则集")
            return 0
        print("规则集列表:")
        for rs in rule_sets:
            print(f"  {rs['rules_id']}: {rs['name']} ({rs['rule_count']}条规则)")
            if rs['description']:
                print(f"      描述: {rs['description']}")
        return 0

    elif args.rules_action == 'create':
        rules_id = log_metadata_manager.create_rule_set(args.name, args.description or '')
        print(f"规则集创建成功: {rules_id}")
        return 0

    elif args.rules_action == 'show':
        rule_set = log_metadata_manager.get_rule_set(args.rules_id)
        if not rule_set:
            print(f"规则集不存在: {args.rules_id}")
            return 1
        print(f"规则集ID: {rule_set['rules_id']}")
        print(f"名称: {rule_set['name']}")
        print(f"描述: {rule_set['description'] or '无'}")
        if rule_set['rules']:
            print("规则列表:")
            for rule in rule_set['rules']:
                print(f"  [{rule['rule_id']}] {rule['file_path']}")
                print(f"      描述: {rule['description'] or '无'}")
                if rule['keywords']:
                    print(f"      关键词: {', '.join(rule['keywords'])}")
                if rule['suggested_plugins']:
                    print(f"      建议插件: {', '.join(rule['suggested_plugins'])}")
        else:
            print("暂无规则")
        return 0

    elif args.rules_action == 'delete':
        if log_metadata_manager.delete_rule_set(args.rules_id):
            print(f"规则集已删除: {args.rules_id}")
            return 0
        else:
            print(f"规则集不存在: {args.rules_id}")
            return 1

    elif args.rules_action == 'add':
        if not args.file_path:
            print("错误: 必须指定 --file-path")
            return 1
        rule = {
            'file_path': args.file_path,
            'description': args.description or '',
            'keywords': args.keywords.split(',') if args.keywords else [],
            'suggested_plugins': args.plugins.split(',') if args.plugins else []
        }
        rule_id = log_metadata_manager.add_rule_to_set(args.rules_id, rule)
        if rule_id:
            print(f"规则添加成功: {rule_id}")
            return 0
        else:
            print(f"规则集不存在或文件路径无效: {args.rules_id}")
            return 1

    elif args.rules_action == 'remove':
        if log_metadata_manager.remove_rule_from_set(args.rules_id, args.rule_id):
            print(f"规则已删除: {args.rule_id}")
            return 0
        else:
            print(f"规则不存在: {args.rule_id}")
            return 1

    return 1


def cmd_cache(args):
    """缓存管理命令"""
    import shutil
    import stat
    import errno
    import time

    def get_dir_size(path):
        """计算目录大小（字节）"""
        if not os.path.exists(path):
            return 0
        total = 0
        try:
            for entry in os.scandir(path):
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += get_dir_size(entry.path)
        except OSError:
            pass
        return total

    def format_size(size_bytes):
        """格式化大小显示"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def handle_readonly(func, path, excinfo):
        """处理只读文件删除失败"""
        if func in (os.rmdir, os.remove):
            exc = excinfo[1]
            if hasattr(exc, 'errno') and exc.errno in (errno.EACCES, errno.EPERM):
                try:
                    os.chmod(path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
                    func(path)
                except OSError:
                    pass

    def delete_with_retry(path, is_dir=False, max_retries=3, delay=0.1):
        """带重试和权限处理的删除"""
        for attempt in range(max_retries):
            try:
                if is_dir:
                    shutil.rmtree(path, onerror=handle_readonly)
                else:
                    if not os.access(path, os.W_OK):
                        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
                    os.remove(path)
                return True
            except OSError:
                if attempt == max_retries - 1:
                    return False
                time.sleep(delay)
        return False

    def clear_dir_contents(path):
        """清空目录内容但保留目录本身，返回统计信息"""
        if not os.path.exists(path):
            return {'deleted': 0, 'failed': 0, 'failed_files': []}

        stats = {'deleted': 0, 'failed': 0, 'failed_files': []}

        for entry in os.scandir(path):
            is_dir = entry.is_dir()
            if delete_with_retry(entry.path, is_dir=is_dir):
                stats['deleted'] += 1
            else:
                stats['failed'] += 1
                stats['failed_files'].append(entry.path)

        return stats

    temp_dir = get_data_dir('temp')
    analysis_output_dir = get_data_dir('analysis_output')

    if args.cache_action == 'stats':
        temp_size = get_dir_size(temp_dir)
        output_size = get_dir_size(analysis_output_dir)
        total_size = temp_size + output_size

        print("缓存统计:")
        print(f"  临时文件: {format_size(temp_size)} ({temp_dir})")
        print(f"  分析结果: {format_size(output_size)} ({analysis_output_dir})")
        print(f"  总计: {format_size(total_size)}")
        return 0

    elif args.cache_action == 'clear-results':
        stats = clear_dir_contents(analysis_output_dir)
        print(f"清理完成：删除 {stats['deleted']} 个文件")
        if stats['failed'] > 0:
            print(f"警告：{stats['failed']} 个文件删除失败")
            for f in stats['failed_files']:
                print(f"  - {f}")
        return 0

    elif args.cache_action == 'clear-temp':
        stats = clear_dir_contents(temp_dir)
        print(f"清理完成：删除 {stats['deleted']} 个文件")
        if stats['failed'] > 0:
            print(f"警告：{stats['failed']} 个文件删除失败")
            for f in stats['failed_files']:
                print(f"  - {f}")
        return 0

    return 1


def handle_command(args):
    """处理CLI子命令（供main直接调用）"""
    if args.command == 'analyze':
        if os.path.isdir(args.path):
            return cmd_analyze_batch(args)
        else:
            return cmd_analyze(args)
    elif args.command == 'plugin':
        return cmd_plugin(args)
    elif args.command == 'kb':
        return cmd_kb(args)
    elif args.command == 'config':
        return cmd_config(args)
    elif args.command == 'log-rules':
        return cmd_log_rules(args)
    elif args.command == 'cache':
        return cmd_cache(args)
    else:
        return 1


def main():
    """主函数"""
    parser = get_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    return handle_command(args)


if __name__ == '__main__':
    sys.exit(main())