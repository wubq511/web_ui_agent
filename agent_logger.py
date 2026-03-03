"""
================================================================================
日志模块 - 详细日志记录系统
================================================================================

【模块概述】
添加详细的日志记录系统，记录步骤执行情况、决策过程和资源消耗。

【核心功能】
1. 多级别日志记录
2. 结构化日志格式
3. 日志文件轮转
4. 执行追踪与性能分析
================================================================================
"""

import os
import json
import logging
import time
from typing import Optional, Any
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, field, asdict

from config import LOG_DIR, LOG_LEVEL, LOG_MAX_SIZE, LOG_BACKUP_COUNT
from security_utils import mask_string, is_sensitive_field, sanitize_log_message
from task_manager import get_current_task_id, get_task_manager


def _mask_step_log(log_dict: dict) -> dict:
    """脱敏步骤日志"""
    result = log_dict.copy()
    if result.get("value") and isinstance(result["value"], str):
        result["value"] = mask_string(result["value"], show_prefix=1, show_suffix=1)
    if result.get("thought") and isinstance(result["thought"], str):
        result["thought"] = sanitize_log_message(result["thought"])
    if result.get("result") and isinstance(result["result"], str):
        result["result"] = sanitize_log_message(result["result"])
    return result


def _mask_decision_log(log_dict: dict) -> dict:
    """脱敏决策日志"""
    result = log_dict.copy()
    if result.get("llm_response") and isinstance(result["llm_response"], str):
        result["llm_response"] = sanitize_log_message(result["llm_response"])
    if result.get("parsed_decision") and isinstance(result["parsed_decision"], dict):
        from security_utils import mask_sensitive_in_dict
        result["parsed_decision"] = mask_sensitive_in_dict(result["parsed_decision"])
    return result


@dataclass
class StepLog:
    """步骤日志记录"""
    step: int
    action_type: str
    target_id: Optional[int]
    value: Optional[str]
    thought: str
    result: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class DecisionLog:
    """决策日志记录"""
    step: int
    llm_response: str
    parsed_decision: dict
    reasoning_time_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class ResourceLog:
    """资源日志记录"""
    step: int
    memory_mb: float
    cpu_percent: float
    elapsed_time: float
    timestamp: float = field(default_factory=time.time)


class AgentLogger:
    """
    Agent日志记录器 - 详细的执行日志系统
    
    【设计思路】
    提供全面的日志记录功能：
    1. 控制台输出与文件记录
    2. 步骤执行详情
    3. LLM决策过程
    4. 资源消耗追踪
    5. 性能分析支持
    """
    
    def __init__(self, log_dir: str = LOG_DIR, 
                 log_level: str = LOG_LEVEL,
                 max_size: int = LOG_MAX_SIZE,
                 backup_count: int = LOG_BACKUP_COUNT,
                 task_id: str = None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.max_size = max_size
        self.backup_count = backup_count
        
        if task_id:
            self._session_id = task_id
        else:
            self._session_id = get_current_task_id()
            if not self._session_id:
                self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self._session_start_time = time.time()
        
        self._logger = self._setup_logger()
        self._step_logs: list[StepLog] = []
        self._decision_logs: list[DecisionLog] = []
        self._resource_logs: list[ResourceLog] = []
    
    def _setup_logger(self) -> logging.Logger:
        """
        设置日志记录器 - 每个会话使用独立的日志文件
        
        【设计思路】
        日志文件名包含会话ID，避免同一天多次运行时的命名冲突
        终端只显示重要信息，详细日志写入文件
        """
        logger = logging.getLogger(f"WebUIAgent_{self._session_id}")
        logger.setLevel(self.log_level)
        
        logger.handlers.clear()
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)
        
        log_file = self.log_dir / f"agent_{self._session_id}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=self.max_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        file_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
        
        return logger
    
    def log_session_start(self, objective: str, start_url: str = ""):
        """记录会话开始"""
        self._logger.info("=" * 60)
        self._logger.info("🚀 会话开始")
        self._logger.info(f"   会话ID: {self._session_id}")
        self._logger.info(f"   目标: {objective}")
        if start_url:
            self._logger.info(f"   起始URL: {start_url}")
        self._logger.info("=" * 60)
    
    def log_session_end(self, success: bool, step_count: int, 
                       duration: float, reason: str = ""):
        """记录会话结束"""
        status = "✅ 成功完成" if success else "❌ 未完成"
        self._logger.info("=" * 60)
        self._logger.info(f"🏁 会话结束: {status}")
        self._logger.info(f"   总步骤: {step_count}")
        self._logger.info(f"   总耗时: {duration:.2f}秒")
        if reason:
            self._logger.info(f"   结束原因: {reason}")
        self._logger.info("=" * 60)
    
    def log_step_start(self, step: int, action_type: str):
        """记录步骤开始"""
        self._logger.info(f"📍 步骤 {step} 开始: {action_type}")
    
    def log_step(self, step_log: StepLog):
        """记录步骤执行"""
        self._step_logs.append(step_log)
        
        self._logger.debug(
            f"📝 步骤 {step_log.step}: {step_log.action_type} "
            f"[{step_log.duration_ms:.0f}ms]"
        )
        if step_log.thought:
            self._logger.debug(f"   思考: {step_log.thought[:100]}")
        if step_log.result:
            self._logger.debug(f"   结果: {step_log.result[:100]}")
    
    def log_decision(self, decision_log: DecisionLog):
        """记录决策过程"""
        self._decision_logs.append(decision_log)
        
        self._logger.debug(
            f"🧠 决策 [{decision_log.reasoning_time_ms:.0f}ms]: "
            f"{decision_log.parsed_decision.get('action_type', 'unknown')}"
        )
    
    def log_resource(self, resource_log: ResourceLog):
        """记录资源使用"""
        self._resource_logs.append(resource_log)
        
        self._logger.debug(
            f"📊 资源: 内存 {resource_log.memory_mb:.1f}MB, "
            f"CPU {resource_log.cpu_percent:.1f}%, "
            f"耗时 {resource_log.elapsed_time:.1f}s"
        )
    
    def log_perception(self, elements_count: int, url: str):
        """记录感知结果"""
        self._logger.debug(f"👁️ 感知: 发现 {elements_count} 个元素")
        self._logger.debug(f"   URL: {url}")
    
    def log_action(self, action_type: str, target: str = "", 
                   result: str = "", success: bool = True):
        """记录动作执行"""
        status = "✅" if success else "❌"
        self._logger.info(f"{status} 动作: {action_type}")
        if target:
            self._logger.debug(f"   目标: {target}")
        if result:
            self._logger.debug(f"   结果: {result[:100]}")
    
    def log_error(self, error: str, step: int = 0):
        """记录错误"""
        self._logger.error(f"❌ 错误 (步骤 {step}): {error}")
    
    def log_warning(self, message: str):
        """记录警告"""
        self._logger.warning(f"⚠️ {message}")
    
    def log_info(self, message: str):
        """记录信息"""
        self._logger.info(f"ℹ️ {message}")
    
    def log_debug(self, message: str):
        """记录调试信息"""
        self._logger.debug(f"🔍 {message}")
    
    def log_termination(self, reason: str, details: str = ""):
        """记录终止"""
        self._logger.info(f"🛑 终止: {reason}")
        if details:
            self._logger.info(f"   详情: {details}")
    
    def log_checkpoint(self, checkpoint_id: str, step: int):
        """记录检查点"""
        self._logger.info(f"💾 检查点: {checkpoint_id} (步骤 {step})")
    
    def log_user_interaction(self, command: str, response: str):
        """记录用户交互"""
        self._logger.info(f"👤 用户命令: {command}")
        self._logger.debug(f"   响应: {response}")
    
    def get_step_summary(self) -> str:
        """获取步骤摘要"""
        if not self._step_logs:
            return "暂无步骤记录"
        
        total_duration = sum(log.duration_ms for log in self._step_logs)
        success_count = sum(1 for log in self._step_logs 
                          if "成功" in log.result or "success" in log.result.lower())
        
        summary_lines = [
            f"步骤执行摘要:",
            f"  总步骤数: {len(self._step_logs)}",
            f"  成功步骤: {success_count}",
            f"  总耗时: {total_duration:.0f}ms",
            f"  平均耗时: {total_duration / len(self._step_logs):.0f}ms"
        ]
        
        return "\n".join(summary_lines)
    
    def get_performance_report(self) -> dict:
        """获取性能报告"""
        if not self._step_logs:
            return {"error": "无步骤记录"}
        
        action_durations: dict[str, list[float]] = {}
        for log in self._step_logs:
            if log.action_type not in action_durations:
                action_durations[log.action_type] = []
            action_durations[log.action_type].append(log.duration_ms)
        
        action_stats = {}
        for action, durations in action_durations.items():
            action_stats[action] = {
                "count": len(durations),
                "total_ms": sum(durations),
                "avg_ms": sum(durations) / len(durations),
                "max_ms": max(durations),
                "min_ms": min(durations)
            }
        
        resource_summary = {}
        if self._resource_logs:
            memory_values = [log.memory_mb for log in self._resource_logs]
            cpu_values = [log.cpu_percent for log in self._resource_logs]
            resource_summary = {
                "memory_avg_mb": sum(memory_values) / len(memory_values),
                "memory_max_mb": max(memory_values),
                "cpu_avg_percent": sum(cpu_values) / len(cpu_values),
                "cpu_max_percent": max(cpu_values)
            }
        
        return {
            "session_id": self._session_id,
            "session_duration": time.time() - self._session_start_time,
            "total_steps": len(self._step_logs),
            "total_decisions": len(self._decision_logs),
            "action_stats": action_stats,
            "resource_summary": resource_summary
        }
    
    def save_session_log(self) -> str:
        """保存会话日志（自动脱敏敏感信息）"""
        log_file = self.log_dir / f"session_{self._session_id}.json"
        
        masked_steps = [_mask_step_log(asdict(log)) for log in self._step_logs]
        masked_decisions = [_mask_decision_log(asdict(log)) for log in self._decision_logs]
        
        session_data = {
            "session_id": self._session_id,
            "start_time": self._session_start_time,
            "end_time": time.time(),
            "performance": self.get_performance_report(),
            "steps": masked_steps,
            "decisions": masked_decisions,
            "resources": [asdict(log) for log in self._resource_logs]
        }
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            self._logger.info(f"📄 会话日志已保存: {log_file}")
            return str(log_file)
            
        except Exception as e:
            self._logger.error(f"保存会话日志失败: {e}")
            return ""
    
    def reset(self):
        """重置日志记录器"""
        self._step_logs.clear()
        self._decision_logs.clear()
        self._resource_logs.clear()
        self._session_id = get_current_task_id()
        if not self._session_id:
            self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_start_time = time.time()
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self._session_id,
            "session_start_time": self._session_start_time,
            "step_count": len(self._step_logs),
            "decision_count": len(self._decision_logs),
            "resource_count": len(self._resource_logs)
        }
