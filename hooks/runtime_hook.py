"""
PyInstaller 运行时钩子
在程序启动时执行，设置正确的工作目录和路径
"""

import sys
import os

# 设置运行时路径
if getattr(sys, 'frozen', False):
    # exe运行时，将工作目录设置为exe所在目录
    exe_dir = os.path.dirname(sys.executable)
    os.chdir(exe_dir)

    # 添加exe所在目录到sys.path（用于加载外部配置和插件）
    if exe_dir not in sys.path:
        sys.path.insert(0, exe_dir)

    # 添加内部资源路径（sys._MEIPASS）到sys.path
    meipass = sys._MEIPASS
    if meipass not in sys.path:
        sys.path.insert(0, meipass)