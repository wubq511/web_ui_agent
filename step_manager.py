"""
================================================================================
步骤管理模块 - 动态步骤数调整机制
================================================================================

【模块概述】
实现动态步骤数调整机制，能够根据任务复杂度自动或手动调整最大步骤限制。

【核心功能】
1. 基于任务复杂度评估自动调整最大步骤数
2. 支持手动干预调整步骤限制
3. 记录步骤调整历史
4. 防止无限扩展的合理限制
================================================================================
"""

from typing import Optional
from dataclasses import dataclass, field

from config import (
    MAX_STEPS, MIN_STEPS, MAX_STEPS_LIMIT,
    DYNAMIC_STEP_INCREMENT, STEP_ADJUSTMENT_THRESHOLD,
    TaskComplexity
)


@dataclass
class StepAdjustment:
    """步骤调整记录"""
    step: int
    old_max: int
    new_max: int
    reason: str
    complexity: TaskComplexity


@dataclass
class StepManager:
    """
    步骤管理器 - 动态调整最大步骤数
    
    【设计思路】
    根据任务执行过程中的各种指标动态调整最大步骤数：
    1. 任务复杂度评估
    2. 执行进度分析
    3. 错误恢复需求
    4. 用户手动干预
    """
    
    initial_max_steps: int = MAX_STEPS
    current_max_steps: int = MAX_STEPS
    min_steps: int = MIN_STEPS
    max_limit: int = MAX_STEPS_LIMIT
    adjustment_history: list[StepAdjustment] = field(default_factory=list)
    
    def estimate_complexity(self, objective: str, elements_count: int, 
                           history_length: int) -> TaskComplexity:
        """
        评估任务复杂度
        
        【参数】
        objective: 任务目标描述
        elements_count: 页面元素数量
        history_length: 已执行步骤数
        
        【返回值】
        TaskComplexity: 任务复杂度级别
        """
        objective_lower = objective.lower()
        
        complex_keywords = ['购买', '下单', '支付', '注册', '登录', '填写', '提交',
                          'buy', 'purchase', 'checkout', 'register', 'login', 'submit']
        very_complex_keywords = ['多个', '批量', '比较', '筛选', '全部', '完整',
                                'multiple', 'batch', 'compare', 'filter', 'all']
        
        has_complex = any(kw in objective_lower for kw in complex_keywords)
        has_very_complex = any(kw in objective_lower for kw in very_complex_keywords)
        
        if has_very_complex or elements_count > 50:
            return TaskComplexity.VERY_COMPLEX
        elif has_complex or elements_count > 30 or history_length > 5:
            return TaskComplexity.COMPLEX
        elif elements_count > 15 or history_length > 3:
            return TaskComplexity.MEDIUM
        else:
            return TaskComplexity.SIMPLE
    
    def get_recommended_steps(self, complexity: TaskComplexity) -> int:
        """
        根据复杂度获取推荐步骤数
        
        【参数】
        complexity: 任务复杂度
        
        【返回值】
        int: 推荐的最大步骤数
        """
        steps_map = {
            TaskComplexity.SIMPLE: self.min_steps,
            TaskComplexity.MEDIUM: self.initial_max_steps,
            TaskComplexity.COMPLEX: self.initial_max_steps + DYNAMIC_STEP_INCREMENT * 2,
            TaskComplexity.VERY_COMPLEX: self.initial_max_steps + DYNAMIC_STEP_INCREMENT * 4
        }
        return min(steps_map[complexity], self.max_limit)
    
    def adjust_max_steps(self, reason: str, complexity: Optional[TaskComplexity] = None,
                        target_steps: Optional[int] = None, current_step: int = 0) -> int:
        """
        调整最大步骤数
        
        【参数】
        reason: 调整原因
        complexity: 任务复杂度（可选）
        target_steps: 目标步骤数（可选，手动调整时使用）
        current_step: 当前步骤数
        
        【返回值】
        int: 调整后的最大步骤数
        """
        old_max = self.current_max_steps
        
        if target_steps is not None:
            new_max = min(max(target_steps, self.min_steps), self.max_limit)
        elif complexity is not None:
            new_max = self.get_recommended_steps(complexity)
        else:
            new_max = min(self.current_max_steps + DYNAMIC_STEP_INCREMENT, self.max_limit)
        
        if new_max != old_max:
            self.adjustment_history.append(StepAdjustment(
                step=current_step,
                old_max=old_max,
                new_max=new_max,
                reason=reason,
                complexity=complexity or TaskComplexity.MEDIUM
            ))
            self.current_max_steps = new_max
            print(f"📊 步骤限制调整: {old_max} -> {new_max} (原因: {reason})")
        
        return self.current_max_steps
    
    def should_extend_steps(self, progress_ratio: float, error_count: int,
                           consecutive_success: int) -> bool:
        """
        判断是否应该扩展步骤数
        
        【参数】
        progress_ratio: 进度比率 (0-1)
        error_count: 错误计数
        consecutive_success: 连续成功次数
        
        【返回值】
        bool: 是否应该扩展
        """
        if self.current_max_steps >= self.max_limit:
            return False
        
        if progress_ratio > STEP_ADJUSTMENT_THRESHOLD and error_count < 2:
            return True
        
        if consecutive_success >= 3 and progress_ratio > 0.5:
            return True
        
        return False
    
    def get_remaining_steps(self, current_step: int) -> int:
        """获取剩余步骤数"""
        return max(0, self.current_max_steps - current_step)
    
    def get_adjustment_summary(self) -> str:
        """获取调整历史摘要"""
        if not self.adjustment_history:
            return "无步骤调整记录"
        
        summary_lines = ["步骤调整历史:"]
        for adj in self.adjustment_history:
            summary_lines.append(
                f"  步骤{adj.step}: {adj.old_max} -> {adj.new_max} "
                f"({adj.reason}, 复杂度: {adj.complexity.value})"
            )
        return "\n".join(summary_lines)
    
    def reset(self):
        """重置步骤管理器"""
        self.current_max_steps = self.initial_max_steps
        self.adjustment_history.clear()
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "initial_max_steps": self.initial_max_steps,
            "current_max_steps": self.current_max_steps,
            "min_steps": self.min_steps,
            "max_limit": self.max_limit,
            "adjustment_count": len(self.adjustment_history),
            "adjustment_history": [
                {
                    "step": adj.step,
                    "old_max": adj.old_max,
                    "new_max": adj.new_max,
                    "reason": adj.reason,
                    "complexity": adj.complexity.value
                }
                for adj in self.adjustment_history
            ]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'StepManager':
        """从字典创建实例"""
        manager = cls(
            initial_max_steps=data.get("initial_max_steps", MAX_STEPS),
            current_max_steps=data.get("current_max_steps", MAX_STEPS),
            min_steps=data.get("min_steps", MIN_STEPS),
            max_limit=data.get("max_limit", MAX_STEPS_LIMIT)
        )
        
        for adj_data in data.get("adjustment_history", []):
            manager.adjustment_history.append(StepAdjustment(
                step=adj_data["step"],
                old_max=adj_data["old_max"],
                new_max=adj_data["new_max"],
                reason=adj_data["reason"],
                complexity=TaskComplexity(adj_data["complexity"])
            ))
        
        return manager
