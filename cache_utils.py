"""
================================================================================
缓存工具模块 - 高性能缓存机制
================================================================================

【模块概述】
提供多层次的缓存机制，包括：
1. LRU内存缓存 - 用于频繁访问的小数据
2. TTL缓存 - 用于有时效性的数据
3. 装饰器缓存 - 用于函数结果缓存

【设计思路】
通过缓存减少重复计算和I/O操作，提升系统整体性能。
使用线程安全的实现，支持并发访问。
================================================================================
"""

import time
import threading
import hashlib
import json
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar, ParamSpec
from functools import wraps, lru_cache
from collections import OrderedDict
from dataclasses import dataclass, field

P = ParamSpec('P')
T = TypeVar('T')


@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    created_at: float
    expires_at: float
    access_count: int = 0
    last_access: float = field(default_factory=time.time)


class TTLCache:
    """
    TTL缓存 - 带过期时间的缓存
    
    【特性】
    1. 支持TTL（Time To Live）过期
    2. 线程安全
    3. 自动清理过期条目
    4. 支持最大容量限制
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: float = 60.0):
        """
        初始化TTL缓存
        
        【参数】
        max_size: 最大缓存条目数
        default_ttl: 默认过期时间（秒）
        """
        self._cache: Dict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def _generate_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = {
            'args': args,
            'kwargs': kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        【参数】
        key: 缓存键
        
        【返回值】
        缓存值，不存在或已过期返回None
        """
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._misses += 1
                return None
            
            if time.time() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                self._evictions += 1
                return None
            
            entry.access_count += 1
            entry.last_access = time.time()
            self._hits += 1
            
            self._cache.move_to_end(key)
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: float = None) -> None:
        """
        设置缓存值
        
        【参数】
        key: 缓存键
        value: 缓存值
        ttl: 过期时间（秒），None使用默认值
        """
        with self._lock:
            current_time = time.time()
            expires_at = current_time + (ttl if ttl is not None else self._default_ttl)
            
            if len(self._cache) >= self._max_size and key not in self._cache:
                self._evict_oldest()
            
            entry = CacheEntry(
                value=value,
                created_at=current_time,
                expires_at=expires_at
            )
            
            if key in self._cache:
                del self._cache[key]
            
            self._cache[key] = entry
    
    def _evict_oldest(self):
        """淘汰最旧的条目"""
        if self._cache:
            self._cache.popitem(last=False)
            self._evictions += 1
    
    def delete(self, key: str) -> bool:
        """
        删除缓存条目
        
        【参数】
        key: 缓存键
        
        【返回值】
        是否成功删除
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
    
    def cleanup_expired(self) -> int:
        """
        清理过期条目
        
        【返回值】
        清理的条目数
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time > entry.expires_at
            ]
            
            for key in expired_keys:
                del self._cache[key]
                self._evictions += 1
            
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0
            
            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'hits': self._hits,
                'misses': self._misses,
                'evictions': self._evictions,
                'hit_rate': hit_rate
            }


class ElementSelectorCache:
    """
    元素选择器缓存 - 专门用于缓存元素定位结果
    
    【设计思路】
    元素定位是perception_node的主要性能瓶颈之一。
    缓存CSS选择器和XPath的定位结果可以显著提升性能。
    """
    
    def __init__(self, ttl: float = 30.0):
        """
        初始化元素选择器缓存
        
        【参数】
        ttl: 缓存过期时间（秒）
        """
        self._selector_cache: Dict[str, Tuple[bool, float]] = {}
        self._xpath_cache: Dict[str, Tuple[bool, float]] = {}
        self._lock = threading.RLock()
        self._ttl = ttl
    
    def get_selector_visibility(self, selector: str) -> Optional[bool]:
        """获取选择器对应的可见性缓存"""
        with self._lock:
            entry = self._selector_cache.get(selector)
            if entry is None:
                return None
            visibility, timestamp = entry
            if time.time() - timestamp > self._ttl:
                del self._selector_cache[selector]
                return None
            return visibility
    
    def set_selector_visibility(self, selector: str, is_visible: bool):
        """设置选择器可见性缓存"""
        with self._lock:
            self._selector_cache[selector] = (is_visible, time.time())
    
    def get_xpath_visibility(self, xpath: str) -> Optional[bool]:
        """获取XPath对应的可见性缓存"""
        with self._lock:
            entry = self._xpath_cache.get(xpath)
            if entry is None:
                return None
            visibility, timestamp = entry
            if time.time() - timestamp > self._ttl:
                del self._xpath_cache[xpath]
                return None
            return visibility
    
    def set_xpath_visibility(self, xpath: str, is_visible: bool):
        """设置XPath可见性缓存"""
        with self._lock:
            self._xpath_cache[xpath] = (is_visible, time.time())
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._selector_cache.clear()
            self._xpath_cache.clear()


class PromptCache:
    """
    Prompt缓存 - 缓存LLM的prompt构建结果
    
    【设计思路】
    相似页面状态的prompt可能非常相似，缓存构建结果可以
    避免重复的字符串拼接操作。
    """
    
    def __init__(self, max_size: int = 100):
        """
        初始化Prompt缓存
        
        【参数】
        max_size: 最大缓存条目数
        """
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.RLock()
        self._max_size = max_size
    
    def _generate_key(self, elements_hash: str, objective: str, 
                      history_hash: str, url: str) -> str:
        """生成缓存键"""
        key_data = f"{elements_hash}|{objective}|{history_hash}|{url}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, elements_hash: str, objective: str, 
            history_hash: str, url: str) -> Optional[str]:
        """获取缓存的prompt"""
        key = self._generate_key(elements_hash, objective, history_hash, url)
        with self._lock:
            return self._cache.get(key)
    
    def set(self, elements_hash: str, objective: str, 
            history_hash: str, url: str, prompt: str):
        """设置prompt缓存"""
        key = self._generate_key(elements_hash, objective, history_hash, url)
        with self._lock:
            if len(self._cache) >= self._max_size and key not in self._cache:
                self._cache.popitem(last=False)
            if key in self._cache:
                del self._cache[key]
            self._cache[key] = prompt
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()


def cached_result(ttl: float = 60.0, max_size: int = 128):
    """
    装饰器：缓存函数结果
    
    【参数】
    ttl: 缓存过期时间（秒）
    max_size: 最大缓存条目数
    
    【使用示例】
    @cached_result(ttl=30.0)
    def expensive_function(arg):
        ...
    """
    cache: Dict[str, Tuple[Any, float]] = {}
    lock = threading.RLock()
    
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            key_data = {
                'args': args,
                'kwargs': kwargs
            }
            key = hashlib.md5(
                json.dumps(key_data, sort_keys=True, default=str).encode()
            ).hexdigest()
            
            with lock:
                entry = cache.get(key)
                if entry is not None:
                    value, timestamp = entry
                    if time.time() - timestamp <= ttl:
                        return value
                    del cache[key]
                
                if len(cache) >= max_size:
                    oldest_key = next(iter(cache))
                    del cache[oldest_key]
            
            result = func(*args, **kwargs)
            
            with lock:
                cache[key] = (result, time.time())
            
            return result
        
        wrapper.cache_clear = lambda: cache.clear()
        wrapper.cache_info = lambda: {
            'size': len(cache),
            'max_size': max_size,
            'ttl': ttl
        }
        
        return wrapper
    
    return decorator


_global_ttl_cache: Optional[TTLCache] = None
_global_selector_cache: Optional[ElementSelectorCache] = None
_global_prompt_cache: Optional[PromptCache] = None
_cache_lock = threading.Lock()


def get_global_cache() -> TTLCache:
    """获取全局TTL缓存实例"""
    global _global_ttl_cache
    if _global_ttl_cache is None:
        with _cache_lock:
            if _global_ttl_cache is None:
                _global_ttl_cache = TTLCache(max_size=2000, default_ttl=120.0)
    return _global_ttl_cache


def get_selector_cache() -> ElementSelectorCache:
    """获取全局元素选择器缓存实例"""
    global _global_selector_cache
    if _global_selector_cache is None:
        with _cache_lock:
            if _global_selector_cache is None:
                _global_selector_cache = ElementSelectorCache(ttl=30.0)
    return _global_selector_cache


def get_prompt_cache() -> PromptCache:
    """获取全局Prompt缓存实例"""
    global _global_prompt_cache
    if _global_prompt_cache is None:
        with _cache_lock:
            if _global_prompt_cache is None:
                _global_prompt_cache = PromptCache(max_size=50)
    return _global_prompt_cache


def clear_all_caches():
    """清空所有全局缓存"""
    global _global_ttl_cache, _global_selector_cache, _global_prompt_cache
    
    with _cache_lock:
        if _global_ttl_cache is not None:
            _global_ttl_cache.clear()
        if _global_selector_cache is not None:
            _global_selector_cache.clear()
        if _global_prompt_cache is not None:
            _global_prompt_cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """获取所有缓存的统计信息"""
    stats = {}
    
    with _cache_lock:
        if _global_ttl_cache is not None:
            stats['ttl_cache'] = _global_ttl_cache.get_stats()
        if _global_selector_cache is not None:
            stats['selector_cache'] = {
                'selector_count': len(_global_selector_cache._selector_cache),
                'xpath_count': len(_global_selector_cache._xpath_cache)
            }
        if _global_prompt_cache is not None:
            stats['prompt_cache'] = {
                'size': len(_global_prompt_cache._cache),
                'max_size': _global_prompt_cache._max_size
            }
    
    return stats
