"""
缓存模块
提供内存缓存、磁盘缓存和混合缓存实现
"""

import os
import json
import time
import hashlib
import threading
from collections import OrderedDict
from typing import Any, Optional


class LRUCache:
    """线程安全的LRU内存缓存"""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """
        初始化LRU缓存

        Args:
            max_size: 最大缓存条目数
            ttl: 缓存过期时间(秒)，默认1小时
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: dict = {}
        self._lock = threading.RLock()

    def _generate_key(self, key: str) -> str:
        """生成缓存键"""
        return hashlib.md5(key.encode('utf-8')).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在或过期返回None
        """
        cache_key = self._generate_key(key)

        with self._lock:
            if cache_key not in self._cache:
                return None

            # 检查是否过期
            if time.time() - self._timestamps.get(cache_key, 0) > self.ttl:
                self._remove(cache_key)
                return None

            # 移到末尾(LRU)
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

    def set(self, key: str, value: Any) -> None:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
        """
        cache_key = self._generate_key(key)

        with self._lock:
            # 如果已存在，更新值并移到末尾
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                self._cache[cache_key] = value
                self._timestamps[cache_key] = time.time()
                return

            # 检查是否需要淘汰
            while len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                self._remove(oldest_key)

            # 添加新条目
            self._cache[cache_key] = value
            self._timestamps[cache_key] = time.time()

    def _remove(self, cache_key: str) -> None:
        """移除缓存条目"""
        if cache_key in self._cache:
            del self._cache[cache_key]
        if cache_key in self._timestamps:
            del self._timestamps[cache_key]

    def delete(self, key: str) -> bool:
        """
        删除缓存条目

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        cache_key = self._generate_key(key)
        with self._lock:
            if cache_key in self._cache:
                self._remove(cache_key)
                return True
            return False

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        with self._lock:
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'ttl': self.ttl
            }


class DiskCache:
    """磁盘缓存，适合持久化"""

    def __init__(self, cache_dir: str = None, ttl: int = 86400):
        """
        初始化磁盘缓存

        Args:
            cache_dir: 缓存目录
            ttl: 缓存过期时间(秒)，默认24小时
        """
        if cache_dir is None:
            cache_dir = self._get_default_cache_dir()
        self.cache_dir = cache_dir
        self.ttl = ttl
        os.makedirs(cache_dir, exist_ok=True)

    def _get_default_cache_dir(self) -> str:
        """获取默认缓存目录"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, 'data', 'cache')

    def _generate_key(self, key: str) -> str:
        """生成缓存文件名"""
        return hashlib.md5(key.encode('utf-8')).hexdigest() + '.json'

    def _get_cache_path(self, key: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, self._generate_key(key))

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在或过期返回None
        """
        cache_path = self._get_cache_path(key)

        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 检查是否过期
            if time.time() - data.get('timestamp', 0) > self.ttl:
                self.delete(key)
                return None

            return data.get('value')
        except (json.JSONDecodeError, IOError):
            return None

    def set(self, key: str, value: Any) -> None:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
        """
        cache_path = self._get_cache_path(key)

        data = {
            'key': key,
            'value': value,
            'timestamp': time.time()
        }

        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except IOError:
            pass

    def delete(self, key: str) -> bool:
        """
        删除缓存条目

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        cache_path = self._get_cache_path(key)

        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
                return True
            except IOError:
                return False
        return False

    def clear(self) -> None:
        """清空缓存"""
        if os.path.exists(self.cache_dir):
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    try:
                        os.remove(os.path.join(self.cache_dir, filename))
                    except IOError:
                        pass

    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        file_count = 0
        total_size = 0

        if os.path.exists(self.cache_dir):
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    file_count += 1
                    file_path = os.path.join(self.cache_dir, filename)
                    total_size += os.path.getsize(file_path)

        return {
            'file_count': file_count,
            'total_size': total_size,
            'cache_dir': self.cache_dir,
            'ttl': self.ttl
        }


class HybridCache:
    """混合缓存：内存 + 磁盘"""

    def __init__(self, memory_size: int = 500, ttl: int = 3600, cache_dir: str = None):
        """
        初始化混合缓存

        Args:
            memory_size: 内存缓存最大条目数
            ttl: 缓存过期时间(秒)
            cache_dir: 磁盘缓存目录
        """
        self.memory_cache = LRUCache(max_size=memory_size, ttl=ttl)
        self.disk_cache = DiskCache(cache_dir=cache_dir, ttl=ttl)
        self.ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值(先查内存，再查磁盘)

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在返回None
        """
        # 先查内存缓存
        value = self.memory_cache.get(key)
        if value is not None:
            return value

        # 再查磁盘缓存
        value = self.disk_cache.get(key)
        if value is not None:
            # 回填到内存缓存
            self.memory_cache.set(key, value)
            return value

        return None

    def set(self, key: str, value: Any, persist: bool = True) -> None:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            persist: 是否持久化到磁盘
        """
        # 写入内存缓存
        self.memory_cache.set(key, value)

        # 可选写入磁盘缓存
        if persist:
            self.disk_cache.set(key, value)

    def delete(self, key: str) -> bool:
        """
        删除缓存条目

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        memory_result = self.memory_cache.delete(key)
        disk_result = self.disk_cache.delete(key)
        return memory_result or disk_result

    def clear(self) -> None:
        """清空所有缓存"""
        self.memory_cache.clear()
        self.disk_cache.clear()

    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        memory_stats = self.memory_cache.get_stats()
        disk_stats = self.disk_cache.get_stats()

        return {
            'memory': memory_stats,
            'disk': disk_stats,
            'ttl': self.ttl
        }