"""
文件工具模块
提供文件读写、JSON处理、压缩文件处理等通用功能
"""

import json
import os
import tarfile
import zipfile
import shutil
from datetime import datetime


def read_file(file_path, encoding='utf-8'):
    """读取文本文件"""
    with open(file_path, 'r', encoding=encoding) as f:
        return f.read()


def write_file(file_path, content, encoding='utf-8'):
    """写入文本文件"""
    ensure_dir(os.path.dirname(file_path))
    with open(file_path, 'w', encoding=encoding) as f:
        f.write(content)


def read_json(file_path):
    """读取JSON文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(file_path, data, indent=4):
    """写入JSON文件"""
    ensure_dir(os.path.dirname(file_path))
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def ensure_dir(dir_path):
    """确保目录存在，不存在则创建"""
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path)


def get_project_root() -> str:
    """获取项目根目录"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(current_dir))


def get_data_dir(subdir: str = '') -> str:
    """
    获取data目录或子目录路径

    Args:
        subdir: 子目录名，如 'temp', 'plugin_output', 'ai_output'

    Returns:
        str: 目录路径
    """
    root = get_project_root()
    data_dir = os.path.join(root, 'data')
    if subdir:
        return os.path.join(data_dir, subdir)
    return data_dir


def get_filename(file_path):
    """获取文件名（不含扩展名）"""
    basename = os.path.basename(file_path)
    name, _ = os.path.splitext(basename)
    return name


def get_archive_type(file_path):
    """
    获取压缩文件类型

    Returns:
        str: 'tar.gz', 'tar', 'zip' 或 None
    """
    lower_path = file_path.lower()
    if lower_path.endswith('.tar.gz') or lower_path.endswith('.tgz'):
        return 'tar.gz'
    elif lower_path.endswith('.tar'):
        return 'tar'
    elif lower_path.endswith('.zip'):
        return 'zip'
    return None


def is_archive_file(file_path):
    """检查是否为压缩文件"""
    return get_archive_type(file_path) is not None


def is_log_file(file_path):
    """检查是否为日志文件（txt或log）"""
    lower_path = file_path.lower()
    return lower_path.endswith('.txt') or lower_path.endswith('.log')


def is_valid_log_file(file_path):
    """检查是否为有效的日志文件（txt或log），排除压缩文件"""
    lower_path = file_path.lower()
    if is_archive_file(file_path):
        return False
    return lower_path.endswith('.txt') or lower_path.endswith('.log')


def get_files_in_directory(dir_path):
    """获取目录下一级文件列表（仅一级目录，不递归）"""
    if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
        return []
    files = []
    for item in os.listdir(dir_path):
        item_path = os.path.join(dir_path, item)
        if os.path.isfile(item_path):
            files.append(item_path)
    return files


def find_log_files_in_directory(dir_path):
    """
    递归查找目录中的所有日志文件。

    Args:
        dir_path: 目录路径

    Returns:
        list: 日志文件路径列表
    """
    if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
        return []
    log_files = []
    for root, dirs, files in os.walk(dir_path):
        for f in files:
            if f.endswith('.log') or f.endswith('.txt'):
                log_files.append(os.path.join(root, f))
    return log_files


def extract_archive(archive_path, extract_to):
    """
    解压压缩文件

    Args:
        archive_path: 压缩文件路径
        extract_to: 解压目标目录

    Returns:
        list: 解压后的文件列表
    """
    archive_type = get_archive_type(archive_path)
    ensure_dir(extract_to)

    extracted_files = []

    if archive_type == 'tar.gz' or archive_type == 'tar':
        with tarfile.open(archive_path, 'r:*') as tar:
            members = tar.getmembers()
            # 检测是否有公共的顶层目录
            common_prefix = get_common_prefix([m.name for m in members if not m.isdir()])

            for member in members:
                if member.isdir():
                    continue
                # 安全处理：避免路径穿越
                if member.name.startswith('/') or '..' in member.name:
                    continue
                # 去除公共前缀
                if common_prefix and member.name.startswith(common_prefix):
                    member.name = member.name[len(common_prefix):]
                    if not member.name:
                        continue
                tar.extract(member, extract_to)
                extracted_path = os.path.join(extract_to, member.name)
                if os.path.isfile(extracted_path):
                    extracted_files.append(extracted_path)

    elif archive_type == 'zip':
        with zipfile.ZipFile(archive_path, 'r') as zf:
            names = [n for n in zf.namelist() if not n.endswith('/')]
            # 检测是否有公共的顶层目录
            common_prefix = get_common_prefix(names)

            for name in names:
                # 安全处理：避免路径穿越
                if name.startswith('/') or '..' in name:
                    continue
                # 去除公共前缀
                target_name = name
                if common_prefix and name.startswith(common_prefix):
                    target_name = name[len(common_prefix):]
                    if not target_name:
                        continue

                # 创建目标路径
                target_path = os.path.join(extract_to, target_name)
                ensure_dir(os.path.dirname(target_path))

                with zf.open(name) as src, open(target_path, 'wb') as dst:
                    dst.write(src.read())

                if os.path.isfile(target_path):
                    extracted_files.append(target_path)

    return extracted_files


def get_common_prefix(paths):
    """
    获取路径列表的公共前缀（以/结尾的目录前缀）

    Args:
        paths: 路径列表

    Returns:
        str: 公共前缀，如 'test/' 或空字符串
    """
    if not paths:
        return ''

    # 找到第一个路径的顶层目录
    first = paths[0]
    if '/' in first:
        top_dir = first.split('/')[0] + '/'
        # 检查所有路径是否都以这个顶层目录开头
        if all(p.startswith(top_dir) for p in paths):
            return top_dir

    return ''


def create_work_directory(base_dir, filename):
    """
    创建工作目录，格式为 时间戳_文件名

    Args:
        base_dir: 基础目录（data/temp）
        filename: 原始文件名

    Returns:
        str: 创建的工作目录路径
    """
    # 移除扩展名，获取干净的文件名
    clean_name = filename
    for ext in ['.tar.gz', '.tgz', '.tar', '.zip', '.log', '.txt']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break

    # 生成时间戳
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 创建目录名
    dir_name = f"{timestamp}_{clean_name}"
    work_dir = os.path.join(base_dir, dir_name)

    ensure_dir(work_dir)
    return work_dir


def create_batch_work_directory(base_dir, folder_name):
    """
    创建批量分析工作目录，格式为 时间戳_文件夹名

    Args:
        base_dir: 基础目录（data/temp）
        folder_name: 上传的文件夹名

    Returns:
        str: 创建的工作目录路径
    """
    # 移除可能的扩展名，获取干净的文件夹名
    clean_name = folder_name
    for ext in ['.tar.gz', '.tgz', '.tar', '.zip']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break

    # 生成时间戳
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 创建目录名
    dir_name = f"{timestamp}_{clean_name}"
    work_dir = os.path.join(base_dir, dir_name)

    ensure_dir(work_dir)
    return work_dir


def create_single_log_output_dir(base_output_dir, log_filename):
    """
    创建单个日志文件的输出目录，格式为 时间戳_日志文件名

    Args:
        base_output_dir: 批量输出基础目录
        log_filename: 日志文件名

    Returns:
        str: 创建的输出目录路径
    """
    # 移除扩展名
    clean_name = log_filename
    for ext in ['.log', '.txt']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dir_name = f"{timestamp}_{clean_name}"
    output_dir = os.path.join(base_output_dir, dir_name)

    ensure_dir(output_dir)
    return output_dir