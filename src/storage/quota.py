"""
存储配额管理模块。
"""

import os
import shutil
from src.utils.file_utils import get_user_data_dir, get_data_dir


def format_size(size_bytes: int) -> str:
    """格式化大小显示。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_dir_size(path: str) -> int:
    """计算目录大小（字节）。"""
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


def check_disk_space(min_gb: float = 10.0) -> tuple[bool, str]:
    """
    检查服务器磁盘剩余空间。

    Args:
        min_gb: 最低要求的剩余空间（GB），默认10GB

    Returns:
        tuple: (是否充足, 错误消息或剩余空间信息)
    """
    data_dir = get_data_dir()
    disk_usage = shutil.disk_usage(data_dir)
    free_gb = disk_usage.free / (1024 * 1024 * 1024)

    if free_gb < min_gb:
        return False, f"服务器存储空间不足，剩余 {free_gb:.2f}GB，需要至少 {min_gb}GB"
    return True, f"剩余空间 {free_gb:.2f}GB"


class StorageQuota:
    """存储配额管理类。"""

    def __init__(self, user_id: str, quota_mb: int = 300):
        """
        初始化配额管理。

        Args:
            user_id: 用户ID
            quota_mb: 配额大小（MB），默认300MB
        """
        self.user_id = user_id
        self.quota = quota_mb * 1024 * 1024

    def get_usage(self) -> int:
        """计算用户已用空间（字节）。"""
        user_dir = get_user_data_dir(self.user_id)
        return get_dir_size(user_dir)

    def check_upload(self, file_size: int) -> tuple:
        """
        检查上传是否超配额。

        Args:
            file_size: 待上传文件大小

        Returns:
            tuple: (是否允许, 错误消息)
        """
        current = self.get_usage()
        if current + file_size > self.quota:
            remaining = self.quota - current
            return False, f"空间不足，剩余 {format_size(remaining)}，需要 {format_size(file_size)}"
        return True, ""

    def get_status(self) -> dict:
        """获取配额状态。"""
        used = self.get_usage()
        quota = self.quota
        percent = round(used / quota * 100, 1) if quota > 0 else 0
        return {
            'used_bytes': used,
            'used_formatted': format_size(used),
            'quota_bytes': quota,
            'quota_formatted': format_size(quota),
            'percent': percent,
            'remaining': format_size(quota - used)
        }