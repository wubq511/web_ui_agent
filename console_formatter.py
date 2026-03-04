"""
================================================================================
终端输出格式化模块 - 统一管理终端输出的样式和排版
================================================================================

【模块概述】
提供统一的终端输出格式化功能，包括颜色、对齐、分隔线等，
使输出更加清晰有条理。

【主要功能】
1. 颜色输出：成功(绿色)、警告(黄色)、错误(红色)、信息(蓝色)
2. 格式化输出：步骤信息、决策信息、执行结果
3. 分隔线和区块划分

【设计思路】
通过统一的格式化函数，确保所有输出风格一致，
提升信息获取效率和视觉体验。
================================================================================
"""

import os
import sys
from datetime import datetime
from typing import Optional

from security_utils import mask_string, is_sensitive_field


SENSITIVE_ACTION_TYPES = {"type", "input", "fill", "enter"}


class Colors:
    """ANSI 颜色代码"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


def supports_color() -> bool:
    """检测终端是否支持颜色输出"""
    if os.name == 'nt':
        return sys.stdout.isatty()
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


USE_COLOR = supports_color()


def colorize(text: str, color: str) -> str:
    """
    为文本添加颜色
    
    【参数】
    text: str - 要着色的文本
    color: str - ANSI 颜色代码
    
    【返回值】
    str: 着色后的文本
    """
    if USE_COLOR:
        return f"{color}{text}{Colors.RESET}"
    return text


def print_step_separator(step: int, max_steps: int):
    """
    打印步骤分隔线
    
    【参数】
    step: int - 当前步骤编号
    max_steps: int - 最大步骤数
    """
    print()
    step_text = f" 步骤 {step}/{max_steps} "
    total_width = 40
    left_width = (total_width - len(step_text)) // 2
    right_width = total_width - len(step_text) - left_width
    line = "─" * left_width + step_text + "─" * right_width
    print(colorize(f"  {line}", Colors.DIM))


def print_perception(elements_count: int, file_path: str):
    """
    打印感知模块输出（简洁版）
    
    【参数】
    elements_count: int - 发现的元素数量
    file_path: str - 详情文件路径
    """
    icon = colorize("👁️", Colors.BLUE)
    count = colorize(str(elements_count), Colors.CYAN + Colors.BOLD)
    print(f"  {icon} 感知: {count} 个元素")


def print_decision(action_type: str, target_id: int = None, value: str = None):
    """
    打印决策模块输出（简洁版，自动脱敏敏感信息）
    
    【参数】
    action_type: str - 动作类型
    target_id: int - 目标元素ID（可选）
    value: str - 操作值（可选）
    """
    icon = colorize("🧠", Colors.MAGENTA)
    action = colorize(action_type, Colors.YELLOW + Colors.BOLD)
    
    parts = [f"  {icon} 决策: {action}"]
    
    if target_id is not None:
        target = colorize(f"[{target_id}]", Colors.CYAN)
        parts.append(f"→ {target}")
    
    if value:
        action_lower = action_type.lower() if action_type else ""
        if action_lower in SENSITIVE_ACTION_TYPES:
            masked_value = mask_string(str(value), show_prefix=1, show_suffix=1)
            value_preview = masked_value[:20] + "..." if len(masked_value) > 20 else masked_value
        else:
            value_preview = str(value)[:20] + "..." if len(str(value)) > 20 else str(value)
        val = colorize(f"'{value_preview}'", Colors.WHITE)
        parts.append(f"= {val}")
    
    print(" ".join(parts))


def print_action_success(action_type: str, duration_ms: float = None):
    """
    打印执行成功信息（简洁版）
    
    【参数】
    action_type: str - 动作类型
    duration_ms: float - 执行耗时（毫秒）
    """
    icon = colorize("✅", Colors.GREEN)
    
    if duration_ms and duration_ms > 1000:
        time_str = colorize(f"{duration_ms/1000:.1f}s", Colors.DIM)
        print(f"  {icon} {action_type} ({time_str})")
    elif duration_ms:
        time_str = colorize(f"{duration_ms:.0f}ms", Colors.DIM)
        print(f"  {icon} {action_type} ({time_str})")
    else:
        print(f"  {icon} {action_type}")


def print_action_warning(message: str):
    """
    打印执行警告信息
    
    【参数】
    message: str - 警告信息
    """
    icon = colorize("⚠️", Colors.YELLOW)
    print(f"  {icon} {message}")


def print_action_error(message: str):
    """
    打印执行错误信息
    
    【参数】
    message: str - 错误信息
    """
    icon = colorize("❌", Colors.RED)
    print(f"  {icon} {message}")


def print_checkpoint_saved(checkpoint_id: str):
    """
    打印检查点保存信息
    
    【参数】
    checkpoint_id: str - 检查点ID
    """
    icon = colorize("💾", Colors.BLUE)
    cp_id = colorize(checkpoint_id, Colors.CYAN)
    print(f"  {icon} 检查点: {cp_id}")


def print_session_saved():
    """打印浏览器会话保存信息"""
    icon = colorize("💾", Colors.BLUE)
    print(f"  {icon} 已保存浏览器状态")


def print_task_complete():
    """打印任务完成信息"""
    print()
    line = "═" * 50
    print(colorize(f"╔{line}╗", Colors.GREEN))
    print(colorize("║" + "🎉 任务完成！".center(46) + "║", Colors.GREEN + Colors.BOLD))
    print(colorize(f"╚{line}╝", Colors.GREEN))


def print_task_terminated(reason: str, message: str):
    """
    打印任务终止信息
    
    【参数】
    reason: str - 终止原因
    message: str - 终止消息
    """
    print()
    line = "═" * 50
    print(colorize(f"╔{line}╗", Colors.YELLOW))
    msg = f"⏹️ 任务终止: {reason}".center(46)
    print(colorize(f"║{msg}║", Colors.YELLOW + Colors.BOLD))
    print(colorize(f"╚{line}╝", Colors.YELLOW))


def print_progress_hint(progress: float, stagnation: int, threshold: int):
    """
    打印进度提示
    
    【参数】
    progress: float - 进度比例
    stagnation: int - 停滞计数
    threshold: int - 停滞阈值
    """
    progress_str = f"{progress:.0%}"
    stagnation_str = f"{stagnation}/{threshold}"
    
    if stagnation > threshold * 0.7:
        color = Colors.YELLOW
    else:
        color = Colors.DIM
    
    info = colorize(f"📊 进度: {progress_str} | 停滞: {stagnation_str}", color)
    print(f"  {info}")


def print_maybe_complete(confidence: float):
    """
    打印可能完成提示
    
    【参数】
    confidence: float - 置信度
    """
    icon = colorize("💡", Colors.YELLOW)
    conf = colorize(f"{confidence:.0%}", Colors.CYAN)
    print(f"  {icon} 可能已完成 (置信度: {conf})")


def print_separator(char: str = "─", width: int = 52):
    """
    打印分隔线
    
    【参数】
    char: str - 分隔字符
    width: int - 线宽
    """
    line = char * width
    print(colorize(f"  {line}", Colors.DIM))


def format_timestamp() -> str:
    """获取格式化的时间戳"""
    return datetime.now().strftime("%H:%M:%S")
