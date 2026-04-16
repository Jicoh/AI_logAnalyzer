#!/usr/bin/env python3
"""
AI日志分析器主入口
"""

import argparse
import os
import sys
from typing import Dict

# 添加src到路径
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.insert(0, src_path)
# 添加项目根目录到路径（用于plugins模块）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from knowledge_base import KnowledgeBaseManager
from ai_analyzer import AIAnalyzer
from ai_analyzer.agent_coordinator import AgentCoordinator
from ai_analyzer.selection_agent import SelectionAgent
from log_metadata import LogMetadataManager
from utils import read_file, write_json, ensure_dir, get_logger
from utils.file_utils import (
    is_archive_file, is_log_file, is_valid_log_file, extract_archive,
    create_batch_work_directory, create_single_log_output_dir, get_data_dir,
    find_log_files_in_directory
)
from plugins.manager import get_plugin_manager
from plugins import render_html
from plugin_selection import PluginSelectionManager

logger = get_logger('cli')


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
    logger.debug(f"开始分析日志: {args.log}")

    config_manager = ConfigManager()
    kb_manager = KnowledgeBaseManager(config=config_manager.get_all())
    plugin_selection_manager = PluginSelectionManager()

    # 检查日志文件
    if not os.path.exists(args.log):
        logger.error(f"日志文件不存在: {args.log}")
        print(f"错误: 日志文件不存在: {args.log}")
        return 1

    # 读取日志内容
    log_content = read_file(args.log)
    logger.debug(f"读取日志内容，长度: {len(log_content)}")

    # 初始化插件管理器
    root_dir = os.path.dirname(os.path.abspath(__file__))
    custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
    plugin_manager = get_plugin_manager(custom_dirs=[custom_plugins_dir])

    # 确定要使用的插件
    log_file_paths = [args.log]  # 用于AI智能选择

    if args.ai_select:
        # AI智能选择模式
        print("AI智能选择模式已启用...")

        # 检查AI配置
        api_config = config_manager.get('api', {})
        if not api_config.get('base_url') or not api_config.get('api_key'):
            print("警告: AI配置不完整，使用默认插件")
            plugin_ids = plugin_selection_manager.get('selected_plugins', ['log_parser'])
        else:
            # 获取用户提示词
            user_prompt = args.prompt
            if user_prompt and os.path.exists(user_prompt):
                user_prompt = read_file(user_prompt)

            if not user_prompt:
                print("警告: AI智能选择需要用户提示词(--prompt)，使用默认插件")
                plugin_ids = plugin_selection_manager.get('selected_plugins', ['log_parser'])
            else:
                try:
                    log_metadata_manager = LogMetadataManager()
                    selection_agent = SelectionAgent(
                        config_manager=config_manager,
                        log_metadata_manager=log_metadata_manager,
                        plugin_manager=plugin_manager
                    )
                    selection_result = selection_agent.select(log_file_paths, user_prompt)

                    plugin_ids = selection_result['selected_plugins']
                    log_file_paths = selection_result['selected_files']

                    print(f"AI选择结果: {selection_result['reason']}")
                    print(f"选择插件: {', '.join(plugin_ids)}")
                    print(f"选择文件: {', '.join([os.path.basename(f) for f in log_file_paths])}")
                except Exception as e:
                    logger.error(f"AI智能选择失败: {e}")
                    print(f"AI智能选择失败: {e}，使用默认插件")
                    plugin_ids = plugin_selection_manager.get('selected_plugins', ['log_parser'])
    elif args.plugins:
        plugin_ids = [p.strip() for p in args.plugins.split(',')]
    else:
        plugin_ids = plugin_selection_manager.get('selected_plugins', ['log_parser'])

    if not plugin_ids:
        logger.error("没有可用的插件")
        print("错误: 没有可用的插件")
        return 1

    print(f"使用插件: {', '.join(plugin_ids)}")

    # 插件分析
    print(f"正在分析日志: {args.log}")
    try:
        # 使用主程序的 logger 作为回调，保持日志一致性
        result_dict = plugin_manager.run_analysis(plugin_ids, args.log, log_callback=logger.info)
        logger.debug("插件分析完成")
    except Exception as e:
        logger.error(f"插件分析失败: {e}")
        print(f"插件分析失败: {e}")
        return 1

    # 统计错误和警告数量
    total_errors = 0
    total_warnings = 0
    for section in result_dict.get('sections', []):
        if section['type'] == 'stats':
            for item in section.get('items', []):
                if item.get('severity') == 'error':
                    total_errors += item.get('value', 0)
                elif item.get('severity') == 'warning':
                    total_warnings += item.get('value', 0)

    print(f"发现 {total_errors} 个错误, {total_warnings} 个警告")

    # 保存插件分析结果
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # 使用日志文件名（去除扩展名）
    log_filename = os.path.basename(args.log)
    clean_name = log_filename
    for ext in ['.tar.gz', '.tgz', '.tar', '.zip', '.log', '.txt']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break
    dir_name = f"{timestamp}_{clean_name}"
    plugin_output_dir = os.path.join('data', 'plugin_output', dir_name)
    ensure_dir(plugin_output_dir)
    plugin_output = os.path.join(plugin_output_dir, 'plugin_result.json')
    write_json(plugin_output, result_dict)
    print(f"插件分析结果已保存: {plugin_output}")

    # 显示结果概览
    display_plugin_result(result_dict)

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
    root_dir = os.path.dirname(os.path.abspath(__file__))
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
        plugin_selection_manager = PluginSelectionManager()
        categories = plugin_manager.get_plugins_categories()

        if not args.category:
            # 显示当前选择的插件
            selected = plugin_selection_manager.get('selected_plugins', [])
            if selected:
                # 显示选中插件的类别
                plugin_type = None
                for p in plugin_manager.get_all_plugins():
                    if p.id in selected:
                        plugin_type = p.get_plugin_type()
                        break
                print(f"当前选择: [{plugin_type}] {', '.join(selected)}")
            else:
                print("未设置默认插件")
            return 0

        # 验证类别是否存在
        if args.category not in categories:
            print(f"错误: 类别 '{args.category}' 不存在")
            print(f"可用类别: {', '.join(categories.keys())}")
            return 1

        category_plugins = categories[args.category].get('plugins', [])
        if not category_plugins:
            print(f"错误: 类别 '{args.category}' 下没有插件")
            return 1

        # 获取该类别下所有插件ID
        category_plugin_ids = [p['id'] for p in category_plugins]

        if args.plugins:
            # 用户指定了具体插件，验证是否属于该类别
            requested_ids = [p.strip() for p in args.plugins.split(',')]
            invalid_ids = [pid for pid in requested_ids if pid not in category_plugin_ids]
            if invalid_ids:
                print(f"错误: 插件 '{', '.join(invalid_ids)}' 不属于类别 '{args.category}'")
                print(f"该类别可用插件: {', '.join(category_plugin_ids)}")
                return 1
            selected_ids = requested_ids
        else:
            # 未指定具体插件，选择该类别全部插件
            selected_ids = category_plugin_ids

        plugin_selection_manager.set('selected_plugins', selected_ids)
        plugin_selection_manager.save()
        print(f"已选择: [{args.category}] {', '.join(selected_ids)}")
        return 0

    return 1


def cmd_analyze_batch(args):
    """批量分析日志目录"""
    from datetime import datetime

    logger.debug(f"开始批量分析: {args.dir}")
    config_manager = ConfigManager()
    kb_manager = KnowledgeBaseManager(config=config_manager.get_all())

    # 检查目录是否存在
    if not os.path.exists(args.dir):
        logger.error(f"目录不存在: {args.dir}")
        print(f"错误: 目录不存在: {args.dir}")
        return 1

    if not os.path.isdir(args.dir):
        logger.error(f"路径不是目录: {args.dir}")
        print(f"错误: 路径不是目录: {args.dir}")
        return 1

    # 初始化插件管理器
    root_dir = os.path.dirname(os.path.abspath(__file__))
    custom_plugins_dir = os.path.join(root_dir, 'custom_plugins')
    plugin_manager = get_plugin_manager(custom_dirs=[custom_plugins_dir])

    # 确定要使用的插件
    if args.plugins:
        plugin_ids = [p.strip() for p in args.plugins.split(',')]
    else:
        plugin_selection_manager = PluginSelectionManager()
        plugin_ids = plugin_selection_manager.get('selected_plugins', ['log_parser'])

    if not plugin_ids:
        logger.error("没有可用的插件")
        print("错误: 没有可用的插件")
        return 1

    # 构建分析单元列表
    # 每个分析单元是一个路径（目录或文件）
    analysis_units = []
    for item in os.listdir(args.dir):
        item_path = os.path.join(args.dir, item)
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
            extract_archive(item_path, extract_dir)
            analysis_units.append({
                'path': extract_dir,
                'name': extract_name,
                'is_archive': True
            })

    if not analysis_units:
        logger.error(f"目录中没有找到日志文件: {args.dir}")
        print(f"错误: 目录中没有找到日志文件: {args.dir}")
        return 1

    print(f"发现 {len(analysis_units)} 个分析单元")
    print(f"使用插件: {', '.join(plugin_ids)}")

    # 创建批量输出目录
    plugin_output_base = get_data_dir('plugin_output')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dir_name = os.path.basename(args.dir)
    clean_name = dir_name
    for ext in ['.tar.gz', '.tgz', '.tar', '.zip']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break
    batch_dir_name = f"{timestamp}_{clean_name}"
    batch_output_dir = os.path.join(plugin_output_base, batch_dir_name)
    ensure_dir(batch_output_dir)

    # 获取知识库ID
    kb_id = args.kb
    if not kb_id:
        kb_id = config_manager.get('knowledge_base.default_id')

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

        try:
            # 使用主程序的 logger 作为回调，保持日志一致性
            plugin_result = plugin_manager.run_analysis(
                plugin_ids, unit_path,
                log_callback=logger.info
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
                    for section in sections:
                        if section.get('type') == 'stats' and section.get('items'):
                            for item in section.get('items', []):
                                severity = item.get('severity', '')
                                value = item.get('value', 0)
                                if isinstance(value, (int, float)):
                                    if severity == 'error':
                                        unit_errors += int(value)
                                    elif severity == 'warning':
                                        unit_warnings += int(value)

            total_errors += unit_errors
            total_warnings += unit_warnings

            # 获取该单元内的日志文件列表（用于AI分析）
            log_files_in_unit = find_log_files_in_directory(unit_path) if os.path.isdir(unit_path) else [unit_path]

            # AI分析（如果启用）
            ai_result = None
            if args.enable_ai:
                print(f"  AI分析中...")
                # 检查AI配置
                api_config = config_manager.get('api', {})
                if not api_config.get('base_url') or not api_config.get('api_key'):
                    print(f"  告: AI配置不完整，跳过AI分析")
                else:
                    try:
                        coordinator = AgentCoordinator(
                            config_manager=config_manager,
                            kb_manager=kb_manager
                        )
                        html_result = coordinator.run_analysis(
                            plugin_result=plugin_result,
                            log_files=log_files_in_unit,
                            kb_id=kb_id,
                            actual_log_paths=log_files_in_unit
                        )
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
        'directory': args.dir,
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

    def clear_dir_contents(path):
        """清空目录内容但保留目录本身"""
        if not os.path.exists(path):
            return
        for entry in os.scandir(path):
            try:
                if entry.is_dir():
                    shutil.rmtree(entry.path)
                else:
                    os.remove(entry.path)
            except OSError:
                pass

    temp_dir = get_data_dir('temp')
    plugin_output_dir = get_data_dir('plugin_output')

    if args.cache_action == 'stats':
        temp_size = get_dir_size(temp_dir)
        output_size = get_dir_size(plugin_output_dir)
        total_size = temp_size + output_size

        print("缓存统计:")
        print(f"  临时文件: {format_size(temp_size)} ({temp_dir})")
        print(f"  分析结果: {format_size(output_size)} ({plugin_output_dir})")
        print(f"  总计: {format_size(total_size)}")
        return 0

    elif args.cache_action == 'clear-results':
        clear_dir_contents(plugin_output_dir)
        print("分析结果已清理")
        return 0

    elif args.cache_action == 'clear-temp':
        clear_dir_contents(temp_dir)
        print("临时文件已清理")
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
    analyze_parser.add_argument('--prompt', '-p', help='自定义提示词或提示词文件路径（AI智能选择必需）')
    analyze_parser.add_argument('--no-ai', action='store_true', help='仅运行插件分析，跳过AI分析')
    analyze_parser.add_argument('--ai-select', action='store_true', help='启用AI智能选择插件和文件')

    # analyze-batch 命令
    analyze_batch_parser = subparsers.add_parser('analyze-batch', help='批量分析日志目录')
    analyze_batch_parser.add_argument('--dir', '-d', required=True, help='日志目录路径')
    analyze_batch_parser.add_argument('--plugins', help='指定使用的插件ID，多个插件用逗号分隔')
    analyze_batch_parser.add_argument('--kb', '-k', help='知识库ID')
    analyze_batch_parser.add_argument('--enable-ai', action='store_true', help='启用AI分析')

    # plugin 命令
    plugin_parser = subparsers.add_parser('plugin', help='插件管理')
    plugin_subparsers = plugin_parser.add_subparsers(dest='plugin_action', help='插件操作')

    # plugin list
    plugin_list = plugin_subparsers.add_parser('list', help='列出可用插件（显示分类信息）')

    # plugin categories
    plugin_categories = plugin_subparsers.add_parser('categories', help='按分类查看插件列表')

    # plugin select
    plugin_select = plugin_subparsers.add_parser('select', help='选择插件（必须指定类别）')
    plugin_select.add_argument('category', nargs='?', help='插件类别名（CloudBMC/iBMC/LxBMC），不指定则显示当前选择')
    plugin_select.add_argument('plugins', nargs='?', help='插件ID列表（逗号分隔），不指定则选择该类别全部插件')

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

    # kb reindex
    kb_reindex = kb_subparsers.add_parser('reindex', help='重建知识库索引')
    kb_reindex.add_argument('--kb-id', required=True, help='知识库ID')

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

    # log-rules 命令
    log_rules_parser = subparsers.add_parser('log-rules', help='日志元数据规则管理')
    log_rules_subparsers = log_rules_parser.add_subparsers(dest='rules_action', help='规则操作')

    # log-rules list
    log_rules_list = log_rules_subparsers.add_parser('list', help='列出所有规则集')

    # log-rules create
    log_rules_create = log_rules_subparsers.add_parser('create', help='创建规则集')
    log_rules_create.add_argument('--name', '-n', required=True, help='规则集名称')
    log_rules_create.add_argument('--description', '-d', help='规则集描述')

    # log-rules show
    log_rules_show = log_rules_subparsers.add_parser('show', help='查看规则集详情')
    log_rules_show.add_argument('--rules-id', required=True, help='规则集ID')

    # log-rules delete
    log_rules_delete = log_rules_subparsers.add_parser('delete', help='删除规则集')
    log_rules_delete.add_argument('--rules-id', required=True, help='规则集ID')

    # log-rules add
    log_rules_add = log_rules_subparsers.add_parser('add', help='添加规则到规则集')
    log_rules_add.add_argument('--rules-id', required=True, help='规则集ID')
    log_rules_add.add_argument('--file-path', '-f', required=True, help='文件路径匹配规则')
    log_rules_add.add_argument('--description', '-d', help='规则描述')
    log_rules_add.add_argument('--keywords', '-k', help='关键词（逗号分隔）')
    log_rules_add.add_argument('--plugins', '-p', help='建议插件（逗号分隔）')

    # log-rules remove
    log_rules_remove = log_rules_subparsers.add_parser('remove', help='从规则集移除规则')
    log_rules_remove.add_argument('--rules-id', required=True, help='规则集ID')
    log_rules_remove.add_argument('--rule-id', required=True, help='规则ID')

    # cache 命令
    cache_parser = subparsers.add_parser('cache', help='缓存管理')
    cache_subparsers = cache_parser.add_subparsers(dest='cache_action', help='缓存操作')

    # cache stats
    cache_stats = cache_subparsers.add_parser('stats', help='查看缓存大小')

    # cache clear-results
    cache_clear_results = cache_subparsers.add_parser('clear-results', help='清理分析结果')

    # cache clear-temp
    cache_clear_temp = cache_subparsers.add_parser('clear-temp', help='清理临时文件')

    args = parser.parse_args()

    if args.command == 'analyze':
        return cmd_analyze(args)
    elif args.command == 'analyze-batch':
        return cmd_analyze_batch(args)
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
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())