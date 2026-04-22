#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包脚本 - 生成可分发的AI日志分析器

用法:
    python scripts/build_package.py

打包结果位于: dist/AI_Log_Analyzer/
"""

import os
import shutil
import subprocess
import sys


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir = os.path.join(project_root, 'dist', 'AI_Log_Analyzer')
    exe_path = os.path.join(project_root, 'dist', 'ai_log_analyzer.exe')

    print("=" * 50)
    print("AI日志分析器打包脚本")
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

    # 2. 运行PyInstaller
    print("\n[1/8] 运行PyInstaller...")
    spec_file = os.path.join(project_root, 'scripts', 'ai_log_analyzer.spec')
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
    print("\n[2/8] 移动exe到最终目录...")
    os.makedirs(dist_dir, exist_ok=True)
    final_exe_path = os.path.join(dist_dir, 'ai_log_analyzer.exe')
    if os.path.exists(exe_path):
        shutil.move(exe_path, final_exe_path)
        print(f"  移动: ai_log_analyzer.exe -> {final_exe_path}")
    else:
        print(f"  错误: 找不到exe文件 {exe_path}")
        sys.exit(1)

    # 3. 复制用户可修改的配置文件到dist目录
    print("\n[3/8] 复制配置文件...")
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
    print("\n[4/8] 创建数据目录...")
    data_dirs = ['uploads', 'temp', 'analysis_output']
    for d in data_dirs:
        data_path = os.path.join(dist_dir, 'data', d)
        os.makedirs(data_path, exist_ok=True)
        print(f"  创建: data/{d}")

    # 5. 创建空的document和custom_plugins目录
    print("\n[5/8] 创建其他目录...")
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

    # 6. 复制bat脚本（使用中文文件名）
    print("\n[6/8] 复制右键菜单脚本...")
    scripts_dir = os.path.join(project_root, 'scripts')

    register_bat = os.path.join(scripts_dir, '注册右键菜单.bat')
    if os.path.exists(register_bat):
        shutil.copy2(register_bat, dist_dir)
        print("  复制: 注册右键菜单.bat")
    else:
        print("  警告: 找不到 注册右键菜单.bat")

    unregister_bat = os.path.join(scripts_dir, '取消右键菜单.bat')
    if os.path.exists(unregister_bat):
        shutil.copy2(unregister_bat, dist_dir)
        print("  复制: 取消右键菜单.bat")
    else:
        print("  警告: 找不到 取消右键菜单.bat")

    # 7. 创建使用说明
    print("\n[7/8] 创建使用说明...")
    create_usage_file(dist_dir)
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
    print("\n使用方法:")
    print("  1. 双击 ai_log_analyzer.exe 启动Web界面")
    print("  2. 运行 注册右键菜单.bat 注册右键菜单")
    print("  3. 配置API后即可使用AI分析功能")
    print("=" * 50)


def create_usage_file(dist_dir):
    content = """AI日志分析器 使用说明

================================================================================
一、启动方式
================================================================================

1. Web界面启动:
   - 双击 ai_log_analyzer.exe 启动Web界面（自动打开浏览器）
   - 命令行启动指定端口: ai_log_analyzer.exe web --port 9000
   - 命令行启动指定主机: ai_log_analyzer.exe web --host 0.0.0.0 --port 80
   - 不自动打开浏览器: ai_log_analyzer.exe web --no-browser

2. CLI命令行分析:
   ai_log_analyzer.exe analyze <日志路径>
   ai_log_analyzer.exe analyze <日志路径> --ai  # 启用AI分析

3. 配置管理:
   ai_log_analyzer.exe config set api.base_url <API地址>
   ai_log_analyzer.exe config set api.api_key <API密钥>
   ai_log_analyzer.exe config set api.model <模型名称>

================================================================================
二、首次使用配置
================================================================================

首次使用需要配置AI API，有两种方式：

方式1：命令行配置
   ai_log_analyzer.exe config set api.base_url https://api.example.com/v1
   ai_log_analyzer.exe config set api.api_key your-api-key
   ai_log_analyzer.exe config set api.model gpt-4

方式2：直接编辑配置文件
   打开 config/ai_config.json 文件，修改 api 部分的配置

================================================================================
三、右键菜单集成
================================================================================

1. 注册右键菜单:
   运行 "注册右键菜单.bat"（需要管理员权限）
   注册后可右键点击以下文件类型快速分析:
   - 压缩包: .zip, .tar.gz, .tgz, .tar
   - 日志文件: .log, .txt
   - 文件夹

2. 取消右键菜单:
   运行 "取消右键菜单.bat"

================================================================================
四、自定义插件
================================================================================

将自定义插件放入 custom_plugins/ 目录
每个插件需要包含:
- plugin.py: 插件实现代码
- plugin.json: 插件元数据

示例 plugin.json:
{
    "id": "my_plugin",
    "name": "My Plugin",
    "version": "1.0.0",
    "description": "插件描述",
    "plugin_type": "CloudBMC"
}

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


if __name__ == '__main__':
    main()