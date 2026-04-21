# -*- mode: python ; coding: utf-8 -*-
"""
AI日志分析器 PyInstaller 配置文件
"""

import sys
import os

block_cipher = None

# 获取项目根目录（spec文件在scripts目录，需要往上一层）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

a = Analysis(
    [os.path.join(project_root, 'entry_point.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        # 配置文件（打包到exe内部作为默认值）
        (os.path.join(project_root, 'config/*.json'), 'config'),
        (os.path.join(project_root, 'config/*.txt'), 'config'),
        # Web模板和静态文件
        (os.path.join(project_root, 'src/web/templates'), 'src/web/templates'),
        (os.path.join(project_root, 'src/web/static'), 'src/web/static'),
        # 源代码模块
        (os.path.join(project_root, 'src'), 'src'),
        # 插件系统（只打包必要的文件）
        (os.path.join(project_root, 'plugins/__init__.py'), 'plugins'),
        (os.path.join(project_root, 'plugins/base.py'), 'plugins'),
        (os.path.join(project_root, 'plugins/manager.py'), 'plugins'),
        (os.path.join(project_root, 'plugins/builtin'), 'plugins/builtin'),
        (os.path.join(project_root, 'plugins/renderer'), 'plugins/renderer'),
        (os.path.join(project_root, 'plugins/README.md'), 'plugins'),
        # 自定义插件目录（空目录占位）
        (os.path.join(project_root, 'custom_plugins/__init__.py'), 'custom_plugins'),
    ],
    hiddenimports=[
        'jieba',
        'jieba.analyse',
        'rank_bm25',
        'faiss',
        'flask',
        'flask.json',
        'werkzeug',
        'werkzeug.serving',
        'pypdf',
        'docx',
        'docx.shared',
        'docx.document',
        'requests',
        'src',
        'src.config_manager',
        'src.config_manager.manager',
        'src.knowledge_base',
        'src.knowledge_base.manager',
        'src.knowledge_base.bm25_retriever',
        'src.knowledge_base.vector_retriever',
        'src.knowledge_base.hybrid_retriever',
        'src.knowledge_base.document_loader',
        'src.knowledge_base.embedding_client',
        'src.ai_analyzer',
        'src.ai_analyzer.analyzer',
        'src.ai_analyzer.client',
        'src.ai_analyzer.agent_coordinator',
        'src.ai_analyzer.sage_agent',
        'src.ai_analyzer.scout_agent',
        'src.ai_analyzer.selection_agent',
        'src.log_metadata',
        'src.log_metadata.manager',
        'src.plugin_selection',
        'src.plugin_selection.manager',
        'src.utils',
        'src.utils.file_utils',
        'src.utils.cache',
        'src.utils.logger',
        'src.web',
        'src.web.routes',
        'src.web.routes.main',
        'src.web.routes.kb_api',
        'src.web.routes.analyze_api',
        'src.web.routes.history_api',
        'src.web.routes.log_metadata_api',
        'src.web.routes.cache_api',
        'plugins',
        'plugins.manager',
        'plugins.base',
        'plugins.renderer',
        'plugins.renderer.html_renderer',
    ],
    hookspath=[os.path.join(project_root, 'hooks')],
    hooksconfig={},
    runtime_hooks=[os.path.join(project_root, 'hooks/runtime_hook.py')],
    # 排除不必要的模块以减小体积（注意：不要排除标准库核心模块）
    excludes=[
        'pytest',
        'unittest',
        'tkinter',
        '_tkinter',
        'IPython',
        'jupyter',
        'notebook',
        'matplotlib',
        'numpy.f2py',
        'scipy',
        'scipy.linalg',
        'scipy.sparse',
        'scipy.special',
        'scipy.stats',
        'PIL',
        'cv2',
        'pillow',
        'sphinx',
        'docutils',
        'pydoc',
        'doctest',
        'distutils',
        'distutils.command',
        'setuptools',
        'pkg_resources',
        # 注意：以下模块不应排除，它们是标准库核心组件
        # 'multiprocessing.pool',
        # 'concurrent.futures.thread',
        'email.mime',
        'html.parser',
        'xml.dom',
        'xml.etree',
        'pytz',
        'dateutil',
        'pyarrow',
        'pandas',
        'sympy',
        'nbconvert',
        'nbformat',
        'jupyter_client',
        'jupyter_core',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ai_log_analyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标: icon='icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=False,
    name='AI_Log_Analyzer',
)