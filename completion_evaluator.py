"""
================================================================================
完成度评估模块 - 任务完成度评估系统
================================================================================

【模块概述】
实现任务完成度评估功能，准确判断任务是否真正完成而非简单计数。

【核心功能】
1. 基于多维度指标评估任务完成度
2. 检测任务停滞状态
3. 分析执行历史判断进度
4. 提供完成置信度评分
================================================================================
"""

from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
import re

from config import (
    COMPLETION_CONFIDENCE_THRESHOLD,
    PROGRESS_STAGNATION_THRESHOLD,
    PROGRESS_STAGNATION_MIN,
    PROGRESS_STAGNATION_MAX,
    PROGRESS_STAGNATION_DEFAULT,
    TASK_COMPLEXITY_KEYWORDS,
    TASK_COMPLEXITY_WEIGHTS,
    PROGRESS_LEVEL_THRESHOLD,
    TaskComplexity
)


class CompletionStatus(Enum):
    """完成状态枚举"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    LIKELY_COMPLETE = "likely_complete"
    CONFIRMED_COMPLETE = "confirmed_complete"
    STAGNANT = "stagnant"
    FAILED = "failed"


class ProgressLevel(Enum):
    """进展程度枚举 - 区分完全无进展和部分进展"""
    NO_PROGRESS = "no_progress"
    PARTIAL_PROGRESS = "partial_progress"
    SIGNIFICANT_PROGRESS = "significant_progress"
    FULL_PROGRESS = "full_progress"


@dataclass
class ProgressIndicator:
    """进度指标"""
    name: str
    weight: float
    value: float
    description: str = ""


@dataclass
class CompletionAssessment:
    """完成度评估结果"""
    status: CompletionStatus
    confidence: float
    progress_ratio: float
    indicators: list[ProgressIndicator]
    stagnation_count: int
    recommendation: str
    details: str = ""
    task_complexity: TaskComplexity = TaskComplexity.MEDIUM
    progress_level: ProgressLevel = ProgressLevel.NO_PROGRESS
    adjusted_stagnation_threshold: int = PROGRESS_STAGNATION_DEFAULT


class CompletionEvaluator:
    """
    完成度评估器 - 多维度任务完成度分析
    
    【设计思路】
    通过多个维度综合评估任务完成度：
    1. 目标关键词匹配度
    2. 页面状态变化分析
    3. 操作历史有效性
    4. 错误恢复情况
    5. 进度停滞检测
    6. 任务复杂度评估（新增）
    7. 进展程度量化（新增）
    """
    
    def __init__(self):
        self.stagnation_count = 0
        self.last_progress_ratio = 0.0
        self.progress_history: list[float] = []
        self.assessment_history: list[CompletionAssessment] = []
        self.task_complexity: TaskComplexity = TaskComplexity.MEDIUM
        # 停滞阈值由 TerminationManager 统一管理，通过参数传入
        self._intervention_paused: bool = False
        self._intervention_pause_until: float = 0
    
    def evaluate_task_complexity(self, objective: str) -> TaskComplexity:
        """
        评估任务复杂度 - 根据目标描述中的关键词判断
        
        【参数】
        objective: 任务目标描述
        
        【返回值】
        TaskComplexity: 任务复杂度级别
        
        【评估规则】（修正版 v2）
        - very_complex_score >= 1 或 complex_score >= 3 → VERY_COMPLEX
        - complex_score >= 1 → COMPLEX（单个complex关键词即可）
        - medium_score >= 2 → MEDIUM
        - medium_score >= 1 或 simple_score >= 2 → MEDIUM
        - 否则 → SIMPLE
        """
        objective_lower = objective.lower()
        
        very_complex_score = 0
        complex_score = 0
        medium_score = 0
        simple_score = 0
        
        for keyword in TASK_COMPLEXITY_KEYWORDS.get("very_complex", []):
            if keyword.lower() in objective_lower:
                very_complex_score += 1
        
        for keyword in TASK_COMPLEXITY_KEYWORDS["complex"]:
            if keyword.lower() in objective_lower:
                complex_score += 1
        
        for keyword in TASK_COMPLEXITY_KEYWORDS["medium"]:
            if keyword.lower() in objective_lower:
                medium_score += 1
        
        for keyword in TASK_COMPLEXITY_KEYWORDS["simple"]:
            if keyword.lower() in objective_lower:
                simple_score += 1
        
        # 修正后的评估规则 v2
        if very_complex_score >= 1 or complex_score >= 3:
            return TaskComplexity.VERY_COMPLEX
        elif complex_score >= 1:
            return TaskComplexity.COMPLEX
        elif medium_score >= 2:
            return TaskComplexity.MEDIUM
        elif medium_score >= 1 or simple_score >= 2:
            return TaskComplexity.MEDIUM
        else:
            return TaskComplexity.SIMPLE
    
    # 注意: calculate_adjusted_stagnation_threshold 已移至 TerminationManager
    # CompletionEvaluator 通过参数接收阈值，不再内部计算
    
    def classify_progress_level(self, progress_delta: float) -> ProgressLevel:
        """
        分类进展程度 - 区分完全无进展和部分进展
        
        【参数】
        progress_delta: 进度变化量
        
        【返回值】
        ProgressLevel: 进展程度级别
        
        【逻辑说明】
        - progress_delta >= 0.08: 显著进展，停滞计数 -2
        - progress_delta >= 0.02: 部分进展，停滞计数 -1
        - progress_delta >= 0.005: 微小进展，停滞计数不变
        - progress_delta < 0.005: 无进展，停滞计数 +1
        """
        if progress_delta >= PROGRESS_LEVEL_THRESHOLD["significant_progress"]:
            return ProgressLevel.SIGNIFICANT_PROGRESS
        elif progress_delta >= PROGRESS_LEVEL_THRESHOLD["partial_progress"]:
            return ProgressLevel.PARTIAL_PROGRESS
        elif progress_delta >= PROGRESS_LEVEL_THRESHOLD["no_progress"]:
            return ProgressLevel.PARTIAL_PROGRESS
        else:
            return ProgressLevel.NO_PROGRESS
    
    def set_intervention_pause(self, duration: int = 60):
        """
        设置人工干预暂停 - 暂停终止倒计时
        
        【参数】
        duration: 暂停时长（秒）
        """
        import time
        self._intervention_paused = True
        self._intervention_pause_until = time.time() + duration
    
    def clear_intervention_pause(self):
        """清除人工干预暂停"""
        self._intervention_paused = False
        self._intervention_pause_until = 0
    
    def is_intervention_paused(self) -> bool:
        """检查是否处于人工干预暂停状态"""
        import time
        if self._intervention_paused and time.time() > self._intervention_pause_until:
            self._intervention_paused = False
        return self._intervention_paused
    
    def extract_keywords(self, objective: str) -> list[str]:
        """
        从目标描述中提取关键词
        
        【参数】
        objective: 任务目标描述
        
        【返回值】
        list[str]: 关键词列表
        """
        objective_lower = objective.lower()
        
        action_keywords = ['购买', '搜索', '查找', '点击', '输入', '选择', '提交',
                          'buy', 'search', 'find', 'click', 'type', 'select', 'submit']
        
        target_keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', objective)
        
        keywords = []
        for kw in action_keywords:
            if kw in objective_lower:
                keywords.append(kw)
        
        for kw in target_keywords:
            if len(kw) > 1 and kw not in keywords:
                keywords.append(kw)
        
        return keywords
    
    def evaluate_goal_progress(self, objective: str, history: list[dict],
                               current_url: str) -> ProgressIndicator:
        """
        评估目标进度
        
        【参数】
        objective: 任务目标
        history: 执行历史
        current_url: 当前URL
        
        【返回值】
        ProgressIndicator: 目标进度指标
        
        【修复说明】
        - 权重调整为0.35，确保权重总和为1.0
        - done动作检测移到函数开头，优先判断
        """
        done_actions = [e for e in history if e.get("action_type") == "done"]
        if done_actions:
            return ProgressIndicator(
                name="goal_progress",
                weight=0.35,
                value=1.0,
                description="检测到done动作，任务已完成"
            )
        
        keywords = self.extract_keywords(objective)
        if not keywords:
            return ProgressIndicator(
                name="goal_progress",
                weight=0.35,
                value=0.0,
                description="无法提取目标关键词"
            )
        
        matched_keywords = set()
        for entry in history:
            thought = entry.get("thought", "").lower()
            action = entry.get("action_type", "").lower()
            result = entry.get("result", "").lower()
            
            for kw in keywords:
                if kw.lower() in thought or kw.lower() in action or kw.lower() in result:
                    matched_keywords.add(kw)
        
        match_ratio = len(matched_keywords) / len(keywords) if keywords else 0
        
        return ProgressIndicator(
            name="goal_progress",
            weight=0.35,
            value=match_ratio,
            description=f"关键词匹配: {len(matched_keywords)}/{len(keywords)}"
        )
    
    def evaluate_action_effectiveness(self, history: list[dict]) -> ProgressIndicator:
        """
        评估操作有效性
        
        【参数】
        history: 执行历史
        
        【返回值】
        ProgressIndicator: 操作有效性指标
        
        【修复说明】
        - 权重调整为0.25（保持不变）
        """
        if not history:
            return ProgressIndicator(
                name="action_effectiveness",
                weight=0.25,
                value=0.0,
                description="暂无操作历史"
            )
        
        successful_actions = 0
        total_actions = len(history)
        
        for entry in history:
            result = entry.get("result", "").lower()
            if "成功" in result or "success" in result or "完成" in result:
                successful_actions += 1
            elif "错误" in result or "error" in result or "失败" in result:
                pass
            else:
                successful_actions += 0.5
        
        effectiveness = successful_actions / total_actions if total_actions > 0 else 0
        
        return ProgressIndicator(
            name="action_effectiveness",
            weight=0.25,
            value=effectiveness,
            description=f"有效操作: {successful_actions}/{total_actions}"
        )
    
    def evaluate_page_progress(self, history: list[dict], 
                               current_url: str) -> ProgressIndicator:
        """
        评估页面进度
        
        【参数】
        history: 执行历史
        current_url: 当前URL
        
        【返回值】
        ProgressIndicator: 页面进度指标
        
        【修复说明】
        - 权重调整为0.20（保持不变）
        """
        if not history:
            return ProgressIndicator(
                name="page_progress",
                weight=0.20,
                value=0.0,
                description="暂无页面变化"
            )
        
        url_changes = 0
        last_url = None
        
        for entry in history:
            goto_actions = [e for e in history if e.get("action_type") == "goto"]
            url_changes = len(goto_actions)
        
        navigation_actions = ["goto", "click", "press"]
        nav_count = sum(1 for e in history if e.get("action_type") in navigation_actions)
        
        progress = min(1.0, nav_count / 5)
        
        return ProgressIndicator(
            name="page_progress",
            weight=0.2,
            value=progress,
            description=f"导航操作: {nav_count}次"
        )
    
    def evaluate_error_recovery(self, history: list[dict]) -> ProgressIndicator:
        """
        评估错误恢复情况
        
        【参数】
        history: 执行历史
        
        【返回值】
        ProgressIndicator: 错误恢复指标
        
        【修复说明】
        - 权重调整为0.20，确保权重总和为1.0 (0.35+0.25+0.20+0.20=1.0)
        - 空历史时返回0.0而非1.0，避免无操作时产生进度
        """
        if not history:
            return ProgressIndicator(
                name="error_recovery",
                weight=0.20,
                value=0.0,
                description="暂无操作历史"
            )
        
        error_count = 0
        recovered_count = 0
        
        for i, entry in enumerate(history):
            result = entry.get("result", "").lower()
            if "错误" in result or "error" in result or "失败" in result:
                error_count += 1
                if i + 1 < len(history):
                    next_result = history[i + 1].get("result", "").lower()
                    if "成功" in next_result or "success" in next_result:
                        recovered_count += 1
        
        if error_count == 0:
            value = 1.0
        else:
            value = recovered_count / error_count
        
        return ProgressIndicator(
            name="error_recovery",
            weight=0.20,
            value=value,
            description=f"错误恢复: {recovered_count}/{error_count}"
        )
    
    def detect_stagnation(self, progress_ratio: float, 
                          adjusted_threshold: int) -> tuple[int, ProgressLevel]:
        """
        检测进度停滞 - 增强版，区分完全无进展和部分进展
        
        【参数】
        progress_ratio: 当前进度比率
        adjusted_threshold: 调整后的停滞阈值（由 TerminationManager 提供）
        
        【返回值】
        tuple[int, ProgressLevel]: (停滞计数, 进展程度)
        
        【逻辑说明】
        - 进度增加 >= 0.08: 显著进展，停滞计数 -2
        - 进度增加 >= 0.02: 部分进展，停滞计数 -1
        - 进度增加 >= 0.005: 微小进展，停滞计数不变（不增不减）
        - 进度变化 < 0.005: 无进展，停滞计数 +1
        - 进度倒退: 停滞计数 +1（但不会超过阈值上限）
        """
        if self.is_intervention_paused():
            return self.stagnation_count, ProgressLevel.PARTIAL_PROGRESS
        
        progress_delta = progress_ratio - self.last_progress_ratio
        
        if progress_delta < 0:
            progress_level = ProgressLevel.NO_PROGRESS
            self.stagnation_count += 1
        else:
            progress_level = self.classify_progress_level(progress_delta)
            
            if progress_level == ProgressLevel.NO_PROGRESS:
                self.stagnation_count += 1
            elif progress_level == ProgressLevel.PARTIAL_PROGRESS:
                self.stagnation_count = max(0, self.stagnation_count - 1)
            elif progress_level == ProgressLevel.SIGNIFICANT_PROGRESS:
                self.stagnation_count = max(0, self.stagnation_count - 2)
        
        self.progress_history.append(progress_ratio)
        self.last_progress_ratio = progress_ratio
        
        return self.stagnation_count, progress_level
    
    def assess_completion(self, objective: str, history: list[dict],
                         current_url: str, is_done: bool = False,
                         fast_mode: bool = False,
                         stagnation_threshold: int = None) -> CompletionAssessment:
        """
        综合评估任务完成度 - 增强版，支持复杂度评估和进展程度量化
        
        【参数】
        objective: 任务目标
        history: 执行历史
        current_url: 当前URL
        is_done: 是否已标记完成
        fast_mode: 是否启用快速模式（使用更严格的阈值）
        stagnation_threshold: 停滞阈值（由 TerminationManager 提供，推荐使用）
        
        【返回值】
        CompletionAssessment: 完成度评估结果
        
        【修复说明】
        - 增加对历史中done动作的检测，优先返回100%进度
        - 确保任务完成时进度正确显示为100%
        - 停滞阈值统一由 TerminationManager 管理，通过参数传入
        """
        default_threshold = PROGRESS_STAGNATION_DEFAULT
        
        if is_done:
            return CompletionAssessment(
                status=CompletionStatus.CONFIRMED_COMPLETE,
                confidence=1.0,
                progress_ratio=1.0,
                indicators=[],
                stagnation_count=0,
                recommendation="任务已完成",
                task_complexity=self.task_complexity,
                progress_level=ProgressLevel.FULL_PROGRESS,
                adjusted_stagnation_threshold=stagnation_threshold or default_threshold
            )
        
        done_actions = [e for e in history if e.get("action_type") == "done"]
        if done_actions:
            return CompletionAssessment(
                status=CompletionStatus.CONFIRMED_COMPLETE,
                confidence=1.0,
                progress_ratio=1.0,
                indicators=[],
                stagnation_count=0,
                recommendation="检测到done动作，任务已完成",
                task_complexity=self.task_complexity,
                progress_level=ProgressLevel.FULL_PROGRESS,
                adjusted_stagnation_threshold=stagnation_threshold or default_threshold
            )
        
        if len(self.assessment_history) == 0:
            self.task_complexity = self.evaluate_task_complexity(objective)
        
        # 使用外部传入的阈值，否则使用默认值
        # 快速模式强制使用更严格的阈值
        if fast_mode:
            effective_threshold = PROGRESS_STAGNATION_THRESHOLD
        elif stagnation_threshold is not None:
            effective_threshold = stagnation_threshold
        else:
            effective_threshold = default_threshold
        
        indicators = [
            self.evaluate_goal_progress(objective, history, current_url),
            self.evaluate_action_effectiveness(history),
            self.evaluate_page_progress(history, current_url),
            self.evaluate_error_recovery(history)
        ]
        
        weighted_sum = sum(ind.value * ind.weight for ind in indicators)
        total_weight = sum(ind.weight for ind in indicators)
        progress_ratio = weighted_sum / total_weight if total_weight > 0 else 0
        
        stagnation, progress_level = self.detect_stagnation(progress_ratio, effective_threshold)
        
        if stagnation >= effective_threshold:
            status = CompletionStatus.STAGNANT
            confidence = 0.3
            recommendation = f"任务进度停滞（{stagnation}/{effective_threshold}），建议调整策略或增加步骤限制"
        elif progress_ratio >= COMPLETION_CONFIDENCE_THRESHOLD:
            status = CompletionStatus.LIKELY_COMPLETE
            confidence = progress_ratio
            recommendation = "任务可能已完成，建议确认或执行done操作"
        elif progress_ratio >= 0.5:
            status = CompletionStatus.IN_PROGRESS
            confidence = progress_ratio
            recommendation = "任务进行中，继续执行"
        elif len(history) == 0:
            status = CompletionStatus.NOT_STARTED
            confidence = 0.0
            recommendation = "任务未开始"
        else:
            status = CompletionStatus.IN_PROGRESS
            confidence = progress_ratio
            recommendation = "任务进行中"
        
        assessment = CompletionAssessment(
            status=status,
            confidence=confidence,
            progress_ratio=progress_ratio,
            indicators=indicators,
            stagnation_count=stagnation,
            recommendation=recommendation,
            task_complexity=self.task_complexity,
            progress_level=progress_level,
            adjusted_stagnation_threshold=effective_threshold
        )
        
        self.assessment_history.append(assessment)
        
        return assessment
    
    def get_completion_summary(self) -> str:
        """获取完成度摘要 - 增强版，包含复杂度和进展程度信息"""
        if not self.assessment_history:
            return "暂无评估记录"
        
        latest = self.assessment_history[-1]
        summary_lines = [
            f"完成状态: {latest.status.value}",
            f"置信度: {latest.confidence:.2%}",
            f"进度比率: {latest.progress_ratio:.2%}",
            f"任务复杂度: {latest.task_complexity.value}",
            f"进展程度: {latest.progress_level.value}",
            f"停滞计数: {latest.stagnation_count}/{latest.adjusted_stagnation_threshold}",
            f"建议: {latest.recommendation}",
            "",
            "指标详情:"
        ]
        
        for ind in latest.indicators:
            summary_lines.append(
                f"  - {ind.name}: {ind.value:.2%} (权重: {ind.weight}) - {ind.description}"
            )
        
        return "\n".join(summary_lines)
    
    def reset(self):
        """重置评估器"""
        self.stagnation_count = 0
        self.last_progress_ratio = 0.0
        self.progress_history.clear()
        self.assessment_history.clear()
        self.task_complexity = TaskComplexity.MEDIUM
        # 停滞阈值由 TerminationManager 管理，此处不再重置
        self._intervention_paused = False
        self._intervention_pause_until = 0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "stagnation_count": self.stagnation_count,
            "last_progress_ratio": self.last_progress_ratio,
            "progress_history": self.progress_history[-10:],
            "assessment_count": len(self.assessment_history),
            "task_complexity": self.task_complexity.value,
            # 停滞阈值由 TerminationManager 管理，不再序列化
            "intervention_paused": self._intervention_paused
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CompletionEvaluator':
        """从字典创建实例"""
        evaluator = cls()
        evaluator.stagnation_count = data.get("stagnation_count", 0)
        evaluator.last_progress_ratio = data.get("last_progress_ratio", 0.0)
        evaluator.progress_history = data.get("progress_history", [])
        complexity_str = data.get("task_complexity", "medium")
        evaluator.task_complexity = TaskComplexity(complexity_str)
        # 停滞阈值由 TerminationManager 管理，不再从字典恢复
        evaluator._intervention_paused = data.get("intervention_paused", False)
        return evaluator
