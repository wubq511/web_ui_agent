"""
================================================================================
输出处理器模块 - 管理详细输出的存储（性能优化版）
================================================================================

【模块概述】
将终端的详细输出重定向到文件，保持终端输出的简洁性。

【主要功能】
1. 将元素列表等详细信息写入 process 文件夹
2. 每次运行创建独立的时间戳子文件夹
3. 提供简洁的终端输出
4. 支持按步骤组织输出文件
5. 异步写入支持（高性能场景）
6. 写入缓冲优化

【设计思路】
通过分离详细输出和简洁输出，让终端只显示关键信息，
详细内容保存到文件中便于后续分析。
每次运行都有独立的文件夹，便于查找历史记录。
================================================================================
"""

import os
import json
import shutil
import threading
import queue
import atexit
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from security_utils import mask_string, is_sensitive_field, sanitize_log_message
from task_manager import get_current_task_id


SENSITIVE_VALUE_FIELDS = {"password", "pwd", "passwd", "secret", "token", "api_key", "key"}
SENSITIVE_ACTION_TYPES = {"type", "input", "fill", "enter"}


def mask_sensitive_in_dict(data: dict, parent_action_type: str = None) -> dict:
    """
    递归脱敏字典中的敏感信息
    
    【参数】
    data: 原始字典
    parent_action_type: 父级的 action_type（用于判断 value 是否需要脱敏）
    
    【返回值】
    脱敏后的字典副本
    """
    if not isinstance(data, dict):
        return data
    
    action_type = data.get("action_type", parent_action_type)
    
    result = {}
    for key, value in data.items():
        key_lower = key.lower() if isinstance(key, str) else ""
        
        if isinstance(value, str):
            if is_sensitive_field(key) or any(s in key_lower for s in SENSITIVE_VALUE_FIELDS):
                if key_lower == "value" and action_type and action_type.lower() not in SENSITIVE_ACTION_TYPES:
                    result[key] = value
                else:
                    result[key] = mask_string(value, show_prefix=1, show_suffix=1)
            elif len(value) > 10 and any(s in value.lower() for s in ["password", "密码"]):
                result[key] = mask_string(value, show_prefix=1, show_suffix=1)
            else:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = mask_sensitive_in_dict(value, action_type)
        elif isinstance(value, list):
            result[key] = [
                mask_sensitive_in_dict(item, action_type) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    
    return result


def mask_password_in_thought(thought: str) -> str:
    """
    脱敏思考过程中的密码信息（智能识别真正的密码值）
    
    【参数】
    thought: 原始思考文本
    
    【返回值】
    脱敏后的文本
    
    【设计思路】
    只脱敏真正的密码值，不脱敏描述性文本如"密码输入框"、"输入密码"等
    真正的密码通常格式为：
    - 密码：'xxx' 或 密码："xxx" 或 密码=xxx
    - password='xxx' 或 password: "xxx"
    """
    import re
    
    patterns = [
        (r"(密码[：:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(密码[：:]\s*)(['\"]?)([^\s'\"，,。！？\]\)\}]{4,20})(['\"]?)", r"\1\2******\4"),
        (r"(password\s*[=:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(password\s*[=:]\s*)(['\"]?)([^\s'\"，,。！？\]\)\}]{4,20})(['\"]?)", r"\1\2******\4"),
        (r"(pwd\s*[=:]\s*['\"])([^'\"]+)(['\"])", r"\1******\3"),
        (r"(pwd\s*[=:]\s*)(['\"]?)([^\s'\"，,。！？\]\)\}]{4,20})(['\"]?)", r"\1\2******\4"),
    ]
    
    result = thought
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


class OutputHandler:
    """
    输出处理器 - 管理详细输出的存储和显示（性能优化版）
    
    【属性】
    process_dir: str - process 根文件夹路径
    session_dir: str - 当前会话的文件夹路径（时间戳命名）
    current_step: int - 当前步骤编号
    session_id: str - 会话ID（运行开始时间）
    
    【性能优化】
    1. 异步写入支持
    2. 写入缓冲
    3. 批量写入
    """
    
    def __init__(self, base_dir: str = None, async_mode: bool = True, task_id: str = None):
        """
        初始化输出处理器
        
        【参数】
        base_dir: str - 基础目录路径，默认为当前文件所在目录
        async_mode: bool - 是否启用异步写入模式
        task_id: str - 任务ID，如果不提供则从任务管理器获取
        """
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.process_dir = os.path.join(base_dir, "process")
        self.current_step = 0
        self._async_mode = async_mode
        
        if task_id:
            self.session_id = task_id
        else:
            self.session_id = get_current_task_id()
            if not self.session_id:
                self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self.session_dir = os.path.join(self.process_dir, self.session_id)
        
        if not os.path.exists(self.process_dir):
            os.makedirs(self.process_dir)
        
        if not os.path.exists(self.session_dir):
            os.makedirs(self.session_dir)
        
        self._write_buffer: list = []
        self._buffer_lock = threading.Lock()
        self._buffer_size = 10
        
        if async_mode:
            self._write_queue: queue.Queue = queue.Queue()
            self._executor = ThreadPoolExecutor(max_workers=1)
            self._running = True
            self._executor.submit(self._async_writer)
            atexit.register(self._shutdown)
    
    def _shutdown(self):
        """关闭异步写入线程"""
        if self._async_mode:
            self._running = False
            self._write_queue.put(None)
            self._executor.shutdown(wait=True)
    
    def _async_writer(self):
        """异步写入线程"""
        while self._running:
            try:
                item = self._write_queue.get(timeout=0.5)
                if item is None:
                    break
                filepath, data = item
                self._write_file_sync(filepath, data)
            except queue.Empty:
                continue
            except Exception:
                pass
    
    def _write_file_sync(self, filepath: str, data: dict):
        """同步写入文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def _write_file(self, filepath: str, data: dict):
        """写入文件（支持异步）"""
        if self._async_mode:
            self._write_queue.put((filepath, data))
        else:
            self._write_file_sync(filepath, data)
    
    def start_step(self, step: int):
        """
        开始新步骤
        
        【参数】
        step: int - 步骤编号
        """
        self.current_step = step
    
    def write_elements(self, elements_dict: dict, url: str, iframe_info: list = None):
        """
        将元素列表详细信息写入文件（性能优化版）
        
        【参数】
        elements_dict: dict - 元素字典
        url: str - 当前页面URL
        iframe_info: list - iframe 信息列表
        
        【返回值】
        str: 相对于 process 文件夹的文件路径
        """
        filename = f"step_{self.current_step:03d}_elements.json"
        filepath = os.path.join(self.session_dir, filename)
        
        elements_data = {}
        for eid, info in elements_dict.items():
            elements_data[str(eid)] = {
                "id": eid,
                "type": info.get("type", ""),
                "text": info.get("text", ""),
                "placeholder": info.get("placeholder", ""),
                "current_value": info.get("current_value", ""),
                "is_clickable": info.get("is_clickable", False),
                "is_input": info.get("is_input", False),
                "is_selectable": info.get("is_selectable", False),
                "is_checkable": info.get("is_checkable", False),
                "attrs": info.get("attrs", {}),
                "selector": info.get("selector", ""),
                "xpath": info.get("xpath", ""),
                "frame": info.get("frame")
            }
        
        data = {
            "step": self.current_step,
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "total_elements": len(elements_dict),
            "iframe_count": len(iframe_info) if iframe_info else 0,
            "iframe_details": iframe_info if iframe_info else [],
            "elements": elements_data
        }
        
        self._write_file(filepath, data)
        
        return os.path.join(self.session_id, filename)
    
    def write_decision(self, decision: dict, thought: str, step: int):
        """
        将决策详细信息写入文件（自动脱敏敏感信息）
        
        【参数】
        decision: dict - 决策内容
        thought: str - 思考过程
        step: int - 步骤编号
        
        【返回值】
        str: 相对于 process 文件夹的文件路径
        """
        filename = f"step_{step:03d}_decision.json"
        filepath = os.path.join(self.session_dir, filename)
        
        masked_decision = mask_sensitive_in_dict(decision) if decision else {}
        masked_thought = mask_password_in_thought(thought) if thought else ""
        
        data = {
            "step": step,
            "timestamp": datetime.now().isoformat(),
            "thought": masked_thought,
            "decision": masked_decision
        }
        
        self._write_file(filepath, data)
        
        return os.path.join(self.session_id, filename)
    
    def write_action_result(self, action_type: str, target_id: int, 
                           value: str, result: str, step: int, error: str = None):
        """
        将执行结果详细信息写入文件（自动脱敏敏感信息）
        
        【参数】
        action_type: str - 动作类型
        target_id: int - 目标元素ID
        value: str - 操作值
        result: str - 执行结果
        step: int - 步骤编号
        error: str - 错误信息（可选）
        
        【返回值】
        str: 相对于 process 文件夹的文件路径
        """
        filename = f"step_{step:03d}_action.json"
        filepath = os.path.join(self.session_dir, filename)
        
        if action_type and action_type.lower() in ("type", "input") and value:
            masked_value = mask_string(value, show_prefix=1, show_suffix=1)
        else:
            masked_value = value
        
        masked_result = sanitize_log_message(result) if result else result
        masked_error = sanitize_log_message(error) if error else error
        
        data = {
            "step": step,
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "target_id": target_id,
            "value": masked_value,
            "result": masked_result,
            "error": masked_error
        }
        
        self._write_file(filepath, data)
        
        return os.path.join(self.session_id, filename)
    
    def write_history(self, history: list, step: int):
        """
        将执行历史写入文件
        
        【参数】
        history: list - 执行历史列表
        step: int - 当前步骤编号
        
        【返回值】
        str: 相对于 process 文件夹的文件路径
        """
        filename = f"step_{step:03d}_history.json"
        filepath = os.path.join(self.session_dir, filename)
        
        data = {
            "step": step,
            "timestamp": datetime.now().isoformat(),
            "history": history
        }
        
        self._write_file(filepath, data)
        
        return os.path.join(self.session_id, filename)
    
    def write_session_summary(self, objective: str, total_steps: int, 
                              success: bool, termination_reason: str = None):
        """
        写入会话摘要文件
        
        【参数】
        objective: str - 任务目标
        total_steps: int - 总步骤数
        success: bool - 是否成功完成
        termination_reason: str - 终止原因（可选）
        """
        filename = "session_summary.json"
        filepath = os.path.join(self.session_dir, filename)
        
        data = {
            "session_id": self.session_id,
            "start_time": self.session_id,
            "end_time": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "objective": objective,
            "total_steps": total_steps,
            "success": success,
            "termination_reason": termination_reason
        }
        
        self._write_file(filepath, data)
        
        return os.path.join(self.session_id, filename)
    
    def print_summary(self, elements_count: int, url: str, saved_file: str):
        """
        打印简洁的摘要信息到终端
        
        【参数】
        elements_count: int - 元素总数
        url: str - 当前URL
        saved_file: str - 保存的文件路径（相对于 process 文件夹）
        """
        print(f"👁️ 感知: 发现 {elements_count} 个元素 | 详情: process/{saved_file}")
    
    def cleanup_old_sessions(self, keep_count: int = 20):
        """
        清理旧的会话文件夹，只保留最近的几个
        
        【参数】
        keep_count: int - 保留的会话文件夹数量
        """
        if not os.path.exists(self.process_dir):
            return
        
        sessions = []
        for name in os.listdir(self.process_dir):
            session_path = os.path.join(self.process_dir, name)
            if os.path.isdir(session_path) and name != self.session_id:
                sessions.append((session_path, os.path.getmtime(session_path)))
        
        sessions.sort(key=lambda x: x[1], reverse=True)
        
        for session_path, _ in sessions[keep_count:]:
            try:
                shutil.rmtree(session_path)
            except Exception:
                pass
    
    def flush(self):
        """刷新写入缓冲区"""
        if self._async_mode:
            while not self._write_queue.empty():
                import time
                time.sleep(0.1)


_output_handler: Optional[OutputHandler] = None


def get_output_handler(base_dir: str = None, async_mode: bool = False) -> OutputHandler:
    """
    获取全局输出处理器实例
    
    【参数】
    base_dir: str - 基础目录路径
    async_mode: bool - 是否启用异步模式（默认禁用，避免线程冲突）
    
    【返回值】
    OutputHandler: 输出处理器实例
    """
    global _output_handler
    if _output_handler is None:
        _output_handler = OutputHandler(base_dir, async_mode)
    return _output_handler


def reset_output_handler():
    """重置全局输出处理器（用于开始新的会话）"""
    global _output_handler
    if _output_handler is not None:
        _output_handler.flush()
        _output_handler._shutdown()
    _output_handler = None
