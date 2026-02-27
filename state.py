"""
================================================================================
状态定义模块 - AgentState 状态结构
================================================================================

【模块概述】
定义 LangGraph 图的状态结构。状态是 Agent 的"记忆"，在各个节点之间传递和更新。

【核心概念：为什么需要状态？】
在 LangGraph 框架中，状态（State）是整个图的核心。想象一下人类操作网页的过程：
1. 我们需要记住"目标是什么"（objective）
2. 我们需要知道"现在在哪里"（current_url）
3. 我们需要看到"页面上有什么"（elements_dict）
4. 我们需要回忆"之前做了什么"（history）
5. 我们需要知道"是否完成了"（is_done）

状态就是 Agent 的"工作记忆"，在各个节点之间传递和更新。
================================================================================
"""

from typing import TypedDict, Optional
from dataclasses import dataclass

from config import (
    MAX_STEPS, DEFAULT_TASK_COMPLEXITY, DEFAULT_PROGRESS_LEVEL,
    PROGRESS_STAGNATION_DEFAULT, DEFAULT_INTERVENTION_PAUSED, DEFAULT_FAST_MODE
)


class AgentState(TypedDict):
    """
    AgentState - Agent 的"记忆"与"状态"容器
    
    【TypedDict 的作用】
    TypedDict 是 Python 3.8+ 引入的类型提示工具，它让我们可以：
    1. 明确定义字典中每个键的类型
    2. 获得 IDE 的自动补全支持
    3. 在开发阶段发现类型错误
    """
    
    objective: str
    """
    objective: str - 用户的原始目标
    
    【作用】存储用户想要完成的任务，例如"在百度搜索 LangGraph 教程"
    【特点】在整个执行过程中保持不变（不可变字段）
    【用途】决策模块会反复参考这个目标，确保每一步都朝着目标前进
    """
    
    current_url: str
    """
    current_url: str - 当前页面的 URL
    
    【作用】记录 Agent 当前所在的网页地址
    【特点】每次页面跳转或刷新后都会更新
    【用途】帮助 Agent 理解当前上下文，决策模块会根据 URL 判断页面类型
    """
    
    elements_dict: dict[int, dict]
    """
    elements_dict: dict[int, dict] - 页面可交互元素字典
    
    【作用】存储当前页面上所有可交互元素的详细信息
    【结构】键是元素的唯一数字 ID（从 1 开始），值是包含元素信息的字典
    【示例】
    {
        1: {
            "type": "input",           # 元素类型
            "text": "搜索",             # 可见文本
            "xpath": "//input[@id='kw']",  # XPath 路径
            "selector": "#kw",         # CSS 选择器
            "is_clickable": False,     # 是否可点击
            "is_input": True           # 是否可输入
        },
        2: {
            "type": "button",
            "text": "百度一下",
            "xpath": "//input[@id='su']",
            "selector": "#su",
            "is_clickable": True,
            "is_input": False
        }
    }
    【用途】决策模块根据这个字典选择要操作的元素
    """
    
    history: list[dict]
    """
    history: list[dict] - 执行历史记录
    
    【作用】记录 Agent 执行过的所有动作和思考过程
    【结构】每个元素是一个字典，包含该步骤的完整信息
    【示例】
    [
        {
            "step": 1,
            "thought": "我需要在搜索框中输入关键词",
            "action_type": "type",
            "target_id": 1,
            "value": "LangGraph 教程",
            "result": "成功输入"
        }
    ]
    【用途】
    1. 帮助 Agent 回忆之前的操作，避免重复
    2. 在出错时提供调试信息
    3. 最终生成执行报告
    """
    
    error_message: str | None
    """
    error_message: str | None - 错误信息
    
    【作用】存储最近一次执行中遇到的错误
    【特点】初始值为 None，出错时设置错误信息，成功执行后重置为 None
    【用途】决策模块会根据错误信息调整策略，实现自我修复
    """
    
    is_done: bool
    """
    is_done: bool - 任务完成标志
    
    【作用】标记任务是否已经完成
    【特点】初始值为 False，当决策模块认为任务完成时设为 True
    【用途】控制图的循环终止条件
    """
    
    step_count: int
    """
    step_count: int - 当前执行步数
    
    【作用】记录 Agent 已经执行了多少步操作
    【特点】每执行一个动作后加 1
    【用途】
    1. 防止无限循环（超过最大步数强制终止）
    2. 在历史记录中标识每一步
    3. 用于调试和性能分析
    """
    
    max_steps: int
    """
    max_steps: int - 当前最大步骤限制
    
    【作用】动态调整的最大步骤限制
    【特点】可根据任务复杂度动态调整
    【用途】支持复杂任务的完整执行
    """
    
    error_count: int
    """
    error_count: int - 错误计数
    
    【作用】记录执行过程中的错误次数
    【特点】每次出错时加 1
    【用途】用于错误恢复和终止判断
    """
    
    consecutive_success: int
    """
    consecutive_success: int - 连续成功次数
    
    【作用】记录连续成功执行的次数
    【特点】成功时加 1，失败时重置为 0
    【用途】用于判断是否应该扩展步骤限制
    """
    
    progress_ratio: float
    """
    progress_ratio: float - 进度比率
    
    【作用】记录当前任务完成进度
    【特点】范围 0.0 - 1.0
    【用途】用于完成度评估和终止判断
    """
    
    stagnation_count: int
    """
    stagnation_count: int - 停滞计数
    
    【作用】记录进度停滞的次数
    【特点】进度无变化时加 1
    【用途】用于检测任务卡住的情况
    """
    
    task_complexity: str
    """
    task_complexity: str - 任务复杂度
    
    【作用】记录任务的复杂度级别
    【特点】可选值: "simple", "medium", "complex"
    【用途】用于动态调整终止阈值
    """
    
    progress_level: str
    """
    progress_level: str - 进展程度
    
    【作用】记录当前的进展程度
    【特点】可选值: "no_progress", "partial_progress", "significant_progress", "full_progress"
    【用途】区分完全无进展和部分进展情况
    """
    
    adjusted_stagnation_threshold: int
    """
    adjusted_stagnation_threshold: int - 调整后的停滞阈值
    
    【作用】根据任务复杂度动态调整的停滞阈值
    【特点】范围 3-8，根据复杂度和执行步数动态变化
    【用途】为复杂任务提供更多探索空间
    """
    
    intervention_paused: bool
    """
    intervention_paused: bool - 人工干预暂停标志
    
    【作用】标记是否处于人工干预暂停状态
    【特点】暂停时终止倒计时停止
    【用途】允许在关键节点暂停终止倒计时
    """
    
    fast_mode: bool
    """
    fast_mode: bool - 快速模式标志
    
    【作用】标记是否启用快速模式
    【特点】快速模式使用更严格的终止条件
    【用途】保留原机制作为快速任务处理模式的可选项
    """
    
    termination_reason: Optional[str]
    """
    termination_reason: Optional[str] - 终止原因
    
    【作用】记录任务终止的原因
    【特点】任务终止时设置
    【用途】用于结果报告和调试
    """
    
    saved_checkpoint_id: Optional[str]
    """
    saved_checkpoint_id: Optional[str] - 保存的检查点ID
    
    【作用】记录最近保存的检查点ID
    【特点】保存检查点时设置
    【用途】用于断点续接
    """
    
    popup_detected: bool
    """
    popup_detected: bool - 弹窗/模态框检测标志
    
    【作用】标记当前页面是否检测到弹窗或模态框
    【特点】在感知节点中检测并设置
    【用途】帮助决策模块优先处理弹窗内容
    """
    
    login_form_detected: bool
    """
    login_form_detected: bool - 登录表单检测标志
    
    【作用】标记当前页面是否检测到登录表单
    【特点】在感知节点中检测并设置
    【用途】帮助决策模块识别并处理登录场景
    """
    
    login_elements: dict
    """
    login_elements: dict - 登录元素信息
    
    【作用】存储检测到的登录相关元素的ID
    【结构】{
        "username": 元素ID或None,
        "password": 元素ID或None,
        "submit": 元素ID或None,
        "sms_code": 元素ID或None,
        "get_code_btn": 元素ID或None
    }
    【用途】帮助决策模块快速定位登录相关元素
    """


def create_initial_state(objective: str, current_url: str = "", 
                        max_steps: int = 10, fast_mode: bool = False) -> AgentState:
    """
    创建初始状态
    
    【参数】
    objective: str - 用户目标
    current_url: str - 当前页面 URL（默认为空）
    max_steps: int - 初始最大步骤限制（默认为配置值）
    fast_mode: bool - 是否启用快速模式（默认为 False）
    
    【返回值】
    AgentState: 初始化后的状态字典
    """
    return AgentState(
        objective=objective,
        current_url=current_url,
        elements_dict={},
        history=[],
        error_message=None,
        is_done=False,
        step_count=0,
        max_steps=max_steps,
        error_count=0,
        consecutive_success=0,
        progress_ratio=0.0,
        stagnation_count=0,
        task_complexity=DEFAULT_TASK_COMPLEXITY.value,
        progress_level=DEFAULT_PROGRESS_LEVEL,
        adjusted_stagnation_threshold=PROGRESS_STAGNATION_DEFAULT,
        intervention_paused=DEFAULT_INTERVENTION_PAUSED,
        fast_mode=fast_mode,
        termination_reason=None,
        saved_checkpoint_id=None,
        popup_detected=False,
        login_form_detected=False,
        login_elements={"username": None, "password": None, "submit": None, "sms_code": None, "get_code_btn": None}
    )


def state_to_dict(state: AgentState) -> dict:
    """将状态转换为可序列化的字典"""
    return dict(state)


def dict_to_state(data: dict) -> AgentState:
    """从字典创建状态"""
    return AgentState(**data)
