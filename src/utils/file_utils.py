"""
文件工具模块
提供文件读写、JSON处理等通用功能
"""

import json
import os


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


def get_file_extension(file_path):
    """获取文件扩展名"""
    _, ext = os.path.splitext(file_path)
    return ext.lower()


def list_files(dir_path, extension=None):
    """列出目录下的文件"""
    if not os.path.exists(dir_path):
        return []
    files = []
    for item in os.listdir(dir_path):
        item_path = os.path.join(dir_path, item)
        if os.path.isfile(item_path):
            if extension is None or get_file_extension(item_path) == extension:
                files.append(item_path)
    return files


def file_exists(file_path):
    """检查文件是否存在"""
    return os.path.isfile(file_path)


def dir_exists(dir_path):
    """检查目录是否存在"""
    return os.path.isdir(dir_path)


def get_filename(file_path):
    """获取文件名（不含扩展名）"""
    basename = os.path.basename(file_path)
    name, _ = os.path.splitext(basename)
    return name


def join_path(*args):
    """拼接路径"""
    return os.path.join(*args)