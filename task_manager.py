"""
================================================================================
任务管理模块 - 统一任务ID生成与文件管理
================================================================================

【模块概述】
提供全局唯一的任务ID，统一管理任务相关的所有文件存储。

【核心功能】
1. 生成全局唯一的任务ID
2. 管理任务生命周期
3. 统一管理任务文件目录

【目录结构】
tasks/
└── 20260302_112930/           # 任务文件夹（任务ID命名）
    ├── agent.log              # 日志文件
    ├── session.json           # 会话文件
    ├── performance.json       # 性能文件
    └── process/               # 过程文件子目录
        ├── step_001_elements.json
        ├── step_001_decision.json
        └── ...

================================================================================
"""

import os
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


def get_project_root() -> str:
    """获取项目根目录"""
    return os.path.dirname(os.path.abspath(__file__))


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    start_time: float
    task_dir: str
    objective: str = ""
    model: str = ""
    status: str = "running"
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskManager:
    """
    任务管理器 - 统一管理任务ID和任务文件目录
    
    【线程安全】
    所有操作都是线程安全的，使用 RLock 保护共享状态。
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        """单例模式：确保只有一个实例"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """初始化任务管理器"""
        if self._initialized:
            return
        
        self._initialized = True
        self._current_task: Optional[TaskInfo] = None
        self._task_lock = threading.RLock()
        self._task_history: list[TaskInfo] = []
        self._max_history = 100
        
        self._tasks_root = os.path.join(get_project_root(), "tasks")
    
    def _ensure_tasks_root(self):
        """确保任务根目录存在"""
        if not os.path.exists(self._tasks_root):
            os.makedirs(self._tasks_root)
    
    def generate_task_id(self) -> str:
        """
        生成任务ID
        
        【格式】YYYYMMDD_HHMMSS
        
        【返回值】
        str: 任务ID，如 "20260302_112930"
        """
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def start_task(self, objective: str = "", model: str = "", 
                   metadata: Dict[str, Any] = None) -> str:
        """
        开始新任务（自动创建任务目录）
        
        【参数】
        objective: 任务目标描述
        model: 使用的模型名称
        metadata: 额外的元数据
        
        【返回值】
        str: 新任务的ID
        """
        with self._task_lock:
            if self._current_task is not None:
                self.end_task(success=False, reason="新任务开始")
            
            task_id = self.generate_task_id()
            
            self._ensure_tasks_root()
            task_dir = os.path.join(self._tasks_root, task_id)
            os.makedirs(task_dir)
            
            process_dir = os.path.join(task_dir, "process")
            os.makedirs(process_dir)
            
            self._current_task = TaskInfo(
                task_id=task_id,
                start_time=time.time(),
                task_dir=task_dir,
                objective=objective,
                model=model,
                status="running",
                metadata=metadata or {}
            )
            
            self._save_task_info()
            
            return task_id
    
    def _save_task_info(self):
        """保存任务信息到文件"""
        if not self._current_task:
            return
        
        import json
        info_path = os.path.join(self._current_task.task_dir, "task_info.json")
        info = {
            "task_id": self._current_task.task_id,
            "start_time": self._current_task.start_time,
            "objective": self._current_task.objective,
            "model": self._current_task.model,
            "status": self._current_task.status,
        }
        
        try:
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def get_task_id(self) -> Optional[str]:
        """
        获取当前任务ID
        
        【返回值】
        str: 当前任务ID，如果没有活动任务则返回 None
        """
        with self._task_lock:
            if self._current_task:
                return self._current_task.task_id
            return None
    
    def get_task_dir(self) -> Optional[str]:
        """
        获取当前任务目录路径
        
        【返回值】
        str: 任务目录路径，如果没有活动任务则返回 None
        """
        with self._task_lock:
            if self._current_task:
                return self._current_task.task_dir
            return None
    
    def get_log_file_path(self) -> Optional[str]:
        """获取日志文件路径"""
        task_dir = self.get_task_dir()
        if task_dir:
            return os.path.join(task_dir, "agent.log")
        return None
    
    def get_session_file_path(self) -> Optional[str]:
        """获取会话文件路径"""
        task_dir = self.get_task_dir()
        if task_dir:
            return os.path.join(task_dir, "session.json")
        return None
    
    def get_performance_file_path(self) -> Optional[str]:
        """获取性能文件路径"""
        task_dir = self.get_task_dir()
        if task_dir:
            return os.path.join(task_dir, "performance.json")
        return None
    
    def get_process_dir(self) -> Optional[str]:
        """获取过程文件目录路径"""
        task_dir = self.get_task_dir()
        if task_dir:
            return os.path.join(task_dir, "process")
        return None
    
    def get_task_info(self) -> Optional[TaskInfo]:
        """获取当前任务信息"""
        with self._task_lock:
            if self._current_task:
                return self._current_task
            return None
    
    def update_task_status(self, status: str, **kwargs):
        """更新任务状态"""
        with self._task_lock:
            if self._current_task:
                self._current_task.status = status
                for key, value in kwargs.items():
                    if hasattr(self._current_task, key):
                        setattr(self._current_task, key, value)
                self._save_task_info()
    
    def end_task(self, success: bool = True, reason: str = "") -> Optional[TaskInfo]:
        """结束当前任务"""
        with self._task_lock:
            if self._current_task is None:
                return None
            
            self._current_task.status = "completed" if success else "failed"
            self._current_task.metadata["end_reason"] = reason
            self._current_task.metadata["end_time"] = time.time()
            self._current_task.metadata["duration"] = (
                time.time() - self._current_task.start_time
            )
            
            self._save_task_info()
            
            completed_task = self._current_task
            self._task_history.append(completed_task)
            
            if len(self._task_history) > self._max_history:
                self._task_history = self._task_history[-self._max_history:]
            
            self._current_task = None
            
            return completed_task
    
    def get_task_history(self, limit: int = 10) -> list[TaskInfo]:
        """获取任务历史"""
        with self._task_lock:
            return self._task_history[-limit:]
    
    def is_task_active(self) -> bool:
        """检查是否有活动任务"""
        with self._task_lock:
            return self._current_task is not None
    
    def reset(self):
        """重置任务管理器"""
        with self._task_lock:
            if self._current_task:
                self.end_task(success=False, reason="管理器重置")
            self._task_history.clear()
    
    def get_tasks_root(self) -> str:
        """获取任务根目录"""
        return self._tasks_root


_task_manager_instance: Optional[TaskManager] = None
_task_manager_lock = threading.RLock()


def get_task_manager() -> TaskManager:
    """获取全局任务管理器实例"""
    global _task_manager_instance
    
    with _task_manager_lock:
        if _task_manager_instance is None:
            _task_manager_instance = TaskManager()
        return _task_manager_instance


def get_current_task_id() -> Optional[str]:
    """获取当前任务ID（便捷函数）"""
    return get_task_manager().get_task_id()


def get_current_task_dir() -> Optional[str]:
    """获取当前任务目录（便捷函数）"""
    return get_task_manager().get_task_dir()


def start_new_task(objective: str = "", model: str = "", 
                   metadata: Dict[str, Any] = None) -> str:
    """开始新任务（便捷函数）"""
    return get_task_manager().start_task(objective=objective, model=model, metadata=metadata)


def end_current_task(success: bool = True, reason: str = "") -> Optional[TaskInfo]:
    """结束当前任务（便捷函数）"""
    return get_task_manager().end_task(success=success, reason=reason)
