"""
设置 API 路由
处理用户设置的读取、更新和日志查看器测试
"""

import os
import subprocess
from flask import Blueprint, request, jsonify

from src.settings_manager.manager import SettingsManager
from src.utils.file_utils import get_data_dir
from src.utils import get_logger

logger = get_logger('settings_api')

settings_bp = Blueprint('settings_api', __name__)

# 全局实例
settings_manager = None


def get_settings_manager():
    """获取或创建 SettingsManager 实例。"""
    global settings_manager
    if settings_manager is None:
        settings_manager = SettingsManager()
    return settings_manager


def resolve_shortcut(lnk_path: str) -> str:
    """解析 Windows 快捷方式(.lnk)文件，获取实际目标路径。"""
    try:
        result = subprocess.run(
            ['powershell', '-command',
             f"(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_path}').TargetPath"],
            capture_output=True, text=True, timeout=5
        )
        target_path = result.stdout.strip()
        if target_path and os.path.exists(target_path):
            return target_path
    except Exception as e:
        logger.warning(f"解析快捷方式失败: {str(e)}")
    return lnk_path


def normalize_path(path: str) -> str:
    """规范化路径：去除双引号、解析快捷方式。"""
    path = path.strip()
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    if path.lower().endswith('.lnk'):
        resolved = resolve_shortcut(path)
        if resolved != path:
            return resolved
    return path


def detect_tool_type(exe_path: str) -> str:
    """根据路径自动检测工具类型。"""
    lower_path = exe_path.lower()
    if 'code' in lower_path and ('vscode' in lower_path or 'visual' in lower_path):
        return 'vscode'
    if 'notepad++' in lower_path or 'notepadplus' in lower_path:
        return 'notepad++'
    return 'custom'


@settings_bp.route('/api/settings', methods=['GET'])
def get_settings():
    """获取通用设置。"""
    try:
        manager = get_settings_manager()
        manager.reload()
        settings = manager.get_all()
        return jsonify({'success': True, 'data': settings})
    except Exception as e:
        logger.error(f"获取设置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/settings', methods=['POST'])
def update_settings():
    """更新通用设置。"""
    try:
        data = request.get_json()
        manager = get_settings_manager()

        if 'log_viewer' in data:
            viewer_config = data['log_viewer']
            if 'enabled' in viewer_config:
                manager.set('log_viewer.enabled', viewer_config['enabled'])
            if 'exe_path' in viewer_config:
                manager.set('log_viewer.exe_path', viewer_config['exe_path'])

        manager.save()
        return jsonify({'success': True, 'message': '设置已更新'})
    except Exception as e:
        logger.error(f"更新设置失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/log-viewer/test', methods=['POST'])
def test_log_viewer():
    """测试日志查看器是否能正常打开。"""
    try:
        data = request.get_json()
        exe_path = data.get('exe_path', '')

        if not exe_path:
            return jsonify({'success': False, 'error': '请先设置查看工具路径'})

        exe_path = normalize_path(exe_path)

        if not os.path.exists(exe_path):
            return jsonify({'success': False, 'error': f'路径不存在: {exe_path}'})

        tool_type = detect_tool_type(exe_path)

        temp_dir = get_data_dir('temp')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        try:
            if tool_type == 'notepad++':
                subprocess.Popen([exe_path, '-multiInst', '-nosession', '-openFoldersAsWorkspace', temp_dir], shell=False)
            else:
                subprocess.Popen([exe_path, temp_dir], shell=False)
            return jsonify({'success': True, 'message': f'已使用 {tool_type} 打开 temp 目录'})
        except Exception as e:
            return jsonify({'success': False, 'error': f'打开失败: {str(e)}'})

    except Exception as e:
        logger.error(f"测试日志查看器失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500