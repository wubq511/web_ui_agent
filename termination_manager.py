"""
================================================================================
终止条件模块 - 多条件终止机制
================================================================================

【模块概述】
设计合理的终止条件，包括正常完成、超时、资源不足等多种情况的处理逻辑。

【核心功能】
1. 多维度终止条件检测
2. 资源监控与限制
3. 超时管理
4. 终止原因记录与分析
================================================================================
"""

import time
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("⚠️ psutil 未安装，资源监控功能不可用。安装方法: pip install psutil")

from config import (
    TASK_TIMEOUT, RESOURCE_MEMORY_LIMIT, RESOURCE_CPU_THRESHOLD,
    ERROR_RETRY_LIMIT, PROGRESS_STAGNATION_THRESHOLD,
    PROGRESS_STAGNATION_MIN, PROGRESS_STAGNATION_MAX,
    PROGRESS_STAGNATION_DEFAULT, ENABLE_FAST_MODE,
    FAST_MODE_STAGNATION_THRESHOLD, ENABLE_HUMAN_INTERVENTION,
    INTERVENTION_PAUSE_DURATION,
    ERROR_TYPE_WEIGHTS, ERROR_SEVERITY_MULTIPLIERS,
    ERROR_RECOVERY_ACTIONS, CONSECUTIVE_ERROR_BONUS,
    SUCCESS_ERROR_REDUCTION, ERROR_LIMIT_MIN, ERROR_LIMIT_MAX,
    ERROR_LIMIT_DEFAULT, TASK_COMPLEXITY_WEIGHTS
)
from completion_evaluator import CompletionStatus, TaskComplexity, ProgressLevel


class ErrorType(Enum):
    """错误类型枚举 - 用于分类不同类型的错误"""
    TIMEOUT = "timeout"
    ELEMENT_NOT_FOUND = "element_not_found"
    CLICK_FAILED = "click_failed"
    INPUT_FAILED = "input_failed"
    NAVIGATION_FAILED = "navigation_failed"
    API_ERROR = "api_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """错误严重程度枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TerminationReason(Enum):
    """终止原因枚举"""
    NORMAL_COMPLETION = "normal_completion"
    STEP_LIMIT = "step_limit"
    TIMEOUT = "timeout"
    MEMORY_LIMIT = "memory_limit"
    CPU_LIMIT = "cpu_limit"
    ERROR_LIMIT = "error_limit"
    STAGNATION = "stagnation"
    USER_ABORT = "user_abort"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    UNKNOWN = "unknown"


@dataclass
class TerminationCheck:
    """终止检查结果"""
    should_terminate: bool
    reason: Optional[TerminationReason]
    message: str
    severity: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ResourceUsage:
    """资源使用情况"""
    memory_used: int
    memory_limit: int
    memory_percent: float
    cpu_percent: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class ErrorRecord:
    """
    错误记录 - 记录每次错误的详细信息
    
    【字段说明】
    error_type: 错误类型
    severity: 严重程度
    message: 错误消息
    step: 发生错误的步骤
    weight: 错误权重（根据类型和严重程度计算）
    timestamp: 发生时间
    """
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    step: int
    weight: float = 1.0
    timestamp: float = field(default_factory=time.time)
    recovered: bool = False


class TerminationManager:
    """
    终止条件管理器 - 多维度终止条件检测
    
    【设计思路】
    综合检测多种终止条件：
    1. 任务正常完成
    2. 步骤数超限
    3. 执行超时
    4. 内存资源不足
    5. CPU资源过载
    6. 错误次数过多（支持加权计数）
    7. 进度停滞（支持动态调整阈值）
    8. 用户主动终止
    9. 人工干预暂停（新增）
    10. 快速模式支持（新增）
    
    【错误处理机制】
    - 错误类型分类：timeout、element_not_found、click_failed 等
    - 严重程度分级：low、medium、high、critical
    - 加权错误计数：不同类型错误贡献不同的错误分数
    - 连续错误加成：连续错误会增加额外权重
    - 成功操作减分：成功操作可减少错误分数
    """
    
    def __init__(self, task_timeout: int = TASK_TIMEOUT,
                 memory_limit: int = RESOURCE_MEMORY_LIMIT,
                 cpu_threshold: float = RESOURCE_CPU_THRESHOLD,
                 error_limit: int = ERROR_RETRY_LIMIT,
                 fast_mode: bool = False):
        self.task_timeout = task_timeout
        self.memory_limit = memory_limit
        self.cpu_threshold = cpu_threshold
        self.error_limit = error_limit
        self.fast_mode = fast_mode
        
        self.start_time: Optional[float] = None
        self.termination_history: list[TerminationCheck] = []
        self.resource_history: list[ResourceUsage] = []
        self._user_abort_flag = False
        
        self.task_complexity: TaskComplexity = TaskComplexity.MEDIUM
        self.adjusted_stagnation_threshold: int = PROGRESS_STAGNATION_DEFAULT
        self._intervention_paused: bool = False
        self._intervention_pause_until: float = 0
        
        self.error_records: list[ErrorRecord] = []
        self.weighted_error_score: float = 0.0
        self.consecutive_errors: int = 0
        self.adjusted_error_limit: float = ERROR_LIMIT_DEFAULT
    
    def classify_error(self, error_message: str) -> ErrorType:
        """
        根据错误消息分类错误类型
        
        【参数】
        error_message: 错误消息
        
        【返回值】
        ErrorType: 错误类型
        """
        error_lower = error_message.lower()
        
        if "timeout" in error_lower or "超时" in error_lower:
            return ErrorType.TIMEOUT
        elif "not found" in error_lower or "未找到" in error_lower or "找不到" in error_lower:
            return ErrorType.ELEMENT_NOT_FOUND
        elif "click" in error_lower or "点击" in error_lower:
            return ErrorType.CLICK_FAILED
        elif "input" in error_lower or "输入" in error_lower or "type" in error_lower:
            return ErrorType.INPUT_FAILED
        elif "navigation" in error_lower or "导航" in error_lower or "goto" in error_lower:
            return ErrorType.NAVIGATION_FAILED
        elif "api" in error_lower or "llm" in error_lower or "model" in error_lower:
            return ErrorType.API_ERROR
        elif "network" in error_lower or "网络" in error_lower or "connection" in error_lower:
            return ErrorType.NETWORK_ERROR
        else:
            return ErrorType.UNKNOWN
    
    def assess_error_severity(self, error_type: ErrorType, error_message: str) -> ErrorSeverity:
        """
        评估错误严重程度
        
        【参数】
        error_type: 错误类型
        error_message: 错误消息
        
        【返回值】
        ErrorSeverity: 严重程度
        """
        if error_type == ErrorType.API_ERROR:
            return ErrorSeverity.CRITICAL
        elif error_type in [ErrorType.NETWORK_ERROR, ErrorType.NAVIGATION_FAILED]:
            return ErrorSeverity.HIGH
        elif error_type in [ErrorType.CLICK_FAILED, ErrorType.INPUT_FAILED]:
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW
    
    def record_error(self, error_message: str, step: int) -> ErrorRecord:
        """
        记录错误并计算加权错误分数
        
        【参数】
        error_message: 错误消息
        step: 当前步骤
        
        【返回值】
        ErrorRecord: 错误记录
        """
        error_type = self.classify_error(error_message)
        severity = self.assess_error_severity(error_type, error_message)
        
        type_weight = ERROR_TYPE_WEIGHTS.get(error_type.value, 1.0)
        severity_multiplier = ERROR_SEVERITY_MULTIPLIERS.get(severity.value, 1.0)
        
        base_weight = type_weight * severity_multiplier
        
        consecutive_bonus = 0.0
        if self.consecutive_errors > 0:
            consecutive_bonus = CONSECUTIVE_ERROR_BONUS * self.consecutive_errors
        
        total_weight = base_weight + consecutive_bonus
        
        record = ErrorRecord(
            error_type=error_type,
            severity=severity,
            message=error_message,
            step=step,
            weight=total_weight
        )
        
        self.error_records.append(record)
        self.weighted_error_score += total_weight
        self.consecutive_errors += 1
        
        return record
    
    def record_success(self):
        """
        记录成功操作 - 减少错误分数
        """
        self.consecutive_errors = 0
        
        if self.weighted_error_score > 0:
            self.weighted_error_score = max(0, self.weighted_error_score - SUCCESS_ERROR_REDUCTION)
    
    def get_effective_error_count(self) -> float:
        """
        获取有效错误计数（加权后的）
        
        【返回值】
        float: 有效错误计数
        """
        return self.weighted_error_score
    
    def update_error_limit_by_complexity(self):
        """
        根据任务复杂度调整错误限制阈值
        """
        complexity_weight = TASK_COMPLEXITY_WEIGHTS.get(self.task_complexity.value, 1.0)
        self.adjusted_error_limit = ERROR_LIMIT_DEFAULT * complexity_weight
        self.adjusted_error_limit = max(ERROR_LIMIT_MIN, min(ERROR_LIMIT_MAX, self.adjusted_error_limit))
    
    def get_recovery_action(self, error_type: ErrorType) -> str:
        """
        获取错误恢复建议
        
        【参数】
        error_type: 错误类型
        
        【返回值】
        str: 恢复动作建议
        """
        return ERROR_RECOVERY_ACTIONS.get(error_type.value, "retry")
    
    def set_task_complexity(self, complexity: TaskComplexity):
        """
        设置任务复杂度 - 用于动态调整终止阈值
        
        【参数】
        complexity: 任务复杂度级别
        """
        self.task_complexity = complexity
        self._update_stagnation_threshold()
        self.update_error_limit_by_complexity()
    
    def _update_stagnation_threshold(self, elapsed_steps: int = 0):
        """
        更新停滞阈值 - 根据复杂度和执行步数动态调整
        
        【参数】
        elapsed_steps: 已执行步数
        """
        from config import TASK_COMPLEXITY_WEIGHTS
        
        base_threshold = PROGRESS_STAGNATION_DEFAULT
        
        complexity_weight = TASK_COMPLEXITY_WEIGHTS.get(self.task_complexity.value, 1.0)
        adjusted = int(base_threshold * complexity_weight)
        
        if elapsed_steps > 20:
            step_bonus = min(3, (elapsed_steps - 20) // 10)
            adjusted += step_bonus
        
        if self.fast_mode:
            adjusted = min(adjusted, FAST_MODE_STAGNATION_THRESHOLD)
        
        self.adjusted_stagnation_threshold = max(
            PROGRESS_STAGNATION_MIN, 
            min(PROGRESS_STAGNATION_MAX, adjusted)
        )
    
    def enable_fast_mode(self, enabled: bool = True):
        """
        启用/禁用快速模式 - 使用更严格的终止条件
        
        【参数】
        enabled: 是否启用快速模式
        """
        self.fast_mode = enabled
        if enabled:
            self.adjusted_stagnation_threshold = FAST_MODE_STAGNATION_THRESHOLD
    
    def set_intervention_pause(self, duration: int = None):
        """
        设置人工干预暂停 - 暂停终止倒计时
        
        【参数】
        duration: 暂停时长（秒），默认使用配置值
        """
        if duration is None:
            duration = INTERVENTION_PAUSE_DURATION
        self._intervention_paused = True
        self._intervention_pause_until = time.time() + duration
    
    def clear_intervention_pause(self):
        """清除人工干预暂停"""
        self._intervention_paused = False
        self._intervention_pause_until = 0
    
    def is_intervention_paused(self) -> bool:
        """检查是否处于人工干预暂停状态"""
        if self._intervention_paused and time.time() > self._intervention_pause_until:
            self._intervention_paused = False
        return self._intervention_paused
    
    def request_intervention(self, duration: int = None) -> bool:
        """
        请求人工干预 - 在关键节点暂停终止倒计时
        
        【参数】
        duration: 暂停时长（秒）
        
        【返回值】
        bool: 是否成功设置干预暂停
        """
        if not ENABLE_HUMAN_INTERVENTION:
            return False
        self.set_intervention_pause(duration)
        return True
    
    def start(self):
        """开始计时"""
        self.start_time = time.time()
        self._user_abort_flag = False
    
    def get_elapsed_time(self) -> float:
        """获取已用时间（秒）"""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time
    
    def get_remaining_time(self) -> float:
        """获取剩余时间（秒）"""
        return max(0, self.task_timeout - self.get_elapsed_time())
    
    def get_current_resource_usage(self) -> ResourceUsage:
        """
        获取当前资源使用情况
        
        【返回值】
        ResourceUsage: 资源使用情况对象
        """
        if HAS_PSUTIL:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_used = memory_info.rss
            cpu_percent = process.cpu_percent(interval=0.1)
        else:
            memory_used = 0
            cpu_percent = 0.0
        
        usage = ResourceUsage(
            memory_used=memory_used,
            memory_limit=self.memory_limit,
            memory_percent=memory_used / self.memory_limit * 100 if self.memory_limit > 0 else 0,
            cpu_percent=cpu_percent
        )
        
        self.resource_history.append(usage)
        
        if len(self.resource_history) > 100:
            self.resource_history = self.resource_history[-100:]
        
        return usage
    
    def check_timeout(self) -> TerminationCheck:
        """检查是否超时"""
        elapsed = self.get_elapsed_time()
        
        if elapsed >= self.task_timeout:
            return TerminationCheck(
                should_terminate=True,
                reason=TerminationReason.TIMEOUT,
                message=f"任务执行超时: {elapsed:.1f}秒 >= {self.task_timeout}秒",
                severity="high"
            )
        
        if elapsed >= self.task_timeout * 0.9:
            return TerminationCheck(
                should_terminate=False,
                reason=None,
                message=f"即将超时: 剩余 {self.get_remaining_time():.1f}秒",
                severity="warning"
            )
        
        return TerminationCheck(
            should_terminate=False,
            reason=None,
            message=f"时间正常: 已用 {elapsed:.1f}秒, 剩余 {self.get_remaining_time():.1f}秒",
            severity="info"
        )
    
    def check_memory(self) -> TerminationCheck:
        """检查内存使用"""
        usage = self.get_current_resource_usage()
        
        if usage.memory_used >= self.memory_limit:
            return TerminationCheck(
                should_terminate=True,
                reason=TerminationReason.MEMORY_LIMIT,
                message=f"内存超限: {usage.memory_used / 1024 / 1024:.1f}MB >= {self.memory_limit / 1024 / 1024:.1f}MB",
                severity="critical"
            )
        
        if usage.memory_percent >= 90:
            return TerminationCheck(
                should_terminate=False,
                reason=None,
                message=f"内存使用率高: {usage.memory_percent:.1f}%",
                severity="warning"
            )
        
        return TerminationCheck(
            should_terminate=False,
            reason=None,
            message=f"内存正常: {usage.memory_percent:.1f}%",
            severity="info"
        )
    
    def check_cpu(self) -> TerminationCheck:
        """检查CPU使用"""
        usage = self.get_current_resource_usage()
        
        if usage.cpu_percent >= self.cpu_threshold:
            return TerminationCheck(
                should_terminate=True,
                reason=TerminationReason.CPU_LIMIT,
                message=f"CPU使用率过高: {usage.cpu_percent:.1f}% >= {self.cpu_threshold}%",
                severity="high"
            )
        
        if usage.cpu_percent >= self.cpu_threshold * 0.9:
            return TerminationCheck(
                should_terminate=False,
                reason=None,
                message=f"CPU使用率较高: {usage.cpu_percent:.1f}%",
                severity="warning"
            )
        
        return TerminationCheck(
            should_terminate=False,
            reason=None,
            message=f"CPU正常: {usage.cpu_percent:.1f}%",
            severity="info"
        )
    
    def check_step_limit(self, current_step: int, max_steps: int) -> TerminationCheck:
        """检查步骤限制"""
        if current_step >= max_steps:
            return TerminationCheck(
                should_terminate=True,
                reason=TerminationReason.STEP_LIMIT,
                message=f"达到步骤限制: {current_step} >= {max_steps}",
                severity="high"
            )
        
        remaining = max_steps - current_step
        if remaining <= 3:
            return TerminationCheck(
                should_terminate=False,
                reason=None,
                message=f"即将达到步骤限制: 剩余 {remaining} 步",
                severity="warning"
            )
        
        return TerminationCheck(
            should_terminate=False,
            reason=None,
            message=f"步骤正常: {current_step}/{max_steps}",
            severity="info"
        )
    
    def check_errors(self, error_count: int = None) -> TerminationCheck:
        """
        检查错误次数 - 增强版，支持加权错误计数
        
        【参数】
        error_count: 简单错误计数（可选，用于兼容旧接口）
        
        【返回值】
        TerminationCheck: 终止检查结果
        
        【逻辑说明】
        - 使用加权错误分数而非简单计数
        - 根据任务复杂度动态调整错误限制
        - 考虑连续错误的累积效应
        """
        effective_limit = self.adjusted_error_limit
        effective_count = self.weighted_error_score
        
        if error_count is not None and error_count >= self.error_limit:
            effective_count = error_count
            effective_limit = self.error_limit
        
        if effective_count >= effective_limit:
            error_summary = self._get_error_summary()
            return TerminationCheck(
                should_terminate=True,
                reason=TerminationReason.ERROR_LIMIT,
                message=f"错误分数过高: {effective_count:.1f}/{effective_limit:.1f} ({error_summary})",
                severity="high"
            )
        
        if effective_count >= effective_limit * 0.7:
            return TerminationCheck(
                should_terminate=False,
                reason=None,
                message=f"错误分数较高: {effective_count:.1f}/{effective_limit:.1f}",
                severity="warning"
            )
        
        return TerminationCheck(
            should_terminate=False,
            reason=None,
            message=f"错误分数正常: {effective_count:.1f}/{effective_limit:.1f}",
            severity="info"
        )
    
    def _get_error_summary(self) -> str:
        """获取错误摘要"""
        if not self.error_records:
            return "无错误记录"
        
        type_counts = {}
        for record in self.error_records:
            type_name = record.error_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        summary_parts = [f"{k}:{v}" for k, v in list(type_counts.items())[:3]]
        return ", ".join(summary_parts)
    
    def check_stagnation(self, stagnation_count: int, 
                         progress_level: ProgressLevel = None) -> TerminationCheck:
        """
        检查进度停滞 - 增强版，支持动态阈值和进展程度
        
        【参数】
        stagnation_count: 当前停滞计数
        progress_level: 进展程度（可选）
        
        【返回值】
        TerminationCheck: 终止检查结果
        """
        if self.is_intervention_paused():
            return TerminationCheck(
                should_terminate=False,
                reason=None,
                message=f"人工干预暂停中，终止倒计时已暂停",
                severity="info"
            )
        
        threshold = self.adjusted_stagnation_threshold
        
        if stagnation_count >= threshold:
            return TerminationCheck(
                should_terminate=True,
                reason=TerminationReason.STAGNATION,
                message=f"进度停滞: 连续 {stagnation_count}/{threshold} 次无进展 (复杂度: {self.task_complexity.value})",
                severity="high"
            )
        
        if stagnation_count >= threshold * 0.7:
            return TerminationCheck(
                should_terminate=False,
                reason=None,
                message=f"进度可能停滞: {stagnation_count}/{threshold} 次 (复杂度: {self.task_complexity.value})",
                severity="warning"
            )
        
        progress_info = f", 进展程度: {progress_level.value}" if progress_level else ""
        return TerminationCheck(
            should_terminate=False,
            reason=None,
            message=f"进度正常{progress_info}",
            severity="info"
        )
    
    def check_user_abort(self) -> TerminationCheck:
        """检查用户终止"""
        if self._user_abort_flag:
            return TerminationCheck(
                should_terminate=True,
                reason=TerminationReason.USER_ABORT,
                message="用户主动终止任务",
                severity="high"
            )
        
        return TerminationCheck(
            should_terminate=False,
            reason=None,
            message="无用户终止请求",
            severity="info"
        )
    
    def request_user_abort(self):
        """请求用户终止"""
        self._user_abort_flag = True
    
    def check_all(self, current_step: int, max_steps: int,
                  error_count: int, stagnation_count: int,
                  completion_status: CompletionStatus,
                  progress_level: ProgressLevel = None) -> TerminationCheck:
        """
        综合检查所有终止条件 - 增强版，支持动态阈值和进展程度
        
        【参数】
        current_step: 当前步骤数
        max_steps: 最大步骤数
        error_count: 错误计数
        stagnation_count: 停滞计数
        completion_status: 完成状态
        progress_level: 进展程度（可选）
        
        【返回值】
        TerminationCheck: 终止检查结果
        """
        self._update_stagnation_threshold(current_step)
        
        if completion_status == CompletionStatus.CONFIRMED_COMPLETE:
            check = TerminationCheck(
                should_terminate=True,
                reason=TerminationReason.NORMAL_COMPLETION,
                message="任务正常完成",
                severity="info"
            )
            self.termination_history.append(check)
            return check
        
        if self.is_intervention_paused():
            return TerminationCheck(
                should_terminate=False,
                reason=None,
                message="人工干预暂停中，跳过终止检查",
                severity="info"
            )
        
        checks = [
            self.check_user_abort(),
            self.check_timeout(),
            self.check_memory(),
            self.check_cpu(),
            self.check_step_limit(current_step, max_steps),
            self.check_errors(),
            self.check_stagnation(stagnation_count, progress_level)
        ]
        
        for check in checks:
            if check.should_terminate:
                self.termination_history.append(check)
                return check
        
        warning_messages = [
            check.message for check in checks
            if check.severity == "warning"
        ]
        
        if warning_messages:
            message = "; ".join(warning_messages)
        else:
            message = "所有检查通过"
        
        result = TerminationCheck(
            should_terminate=False,
            reason=None,
            message=message,
            severity="info"
        )
        
        return result
    
    def get_termination_summary(self) -> str:
        """获取终止检查摘要 - 增强版，包含复杂度和阈值信息"""
        summary_lines = [
            f"任务超时限制: {self.task_timeout}秒",
            f"已执行时间: {self.get_elapsed_time():.1f}秒",
            f"剩余时间: {self.get_remaining_time():.1f}秒",
            f"任务复杂度: {self.task_complexity.value}",
            f"停滞阈值: {self.adjusted_stagnation_threshold} (范围: {PROGRESS_STAGNATION_MIN}-{PROGRESS_STAGNATION_MAX})",
            f"错误分数: {self.weighted_error_score:.1f}/{self.adjusted_error_limit:.1f}",
            f"连续错误: {self.consecutive_errors}",
            f"快速模式: {'启用' if self.fast_mode else '禁用'}",
            f"人工干预暂停: {'是' if self._intervention_paused else '否'}",
            "",
            "终止检查历史:"
        ]
        
        for check in self.termination_history[-10:]:
            timestamp_str = datetime.fromtimestamp(check.timestamp).strftime("%H:%M:%S")
            summary_lines.append(
                f"  [{timestamp_str}] {check.severity.upper()}: {check.message}"
            )
        
        if self.error_records:
            summary_lines.extend(["", "错误记录:"])
            for record in self.error_records[-5:]:
                summary_lines.append(
                    f"  步骤{record.step}: [{record.error_type.value}] {record.message[:40]} (权重:{record.weight:.1f})"
                )
        
        return "\n".join(summary_lines)
    
    def reset(self):
        """重置管理器"""
        self.start_time = None
        self._user_abort_flag = False
        self.termination_history.clear()
        self.resource_history.clear()
        self.task_complexity = TaskComplexity.MEDIUM
        self.adjusted_stagnation_threshold = PROGRESS_STAGNATION_DEFAULT
        self._intervention_paused = False
        self._intervention_pause_until = 0
        self.error_records.clear()
        self.weighted_error_score = 0.0
        self.consecutive_errors = 0
        self.adjusted_error_limit = ERROR_LIMIT_DEFAULT
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "task_timeout": self.task_timeout,
            "memory_limit": self.memory_limit,
            "cpu_threshold": self.cpu_threshold,
            "error_limit": self.error_limit,
            "start_time": self.start_time,
            "elapsed_time": self.get_elapsed_time(),
            "user_abort_requested": self._user_abort_flag,
            "termination_count": len(self.termination_history),
            "task_complexity": self.task_complexity.value,
            "adjusted_stagnation_threshold": self.adjusted_stagnation_threshold,
            "fast_mode": self.fast_mode,
            "intervention_paused": self._intervention_paused,
            "weighted_error_score": self.weighted_error_score,
            "consecutive_errors": self.consecutive_errors,
            "adjusted_error_limit": self.adjusted_error_limit
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TerminationManager':
        """从字典创建实例"""
        manager = cls(
            task_timeout=data.get("task_timeout", TASK_TIMEOUT),
            memory_limit=data.get("memory_limit", RESOURCE_MEMORY_LIMIT),
            cpu_threshold=data.get("cpu_threshold", RESOURCE_CPU_THRESHOLD),
            error_limit=data.get("error_limit", ERROR_RETRY_LIMIT),
            fast_mode=data.get("fast_mode", False)
        )
        manager.start_time = data.get("start_time")
        manager._user_abort_flag = data.get("user_abort_requested", False)
        complexity_str = data.get("task_complexity", "medium")
        manager.task_complexity = TaskComplexity(complexity_str)
        manager.adjusted_stagnation_threshold = data.get(
            "adjusted_stagnation_threshold", PROGRESS_STAGNATION_DEFAULT
        )
        manager._intervention_paused = data.get("intervention_paused", False)
        manager.weighted_error_score = data.get("weighted_error_score", 0.0)
        manager.consecutive_errors = data.get("consecutive_errors", 0)
        manager.adjusted_error_limit = data.get("adjusted_error_limit", ERROR_LIMIT_DEFAULT)
        return manager
