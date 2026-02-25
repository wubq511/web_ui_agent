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

from typing import TypedDict


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


def create_initial_state(objective: str, current_url: str = "") -> AgentState:
    """
    创建初始状态
    
    【参数】
    objective: str - 用户目标
    current_url: str - 当前页面 URL（默认为空）
    
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
        step_count=0
    )
