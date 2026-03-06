"""
================================================================================
性能监控模块 - 实时性能追踪与优化建议
================================================================================

【模块概述】
提供实时的性能监控功能，包括：
1. 各阶段耗时统计
2. 性能瓶颈自动检测
3. 优化建议生成
4. 性能报告输出
5. 异步记录支持（高性能场景）
6. 内存限制和数据采样
7. 实时告警机制
8. 性能对比功能

【设计思路】
通过装饰器和上下文管理器实现无侵入式的性能监控，
自动收集各阶段的执行耗时，并生成优化建议。
================================================================================
"""

import time
import json
import threading
import queue
import atexit
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from functools import wraps
from contextlib import contextmanager
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from task_manager import get_current_task_id


@dataclass
class PerformanceMetric:
    """性能指标记录"""
    name: str
    duration_ms: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StageMetrics:
    """阶段性能统计"""
    name: str
    total_calls: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    last_duration_ms: float = 0.0
    
    def update(self, duration_ms: float):
        """更新统计"""
        self.total_calls += 1
        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.avg_duration_ms = self.total_duration_ms / self.total_calls
        self.last_duration_ms = duration_ms


class AlertCallback:
    """告警回调基类"""
    
    def __call__(self, stage_name: str, duration_ms: float, threshold_ms: float):
        """触发告警"""
        raise NotImplementedError


class PrintAlertCallback(AlertCallback):
    """打印告警回调"""
    
    def __call__(self, stage_name: str, duration_ms: float, threshold_ms: float):
        print(f"⚠️ 性能告警: {stage_name} 耗时 {duration_ms:.1f}ms 超过阈值 {threshold_ms}ms")


class PerformanceMonitor:
    """
    性能监控器 - 实时追踪各阶段性能
    
    【使用示例】
    ```python
    monitor = PerformanceMonitor()
    
    # 使用装饰器
    @monitor.track("perception")
    def perception_node():
        ...
    
    # 使用上下文管理器
    with monitor.track_stage("action"):
        do_action()
    
    # 获取报告
    report = monitor.get_report()
    ```
    """
    
    THRESHOLDS = {
        "perception": 3000,
        "reasoning": 10000,
        "action": 1500,  # 优化后从 2000 降低到 1500
        "click": 300,    # 优化后从 500 降低到 300
        "type": 800,     # 优化后从 1000 降低到 800
        "goto": 3000,    # 优化后从 5000 降低到 3000
        "llm_call": 8000,
        "element_visibility": 100,
        "iframe_extraction": 2000,
    }
    
    OPTIMIZATION_SUGGESTIONS = {
        "perception": [
            "考虑使用批量元素检查替代逐个检查",
            "减少iframe超时等待时间",
            "使用JavaScript批量获取元素状态"
        ],
        "reasoning": [
            "精简prompt内容，减少token数量",
            "考虑使用更快的模型",
            "缓存重复的LLM调用结果"
        ],
        "action": [
            "启用快速模式减少人类模拟延迟",
            "减少重试次数",
            "优化元素定位策略"
        ],
        "click": [
            "减少鼠标移动模拟步数",
            "使用直接点击替代模拟移动"
        ],
        "type": [
            "使用fill()替代逐字输入",
            "减少输入验证重试次数"
        ],
        "goto": [
            "使用更短的超时时间",
            "考虑预加载资源"
        ],
        "element_visibility": [
            "使用JavaScript批量检查",
            "减少单个元素检查超时"
        ]
    }
    
    def __init__(self, log_dir: str = "logs/performance", 
                 max_metrics: int = 10000,
                 sample_rate: float = 1.0,
                 async_mode: bool = False,
                 alert_callback: AlertCallback = None,
                 task_id: str = None):
        """
        初始化性能监控器
        
        【参数】
        log_dir: 日志目录
        max_metrics: 最大存储指标数量（防止内存溢出）
        sample_rate: 采样率（0.0-1.0，1.0表示100%采样）
        async_mode: 是否启用异步模式（高性能场景）
        alert_callback: 告警回调函数
        task_id: 任务ID，如果不提供则从任务管理器获取
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self._max_metrics = max_metrics
        self._sample_rate = max(0.0, min(1.0, sample_rate))
        self._async_mode = async_mode
        self._alert_callback = alert_callback
        
        self._lock = threading.RLock()
        self._metrics: List[PerformanceMetric] = []
        self._stage_stats: Dict[str, StageMetrics] = {}
        self._session_start = time.time()
        
        if task_id:
            self._session_id = task_id
        else:
            self._session_id = get_current_task_id()
            if not self._session_id:
                self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self._slow_operations: List[PerformanceMetric] = []
        self._optimization_flags: Dict[str, int] = defaultdict(int)
        
        self._sample_counter = 0
        self._dropped_count = 0
        
        if async_mode:
            self._async_queue: queue.Queue = queue.Queue()
            self._executor = ThreadPoolExecutor(max_workers=1)
            self._running = True
            self._executor.submit(self._async_worker)
            atexit.register(self._shutdown)
    
    def _shutdown(self):
        """关闭异步工作线程"""
        if self._async_mode:
            self._running = False
            self._executor.shutdown(wait=True)
    
    def _async_worker(self):
        """异步工作线程"""
        while self._running:
            try:
                item = self._async_queue.get(timeout=0.1)
                if item is None:
                    break
                stage_name, duration_ms, metadata = item
                self._record_sync(stage_name, duration_ms, metadata)
            except queue.Empty:
                continue
            except Exception:
                pass
    
    def _should_sample(self) -> bool:
        """判断是否应该采样"""
        if self._sample_rate >= 1.0:
            return True
        self._sample_counter += 1
        return (self._sample_counter % int(1 / self._sample_rate)) == 0
    
    def record(self, stage_name: str, duration_ms: float, metadata: Dict = None):
        """
        记录性能指标
        
        【参数】
        stage_name: 阶段名称
        duration_ms: 耗时（毫秒）
        metadata: 额外元数据
        """
        if not self._should_sample():
            with self._lock:
                self._dropped_count += 1
            return
        
        if self._async_mode:
            self._async_queue.put((stage_name, duration_ms, metadata))
        else:
            self._record_sync(stage_name, duration_ms, metadata)
    
    def _record_sync(self, stage_name: str, duration_ms: float, metadata: Dict = None):
        """同步记录（内部方法）"""
        with self._lock:
            if len(self._metrics) >= self._max_metrics:
                self._metrics.pop(0)
            
            metric = PerformanceMetric(
                name=stage_name,
                duration_ms=duration_ms,
                timestamp=time.time(),
                metadata=metadata or {}
            )
            self._metrics.append(metric)
            
            if stage_name not in self._stage_stats:
                self._stage_stats[stage_name] = StageMetrics(name=stage_name)
            self._stage_stats[stage_name].update(duration_ms)
            
            threshold = self.THRESHOLDS.get(stage_name, 1000)
            if duration_ms > threshold:
                if len(self._slow_operations) < self._max_metrics:
                    self._slow_operations.append(metric)
                self._optimization_flags[stage_name] += 1
                
                if self._alert_callback:
                    try:
                        self._alert_callback(stage_name, duration_ms, threshold)
                    except Exception:
                        pass
    
    def track(self, stage_name: str) -> Callable:
        """
        装饰器：追踪函数执行时间
        
        【参数】
        stage_name: 阶段名称
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    self.record(stage_name, duration_ms)
            return wrapper
        return decorator
    
    @contextmanager
    def track_stage(self, stage_name: str, metadata: Dict = None):
        """
        上下文管理器：追踪代码块执行时间
        
        【参数】
        stage_name: 阶段名称
        metadata: 额外元数据
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.record(stage_name, duration_ms, metadata or {})
    
    def get_stage_stats(self, stage_name: str = None) -> Dict:
        """
        获取阶段统计
        
        【参数】
        stage_name: 阶段名称（可选，不提供则返回所有）
        """
        with self._lock:
            if stage_name:
                if stage_name in self._stage_stats:
                    return asdict(self._stage_stats[stage_name])
                return {}
            return {name: asdict(stats) for name, stats in self._stage_stats.items()}
    
    def get_slow_operations_count(self) -> Dict[str, int]:
        """获取慢操作统计"""
        with self._lock:
            return dict(self._optimization_flags)
    
    def _get_optimization_suggestions_unlocked(self) -> List[Dict]:
        """
        内部方法：获取优化建议（不加锁）
        
        【注意】调用此方法前必须已持有 self._lock
        """
        suggestions = []
        
        for stage_name, count in self._optimization_flags.items():
            if count > 0 and stage_name in self._stage_stats:
                stats = self._stage_stats[stage_name]
                threshold = self.THRESHOLDS.get(stage_name, 1000)
                
                if stats.avg_duration_ms > threshold:
                    suggestions.append({
                        "stage": stage_name,
                        "avg_time_ms": round(stats.avg_duration_ms, 2),
                        "threshold_ms": threshold,
                        "slow_count": count,
                        "suggestions": self.OPTIMIZATION_SUGGESTIONS.get(stage_name, [])
                    })
        
        return sorted(suggestions, key=lambda x: x["avg_time_ms"], reverse=True)
    
    def get_optimization_suggestions(self) -> List[Dict]:
        """
        获取优化建议
        
        【返回值】
        List of {stage, avg_time, threshold, suggestions}
        """
        with self._lock:
            return self._get_optimization_suggestions_unlocked()
    
    def get_report(self) -> Dict:
        """
        生成性能报告
        
        【返回值】
        包含完整性能统计的字典
        """
        with self._lock:
            session_duration = time.time() - self._session_start
            
            total_metrics = len(self._metrics)
            total_slow = len(self._slow_operations)
            
            stage_summary = []
            for name, stats in self._stage_stats.items():
                threshold = self.THRESHOLDS.get(name, 1000)
                stage_summary.append({
                    "name": name,
                    "calls": stats.total_calls,
                    "total_ms": round(stats.total_duration_ms, 2),
                    "avg_ms": round(stats.avg_duration_ms, 2),
                    "min_ms": round(stats.min_duration_ms, 2) if stats.min_duration_ms != float('inf') else 0,
                    "max_ms": round(stats.max_duration_ms, 2),
                    "threshold_ms": threshold,
                    "exceeds_threshold": stats.avg_duration_ms > threshold
                })
            
            stage_summary.sort(key=lambda x: x["total_ms"], reverse=True)
            
            return {
                "session_id": self._session_id,
                "session_duration_s": round(session_duration, 2),
                "total_metrics": total_metrics,
                "dropped_metrics": self._dropped_count,
                "sample_rate": self._sample_rate,
                "slow_operations": total_slow,
                "stages": stage_summary,
                "optimization_suggestions": self._get_optimization_suggestions_unlocked()
            }
    
    def compare_with(self, other_report: Dict) -> Dict:
        """
        与另一个报告进行性能对比
        
        【参数】
        other_report: 另一个性能报告字典
        
        【返回值】
        对比结果字典
        """
        current = self.get_report()
        
        comparison = {
            "current_session": current["session_id"],
            "other_session": other_report.get("session_id", "unknown"),
            "stages_comparison": []
        }
        
        current_stages = {s["name"]: s for s in current["stages"]}
        other_stages = {s["name"]: s for s in other_report.get("stages", [])}
        
        all_stages = set(current_stages.keys()) | set(other_stages.keys())
        
        for stage_name in all_stages:
            curr = current_stages.get(stage_name, {})
            other = other_stages.get(stage_name, {})
            
            curr_avg = curr.get("avg_ms", 0)
            other_avg = other.get("avg_ms", 0)
            
            if other_avg > 0:
                change_percent = ((curr_avg - other_avg) / other_avg) * 100
            else:
                change_percent = 0 if curr_avg == 0 else 100
            
            comparison["stages_comparison"].append({
                "stage": stage_name,
                "current_avg_ms": curr_avg,
                "other_avg_ms": other_avg,
                "change_percent": round(change_percent, 2),
                "improved": change_percent < 0,
                "current_calls": curr.get("calls", 0),
                "other_calls": other.get("calls", 0)
            })
        
        comparison["stages_comparison"].sort(key=lambda x: abs(x["change_percent"]), reverse=True)
        
        return comparison
    
    def save_report(self) -> str:
        """
        保存性能报告到文件
        
        【返回值】
        文件路径
        """
        report = self.get_report()
        filepath = self.log_dir / f"perf_{self._session_id}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return str(filepath)
    
    def print_summary(self):
        """打印性能摘要"""
        report = self.get_report()
        
        print("\n" + "=" * 60)
        print("📊 性能监控报告")
        print("=" * 60)
        print(f"会话时长: {report['session_duration_s']:.1f}秒")
        print(f"总记录数: {report['total_metrics']}")
        if report['dropped_metrics'] > 0:
            print(f"丢弃记录: {report['dropped_metrics']} (采样率: {report['sample_rate']:.0%})")
        print(f"慢操作数: {report['slow_operations']}")
        
        print("\n📈 阶段耗时统计:")
        print("-" * 60)
        print(f"{'阶段':<15} {'调用次数':>8} {'平均耗时':>10} {'总耗时':>10} {'状态':>8}")
        print("-" * 60)
        
        for stage in report['stages']:
            status = "⚠️ 慢" if stage['exceeds_threshold'] else "✅ 正常"
            print(f"{stage['name']:<15} {stage['calls']:>8} {stage['avg_ms']:>8.1f}ms {stage['total_ms']:>8.1f}ms {status:>8}")
        
        if report['optimization_suggestions']:
            print("\n💡 优化建议:")
            for sug in report['optimization_suggestions']:
                print(f"  - {sug['stage']}: 平均 {sug['avg_time_ms']:.1f}ms (阈值 {sug['threshold_ms']}ms)")
                for s in sug['suggestions'][:2]:
                    print(f"      • {s}")
        
        print("=" * 60)
    
    def reset(self):
        """重置监控器"""
        with self._lock:
            self._metrics.clear()
            self._stage_stats.clear()
            self._slow_operations.clear()
            self._optimization_flags.clear()
            self._session_start = time.time()
            self._session_id = get_current_task_id()
            if not self._session_id:
                self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._sample_counter = 0
            self._dropped_count = 0


_monitor_instance: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控器实例"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = PerformanceMonitor()
    return _monitor_instance


def reset_performance_monitor():
    """重置全局性能监控器"""
    global _monitor_instance
    if _monitor_instance:
        _monitor_instance.reset()


def track_performance(stage_name: str):
    """
    装饰器：追踪函数性能
    
    【使用示例】
    @track_performance("perception")
    def perception_node():
        ...
    """
    return get_performance_monitor().track(stage_name)


@contextmanager
def measure_time(stage_name: str, metadata: Dict = None):
    """
    上下文管理器：测量代码块执行时间
    
    【使用示例】
    with measure_time("action"):
        do_action()
    """
    monitor = get_performance_monitor()
    with monitor.track_stage(stage_name, metadata):
        yield


def enable_async_mode():
    """启用异步模式（高性能场景）"""
    global _monitor_instance
    _monitor_instance = PerformanceMonitor(async_mode=True)
    return _monitor_instance


def set_alert_callback(callback: AlertCallback):
    """设置告警回调"""
    monitor = get_performance_monitor()
    monitor._alert_callback = callback
