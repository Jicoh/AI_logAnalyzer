#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包脚本 - 生成可分发的AI日志分析器

用法:
    python scripts/build_package.py           # 打包全功能二进制 ai_log_analyzer
    python scripts/build_package.py serve     # 打包常驻服务二进制 log_analyze_serve

打包结果位于: dist/AI_Log_Analyzer/ 或 dist/AI_Log_Analyzer_Serve/
"""

import os
import shutil
import subprocess
import sys
import json
import re
import platform
import argparse

# 根据操作系统确定可执行文件后缀
EXE_SUFFIX = '.exe' if platform.system() == 'Windows' else ''


def load_plugin_dependencies(project_root):
    """读取插件依赖配置，从 requirements.txt 解析包名"""
    req_file = os.path.join(project_root, 'plugins', 'requirements.txt')
    dependencies = []
    if os.path.exists(req_file):
        with open(req_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                # 提取包名，去掉版本约束 (如 pandas>=2.0.0 -> pandas)
                package = re.split(r'[<>=!~\s]', line)[0]
                if package:
                    dependencies.append(package)
    return dependencies


def update_spec_file(spec_file, plugin_deps):
    """动态更新 .spec 文件，添加插件依赖到 hiddenimports，从 excludes 移除"""
    with open(spec_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 添加插件依赖到 hiddenimports
    hiddenimports_pattern = r'hiddenimports=\[(.*?)\]'
    match = re.search(hiddenimports_pattern, content, re.DOTALL)
    if match:
        existing_imports = match.group(1)
        # 添加新依赖（避免重复）
        new_imports = existing_imports.rstrip()
        for dep in plugin_deps:
            if dep not in existing_imports:
                # 检查最后一项是否已有逗号
                if new_imports.rstrip().endswith(','):
                    new_imports += f"\n        '{dep}'"
                else:
                    new_imports += f",\n        '{dep}'"
        content = content.replace(match.group(0), f"hiddenimports=[{new_imports}]")

    # 从 excludes 移除插件依赖
    excludes_pattern = r'excludes=\[(.*?)\]'
    match = re.search(excludes_pattern, content, re.DOTALL)
    if match:
        existing_excludes = match.group(1)
        # 移除插件依赖
        new_excludes = existing_excludes
        for dep in plugin_deps:
            # 移除单行模式
            new_excludes = re.sub(rf"^\s*'{dep}',?\s*\n", '', new_excludes, flags=re.MULTILINE)
        content = content.replace(match.group(0), f"excludes=[{new_excludes}]")

    with open(spec_file, 'w', encoding='utf-8') as f:
        f.write(content)


# ---- 构建配置 ----

BUILD_CONFIGS = {
    None: {
        'name': '全功能版',
        'spec_file': 'ai_log_analyzer.spec',
        'exe_name': 'ai_log_analyzer',
        'dist_dir': 'AI_Log_Analyzer',
        'data_dirs': ['uploads', 'temp', 'analysis_output', 'users'],
        'create_document_dir': True,
        'usage_func': 'create_usage_file',
    },
    'serve': {
        'name': '常驻服务版',
        'spec_file': 'ai_log_analyzer_serve.spec',
        'exe_name': 'log_analyze_serve',
        'dist_dir': 'AI_Log_Analyzer_Serve',
        'data_dirs': ['temp'],
        'create_document_dir': True,
        'usage_func': 'create_serve_usage_file',
    },
}


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='AI日志分析器打包脚本')
    parser.add_argument('mode', nargs='?', default=None,
                        choices=['serve'],
                        help='打包模式: 不指定=全功能版, serve=常驻服务版')
    args = parser.parse_args()

    config = BUILD_CONFIGS[args.mode]

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir = os.path.join(project_root, 'dist', config['dist_dir'])
    exe_path = os.path.join(project_root, 'dist', f"{config['exe_name']}{EXE_SUFFIX}")

    print("=" * 50)
    print(f"AI日志分析器打包脚本 - {config['name']}")
    print("=" * 50)

    # 1. 检查PyInstaller是否安装
    try:
        import PyInstaller
        print("PyInstaller 已安装")
    except ImportError:
        print("安装 PyInstaller...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)

    # 清理PyInstaller缓存
    print("\n[0/8] 清理PyInstaller缓存...")
    cache_dir = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'pyinstaller')
    if cache_dir and os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
        print(f"  删除: {cache_dir}")

    spec_file = os.path.join(project_root, 'scripts', config['spec_file'])

    # 读取插件依赖并更新 .spec 文件
    print("\n[1/8] 读取插件依赖配置...")
    plugin_deps = load_plugin_dependencies(project_root)
    if plugin_deps:
        print(f"  发现依赖: {plugin_deps}")
        print("  更新 .spec 文件...")
        update_spec_file(spec_file, plugin_deps)
        print("  已添加到 hiddenimports 并从 excludes 移除")
    else:
        print("  无额外插件依赖")

    # 2. 运行PyInstaller
    print("\n[2/8] 运行PyInstaller...")
    if not os.path.exists(spec_file):
        print(f"错误: 找不到spec文件 {spec_file}")
        sys.exit(1)

    result = subprocess.run([
        sys.executable, '-m', 'PyInstaller',
        spec_file,
        '--clean',
        '--noconfirm'
    ], cwd=project_root)

    if result.returncode != 0:
        print("PyInstaller 打包失败")
        sys.exit(1)

    print("PyInstaller 打包完成")

    # 移动exe到最终目录
    print("\n[3/8] 移动exe到最终目录...")
    os.makedirs(dist_dir, exist_ok=True)
    final_exe_path = os.path.join(dist_dir, f"{config['exe_name']}{EXE_SUFFIX}")
    if os.path.exists(exe_path):
        shutil.move(exe_path, final_exe_path)
        print(f"  移动: {config['exe_name']}{EXE_SUFFIX} -> {final_exe_path}")
    else:
        print(f"  错误: 找不到exe文件 {exe_path}")
        sys.exit(1)

    # 3. 复制用户可修改的配置文件到dist目录
    print("\n[4/8] 复制配置文件...")
    config_src = os.path.join(project_root, 'config')
    config_dst = os.path.join(dist_dir, 'config')
    os.makedirs(config_dst, exist_ok=True)
    for f in os.listdir(config_src):
        src_file = os.path.join(config_src, f)
        dst_file = os.path.join(config_dst, f)
        if os.path.isfile(src_file):
            shutil.copy2(src_file, dst_file)
            print(f"  复制: {f}")

    # 4. 创建空的数据目录
    print("\n[5/8] 创建数据目录...")
    for d in config['data_dirs']:
        data_path = os.path.join(dist_dir, 'data', d)
        os.makedirs(data_path, exist_ok=True)
        print(f"  创建: data/{d}")

    # 5. 创建空的document和custom_plugins目录
    print("\n[6/8] 创建其他目录...")
    if config['create_document_dir']:
        os.makedirs(os.path.join(dist_dir, 'document'), exist_ok=True)
        print("  创建: document/")

    custom_plugins_dir = os.path.join(dist_dir, 'custom_plugins')
    os.makedirs(custom_plugins_dir, exist_ok=True)
    # 创建__init__.py
    init_file = os.path.join(custom_plugins_dir, '__init__.py')
    if not os.path.exists(init_file):
        with open(init_file, 'w', encoding='utf-8') as f:
            f.write('')
    print("  创建: custom_plugins/")

    # 7. 创建使用说明
    print("\n[7/8] 创建使用说明...")
    if config['usage_func'] == 'create_serve_usage_file':
        create_serve_usage_file(dist_dir, EXE_SUFFIX)
    else:
        create_usage_file(dist_dir, EXE_SUFFIX)
    print("  创建: 使用说明.txt")

    # 8. 清理打包临时文件
    print("\n[8/8] 清理临时文件...")
    build_dir = os.path.join(project_root, 'build')
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
        print("  删除: build/")

    # 删除 __pycache__ 目录
    for root, dirs, files in os.walk(project_root):
        for d in dirs:
            if d == '__pycache__':
                pycache_path = os.path.join(root, d)
                shutil.rmtree(pycache_path)
                print(f"  删除: {pycache_path}")

    print("\n" + "=" * 50)
    print("打包完成!")
    print("=" * 50)
    print(f"输出目录: {dist_dir}")
    print(f"可执行文件: {config['exe_name']}{EXE_SUFFIX}")
    print("\n使用方法:")
    if args.mode == 'serve':
        print(f"  1. 运行 ./{config['exe_name']}{EXE_SUFFIX} 启动分析服务")
        print("  2. 配置API后即可使用AI分析功能")
    else:
        print(f"  1. 运行 ./{config['exe_name']}{EXE_SUFFIX} 启动Web界面")
        print("  2. 配置API后即可使用AI分析功能")
    print("=" * 50)


def create_usage_file(dist_dir, exe_suffix):
    exe_name = f'ai_log_analyzer{exe_suffix}'
    content = f"""AI日志分析器 使用说明

================================================================================
一、启动方式
================================================================================

1. Web界面启动:
   - 双击 {exe_name} 启动Web界面（自动打开浏览器）
   - 命令行启动指定端口: {exe_name} web --port 18888
   - 命令行启动指定主机: {exe_name} web --host 0.0.0.0 --port 80
   - 不自动打开浏览器: {exe_name} web --no-browser

2. CLI命令行分析:
   {exe_name} analyze <日志路径>
   {exe_name} analyze <日志路径> --ai  # 启用AI分析

3. 配置管理:
   {exe_name} config set api.base_url <API地址>
   {exe_name} config set api.api_key <API密钥>
   {exe_name} config set api.model <模型名称>

================================================================================
二、用户登录
================================================================================

首次启动Web界面时，系统会自动创建默认管理员账号：
   - 工号: Administrator
   - 密码: Admin@9000

【重要】请在首次登录后修改管理员密码！

用户功能：
   - 普通用户: 日志分析、知识库管理、历史记录查看
   - 管理员: 用户管理、系统配置、全局统计

================================================================================
三、首次使用配置
================================================================================

首次使用需要配置AI API，有两种方式：

方式1：命令行配置
   {exe_name} config set api.base_url https://api.example.com/v1
   {exe_name} config set api.api_key your-api-key
   {exe_name} config set api.model gpt-4

方式2：直接编辑配置文件
   打开 config/ai_config.json 文件，修改 api 部分的配置

================================================================================
四、自定义插件
================================================================================

将自定义插件放入 custom_plugins/ 目录
每个插件需要包含:
- plugin.py: 插件实现代码
- plugin.json: 插件元数据

示例 plugin.json:
{{
    "id": "my_plugin",
    "name": "My Plugin",
    "version": "1.0.0",
    "description": "插件描述",
    "plugin_type": "CloudBMC"
}}

【重要】插件依赖声明:
如果插件需要额外的Python模块，需要在打包前声明依赖：
1. 编辑 plugins/requirements.txt 文件
2. 添加需要的模块，格式如: pandas>=2.0.0
3. 运行打包脚本，依赖模块会被自动包含在 exe 中

================================================================================
五、知识库
================================================================================

将参考文档放入 document/ 目录
通过Web界面创建和管理知识库

================================================================================
六、支持的日志格式
================================================================================

- 压缩包: .zip, .tar.gz, .tgz, .tar
- 日志文件: .log, .txt
- JSON日志集: .json (包含日志文件列表)

================================================================================
如有问题，请查看项目文档或联系开发者。
"""
    usage_file = os.path.join(dist_dir, '使用说明.txt')
    with open(usage_file, 'w', encoding='utf-8') as f:
        f.write(content)


def create_serve_usage_file(dist_dir, exe_suffix):
    exe_name = f'log_analyze_serve{exe_suffix}'
    content = f"""AI日志分析器 - 常驻分析服务 使用说明

================================================================================
一、启动方式
================================================================================

1. 默认启动（TCP模式）:
   {exe_name}
   {exe_name} serve

2. 自定义TCP端口:
   {exe_name} serve --port 9000

3. 自定义绑定地址:
   {exe_name} serve --host 0.0.0.0 --port 19888

4. Unix socket模式（仅Linux）:
   {exe_name} serve --socket /tmp/ai_log_analyzer.sock

================================================================================
二、客户端调用
================================================================================

使用 src/serve/client.py 中的 AnalyzeClient 连接服务:

   from src.serve.client import AnalyzeClient

   # TCP 连接
   client = AnalyzeClient(port=19888)

   # Unix socket 连接
   client = AnalyzeClient(socket_path='/tmp/ai_log_analyzer.sock')

   # 心跳检测
   client.ping()

   # 执行分析
   result = client.analyze(
       plugin_id='CloudBMC_00001',
       log_content={{'system.log': ['日志行1', '日志行2']}},
       task_name='任务名称',
       bmc_ip='192.168.1.1',
       date='2024-01-01'
   )

客户端代码无第三方依赖，可直接拷贝使用。

================================================================================
三、首次使用配置
================================================================================

首次使用需要配置AI API，编辑配置文件:
   打开 config/system_config.json 文件，修改 api 部分的配置

================================================================================
四、自定义插件
================================================================================

将自定义插件放入 custom_plugins/ 目录
每个插件需要包含:
- plugin.py: 插件实现代码
- plugin.json: 插件元数据

================================================================================
五、注意事项
================================================================================

- 本程序仅支持 serve 命令（常驻分析服务），不支持 Web 界面和 CLI 分析
- Linux 优先使用 Unix socket，Windows 使用 TCP 端口
- 默认锁文件位于 data/.serve.lock，防止多实例运行
- 支持信号退出: Ctrl+C 或 kill 命令

================================================================================
如有问题，请查看项目文档或联系开发者。
"""
    usage_file = os.path.join(dist_dir, '使用说明.txt')
    with open(usage_file, 'w', encoding='utf-8') as f:
        f.write(content)


if __name__ == '__main__':
    main()
