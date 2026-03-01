"""
================================================================================
模型管理器 - 多模型自主切换支持
================================================================================

【模块概述】
实现多模型管理功能，支持在多个大语言模型之间自主切换：
- gemini-3-flash-preview
- kimi-k2.5
- claude-opus-4-6
- doubao-seed-2-0-pro
- minimax-m2.5

【核心功能】
1. 模型实例管理：延迟初始化，按需创建模型实例
2. 自动切换：根据错误率、响应时间等指标自动切换模型
3. 手动切换：支持用户命令手动切换模型
4. 健康监控：跟踪每个模型的成功/失败次数

【设计思路】
采用"延迟初始化 + 单例缓存"模式：
- 只有实际使用的模型才会创建实例
- 创建后的实例会被缓存，避免重复创建
- 切换模型时直接使用缓存的实例
================================================================================
"""

import time
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from langchain_openai import ChatOpenAI

from config import (
    API_BASE_URL, LLM_TIMEOUT, LLM_TEMPERATURE,
    AVAILABLE_MODELS, DEFAULT_MODEL, MODEL_SWITCH_CONFIG, AUTO_SWITCH_TARGET_MODEL
)


class SwitchReason(Enum):
    """模型切换原因枚举"""
    AUTO_FAILURE = "auto_failure"
    AUTO_SUCCESS = "auto_success"
    MANUAL = "manual"
    INIT = "init"
    ERROR_RECOVERY = "error_recovery"


@dataclass
class ModelStats:
    """
    模型统计信息
    
    【字段说明】
    success_count: 成功调用次数
    failure_count: 失败调用次数
    total_latency_ms: 总延迟（毫秒）
    call_count: 总调用次数
    last_success_time: 上次成功时间戳
    last_failure_time: 上次失败时间戳
    consecutive_failures: 连续失败次数
    consecutive_successes: 连续成功次数
    """
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    call_count: int = 0
    last_success_time: float = 0.0
    last_failure_time: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    @property
    def success_rate(self) -> float:
        """计算成功率"""
        if self.call_count == 0:
            return 1.0
        return self.success_count / self.call_count
    
    @property
    def avg_latency_ms(self) -> float:
        """计算平均延迟"""
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count
    
    def record_success(self, latency_ms: float):
        """记录成功调用"""
        self.success_count += 1
        self.call_count += 1
        self.total_latency_ms += latency_ms
        self.last_success_time = time.time()
        self.consecutive_failures = 0
        self.consecutive_successes += 1
    
    def record_failure(self):
        """记录失败调用"""
        self.failure_count += 1
        self.call_count += 1
        self.last_failure_time = time.time()
        self.consecutive_successes = 0
        self.consecutive_failures += 1
    
    def reset_consecutive(self):
        """重置连续计数"""
        self.consecutive_failures = 0
        self.consecutive_successes = 0


@dataclass
class SwitchRecord:
    """模型切换记录"""
    from_model: str
    to_model: str
    reason: SwitchReason
    timestamp: float
    detail: str = ""


class ModelManager:
    """
    模型管理器 - 核心类
    
    【职责】
    1. 管理多个 LLM 实例
    2. 实现自动切换逻辑
    3. 跟踪模型健康状态
    4. 提供切换接口
    
    【使用示例】
    ```python
    manager = ModelManager(api_key)
    llm = manager.get_current_llm()
    manager.switch_model("kimi-k2.5")
    ```
    """
    
    def __init__(self, api_key: str):
        """
        初始化模型管理器
        
        【参数】
        api_key: API密钥
        """
        self.api_key = api_key
        self._llm_instances: Dict[str, ChatOpenAI] = {}
        self._model_stats: Dict[str, ModelStats] = {}
        self._current_model: str = DEFAULT_MODEL
        self._initial_model: str = DEFAULT_MODEL
        self._switch_history: list[SwitchRecord] = []
        self._last_switch_time: float = 0
        self._config = MODEL_SWITCH_CONFIG
        
        for model_id in AVAILABLE_MODELS:
            self._model_stats[model_id] = ModelStats()
        
        self._record_switch(
            from_model="none",
            to_model=DEFAULT_MODEL,
            reason=SwitchReason.INIT,
            detail="初始化默认模型"
        )
    
    def set_initial_model(self, model_id: str) -> bool:
        """
        设置初始模型（启动时调用）
        
        【参数】
        model_id: 模型标识符
        
        【返回值】
        bool: 是否设置成功
        """
        if model_id not in AVAILABLE_MODELS:
            return False
        
        self._initial_model = model_id
        self._current_model = model_id
        self._record_switch(
            from_model="none",
            to_model=model_id,
            reason=SwitchReason.INIT,
            detail="设置初始模型"
        )
        return True
    
    def get_initial_model(self) -> str:
        """获取初始模型ID"""
        return self._initial_model
    
    def _create_llm_instance(self, model_id: str) -> ChatOpenAI:
        """
        创建 LLM 实例（延迟初始化）
        
        【参数】
        model_id: 模型标识符
        
        【返回值】
        ChatOpenAI: 模型实例
        """
        model_config = AVAILABLE_MODELS.get(model_id)
        if not model_config:
            raise ValueError(f"未知模型: {model_id}")
        
        llm = ChatOpenAI(
            model=model_id,
            openai_api_key=self.api_key,
            openai_api_base=API_BASE_URL,
            timeout=LLM_TIMEOUT,
            temperature=LLM_TEMPERATURE,
            max_tokens=model_config.get("max_tokens", 4096)
        )
        
        return llm
    
    def get_current_model(self) -> str:
        """
        获取当前使用的模型ID
        
        【返回值】
        str: 当前模型标识符
        """
        return self._current_model
    
    def get_current_llm(self) -> ChatOpenAI:
        """
        获取当前模型的 LLM 实例
        
        【返回值】
        ChatOpenAI: 当前模型实例
        """
        if self._current_model not in self._llm_instances:
            self._llm_instances[self._current_model] = self._create_llm_instance(
                self._current_model
            )
        return self._llm_instances[self._current_model]
    
    def get_llm(self, model_id: str) -> ChatOpenAI:
        """
        获取指定模型的 LLM 实例
        
        【参数】
        model_id: 模型标识符
        
        【返回值】
        ChatOpenAI: 模型实例
        """
        if model_id not in self._llm_instances:
            self._llm_instances[model_id] = self._create_llm_instance(model_id)
        return self._llm_instances[model_id]
    
    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        获取模型配置信息
        
        【参数】
        model_id: 模型标识符
        
        【返回值】
        dict: 模型配置信息
        """
        return AVAILABLE_MODELS.get(model_id)
    
    def get_model_stats(self, model_id: str) -> ModelStats:
        """
        获取模型统计信息
        
        【参数】
        model_id: 模型标识符
        
        【返回值】
        ModelStats: 模型统计信息
        """
        return self._model_stats.get(model_id, ModelStats())
    
    def record_success(self, model_id: str, latency_ms: float):
        """
        记录成功调用
        
        【参数】
        model_id: 模型标识符
        latency_ms: 响应延迟（毫秒）
        """
        if model_id in self._model_stats:
            self._model_stats[model_id].record_success(latency_ms)
            
            if self._should_switch_back(model_id):
                self._auto_switch_back()
    
    def record_failure(self, model_id: str) -> bool:
        """
        记录失败调用，并判断是否需要切换模型
        
        【参数】
        model_id: 模型标识符
        
        【返回值】
        bool: 是否触发了模型切换
        """
        if model_id in self._model_stats:
            self._model_stats[model_id].record_failure()
            
            stats = self._model_stats[model_id]
            threshold = self._config.get("failure_threshold", 3)
            
            if (stats.consecutive_failures >= threshold and 
                self._config.get("switch_on_error", True)):
                return self._auto_switch_on_failure(model_id)
        
        return False
    
    def _should_switch_back(self, current_model: str) -> bool:
        """
        判断是否应该切换回初始模型
        
        【参数】
        current_model: 当前模型ID
        
        【返回值】
        bool: 是否应该切换
        """
        if not self._config.get("auto_switch_enabled", True):
            return False
        
        if current_model != AUTO_SWITCH_TARGET_MODEL:
            return False
        
        if self._initial_model == current_model:
            return False
        
        stats = self._model_stats[current_model]
        threshold = self._config.get("success_threshold", 5)
        
        if stats.consecutive_successes < threshold:
            return False
        
        return True
    
    def _auto_switch_back(self):
        """自动切换回初始模型"""
        from_model = self._current_model
        target_model = self._initial_model
        self._current_model = target_model
        self._record_switch(
            from_model=from_model,
            to_model=target_model,
            reason=SwitchReason.AUTO_SUCCESS,
            detail="连续成功，切换回初始模型"
        )
        print(f"🔄 模型自动切换: {from_model} -> {target_model} (连续成功，切回初始模型)")
    
    def _auto_switch_on_failure(self, failed_model: str) -> bool:
        """
        因失败自动切换到备用模型
        
        【切换策略】
        自动切换只切换到 claude-opus-4-6（最强模型）
        成功后切回初始模型
        
        【参数】
        failed_model: 失败的模型ID
        
        【返回值】
        bool: 是否成功切换
        """
        if not self._can_switch():
            return False
        
        if self._current_model == AUTO_SWITCH_TARGET_MODEL:
            return False
        
        from_model = self._current_model
        self._current_model = AUTO_SWITCH_TARGET_MODEL
        self._last_switch_time = time.time()
        
        self._record_switch(
            from_model=from_model,
            to_model=AUTO_SWITCH_TARGET_MODEL,
            reason=SwitchReason.AUTO_FAILURE,
            detail=f"连续失败，自动切换到最强模型"
        )
        
        print(f"🔄 模型自动切换: {from_model} -> {AUTO_SWITCH_TARGET_MODEL} (连续失败，切换到最强模型)")
        return True
    
    def _can_switch(self) -> bool:
        """
        检查是否可以切换模型（冷却时间检查）
        
        【返回值】
        bool: 是否可以切换
        """
        if not self._config.get("auto_switch_enabled", True):
            return False
        
        cooldown = self._config.get("switch_cooldown", 30)
        elapsed = time.time() - self._last_switch_time
        
        return elapsed >= cooldown
    
    def switch_model(self, model_id: str, reason: str = "手动切换") -> bool:
        """
        手动切换模型
        
        【参数】
        model_id: 目标模型ID
        reason: 切换原因
        
        【返回值】
        bool: 是否切换成功
        """
        if model_id not in AVAILABLE_MODELS:
            print(f"❌ 未知模型: {model_id}")
            print(f"   可用模型: {', '.join(AVAILABLE_MODELS.keys())}")
            return False
        
        if model_id == self._current_model:
            print(f"ℹ️ 已经在使用模型: {model_id}")
            return True
        
        from_model = self._current_model
        self._current_model = model_id
        self._last_switch_time = time.time()
        
        self._record_switch(
            from_model=from_model,
            to_model=model_id,
            reason=SwitchReason.MANUAL,
            detail=reason
        )
        
        model_info = AVAILABLE_MODELS[model_id]
        print(f"✅ 模型已切换: {from_model} -> {model_id}")
        print(f"   模型名称: {model_info['name']}")
        print(f"   描述: {model_info['description']}")
        
        return True
    
    def _record_switch(self, from_model: str, to_model: str, 
                       reason: SwitchReason, detail: str = ""):
        """
        记录模型切换
        
        【参数】
        from_model: 原模型ID
        to_model: 目标模型ID
        reason: 切换原因
        detail: 详细说明
        """
        record = SwitchRecord(
            from_model=from_model,
            to_model=to_model,
            reason=reason,
            timestamp=time.time(),
            detail=detail
        )
        self._switch_history.append(record)
    
    def get_available_models(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有可用模型列表
        
        【返回值】
        dict: 模型配置字典
        """
        return AVAILABLE_MODELS.copy()
    
    def get_status_display(self) -> str:
        """
        获取状态显示文本
        
        【返回值】
        str: 格式化的状态文本
        """
        lines = []
        lines.append("═" * 60)
        lines.append("📊 模型管理器状态")
        lines.append("═" * 60)
        
        current_info = AVAILABLE_MODELS.get(self._current_model, {})
        lines.append(f"当前模型: {self._current_model}")
        lines.append(f"模型名称: {current_info.get('name', '未知')}")
        lines.append(f"描述: {current_info.get('description', '无')}")
        
        lines.append(f"\n默认模型: {DEFAULT_MODEL}")
        lines.append(f"初始模型: {self._initial_model}")
        lines.append(f"自动切换目标: {AUTO_SWITCH_TARGET_MODEL} (最强模型)")
        
        lines.append("\n📋 所有模型统计:")
        lines.append("-" * 60)
        
        for model_id, config in AVAILABLE_MODELS.items():
            stats = self._model_stats[model_id]
            is_current = "👉 " if model_id == self._current_model else "   "
            auto_tag = "[自动]" if config.get("supports_auto_switch", False) else "[手动]"
            
            lines.append(
                f"{is_current}{model_id} {auto_tag}\n"
                f"      成功率: {stats.success_rate:.1%} "
                f"| 成功: {stats.success_count} | 失败: {stats.failure_count}\n"
                f"      平均延迟: {stats.avg_latency_ms:.0f}ms "
                f"| 连续失败: {stats.consecutive_failures}"
            )
        
        if self._switch_history:
            lines.append("\n📜 最近切换记录:")
            lines.append("-" * 60)
            for record in self._switch_history[-5:]:
                time_str = time.strftime("%H:%M:%S", time.localtime(record.timestamp))
                lines.append(
                    f"   [{time_str}] {record.from_model} -> {record.to_model}\n"
                    f"      原因: {record.reason.value} | {record.detail}"
                )
        
        lines.append("═" * 60)
        return "\n".join(lines)
    
    def list_models(self) -> str:
        """
        列出所有可用模型
        
        【返回值】
        str: 格式化的模型列表
        """
        lines = []
        lines.append("═" * 60)
        lines.append("📋 可用模型列表")
        lines.append("═" * 60)
        
        for model_id, config in AVAILABLE_MODELS.items():
            is_current = "👉 " if model_id == self._current_model else "   "
            is_default = " [默认]" if model_id == DEFAULT_MODEL else ""
            is_auto = " [支持自动切换]" if config.get("supports_auto_switch", False) else " [仅手动切换]"
            stats = self._model_stats[model_id]
            
            lines.append(f"{is_current}{model_id}{is_default}{is_auto}")
            lines.append(f"   名称: {config['name']}")
            lines.append(f"   描述: {config['description']}")
            lines.append(f"   标签: {', '.join(config['tags'])}")
            lines.append(f"   成功率: {stats.success_rate:.1%}")
            lines.append("")
        
        lines.append("💡 使用 'switch <模型ID>' 手动切换模型")
        lines.append("💡 自动切换仅切换到 claude-opus-4-6（最强模型）")
        lines.append("═" * 60)
        return "\n".join(lines)
    
    def reset_stats(self, model_id: Optional[str] = None):
        """
        重置模型统计信息
        
        【参数】
        model_id: 指定模型ID，为None则重置所有模型
        """
        if model_id:
            if model_id in self._model_stats:
                self._model_stats[model_id] = ModelStats()
                print(f"✅ 已重置模型 {model_id} 的统计信息")
        else:
            for mid in self._model_stats:
                self._model_stats[mid] = ModelStats()
            print("✅ 已重置所有模型的统计信息")


_model_manager_instance: Optional[ModelManager] = None


def get_model_manager() -> Optional[ModelManager]:
    """
    获取模型管理器单例实例
    
    【返回值】
    ModelManager: 模型管理器实例，未初始化时返回None
    """
    return _model_manager_instance


def init_model_manager(api_key: str) -> ModelManager:
    """
    初始化模型管理器单例
    
    【参数】
    api_key: API密钥
    
    【返回值】
    ModelManager: 模型管理器实例
    """
    global _model_manager_instance
    _model_manager_instance = ModelManager(api_key)
    return _model_manager_instance
