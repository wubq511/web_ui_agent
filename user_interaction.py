"""
================================================================================
用户交互模块 - 任务执行过程中的用户干预接口
================================================================================

【模块概述】
增加用户交互接口，允许在任务执行过程中动态调整参数或提供人工干预。

【核心功能】
1. 实时状态展示
2. 用户命令处理
3. 参数动态调整
4. 人工干预支持

【跨平台支持】
- Windows: 使用 msvcrt 模块实现非阻塞输入
- Unix/Linux/Mac: 使用 select 模块实现非阻塞输入
- IDE终端兼容: 使用定时轮询方式检测输入
================================================================================
"""

import sys
import os
import threading
import queue
import time
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from config import (
    ENABLE_USER_INTERACTION, INTERACTION_CHECK_INTERVAL,
    USER_INPUT_TIMEOUT
)

IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    try:
        import msvcrt
        HAS_MSVCRT = True
    except ImportError:
        HAS_MSVCRT = False
else:
    try:
        import select
        HAS_SELECT = True
    except ImportError:
        HAS_SELECT = False


class UserCommand(Enum):
    """用户命令枚举"""
    CONTINUE = "continue"
    PAUSE = "pause"
    ABORT = "abort"
    EXTEND_STEPS = "extend_steps"
    REDUCE_STEPS = "reduce_steps"
    SHOW_STATUS = "show_status"
    SAVE_CHECKPOINT = "save_checkpoint"
    LOAD_CHECKPOINT = "load_checkpoint"
    SET_TIMEOUT = "set_timeout"
    INTERVENE = "intervene"
    FAST_MODE = "fast_mode"
    HELP = "help"
    UNKNOWN = "unknown"
    CREDENTIAL_LOGIN = "credential_login"
    CREDENTIAL_ADD = "credential_add"
    CREDENTIAL_LIST = "credential_list"
    CREDENTIAL_SEARCH = "credential_search"
    CREDENTIAL_DELETE = "credential_delete"
    CREDENTIAL_STATUS = "credential_status"
    MODEL_SWITCH = "model_switch"
    MODEL_LIST = "model_list"
    MODEL_STATUS = "model_status"


@dataclass
class InteractionRequest:
    """交互请求"""
    command: UserCommand
    parameters: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class InteractionResponse:
    """交互响应"""
    success: bool
    message: str
    data: dict = field(default_factory=dict)


class UserInteractionManager:
    """
    用户交互管理器 - 处理任务执行过程中的用户干预
    
    【设计思路】
    提供非阻塞的用户交互机制：
    1. 后台线程监听用户输入（跨平台兼容）
    2. 命令队列处理用户请求
    3. 回调机制通知主程序
    4. 状态同步与展示
    
    【跨平台输入检测】
    - Windows: 使用 msvcrt.kbhit() 检测按键
    - Unix: 使用 select.select() 检测标准输入
    - 降级方案: 定时尝试读取输入
    """
    
    MAX_CONSECUTIVE_ERRORS = 5
    ERROR_RESTART_DELAY = 2.0
    INPUT_CHECK_INTERVAL = 0.02
    
    def __init__(self, enabled: bool = ENABLE_USER_INTERACTION):
        self.enabled = enabled
        self._command_queue: queue.Queue[InteractionRequest] = queue.Queue()
        self._input_thread: Optional[threading.Thread] = None
        self._running = False
        self._paused = False
        self._aborted = False
        self._callbacks: dict[UserCommand, list[Callable]] = {}
        
        self._current_status: dict = {}
        self._last_interaction_time: Optional[float] = None
        self._consecutive_errors: int = 0
        self._thread_restart_count: int = 0
        
        self._input_buffer: str = ""
        self._last_prompt_time: float = 0
        self._prompt_interval: float = 5.0
        self._last_process_time: float = 0
        self._process_interval: float = 0.5
    
    def _kbhit(self) -> bool:
        """
        检测是否有键盘输入（非阻塞）
        
        【跨平台实现】
        - Windows: 使用 msvcrt.kbhit()
        - Unix: 使用 select.select()
        - 降级: 总是返回 False，依赖其他机制
        """
        if IS_WINDOWS and HAS_MSVCRT:
            return bool(msvcrt.kbhit())
        elif not IS_WINDOWS and HAS_SELECT:
            try:
                readable, _, _ = select.select([sys.stdin], [], [], 0)
                return len(readable) > 0
            except Exception:
                return False
        else:
            return False
    
    def _getch(self) -> Optional[str]:
        """
        获取单个字符（非阻塞）
        
        【返回值】
        - 有输入时返回字符
        - 无输入时返回 None
        """
        if IS_WINDOWS and HAS_MSVCRT:
            if msvcrt.kbhit():
                char = msvcrt.getch()
                try:
                    return char.decode('utf-8')
                except UnicodeDecodeError:
                    return char.decode('gbk', errors='ignore')
        elif not IS_WINDOWS and HAS_SELECT:
            try:
                readable, _, _ = select.select([sys.stdin], [], [], 0)
                if readable:
                    return sys.stdin.read(1)
            except Exception:
                pass
        return None
    
    def _read_line_nonblocking(self) -> Optional[str]:
        """
        非阻塞读取一行输入
        
        【设计思路】
        逐字符读取，直到遇到换行符
        使用缓冲区存储部分输入
        """
        while self._kbhit():
            char = self._getch()
            if char is None:
                break
            
            if char in ('\r', '\n'):
                if self._input_buffer:
                    result = self._input_buffer
                    self._input_buffer = ""
                    return result
            elif char == '\x03':
                print("\n⚠️ 检测到 Ctrl+C，请使用 'abort' 命令终止任务")
            elif char == '\x08' or char == '\x7f':
                if self._input_buffer:
                    self._input_buffer = self._input_buffer[:-1]
                    print('\b \b', end='', flush=True)
            elif char.isprintable() or char == '\t':
                self._input_buffer += char
                print(char, end='', flush=True)
        
        return None
    
    def start(self):
        """启动交互监听"""
        if not self.enabled:
            return
        
        self._running = True
        # 注意：禁用后台线程，因为它会干扰 Playwright 的 greenlet
        # 用户交互改为在主线程中通过 process_user_commands() 处理
        # self._input_thread = threading.Thread(target=self._input_listener, daemon=True)
        # self._input_thread.start()
        print("💬 用户交互已启用 (输入 'help' 查看可用命令)")
        print("   💡 提示: 直接输入命令后按 Enter 即可执行")
    
    def stop(self):
        """停止交互监听"""
        self._running = False
        if self._input_thread and self._input_thread.is_alive():
            self._input_thread.join(timeout=1.0)
    
    def _input_listener(self):
        """
        后台输入监听线程 - 跨平台兼容版本
        
        【设计思路】
        使用非阻塞方式检测输入，兼容 IDE 终端和独立终端：
        1. Windows: 使用 msvcrt.kbhit() 检测按键
        2. Unix: 使用 select.select() 检测标准输入
        3. 定时显示提示信息，提醒用户可以输入命令
        """
        while self._running:
            try:
                line = self._read_line_nonblocking()
                
                if line is not None:
                    print()
                    if line.strip():
                        request = self._parse_command(line.strip())
                        self._command_queue.put(request)
                        self._consecutive_errors = 0
                    self._last_prompt_time = time.time()
                
                current_time = time.time()
                if current_time - self._last_prompt_time > self._prompt_interval:
                    if not self._paused:
                        pass
                    self._last_prompt_time = current_time
                
                time.sleep(self.INPUT_CHECK_INTERVAL)
                
            except Exception as e:
                self._consecutive_errors += 1
                print(f"⚠️ 输入处理错误 ({self._consecutive_errors}/{self.MAX_CONSECUTIVE_ERRORS}): {e}")
                
                if self._consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                    print(f"❌ 连续错误次数过多，尝试重启输入线程...")
                    self._thread_restart_count += 1
                    if self._thread_restart_count < 3:
                        time.sleep(self.ERROR_RESTART_DELAY)
                        self._consecutive_errors = 0
                    else:
                        print("❌ 输入线程重启次数过多，停止监听")
                        break
    
    def _restart_input_thread(self):
        """重启输入线程"""
        if self._input_thread and self._input_thread.is_alive():
            return
        
        self._input_thread = threading.Thread(target=self._input_listener, daemon=True)
        self._input_thread.start()
        print("🔄 输入线程已重启")
    
    def _parse_command(self, input_str: str) -> InteractionRequest:
        """解析用户命令"""
        parts = input_str.lower().split(maxsplit=2)
        cmd_str = parts[0] if parts else ""
        params = {}
        
        if len(parts) > 1:
            try:
                params["value"] = int(parts[1])
            except ValueError:
                params["value"] = parts[1]
        
        if len(parts) > 2:
            params["extra"] = parts[2]
        
        command_map = {
            "continue": UserCommand.CONTINUE,
            "c": UserCommand.CONTINUE,
            "pause": UserCommand.PAUSE,
            "p": UserCommand.PAUSE,
            "abort": UserCommand.ABORT,
            "a": UserCommand.ABORT,
            "stop": UserCommand.ABORT,
            "extend": UserCommand.EXTEND_STEPS,
            "e": UserCommand.EXTEND_STEPS,
            "reduce": UserCommand.REDUCE_STEPS,
            "r": UserCommand.REDUCE_STEPS,
            "status": UserCommand.SHOW_STATUS,
            "s": UserCommand.SHOW_STATUS,
            "save": UserCommand.SAVE_CHECKPOINT,
            "load": UserCommand.LOAD_CHECKPOINT,
            "timeout": UserCommand.SET_TIMEOUT,
            "intervene": UserCommand.INTERVENE,
            "i": UserCommand.INTERVENE,
            "fast": UserCommand.FAST_MODE,
            "f": UserCommand.FAST_MODE,
            "help": UserCommand.HELP,
            "h": UserCommand.HELP,
            "?": UserCommand.HELP,
            "cred_login": UserCommand.CREDENTIAL_LOGIN,
            "cred_add": UserCommand.CREDENTIAL_ADD,
            "cred_list": UserCommand.CREDENTIAL_LIST,
            "cred_search": UserCommand.CREDENTIAL_SEARCH,
            "cred_del": UserCommand.CREDENTIAL_DELETE,
            "cred_status": UserCommand.CREDENTIAL_STATUS,
            "credential": UserCommand.CREDENTIAL_STATUS,
            "cred": UserCommand.CREDENTIAL_STATUS,
            "model": UserCommand.MODEL_STATUS,
            "models": UserCommand.MODEL_LIST,
            "switch": UserCommand.MODEL_SWITCH,
            "m": UserCommand.MODEL_STATUS
        }
        
        command = command_map.get(cmd_str, UserCommand.UNKNOWN)
        
        return InteractionRequest(command=command, parameters=params)
    
    def register_callback(self, command: UserCommand, callback: Callable):
        """注册命令回调"""
        if command not in self._callbacks:
            self._callbacks[command] = []
        self._callbacks[command].append(callback)
    
    def show_input_prompt(self):
        """
        显示输入提示符
        
        【设计思路】
        在程序运行过程中定期显示提示符，提醒用户可以输入命令
        控制显示频率，避免刷屏
        """
        current_time = time.time()
        if current_time - self._last_prompt_time >= self._prompt_interval:
            if self.enabled and not self._paused:
                print("\n> ", end="", flush=True)
                self._last_prompt_time = current_time
    
    def process_commands(self, show_prompt: bool = False) -> list[InteractionResponse]:
        """
        处理待处理的命令
        
        【设计思路】
        主动检测用户输入并处理命令，不依赖后台线程
        控制提示符显示频率，避免刷屏
        
        【参数】
        show_prompt: 是否显示输入提示符
        """
        if show_prompt:
            self.show_input_prompt()
        
        responses = []
        
        line = self._read_line_nonblocking()
        if line is not None:
            print()
            if line.strip():
                request = self._parse_command(line.strip())
                response = self._handle_command(request)
                responses.append(response)
        
        while not self._command_queue.empty():
            try:
                request = self._command_queue.get_nowait()
                response = self._handle_command(request)
                responses.append(response)
            except queue.Empty:
                break
        
        return responses
    
    def _handle_command(self, request: InteractionRequest) -> InteractionResponse:
        """处理单个命令"""
        self._last_interaction_time = datetime.now().timestamp()
        
        if request.command == UserCommand.HELP:
            return self._handle_help()
        
        if request.command == UserCommand.PAUSE:
            self._paused = True
            return InteractionResponse(
                success=True,
                message="任务已暂停，输入 'continue' 继续"
            )
        
        if request.command == UserCommand.CONTINUE:
            self._paused = False
            return InteractionResponse(
                success=True,
                message="任务继续执行"
            )
        
        if request.command == UserCommand.ABORT:
            self._aborted = True
            self._paused = False
            self._running = False
            return InteractionResponse(
                success=True,
                message="任务已终止"
            )
        
        if request.command in self._callbacks:
            for callback in self._callbacks[request.command]:
                try:
                    result = callback(request.parameters)
                    if isinstance(result, dict):
                        return InteractionResponse(
                            success=True,
                            message=result.get("message", "命令执行成功"),
                            data=result
                        )
                except Exception as e:
                    return InteractionResponse(
                        success=False,
                        message=f"命令执行失败: {e}"
                    )
        
        return InteractionResponse(
            success=False,
            message=f"未知命令: {request.command.value}"
        )
    
    def _handle_help(self) -> InteractionResponse:
        """处理帮助命令"""
        help_text = """
可用命令:
  continue (c)     - 继续执行暂停的任务
  pause (p)        - 暂停当前任务
  abort (a)        - 终止任务
  extend (e) [n]   - 增加步骤限制 n (默认5)
  reduce (r) [n]   - 减少步骤限制 n (默认5)
  status (s)       - 显示当前状态
  save             - 保存检查点
  load             - 加载检查点
  timeout [n]      - 设置超时时间(秒)
  intervene (i) [n]- 人工干预：暂停终止倒计时 n秒 (默认60秒)
  fast (f)         - 切换快速模式（使用更严格的终止条件）
  help (h/?)       - 显示此帮助

凭证管理命令:
  cred_login       - 登录凭证管理器
  cred_add         - 添加账号凭证
  cred_list        - 列出所有凭证
  cred_search [关键词] - 搜索凭证
  cred_del [id]    - 删除凭证
  cred_status      - 显示凭证管理器状态
"""
        return InteractionResponse(
            success=True,
            message=help_text
        )
    
    def is_paused(self) -> bool:
        """检查是否暂停"""
        return self._paused
    
    def is_aborted(self) -> bool:
        """检查是否已终止"""
        return self._aborted
    
    def wait_if_paused(self, timeout: float = None):
        """
        如果暂停则等待
        
        【设计思路】
        在等待循环中持续检测用户输入并处理命令，
        确保用户输入的 continue/abort 命令能够被正确处理
        """
        if not self._paused:
            return
        
        print("⏸️ 任务已暂停，等待继续...")
        print("   输入 'c' 或 'continue' 继续执行")
        print("   输入 'a' 或 'abort' 终止任务")
        
        while self._paused and self._running and not self._aborted:
            line = self._read_line_nonblocking()
            if line is not None:
                print()
                if line.strip():
                    request = self._parse_command(line.strip())
                    if request.command == UserCommand.CONTINUE:
                        self._paused = False
                        print("💬 任务继续执行")
                        return
                    elif request.command == UserCommand.ABORT:
                        self._aborted = True
                        self._paused = False
                        print("💬 任务已终止")
                        return
                    else:
                        response = self._handle_command(request)
                        print(f"💬 {response.message}")
            
            time.sleep(0.02)
            
            if timeout:
                timeout -= 0.02
                if timeout <= 0:
                    break
    
    def update_status(self, status: dict):
        """更新当前状态"""
        self._current_status = status.copy()
    
    def get_status_display(self) -> str:
        """获取状态显示字符串"""
        if not self._current_status:
            return "暂无状态信息"
        
        lines = ["📊 当前任务状态:"]
        
        if "objective" in self._current_status:
            lines.append(f"  目标: {self._current_status['objective']}")
        if "step_count" in self._current_status:
            lines.append(f"  步骤: {self._current_status['step_count']}")
        if "max_steps" in self._current_status:
            lines.append(f"  最大步骤: {self._current_status['max_steps']}")
        if "progress" in self._current_status:
            lines.append(f"  进度: {self._current_status['progress']:.1%}")
        if "elapsed_time" in self._current_status:
            lines.append(f"  已用时间: {self._current_status['elapsed_time']:.1f}秒")
        if "status" in self._current_status:
            lines.append(f"  状态: {self._current_status['status']}")
        
        return "\n".join(lines)
    
    def request_user_confirmation(self, message: str, 
                                  options: list[str] = None) -> str:
        """
        请求用户确认
        
        【参数】
        message: 提示消息
        options: 可选项列表
        
        【返回值】
        str: 用户选择
        """
        if not self.enabled:
            return options[0] if options else "yes"
        
        print(f"\n❓ {message}")
        if options:
            print(f"   可选项: {', '.join(options)}")
        print("   请输入选择: ", end="", flush=True)
        
        try:
            user_input = input().strip().lower()
            return user_input if user_input else (options[0] if options else "yes")
        except EOFError:
            return options[0] if options else "yes"
    
    def reset(self):
        """重置交互管理器"""
        self._paused = False
        self._aborted = False
        self._current_status.clear()
        self._last_interaction_time = None
        while not self._command_queue.empty():
            try:
                self._command_queue.get_nowait()
            except queue.Empty:
                break
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "paused": self._paused,
            "aborted": self._aborted,
            "running": self._running,
            "last_interaction_time": self._last_interaction_time,
            "pending_commands": self._command_queue.qsize()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserInteractionManager':
        """从字典创建实例"""
        manager = cls(enabled=data.get("enabled", ENABLE_USER_INTERACTION))
        manager._paused = data.get("paused", False)
        manager._aborted = data.get("aborted", False)
        manager._last_interaction_time = data.get("last_interaction_time")
        return manager
