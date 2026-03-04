"""
================================================================================
Web UI Agent Web服务器
提供HTTP API和WebSocket服务供前端调用
实现真实的浏览器控制和高频截图流
支持执行 python main.py 命令
================================================================================
"""

import asyncio
import sys
import subprocess
import os
import re

# Windows 平台需要使用 ProactorEventLoop 来支持子进程
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import base64
import io
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
from PIL import Image

# 尝试导入 Playwright
try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: Playwright not available. Browser features disabled.")

# 导入配置
from config import (
    AVAILABLE_MODELS, DEFAULT_MODEL,
    CDP_PORT, CDP_HOST,
    SCREENSHOT_TARGET_FPS, SCREENSHOT_MIN_FPS, SCREENSHOT_MAX_FPS,
    SCREENSHOT_JPEG_QUALITY, SCREENSHOT_MAX_WIDTH, SCREENSHOT_MAX_HEIGHT
)

# 导入安全工具
from security_utils import mask_string, sanitize_log_message

# 导入暂停控制器
try:
    from pause_controller import PauseController, get_pause_controller
    PAUSE_CONTROLLER_AVAILABLE = True
except ImportError:
    PAUSE_CONTROLLER_AVAILABLE = False
    print("Warning: PauseController not available. Pause/Resume features disabled.")


# ================================================================================
# 请求模型
# ================================================================================

class StartAgentRequest(BaseModel):
    """启动 Agent 请求模型"""
    objective: str
    model: str = DEFAULT_MODEL


class UserInputRequest(BaseModel):
    """用户输入请求模型"""
    input: str


class MouseClickRequest(BaseModel):
    """鼠标点击请求模型"""
    x: int
    y: int


class TypeTextRequest(BaseModel):
    """输入文本请求模型"""
    text: str


# ================================================================================
# 全局状态管理
# ================================================================================

class AgentStateManager:
    """
    Agent 状态管理器
    
    管理 Agent 的运行状态、浏览器实例、日志等
    """
    
    def __init__(self):
        """初始化状态管理器"""
        # Agent 状态
        self.status: str = "idle"
        self.objective: str = ""
        self.selected_model: str = DEFAULT_MODEL
        self.current_step: int = 0
        self.max_steps: int = 15
        self.progress_ratio: float = 0.0  # 基于多维度评估的进度
        self.last_action: str = "Waiting to start..."
        self.step_description: str = "Agent is ready"
        self.current_url: str = ""
        self.logs: List[Dict] = []
        self.websocket_clients: List[WebSocket] = []
        self.task_complexity: str = "simple"
        self.popup_detected: bool = False
        self.login_form_detected: bool = False
        self.credential_manager_logged_in: bool = False  # 凭证管理器登录状态
        
        # 浏览器相关
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        # 截图流控制 - 动态帧率
        self.screenshot_task: Optional[asyncio.Task] = None
        self.screenshot_interval: float = 1.0 / SCREENSHOT_TARGET_FPS
        self.latest_screenshot: Optional[str] = None
        self.is_capturing: bool = False
        # 动态帧率控制
        self._current_fps: float = SCREENSHOT_TARGET_FPS
        self._last_screenshot_time: float = 0
        self._screenshot_durations: List[float] = []  # 记录最近截图耗时
        self._screenshot_cache: Optional[bytes] = None  # 截图字节缓存
        self._last_screenshot_hash: Optional[str] = None  # 上次截图的哈希值（用于差分检测）
        
        # 命令执行相关
        self.command_process: Optional[asyncio.subprocess.Process] = None
        self.command_output: List[str] = []
        self.command_status: str = "idle"  # idle, running, completed, error
        self.command_exit_code: Optional[int] = None
        self.command_start_time: Optional[float] = None
        
        # 交互式终端相关
        self.waiting_for_input: bool = False  # 是否等待用户输入
        self.input_prompt: str = ""  # 输入提示信息
        self.input_queue: asyncio.Queue = asyncio.Queue()  # 用户输入队列
        self.terminal_lines: List[Dict] = []  # 终端输出行（带类型标记）
        self._current_input_is_password: bool = False  # 当前输入是否是密码
    
    def add_log(self, message: str, level: str = "info", details: str = None):
        """
        添加日志并广播
        
        Args:
            message: 日志消息
            level: 日志级别 (info, success, warning, error)
            details: 详细内容
        """
        log_entry = {
            "id": f"{datetime.now().timestamp()}-{len(self.logs)}",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "details": details
        }
        self.logs.insert(0, log_entry)
        if len(self.logs) > 100:
            self.logs = self.logs[:100]
        
        # 广播日志
        asyncio.create_task(self.broadcast({
            "type": "log",
            "payload": log_entry
        }))
    
    async def broadcast(self, message: Dict):
        """
        广播消息给所有 WebSocket 客户端
        
        Args:
            message: 要广播的消息字典
        """
        disconnected = []
        for client in self.websocket_clients:
            try:
                await client.send_json(message)
            except:
                disconnected.append(client)
        
        for client in disconnected:
            if client in self.websocket_clients:
                self.websocket_clients.remove(client)
    
    async def broadcast_state(self):
        """广播当前状态"""
        await self.broadcast({
            "type": "state_update",
            "payload": self.get_state_dict()
        })
    
    async def broadcast_screenshot(self, screenshot_base64: str):
        """
        广播截图
        
        Args:
            screenshot_base64: Base64 编码的截图
        """
        self.latest_screenshot = screenshot_base64
        await self.broadcast({
            "type": "screenshot",
            "payload": {
                "screenshot": screenshot_base64,
                "url": self.current_url,
                "timestamp": datetime.now().isoformat()
            }
        })
    
    def get_state_dict(self) -> Dict[str, Any]:
        """
        获取状态字典
        
        Returns:
            包含当前状态的字典
        """
        return {
            "objective": self.objective,
            "currentUrl": self.current_url,
            "currentStep": self.current_step,
            "maxSteps": self.max_steps,
            "lastAction": self.last_action,
            "stepDescription": self.step_description,
            "isDone": self.status == "completed",
            "errorMessage": None if self.status != "error" else "An error occurred",
            "progressRatio": self.progress_ratio,  # 使用多维度评估的进度
            "stagnationCount": 0,
            "taskComplexity": self.task_complexity,
            "popupDetected": self.popup_detected,
            "loginFormDetected": self.login_form_detected,
            "waitingForInput": self.waiting_for_input,
            "inputPrompt": self.input_prompt,
            "terminalLines": self.terminal_lines[-100:] if self.terminal_lines else [],
            "credentialManagerLoggedIn": self.credential_manager_logged_in,
        }
    
    async def add_terminal_line(self, line: str, line_type: str = "output"):
        """
        添加终端输出行并广播
        
        Args:
            line: 输出行内容
            line_type: 行类型 (output, error, input, prompt, system)
        """
        line_entry = {
            "id": f"{datetime.now().timestamp()}-{len(self.terminal_lines)}",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "type": line_type,
            "content": line
        }
        self.terminal_lines.append(line_entry)
        if len(self.terminal_lines) > 500:
            self.terminal_lines = self.terminal_lines[-500:]
        
        await self.broadcast({
            "type": "terminal_line",
            "payload": line_entry
        })
    
    async def set_waiting_for_input(self, prompt: str = ""):
        """
        设置等待用户输入状态
        
        Args:
            prompt: 输入提示信息
        """
        self.waiting_for_input = True
        self.input_prompt = prompt
        
        if prompt:
            await self.add_terminal_line(prompt, "prompt")
        
        await self.broadcast({
            "type": "input_required",
            "payload": {
                "waiting": True,
                "prompt": prompt
            }
        })
    
    async def submit_user_input(self, user_input: str, is_password: bool = False):
        """
        提交用户输入
        
        Args:
            user_input: 用户输入的内容
            is_password: 是否是密码输入
        """
        if not self.waiting_for_input:
            return False
        
        if is_password:
            display_text = "> " + "*" * min(len(user_input), 8)
        else:
            display_text = f"> {user_input}"
        await self.add_terminal_line(display_text, "input")
        
        await self.input_queue.put(user_input)
        
        self.waiting_for_input = False
        self.input_prompt = ""
        
        await self.broadcast({
            "type": "input_required",
            "payload": {
                "waiting": False,
                "prompt": ""
            }
        })
        
        return True
    
    async def get_user_input(self, prompt: str = "") -> str:
        """
        等待并获取用户输入
        
        Args:
            prompt: 输入提示信息
            
        Returns:
            用户输入的内容
        """
        await self.set_waiting_for_input(prompt)
        
        user_input = await self.input_queue.get()
        return user_input
    
    def clear_terminal(self):
        """清空终端输出"""
        self.terminal_lines = []
        self.waiting_for_input = False
        self.input_prompt = ""
    
    async def launch_browser(self) -> bool:
        """
        启动或连接浏览器
        
        【设计思路】
        1. 首先尝试通过 CDP 连接到 agent 已启动的浏览器（localhost:9222）
        2. 如果连接失败，则启动独立的浏览器实例
        
        Returns:
            启动成功返回 True，失败返回 False
        """
        if not PLAYWRIGHT_AVAILABLE:
            self.add_log("Playwright not available, browser not launched", "warning")
            return False
        
        try:
            if not self.playwright:
                self.add_log("Starting playwright...", "info")
                self.playwright = await async_playwright().start()
            
            # 首先尝试连接到 agent 的浏览器（通过 CDP）
            cdp_url = f"http://{CDP_HOST}:{CDP_PORT}"
            self.add_log(f"Trying to connect to agent browser via CDP: {cdp_url}", "info")
            
            try:
                self.browser = await self.playwright.chromium.connect_over_cdp(cdp_url)
                self.add_log("Connected to agent browser via CDP", "success")
                
                # 获取现有的上下文和页面 - 使用最新的
                contexts = self.browser.contexts
                if contexts:
                    # 获取最后一个 context（最新创建的）
                    self.context = contexts[-1]
                    pages = self.context.pages
                    if pages:
                        # 获取最后一个页面（最新打开的）
                        self.page = pages[-1]
                        self.add_log(f"Using latest page: {self.page.url[:50] if self.page.url else 'about:blank'}", "info")
                    else:
                        self.page = await self.context.new_page()
                        self.add_log("Created new page in existing context", "info")
                else:
                    self.context = await self.browser.new_context(
                        viewport={'width': SCREENSHOT_MAX_WIDTH, 'height': SCREENSHOT_MAX_HEIGHT}
                    )
                    self.page = await self.context.new_page()
                    self.add_log("Created new context and page", "info")
                
                # 设置浏览器级别的监听器
                self._setup_browser_listeners()
                
                return True
                
            except Exception as cdp_error:
                self.add_log(f"CDP connection failed: {str(cdp_error)[:100]}", "warning")
                self.add_log("Launching independent browser instance...", "info")
                
                # CDP 连接失败，启动独立浏览器
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox', 
                        '--disable-setuid-sandbox',
                        f'--window-size={SCREENSHOT_MAX_WIDTH},{SCREENSHOT_MAX_HEIGHT}'
                    ]
                )
                
                self.context = await self.browser.new_context(
                    viewport={'width': SCREENSHOT_MAX_WIDTH, 'height': SCREENSHOT_MAX_HEIGHT}
                )
                
                self.page = await self.context.new_page()
                self.add_log("Independent browser launched", "success")
                
                return True
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[BROWSER ERROR] {error_detail}")
            self.add_log(f"Failed to launch browser: {str(e)}", "error")
            return False
    
    def _setup_browser_listeners(self):
        """
        设置浏览器级别的监听器
        
        【功能说明】
        1. 监听新 context 创建
        2. 监听新页面创建
        3. 自动切换到最新的活动页面
        """
        if not self.browser:
            return
        
        def on_context_created(context):
            print(f"[Screenshot Stream] New context created")
            self.context = context
            
            # 在新 context 上监听页面创建
            def on_page_created(page):
                print(f"[Screenshot Stream] New page created: {page.url if page.url else 'about:blank'}")
                self.page = page
                self.add_log(f"Switched to new page: {page.url[:50] if page.url else 'about:blank'}", "info")
            
            context.on("page", on_page_created)
            
            # 如果 context 已有页面，切换到最新的
            pages = context.pages
            if pages:
                self.page = pages[-1]
                print(f"[Screenshot Stream] Using existing page: {self.page.url if self.page.url else 'about:blank'}")
        
        try:
            # 监听新 context 创建
            self.browser.on("context", on_context_created)
            print("[Screenshot Stream] Browser listeners set up successfully")
            
            # 为现有的 context 也设置监听器
            for ctx in self.browser.contexts:
                def on_page_created_for_ctx(page, ctx=ctx):
                    print(f"[Screenshot Stream] New page in existing context: {page.url if page.url else 'about:blank'}")
                    self.page = page
                    self.context = ctx
                    self.add_log(f"Switched to new page: {page.url[:50] if page.url else 'about:blank'}", "info")
                
                ctx.on("page", on_page_created_for_ctx)
                
        except Exception as e:
            print(f"[Screenshot Stream] Failed to set up browser listeners: {e}")
    
    def _setup_page_listener(self):
        """
        设置页面监听器（兼容旧调用）
        
        【功能说明】
        当 agent 创建新页面时，自动切换到最新页面进行截图
        """
        # 调用新的 browser 级别监听器
        self._setup_browser_listeners()
    
    async def try_connect_to_agent_browser(self) -> bool:
        """
        尝试连接到 agent 的浏览器
        
        【使用场景】
        当 agent 通过 main.py 启动后，web_server 需要连接到其浏览器才能截图
        
        Returns:
            连接成功返回 True
        """
        if not PLAYWRIGHT_AVAILABLE or not self.playwright:
            return False
        
        try:
            cdp_url = f"http://{CDP_HOST}:{CDP_PORT}"
            self.browser = await self.playwright.chromium.connect_over_cdp(cdp_url)
            
            contexts = self.browser.contexts
            if contexts:
                # 获取最后一个 context（最新创建的）
                self.context = contexts[-1]
                pages = self.context.pages
                if pages:
                    # 获取最后一个页面（最新打开的）
                    self.page = pages[-1]
                    self.add_log("Connected to agent browser", "success")
                    # 设置页面监听器
                    self._setup_page_listener()
                    return True
            
            return False
        except Exception:
            return False
    
    async def close_browser(self):
        """
        关闭浏览器连接
        
        【注意】
        如果是通过 CDP 连接到 agent 的浏览器，我们只断开连接，不关闭浏览器
        因为浏览器是由 agent 进程管理的
        """
        try:
            # 首先停止截图流
            await self.stop_screenshot_stream()
            
            # 断开页面引用（不关闭，因为可能是 agent 的页面）
            self.page = None
            self.context = None
            
            # 如果是独立启动的浏览器，才关闭它
            # CDP 连接的浏览器不应该被我们关闭
            if self.browser and self.browser.is_connected():
                try:
                    # 检查是否是 CDP 连接
                    # CDP 连接的浏览器调用 close() 会关闭整个浏览器，包括 agent 的
                    # 所以我们只断开连接
                    self.browser = None
                except Exception:
                    pass
            
            # 只有当我们独立启动了 playwright 时才停止它
            # 这需要更复杂的逻辑来判断，暂时保留
            if self.playwright:
                # 不停止 playwright，因为它可能被重用
                pass
            
            self.add_log("Browser connection closed", "info")
            
        except Exception as e:
            print(f"Error closing browser: {e}")
    
    async def start_screenshot_stream(self):
        """启动高频截图流（动态帧率）"""
        self.is_capturing = True
        if self.screenshot_task:
            self.screenshot_task.cancel()
        
        # 重置帧率控制变量
        self._current_fps = SCREENSHOT_TARGET_FPS
        self._screenshot_durations = []
        
        self.screenshot_task = asyncio.create_task(self._screenshot_loop())
        self.add_log(f"Screenshot stream started (target: {SCREENSHOT_TARGET_FPS}fps)", "info")
    
    async def stop_screenshot_stream(self):
        """停止截图流"""
        self.is_capturing = False
        if self.screenshot_task:
            self.screenshot_task.cancel()
            try:
                await self.screenshot_task
            except asyncio.CancelledError:
                pass
            self.screenshot_task = None
        self.add_log("Screenshot stream stopped", "info")
    
    def _calculate_dynamic_interval(self, screenshot_duration: float) -> float:
        """
        计算动态截图间隔
        
        【算法说明】
        根据截图耗时动态调整帧率：
        - 如果截图很快（< 20ms），保持高帧率
        - 如果截图较慢，降低帧率以保证稳定性
        - 避免帧率过低（最低 10fps）
        """
        # 记录最近的截图耗时
        self._screenshot_durations.append(screenshot_duration)
        if len(self._screenshot_durations) > 10:
            self._screenshot_durations.pop(0)
        
        # 计算平均耗时
        avg_duration = sum(self._screenshot_durations) / len(self._screenshot_durations)
        
        # 目标帧间隔 = 目标帧时间 - 平均截图耗时
        target_frame_time = 1.0 / SCREENSHOT_TARGET_FPS
        ideal_interval = max(0.001, target_frame_time - avg_duration)
        
        # 计算实际帧率
        actual_fps = 1.0 / (avg_duration + ideal_interval)
        
        # 限制帧率范围
        if actual_fps > SCREENSHOT_MAX_FPS:
            actual_fps = SCREENSHOT_MAX_FPS
        elif actual_fps < SCREENSHOT_MIN_FPS:
            actual_fps = SCREENSHOT_MIN_FPS
        
        self._current_fps = actual_fps
        return 1.0 / actual_fps
    
    async def _screenshot_loop(self):
        """
        高频截图循环 - 动态帧率
        
        【优化特性】
        1. 动态帧率调整：根据截图耗时自动调整帧率
        2. 内存优化：重用缓存，减少临时对象
        3. 差分检测：避免发送相同的截图
        4. 自动切换到最新活动页面
        """
        import time
        import hashlib
        
        print(f"[Screenshot Loop] Started, is_capturing={self.is_capturing}")
        
        while self.is_capturing:
            try:
                start_time = time.time()
                
                # 定期检查是否有更新的页面
                if self.browser and self.browser.contexts:
                    contexts = self.browser.contexts
                    if contexts:
                        latest_context = contexts[-1]
                        if latest_context.pages:
                            latest_page = latest_context.pages[-1]
                            # 如果发现更新的页面，切换到它
                            if latest_page != self.page:
                                print(f"[Screenshot Loop] Switching to newer page: {latest_page.url if latest_page.url else 'about:blank'}")
                                self.page = latest_page
                                self.context = latest_context
                
                # 检查是否有可用的页面
                if self.page:
                    try:
                        # 截取页面截图
                        screenshot_bytes = await self.page.screenshot(
                            type='jpeg',
                            quality=SCREENSHOT_JPEG_QUALITY,
                            full_page=False
                        )
                        
                        # 计算截图哈希（用于差分检测）
                        screenshot_hash = hashlib.md5(screenshot_bytes).hexdigest()[:16]
                        
                        # 只有当截图内容变化时才广播
                        if screenshot_hash != self._last_screenshot_hash:
                            self._last_screenshot_hash = screenshot_hash
                            self._screenshot_cache = screenshot_bytes
                            
                            # 转换为 base64（直接使用缓存的字节）
                            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                            
                            # 广播截图
                            await self.broadcast_screenshot(f"data:image/jpeg;base64,{screenshot_base64}")
                        
                        # 更新当前 URL
                        try:
                            self.current_url = self.page.url
                        except Exception:
                            pass
                        
                    except Exception as screenshot_error:
                        error_str = str(screenshot_error).lower()
                        # 截图失败时尝试重新连接浏览器
                        if "target closed" in error_str or "disconnected" in error_str or "page closed" in error_str:
                            print(f"[Screenshot Loop] Page error: {screenshot_error}")
                            # 尝试获取其他可用页面
                            if self.browser and self.browser.contexts:
                                for ctx in reversed(self.browser.contexts):
                                    if ctx.pages:
                                        self.page = ctx.pages[-1]
                                        self.context = ctx
                                        print(f"[Screenshot Loop] Switched to backup page")
                                        break
                
                # 计算截图耗时
                screenshot_duration = time.time() - start_time
                
                # 动态调整间隔
                dynamic_interval = self._calculate_dynamic_interval(screenshot_duration)
                
                await asyncio.sleep(dynamic_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Screenshot error: {e}")
                await asyncio.sleep(0.1)  # 错误时等待稍长时间
    
    async def navigate_to(self, url: str) -> bool:
        """
        导航到指定 URL
        
        Args:
            url: 目标 URL
            
        Returns:
            导航成功返回 True，失败返回 False
        """
        if self.page:
            try:
                await self.page.goto(url, wait_until='networkidle')
                self.current_url = self.page.url
                self.add_log(f"Navigated to {url}", "info")
                return True
            except Exception as e:
                self.add_log(f"Failed to navigate to {url}: {str(e)}", "error")
                return False
        return False
    
    async def click(self, x: int, y: int) -> bool:
        """
        在指定坐标点击
        
        Args:
            x: X 坐标
            y: Y 坐标
            
        Returns:
            点击成功返回 True，失败返回 False
        """
        if self.page:
            try:
                await self.page.mouse.click(x, y)
                self.add_log(f"Clicked at ({x}, {y})", "info")
                return True
            except Exception as e:
                self.add_log(f"Failed to click: {str(e)}", "error")
                return False
        return False
    
    async def type_text(self, text: str) -> bool:
        """
        输入文本
        
        Args:
            text: 要输入的文本
            
        Returns:
            输入成功返回 True，失败返回 False
        """
        if self.page:
            try:
                await self.page.keyboard.type(text)
                self.add_log(f"Typed text: {text[:50]}...", "info")
                return True
            except Exception as e:
                self.add_log(f"Failed to type: {str(e)}", "error")
                return False
        return False
    
    async def press_key(self, key: str) -> bool:
        """
        按下键盘按键
        
        Args:
            key: 按键名称
            
        Returns:
            按键成功返回 True，失败返回 False
        """
        if self.page:
            try:
                await self.page.keyboard.press(key)
                self.add_log(f"Pressed key: {key}", "info")
                return True
            except Exception as e:
                self.add_log(f"Failed to press key: {str(e)}", "error")
                return False
        return False
    
    async def execute_main_py(self, objective: str = None, url: str = None, 
                               max_steps: int = None, model: str = None) -> bool:
        """
        执行 python main.py 命令
        
        【安全措施】
        1. 只允许执行 python main.py，不接受任意命令
        2. 参数经过严格验证和转义
        3. 使用 subprocess 安全执行
        
        Args:
            objective: 任务目标
            url: 起始 URL
            max_steps: 最大步骤数
            model: 使用的模型
            
        Returns:
            启动成功返回 True
        """
        if self.command_status == "running":
            self.add_log("Command already running", "warning")
            return False
        
        # 设置 Agent 状态为 running
        self.status = "running"
        self.command_status = "running"
        self.command_output = []
        self.command_exit_code = None
        self.command_start_time = datetime.now().timestamp()
        self.clear_terminal()
        
        cmd = ["python", "main.py"]
        
        if objective:
            sanitized_objective = self._sanitize_arg(objective)
            cmd.extend(["-o", sanitized_objective])
        if url:
            sanitized_url = self._sanitize_url(url)
            cmd.extend(["-u", sanitized_url])
        if max_steps:
            try:
                steps = int(max_steps)
                if 1 <= steps <= 100:
                    cmd.extend(["-m", str(steps)])
                    self.max_steps = steps  # 更新后端的 max_steps
            except ValueError:
                pass
        else:
            # 使用 main.py 的默认值
            self.max_steps = 30
        if model and model in AVAILABLE_MODELS:
            cmd.extend(["--model", model])
        
        self.add_log("Starting python main.py...", "info")
        await self.add_terminal_line(f"$ {' '.join(cmd)}", "system")
        
        try:
            project_dir = os.path.dirname(os.path.abspath(__file__))
            
            self.command_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=project_dir,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}
            )
            
            asyncio.create_task(self._read_command_output())
            
            # 启动截图流（延迟启动，等待 agent 浏览器初始化）
            asyncio.create_task(self._delayed_start_screenshot_stream())
            
            self.add_log(f"Command started: {' '.join(cmd)}", "success")
            await self.broadcast_command_status()
            return True
            
        except Exception as e:
            self.command_status = "error"
            self.command_exit_code = -1
            self.add_log(f"Failed to start command: {str(e)}", "error")
            await self.broadcast_command_status()
            return False
    
    async def _delayed_start_screenshot_stream(self, max_retries: int = 15, retry_delay: float = 1.0):
        """
        延迟启动截图流
        
        【设计思路】
        agent 启动浏览器需要时间，我们延迟一段时间后尝试连接并启动截图流
        
        Args:
            max_retries: 最大重试次数
            retry_delay: 每次重试的间隔（秒）
        """
        import asyncio
        
        print(f"[Screenshot Stream] Waiting for agent browser to start...")
        
        for attempt in range(max_retries):
            await asyncio.sleep(retry_delay)
            
            # 检查命令是否仍在运行
            if self.command_status != "running":
                self.add_log("Command not running, aborting screenshot stream", "info")
                print(f"[Screenshot Stream] Command not running, aborting")
                return
            
            # 尝试连接到 agent 的浏览器
            try:
                if not self.playwright:
                    self.playwright = await async_playwright().start()
                
                cdp_url = f"http://{CDP_HOST}:{CDP_PORT}"
                print(f"[Screenshot Stream] Attempt {attempt + 1}/{max_retries}: Connecting to {cdp_url}")
                self.browser = await self.playwright.chromium.connect_over_cdp(cdp_url)
                
                # 设置浏览器级别的监听器（监听新 context 和页面）
                self._setup_browser_listeners()
                
                # 获取页面 - 使用最新的页面而不是第一个
                contexts = self.browser.contexts
                print(f"[Screenshot Stream] Found {len(contexts)} contexts")
                
                if contexts:
                    # 获取最后一个 context（最新创建的）
                    self.context = contexts[-1]
                    pages = self.context.pages
                    print(f"[Screenshot Stream] Found {len(pages)} pages in last context")
                    
                    if pages:
                        # 获取最后一个页面（最新打开的）
                        self.page = pages[-1]
                        page_url = self.page.url if self.page.url else 'about:blank'
                        self.add_log(f"Connected to agent browser: {page_url[:50]}", "success")
                        print(f"[Screenshot Stream] Connected to latest page: {page_url}")
                        
                        # 启动截图流
                        await self.start_screenshot_stream()
                        print(f"[Screenshot Stream] Screenshot stream started successfully")
                        return
                    else:
                        print(f"[Screenshot Stream] No pages found in context")
                else:
                    print(f"[Screenshot Stream] No contexts found")
                
            except Exception as e:
                print(f"[Screenshot Stream] Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    self.add_log(f"Waiting for agent browser... (attempt {attempt + 1}/{max_retries})", "info")
                else:
                    self.add_log(f"Failed to connect to agent browser after {max_retries} attempts", "warning")
        
        self.add_log("Screenshot stream not started (no browser connection)", "warning")
        print(f"[Screenshot Stream] Failed to start after {max_retries} attempts")
    
    def _sanitize_arg(self, arg: str) -> str:
        """
        清理参数，防止命令注入
        
        移除或转义危险字符
        """
        if not arg:
            return ""
        dangerous_chars = [';', '&', '|', '`', '$', '(', ')', '{', '}', '<', '>', '\n', '\r']
        result = arg
        for char in dangerous_chars:
            result = result.replace(char, '')
        return result.strip()
    
    def _sanitize_url(self, url: str) -> str:
        """
        清理 URL 参数
        
        只允许 http/https 协议
        """
        if not url:
            return ""
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            return ""
        return self._sanitize_arg(url)
    
    async def _read_command_output(self):
        """
        异步读取命令输出并广播
        
        【交互式终端支持】
        1. 检测需要用户输入的提示（如密码输入、确认等）
        2. 等待前端用户输入
        3. 将用户输入传递给子进程
        
        【重要改进】
        使用行读取 + 超时机制，处理没有换行符的提示（如 "主密码: "）
        """
        if not self.command_process:
            return
        
        input_prompt_patterns = [
            "主密码:", "密码:", "password:", "Password:", 
            "username:", "用户名:", "请输入", "按 Enter", 
            "跳过", "[y/n]", "(y/n)", "登录后", "自动填充"
        ]
        
        try:
            while True:
                try:
                    line = await asyncio.wait_for(
                        self.command_process.stdout.readline(),
                        timeout=0.5
                    )
                    
                    if not line:
                        break
                    
                    try:
                        line_text = line.decode('utf-8', errors='replace').rstrip()
                    except:
                        line_text = line.decode('gbk', errors='replace').rstrip()
                    
                    if line_text:
                        self.command_output.append(line_text)
                        if len(self.command_output) > 500:
                            self.command_output = self.command_output[-500:]
                        
                        line_type = self._detect_line_type(line_text)
                        await self.add_terminal_line(line_text, line_type)
                        
                        await self.broadcast({
                            "type": "command_output",
                            "payload": {
                                "line": line_text,
                                "timestamp": datetime.now().isoformat()
                            }
                        })
                        
                        self._parse_output_for_status(line_text)
                        
                        # 解析最大步骤数
                        max_steps_match = re.search(r'最大步骤:\s*(\d+)', line_text)
                        if max_steps_match:
                            self.max_steps = int(max_steps_match.group(1))
                            print(f"[WebSocket] Max steps updated to {self.max_steps}")
                        
                        # 解析进度信息（基于多维度评估的准确进度）
                        # 格式: "📊 进度: 45% | 停滞: 2/8" (可能包含 ANSI 颜色代码)
                        clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line_text)
                        progress_match = re.search(r'📊 进度:\s*(\d+)%', clean_line)
                        if progress_match:
                            new_progress = int(progress_match.group(1)) / 100
                            if new_progress != self.progress_ratio:
                                self.progress_ratio = new_progress
                                print(f"[WebSocket] Progress updated to {new_progress:.0%}")
                        
                        # 解析凭证管理器登录状态
                        if "✅ 凭证管理器登录成功" in line_text:
                            self.credential_manager_logged_in = True
                            print(f"[WebSocket] Credential manager logged in")
                        
                        # 解析任务复杂度更新
                        complexity_match = re.search(r'任务复杂度更新:\s*(simple|medium|complex|very_complex)', line_text)
                        if complexity_match:
                            new_complexity = complexity_match.group(1)
                            if new_complexity != self.task_complexity:
                                self.task_complexity = new_complexity
                                print(f"[WebSocket] Task complexity updated to {new_complexity}")
                        
                        # 广播状态更新（每次输出都广播，确保前端实时显示）
                        # 打印当前状态用于调试
                        print(f"[WebSocket] Broadcasting state: step={self.current_step}, stepDesc={self.step_description[:50]}, lastAction={self.last_action[:30]}")
                        await self.broadcast_state()
                        
                        if self._is_input_required(line_text):
                            await self._handle_input_request(line_text)
                    
                except asyncio.TimeoutError:
                    if self.command_process.stdout.at_eof():
                        break
                    
                    try:
                        chunk = await self.command_process.stdout.read(1024)
                        if chunk:
                            try:
                                chunk_text = chunk.decode('utf-8', errors='replace')
                            except:
                                chunk_text = chunk.decode('gbk', errors='replace')
                            
                            chunk_stripped = chunk_text.rstrip()
                            if chunk_stripped:
                                self.command_output.append(chunk_stripped)
                                if len(self.command_output) > 500:
                                    self.command_output = self.command_output[-500:]
                                
                                line_type = self._detect_line_type(chunk_stripped)
                                await self.add_terminal_line(chunk_stripped, line_type)
                                
                                await self.broadcast({
                                    "type": "command_output",
                                    "payload": {
                                        "line": chunk_stripped,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                })
                                
                                # 解析状态更新
                                self._parse_output_for_status(chunk_stripped)
                                
                                # 解析进度信息
                                clean_chunk = re.sub(r'\x1b\[[0-9;]*m', '', chunk_stripped)
                                progress_match = re.search(r'📊 进度:\s*(\d+)%', clean_chunk)
                                if progress_match:
                                    new_progress = int(progress_match.group(1)) / 100
                                    if new_progress != self.progress_ratio:
                                        self.progress_ratio = new_progress
                                        print(f"[WebSocket] Progress updated to {new_progress:.0%}")
                                
                                # 解析凭证管理器登录状态
                                if "✅ 凭证管理器登录成功" in chunk_stripped:
                                    self.credential_manager_logged_in = True
                                    print(f"[WebSocket] Credential manager logged in")
                                
                                # 解析任务复杂度更新
                                complexity_match = re.search(r'任务复杂度更新:\s*(simple|medium|complex|very_complex)', chunk_stripped)
                                if complexity_match:
                                    new_complexity = complexity_match.group(1)
                                    if new_complexity != self.task_complexity:
                                        self.task_complexity = new_complexity
                                        print(f"[WebSocket] Task complexity updated to {new_complexity}")
                                
                                # 广播状态更新
                                await self.broadcast_state()
                                
                                if self._is_input_required(chunk_stripped):
                                    await self._handle_input_request(chunk_stripped)
                    except:
                        pass
            
            await self.command_process.wait()
            self.command_exit_code = self.command_process.returncode
            self.command_status = "completed" if self.command_exit_code == 0 else "error"
            
            # 同步更新 Agent 状态
            self.status = "completed" if self.command_exit_code == 0 else "error"
            
            # 停止截图流
            await self.stop_screenshot_stream()
            
            # 任务结束时重置所有状态到默认值
            self.credential_manager_logged_in = False
            self.progress_ratio = 0.0
            self.current_step = 0
            # 重置显示状态到默认值
            self.last_action = "Waiting to start..."
            self.step_description = "Agent is ready"
            self.task_complexity = "simple"
            
            # 重置暂停状态
            if PAUSE_CONTROLLER_AVAILABLE:
                try:
                    controller = get_pause_controller()
                    controller.reset()
                    print("[Command] Pause state reset on completion")
                except:
                    pass
            
            await self.add_terminal_line(
                f"[Process finished with exit code: {self.command_exit_code}]",
                "system"
            )
            self.add_log(
                f"Command finished with exit code: {self.command_exit_code}",
                "success" if self.command_exit_code == 0 else "error"
            )
            await self.broadcast_command_status()
            await self.broadcast_state()
            
        except asyncio.CancelledError:
            await self.add_terminal_line("[Process terminated by user]", "system")
        except Exception as e:
            self.command_status = "error"
            self.add_log(f"Error reading output: {str(e)}", "error")
            await self.broadcast_command_status()
    
    def _detect_line_type(self, line: str) -> str:
        """
        检测输出行的类型
        
        Args:
            line: 输出行内容
            
        Returns:
            行类型: output, error, warning, info, prompt
        """
        line_lower = line.lower()
        
        if any(kw in line_lower for kw in ['error', '错误', 'failed', 'exception']):
            return "error"
        elif any(kw in line_lower for kw in ['warning', '警告', 'warn']):
            return "warning"
        elif any(kw in line_lower for kw in ['success', '成功', 'completed', '完成']):
            return "success"
        elif any(kw in line_lower for kw in ['password', '密码', 'input', 'enter', '请输入']):
            return "prompt"
        else:
            return "output"
    
    def _is_input_required(self, line: str) -> bool:
        """
        检测是否需要用户输入
        
        【重要】需要区分真正的输入提示和提示信息
        
        Args:
            line: 输出行内容
            
        Returns:
            是否需要用户输入
        """
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        skip_patterns = [
            r"输入.*命令",          # "输入 'help' 查看可用命令"
            r"输入.*help",          # "输入 help"
            r"直接输入",            # "直接输入命令后"
            r"查看可用",            # "查看可用命令"
            r"即可执行",            # "即可执行"
            r"用户交互已启用",       # 提示信息
            r"提示:",               # 提示信息
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                return False
        
        input_patterns = [
            r'主密码\s*[:：]',         # 主密码: 或 主密码：
            r'密码\s*[:：]\s*$',       # 密码: (行尾)
            r'password\s*[:：]\s*$',   # Password:
            r'username\s*[:：]\s*$',   # Username:
            r'用户名\s*[:：]\s*$',     # 用户名：
            r'请输入\s*[:：]?\s*$',    # 请输入: (行尾)
            r'\[y/n\]',               # [y/n]
            r'\(y/n\)',               # (y/n)
            r'continue\?\s*$',        # continue?
            r'登录后.*跳过',           # 登录后...跳过
            r'按\s*enter\s*跳过',      # 按 Enter 跳过
            # 人工干预场景 - 检测"按 Enter 键继续"的提示
            r'按\s*enter\s*键\s*继续',  # 按 Enter 键继续
            r'完成后.*按.*enter',       # 完成后请按 Enter 键继续
            r'处理完成后.*按.*enter',   # 处理完成后请按 Enter 键继续
            r'按\s*enter\s*键\s*跳过',  # 按 Enter 键跳过
        ]
        
        for pattern in input_patterns:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                return True
        
        # 特殊检测：人工干预提示
        # 当检测到"需要人工干预"相关提示时，检查后续是否有"按 Enter"提示
        if '需要人工干预' in line_stripped or '人工干预' in line_stripped:
            return True
        
        # 检测进度停滞提示
        if '进度停滞' in line_stripped and '按' in line_stripped:
            return True
        
        return False
    
    async def _handle_input_request(self, prompt_line: str):
        """
        处理输入请求
        
        【重要】此方法会阻塞输出读取循环，直到用户提交输入
        这是必要的，因为子进程在等待 stdin 输入
        
        Args:
            prompt_line: 包含输入提示的行
        """
        self._current_input_is_password = any(kw in prompt_line.lower() for kw in ['password', '密码', '主密码'])
        
        prompt_message = "Waiting for your input"
        if self._current_input_is_password:
            prompt_message = "Password input (hidden)"
        elif 'username' in prompt_line.lower() or '用户名' in prompt_line:
            prompt_message = "Please enter your username"
        elif '[y/n]' in prompt_line.lower() or '(y/n)' in prompt_line.lower():
            prompt_message = "Please enter Y or N"
        elif '需要人工干预' in prompt_line or '人工干预' in prompt_line:
            # 人工干预场景 - 用户需要在浏览器中完成操作后按 Enter
            prompt_message = "⚠️ Manual intervention required - Press Enter when done"
            self._current_input_is_password = False
        elif '进度停滞' in prompt_line:
            # 进度停滞场景 - 用户确认后继续
            prompt_message = "⚠️ Progress stagnation detected - Press Enter to continue or type 'exit' to abort"
            self._current_input_is_password = False
        elif '按' in prompt_line and 'enter' in prompt_line.lower():
            prompt_message = "Press Enter to continue or type input"
        
        await self.set_waiting_for_input(prompt_message)
        
        user_input = await self.input_queue.get()
        
        if self.command_process and self.command_process.stdin:
            try:
                self.command_process.stdin.write((user_input + '\n').encode('utf-8'))
                await self.command_process.stdin.drain()
            except Exception as e:
                self.add_log(f"Failed to write to stdin: {str(e)}", "error")
    
    def _parse_output_for_status(self, line: str) -> bool:
        """
        解析输出以更新 Agent 状态
        
        从 main.py 的输出中提取状态信息
        同时更新 last_action 和 step_description 以实现实时显示
        
        【实际输出格式】
        - 步骤分隔符: "步骤 6/30" 或 "─────────────── 步骤 6/30 ───────────────"
        - 决策信息: "🧠 决策: click = '按钮'" 或 "🧠 决策: wait = '2000'"
        - 感知信息: "👁️ 感知: 20 个元素"
        - 执行成功: "✅ click (成功)" 或 "✅ wait (2.0s)"
        - 执行警告: "⚠️ 检测到弹窗/模态框"
        - 进度信息: "📊 进度: 88% | 停滞: 1/5"
        
        【返回值】
        True: 状态有重要变化，需要广播
        False: 无重要变化，不需要广播
        """
        # 去除 ANSI 颜色代码
        clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
        
        # 调试：打印每一行
        print(f"[Parse] Line: {clean_line[:80]}")
        
        # 解析步骤分隔符 - 格式: "步骤 X/Y" 或 "──── 步骤 X/Y ────"
        step_sep_match = re.search(r'步骤\s*(\d+)\s*/\s*(\d+)', clean_line)
        if step_sep_match:
            new_step = int(step_sep_match.group(1))
            max_steps = int(step_sep_match.group(2))
            if new_step != self.current_step:
                self.current_step = new_step
            if max_steps != self.max_steps:
                self.max_steps = max_steps
            # 步骤分隔符只更新步数，不更新 step_description
            # 让后续的决策/感知信息来更新 step_description
            print(f"[WebSocket] Step {new_step}/{max_steps}")
            return True  # 步骤变化需要广播
        
        # 解析决策信息 - 格式: "🧠 决策: action → [target_id] = 'value'" 或 "🧠 决策: action = 'value'"
        # 决策只是计划，不更新 last_action（只有执行成功才更新）
        # 支持: "决策: click → [123] = 'value'" 或 "决策: type = 'hello'" 或 "决策: wait"
        decision_match = re.search(r'🧠\s*决策\s*[:：]\s*(\w+)(?:\s*→\s*\[\d+\])?\s*(?:=\s*[\'"]?([^\'"]*)[\'"]?)?', clean_line)
        if decision_match:
            action_type = decision_match.group(1)
            action_value = decision_match.group(2) or ''
            # 脱敏敏感信息
            action_lower = action_type.lower() if action_type else ""
            if action_lower in ("type", "input", "fill") and action_value:
                masked_value = mask_string(action_value, show_prefix=1, show_suffix=1)
            else:
                masked_value = action_value
            # 只更新 step_description，不更新 last_action
            if masked_value:
                self.step_description = f"Planning: {action_type} = {masked_value[:30]}"
            else:
                self.step_description = f"Planning: {action_type}"
            print(f"[WebSocket] Decision: {action_type} = {masked_value}")
            return True  # 决策变化需要广播
        
        # 解析感知信息 - 格式: "👁️ 感知: X 个元素"
        perception_match = re.search(r'👁️\s*感知\s*[:：]\s*(\d+)', clean_line)
        if perception_match:
            elements_count = perception_match.group(1)
            self.step_description = f"Perceiving page ({elements_count} elements found)"
            return True  # 感知变化需要广播
        
        # 解析执行成功 - 格式: "✅ action" 或 "✅ action (details)"
        # 括号是可选的，支持 "✅ type" 和 "✅ wait (2.0s)" 两种格式
        success_match = re.search(r'✅\s*(\w+)(?:\s*\(([^)]*)\))?', clean_line)
        if success_match:
            action_type = success_match.group(1)
            details = success_match.group(2) or ''
            if details:
                self.last_action = f"✓ {action_type} ({details[:30]})"
            else:
                self.last_action = f"✓ {action_type}"
            return True  # 执行成功需要广播
        
        # 解析执行警告 - 格式: "⚠️ xxx"
        warning_match = re.search(r'⚠️\s*(.+)', clean_line)
        if warning_match:
            warning_text = warning_match.group(1).strip()
            self.step_description = f"Warning: {warning_text[:80]}"
            return True  # 警告需要广播
        
        # 解析检测信息 - 格式: "🚨 xxx"
        alert_match = re.search(r'🚨\s*(.+)', clean_line)
        if alert_match:
            alert_text = alert_match.group(1).strip()
            self.step_description = f"Alert: {alert_text[:80]}"
            return True  # 警报需要广播
        
        # 解析截图信息 - 格式: "📸 截图 xxx"
        screenshot_match = re.search(r'📸\s*截图\s*(?:\([^)]*\))?\s*[:：]?\s*(.+)', clean_line)
        if screenshot_match:
            screenshot_info = screenshot_match.group(1).strip()
            self.step_description = f"Capturing screenshot: {screenshot_info[:50]}"
            return False  # 截图信息不需要广播（太频繁）
        
        # 解析任务完成提示 - 格式: "💡 任务可能已完成"
        # 注意：只解析特定的任务相关提示，忽略终端初始化提示
        complete_hint_match = re.search(r'💡\s*(.+)', clean_line)
        if complete_hint_match:
            hint_text = complete_hint_match.group(1).strip()
            print(f"[Parse] 💡 hint detected: {hint_text[:50]}")
            # 只处理任务相关的提示，忽略终端操作提示
            if '任务' in hint_text or 'task' in hint_text.lower():
                self.step_description = f"Hint: {hint_text[:80]}"
                print(f"[Parse] Updated step_description to: {self.step_description}")
                return True  # 任务相关提示需要广播
            # 其他提示（如终端操作提示）不更新状态
            print(f"[Parse] Ignoring non-task hint")
            return False
        
        # 根据关键词更新状态（保留原有逻辑作为后备）
        # 注意：这些后备逻辑只在前面没有匹配到的情况下才执行
        # 重要：不要覆盖已经解析的 last_action（如 ✅ goto）
        if '正在启动浏览器' in clean_line or 'launching browser' in clean_line.lower():
            self.status = "running"
            self.last_action = "Launching browser"
            self.step_description = "Initializing browser environment"
            return True
        elif '任务完成' in clean_line or 'task completed' in clean_line.lower():
            self.status = "completed"
            self.last_action = "Task completed"
            self.step_description = "Task completed successfully"
            return True
        elif '❌' in clean_line and ('错误' in clean_line or 'error' in clean_line.lower()):
            self.status = "error"
            self.last_action = "Error occurred"
            self.step_description = f"Error: {clean_line[:100]}"
            return True
        
        return False  # 无重要变化
    
    async def _broadcast_complexity_update(self, complexity: str):
        """
        广播任务复杂度更新
        
        【参数】
        complexity: 新的复杂度值 (simple/medium/complex/very_complex)
        """
        print(f"[WebSocket] Broadcasting complexity update: {complexity}")
        await self.broadcast({
            "type": "complexity_update",
            "payload": {
                "taskComplexity": complexity,
                "timestamp": datetime.now().isoformat()
            }
        })
        # 同时更新状态
        await self.broadcast_state()
    
    async def stop_command(self) -> bool:
        """
        停止正在执行的命令
        """
        if self.command_process and self.command_status == "running":
            try:
                # 首先停止截图流
                await self.stop_screenshot_stream()
                
                self.command_process.terminate()
                try:
                    await asyncio.wait_for(self.command_process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.command_process.kill()
                
                self.command_status = "stopped"
                self.status = "stopped"
                # 重置所有状态到默认值
                self.credential_manager_logged_in = False
                self.progress_ratio = 0.0
                self.current_step = 0
                # 重置显示状态到默认值
                self.last_action = "Waiting to start..."
                self.step_description = "Agent is ready"
                self.task_complexity = "simple"
                
                # 重置暂停状态
                if PAUSE_CONTROLLER_AVAILABLE:
                    try:
                        controller = get_pause_controller()
                        controller.reset()
                        print("[Command] Pause state reset on stop")
                    except:
                        pass
                
                self.add_log("Command stopped by user", "warning")
                await self.broadcast_command_status()
                await self.broadcast_state()
                return True
            except Exception as e:
                self.add_log(f"Failed to stop command: {str(e)}", "error")
                return False
        return False
    
    async def broadcast_command_status(self):
        """
        广播命令执行状态
        """
        await self.broadcast({
            "type": "command_status",
            "payload": {
                "status": self.command_status,
                "exit_code": self.command_exit_code,
                "output_count": len(self.command_output),
                "start_time": self.command_start_time,
                "duration": datetime.now().timestamp() - self.command_start_time if self.command_start_time else 0
            }
        })


# 创建全局状态实例
agent_state = AgentStateManager()


# ================================================================================
# FastAPI 应用
# ================================================================================

app = FastAPI(
    title="Web UI Agent API",
    description="Web UI Agent Control Center API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================================================================
# HTTP API 路由
# ================================================================================

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "agent_status": agent_state.status,
        "current_objective": agent_state.objective,
        "browser_available": PLAYWRIGHT_AVAILABLE
    }


@app.get("/api/test")
async def test_endpoint():
    """测试端点 - 显示当前状态"""
    return {
        "message": "Web UI Agent Server is running",
        "status": agent_state.status,
        "objective": agent_state.objective,
        "model": agent_state.selected_model,
        "current_step": agent_state.current_step,
        "logs_count": len(agent_state.logs)
    }


@app.get("/api/models")
async def get_models():
    """获取可用模型列表"""
    models = []
    for model_id, config in AVAILABLE_MODELS.items():
        models.append({
            "id": model_id,
            "name": config["name"],
            "description": config["description"],
            "priority": config["priority"],
            "tags": config["tags"],
            "maxTokens": config["max_tokens"],
            "supportsVision": config["supports_vision"],
            "supportsAutoSwitch": config["supports_auto_switch"]
        })
    return models


@app.post("/api/agent/start")
async def start_agent(request: StartAgentRequest):
    """
    启动 Agent
    
    【功能说明】
    直接同步启动浏览器（避免后台任务问题）
    前端有超时处理，不会无限等待
    """
    try:
        print(f"[API] Received start request with objective: {request.objective}")
        print(f"[API] Model: {request.model}")
        
        if agent_state.status == "running":
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Agent is already running"}
            )
        
        # 保存 objective
        agent_state.objective = request.objective
        agent_state.selected_model = request.model
        agent_state.status = "running"
        agent_state.current_step = 0
        agent_state.last_action = "Starting agent..."
        agent_state.step_description = f"Objective: {request.objective}"
        
        agent_state.add_log(f"Agent started with model: {request.model}", "success", request.objective)
        agent_state.add_log("Initializing browser environment...", "info")
        
        # 广播初始状态更新
        await agent_state.broadcast_state()
        await agent_state.broadcast({
            "type": "status_change",
            "payload": {"status": "running"}
        })
        
        # 直接启动浏览器（同步等待）
        print("[API] Starting browser directly...")
        agent_state.add_log("Launching browser...", "info")
        browser_launched = await agent_state.launch_browser()
        
        if browser_launched:
            agent_state.add_log("Browser launched successfully", "success")
            print("[API] Browser launched")
            
            # 启动高频截图流 (30fps)
            await agent_state.start_screenshot_stream()
            agent_state.add_log("Screenshot stream started (30fps)", "info")
            
            # 导航到初始页面
            await agent_state.navigate_to("https://www.google.com")
            agent_state.add_log("Navigated to initial page", "info")
        else:
            agent_state.add_log("Browser launch failed, continuing without browser", "warning")
        
        # 启动 Agent 任务执行
        import asyncio
        asyncio.create_task(auto_execute_agent())
        
        return {"success": True, "message": f"Agent started with objective: {request.objective}"}
    
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[API ERROR] {error_detail}")
        agent_state.status = "error"
        agent_state.add_log(f"Failed to start agent: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))


async def _async_start_agent():
    """
    异步启动 Agent 的后台任务
    
    【功能说明】
    在后台执行浏览器启动、截图流启动和 Agent 任务
    不阻塞前端 API 调用
    """
    try:
        print("[DEBUG] _async_start_agent started")
        agent_state.add_log("[DEBUG] Starting browser launch process...", "info")
        
        # 启动浏览器
        agent_state.add_log("Launching browser...", "info")
        print("[DEBUG] About to call launch_browser()")
        browser_launched = await agent_state.launch_browser()
        print(f"[DEBUG] launch_browser() returned: {browser_launched}")
        
        if browser_launched:
            agent_state.add_log("Browser launched successfully", "success")
            print("[DEBUG] Browser launched, starting screenshot stream...")
            
            # 启动高频截图流 (30fps)
            try:
                await agent_state.start_screenshot_stream()
                agent_state.add_log("Screenshot stream started (30fps)", "info")
                print("[DEBUG] Screenshot stream started")
            except Exception as ss_error:
                print(f"[DEBUG] Screenshot stream error: {ss_error}")
                agent_state.add_log(f"Screenshot stream error: {ss_error}", "warning")
            
            # 导航到初始页面
            try:
                print("[DEBUG] Navigating to google.com...")
                await agent_state.navigate_to("https://www.google.com")
                agent_state.add_log("Navigated to initial page", "info")
                print("[DEBUG] Navigation complete")
            except Exception as nav_error:
                print(f"[DEBUG] Navigation error: {nav_error}")
                agent_state.add_log(f"Navigation error: {nav_error}", "warning")
        else:
            agent_state.add_log("Browser launch returned False, continuing without browser", "warning")
            print("[DEBUG] Browser launch returned False")
        
        # 启动 Agent 任务执行
        print("[DEBUG] Starting auto_execute_agent...")
        asyncio.create_task(auto_execute_agent())
        print("[DEBUG] _async_start_agent completed")
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[ERROR] Failed to start agent: {e}")
        print(f"[ERROR] Traceback: {error_detail}")
        agent_state.add_log(f"Error during agent startup: {str(e)}", "error")


@app.post("/api/agent/pause")
async def pause_agent():
    """
    暂停 Agent
    
    【工作原理】
    1. 通过 PauseController 写入暂停状态文件
    2. Agent 子进程在每个步骤开始时检查该文件
    3. 如果检测到暂停状态，Agent 会阻塞等待
    """
    if agent_state.status != "running":
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Agent is not running"}
        )
    
    # 使用 PauseController 写入暂停状态（进程间通信）
    if PAUSE_CONTROLLER_AVAILABLE:
        controller = get_pause_controller()
        controller.pause()
        print("[API] Pause signal sent via PauseController")
    
    agent_state.status = "paused"
    agent_state.last_action = "Agent paused"
    agent_state.add_log("Agent paused by user", "warning")
    
    await agent_state.broadcast_state()
    await agent_state.broadcast({
        "type": "status_change",
        "payload": {"status": "paused"}
    })
    
    return {"success": True, "message": "Agent paused"}


@app.post("/api/agent/resume")
async def resume_agent():
    """
    恢复 Agent
    
    【工作原理】
    1. 通过 PauseController 清除暂停状态
    2. Agent 子进程检测到状态变化后继续执行
    """
    if agent_state.status != "paused":
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Agent is not paused"}
        )
    
    # 使用 PauseController 清除暂停状态（进程间通信）
    if PAUSE_CONTROLLER_AVAILABLE:
        controller = get_pause_controller()
        controller.resume()
        print("[API] Resume signal sent via PauseController")
    
    agent_state.status = "running"
    agent_state.last_action = "Agent resumed"
    agent_state.add_log("Agent resumed", "info")
    
    await agent_state.broadcast_state()
    await agent_state.broadcast({
        "type": "status_change",
        "payload": {"status": "running"}
    })
    
    return {"success": True, "message": "Agent resumed"}


@app.post("/api/agent/stop")
async def stop_agent():
    """停止 Agent"""
    if agent_state.status in ["idle", "stopped", "completed"]:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Agent is not running"}
        )
    
    # 重置暂停状态（防止下次运行时意外暂停）
    if PAUSE_CONTROLLER_AVAILABLE:
        controller = get_pause_controller()
        controller.reset()
        print("[API] Pause state reset on stop")
    
    # 停止截图流
    await agent_state.stop_screenshot_stream()
    
    # 关闭浏览器
    await agent_state.close_browser()
    
    agent_state.status = "stopped"
    # 重置显示状态到默认值
    agent_state.last_action = "Waiting to start..."
    agent_state.step_description = "Agent is ready"
    agent_state.current_step = 0
    agent_state.progress_ratio = 0.0
    agent_state.task_complexity = "simple"
    agent_state.add_log("Agent stopped by user", "warning")
    
    await agent_state.broadcast_state()
    await agent_state.broadcast({
        "type": "status_change",
        "payload": {"status": "stopped"}
    })
    
    return {"success": True, "message": "Agent stopped"}


@app.post("/api/agent/reset")
async def reset_agent():
    """重置 Agent"""
    # 重置暂停状态（防止下次运行时意外暂停）
    if PAUSE_CONTROLLER_AVAILABLE:
        controller = get_pause_controller()
        controller.reset()
        print("[API] Pause state reset on reset")
    
    # 停止截图流
    await agent_state.stop_screenshot_stream()
    
    # 关闭浏览器
    await agent_state.close_browser()
    
    # 重置所有状态到默认值
    agent_state.status = "idle"
    agent_state.current_step = 0
    agent_state.last_action = "Waiting to start..."
    agent_state.step_description = "Agent is ready"
    agent_state.objective = ""
    agent_state.current_url = ""
    agent_state.logs = []
    agent_state.latest_screenshot = None
    agent_state.progress_ratio = 0.0
    agent_state.task_complexity = "simple"
    agent_state.credential_manager_logged_in = False
    
    agent_state.add_log("Agent reset", "info")
    
    await agent_state.broadcast_state()
    await agent_state.broadcast({
        "type": "status_change",
        "payload": {"status": "idle"}
    })
    
    return {"success": True, "message": "Agent reset"}


# 浏览器交互 API
@app.post("/api/browser/click")
async def browser_click(request: MouseClickRequest):
    """在浏览器中点击"""
    success = await agent_state.click(request.x, request.y)
    return {"success": success}


@app.post("/api/browser/type")
async def browser_type(request: TypeTextRequest):
    """在浏览器中输入文本"""
    success = await agent_state.type_text(request.text)
    return {"success": success}


@app.post("/api/browser/navigate")
async def browser_navigate(url: str):
    """导航到指定 URL"""
    success = await agent_state.navigate_to(url)
    return {"success": success}


@app.get("/api/agent/state")
async def get_agent_state():
    """获取 Agent 状态"""
    return agent_state.get_state_dict()


@app.get("/api/agent/screenshot")
async def get_screenshot():
    """获取当前截图"""
    return {
        "screenshot": agent_state.latest_screenshot,
        "url": agent_state.current_url or "about:blank"
    }


@app.get("/api/agent/logs")
async def get_logs(limit: int = 50):
    """获取日志"""
    return agent_state.logs[:limit]


@app.post("/api/agent/input")
async def send_user_input(request: UserInputRequest):
    """
    发送用户输入到交互式终端
    
    【功能说明】
    当 Agent 等待用户输入时，通过此 API 提交输入内容
    输入会被放入队列，由 _handle_input_request 处理
    """
    if not agent_state.waiting_for_input:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Agent is not waiting for input"}
        )
    
    is_password = agent_state._current_input_is_password
    success = await agent_state.submit_user_input(request.input, is_password)
    
    if success:
        agent_state.add_log(f"User input submitted", "info")
        return {"success": True, "message": "Input submitted"}
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Failed to submit input"}
        )


@app.get("/api/terminal/output")
async def get_terminal_output(limit: int = 100):
    """获取终端输出"""
    return {
        "lines": agent_state.terminal_lines[-limit:] if agent_state.terminal_lines else [],
        "total": len(agent_state.terminal_lines),
        "waitingForInput": agent_state.waiting_for_input,
        "inputPrompt": agent_state.input_prompt
    }


@app.post("/api/terminal/clear")
async def clear_terminal():
    """清空终端输出"""
    agent_state.clear_terminal()
    await agent_state.broadcast({
        "type": "terminal_cleared",
        "payload": {}
    })
    return {"success": True, "message": "Terminal cleared"}


# ================================================================================
# 命令执行 API
# ================================================================================

class ExecuteCommandRequest(BaseModel):
    """执行命令请求模型"""
    objective: str = ""
    url: str = ""
    max_steps: int = 30
    model: str = DEFAULT_MODEL


@app.post("/api/command/execute")
async def execute_command(request: ExecuteCommandRequest):
    """
    执行 python main.py 命令
    
    【安全说明】
    此 API 只允许执行预定义的 python main.py 命令，
    参数经过严格验证，不接受任意命令。
    """
    try:
        if agent_state.command_status == "running":
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "A command is already running"}
            )
        
        success = await agent_state.execute_main_py(
            objective=request.objective if request.objective else None,
            url=request.url if request.url else None,
            max_steps=request.max_steps,
            model=request.model if request.model != DEFAULT_MODEL else None
        )
        
        if success:
            return {
                "success": True, 
                "message": "Command started successfully",
                "command": "python main.py"
            }
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Failed to start command"}
            )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/command/stop")
async def stop_command():
    """停止正在执行的命令"""
    if agent_state.command_status != "running":
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "No command is running"}
        )
    
    success = await agent_state.stop_command()
    return {"success": success, "message": "Command stopped" if success else "Failed to stop command"}


@app.get("/api/command/status")
async def get_command_status():
    """获取命令执行状态"""
    return {
        "status": agent_state.command_status,
        "exit_code": agent_state.command_exit_code,
        "output_count": len(agent_state.command_output),
        "start_time": agent_state.command_start_time,
        "duration": datetime.now().timestamp() - agent_state.command_start_time if agent_state.command_start_time else 0,
        "output": agent_state.command_output[-50:] if agent_state.command_output else []
    }


@app.get("/api/command/output")
async def get_command_output(limit: int = 100):
    """获取命令输出"""
    return {
        "output": agent_state.command_output[-limit:] if agent_state.command_output else [],
        "total_lines": len(agent_state.command_output)
    }


# ================================================================================
# 文件管理 API - 用于日志和过程文件查看
# ================================================================================

# 基础路径配置
LOGS_DIR = Path("d:/MyCode/CODE_C/C_Multiple/web_ui_agent/logs")
PROCESS_DIR = Path("d:/MyCode/CODE_C/C_Multiple/web_ui_agent/process")
PERFORMANCE_DIR = Path("d:/MyCode/CODE_C/C_Multiple/web_ui_agent/logs/performance")


class FileInfo(BaseModel):
    """文件信息模型"""
    name: str
    path: str
    type: str  # 'log', 'session', 'performance', 'process'
    size: int
    modified: str
    task_id: Optional[str] = None  # 任务ID（用于分组）


class TaskGroup(BaseModel):
    """任务分组模型"""
    task_id: str
    task_time: str
    files: List[FileInfo]


def parse_task_timestamp(timestamp_str: str) -> Optional[float]:
    """
    将任务时间戳字符串转换为Unix时间戳
    
    【参数】
    timestamp_str: 时间戳字符串，如 "20260302_112930"
    
    【返回值】
    float: Unix时间戳，解析失败返回 None
    """
    try:
        dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        return dt.timestamp()
    except ValueError:
        return None


def extract_task_id(filename: str) -> Optional[str]:
    """
    从文件名或目录名中提取任务ID
    
    【命名规范】
    - 日志文件: agent_{task_id}.log, session_{task_id}.json
    - 过程目录: process/{task_id}/
    - 性能文件: logs/performance/perf_{task_id}.json
    
    【参数】
    filename: 文件名或目录名
    
    【返回值】
    任务ID，如 "20260302_112930"
    """
    match = re.search(r'(\d{8}_\d{6})', filename)
    if match:
        return match.group(1)
    return None


def group_task_ids_by_time(task_ids: list, threshold_seconds: float = 120) -> dict:
    """
    将相近时间的任务ID分组
    
    【设计思路】
    由于历史文件的时间戳可能存在秒级差异，需要将相近时间的文件归为同一任务。
    使用时间阈值（默认120秒）来判断两个时间戳是否属于同一任务。
    
    【参数】
    task_ids: 任务ID列表
    threshold_seconds: 时间阈值（秒），默认120秒
    
    【返回值】
    dict: {原始task_id: 分组后的代表task_id}
    """
    if not task_ids:
        return {}
    
    # 解析时间戳并排序
    timestamp_data = []
    for tid in task_ids:
        ts = parse_task_timestamp(tid)
        if ts:
            timestamp_data.append((tid, ts))
    
    # 按时间排序
    timestamp_data.sort(key=lambda x: x[1])
    
    # 分组：相邻时间差小于阈值的归为一组
    groups = []
    current_group = [timestamp_data[0]]
    
    for i in range(1, len(timestamp_data)):
        prev_ts = timestamp_data[i-1][1]
        curr_ts = timestamp_data[i][1]
        
        if curr_ts - prev_ts <= threshold_seconds:
            current_group.append(timestamp_data[i])
        else:
            groups.append(current_group)
            current_group = [timestamp_data[i]]
    
    groups.append(current_group)
    
    # 创建映射：每个task_id映射到组内最早的task_id
    mapping = {}
    for group in groups:
        # 使用组内最早的task_id作为代表
        representative = group[0][0]
        for tid, _ in group:
            mapping[tid] = representative
    
    return mapping


@app.get("/api/files/logs")
async def get_log_files():
    """
    获取日志文件列表
    
    返回 logs 目录下的所有文件，按时间倒序排列
    """
    files = []
    
    if not LOGS_DIR.exists():
        return {"files": [], "groups": []}
    
    for file_path in LOGS_DIR.iterdir():
        if file_path.is_file():
            stat = file_path.stat()
            file_type = "log"
            
            if "session" in file_path.name:
                file_type = "session"
            elif "perf" in file_path.name:
                file_type = "performance"
            elif file_path.suffix == ".json":
                file_type = "json"
            
            files.append({
                "name": file_path.name,
                "path": str(file_path),
                "type": file_type,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    
    files.sort(key=lambda x: x["modified"], reverse=True)
    
    return {"files": files}


@app.get("/api/files/process")
async def get_process_files():
    """
    获取过程文件列表
    
    返回 process 目录下的所有文件，按任务分组
    """
    groups = {}
    
    if not PROCESS_DIR.exists():
        return {"groups": []}
    
    for task_dir in PROCESS_DIR.iterdir():
        if task_dir.is_dir():
            task_id = task_dir.name
            task_files = []
            
            for file_path in task_dir.iterdir():
                if file_path.is_file():
                    stat = file_path.stat()
                    file_type = "process"
                    
                    if "action" in file_path.name:
                        file_type = "action"
                    elif "decision" in file_path.name:
                        file_type = "decision"
                    elif "elements" in file_path.name:
                        file_type = "elements"
                    
                    task_files.append({
                        "name": file_path.name,
                        "path": str(file_path),
                        "type": file_type,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "task_id": task_id
                    })
            
            task_files.sort(key=lambda x: x["name"])
            
            task_time = task_id.replace("_", " ")
            groups[task_id] = {
                "task_id": task_id,
                "task_time": task_time,
                "files": task_files
            }
    
    sorted_groups = sorted(groups.values(), key=lambda x: x["task_id"], reverse=True)
    
    return {"groups": sorted_groups}


@app.get("/api/files/content")
async def get_file_content(file_path: str):
    """
    获取文件内容
    
    安全地读取指定文件的内容，支持文本和JSON格式
    """
    try:
        path = Path(file_path)
        
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        resolved_path = str(path.resolve()).lower()
        allowed_prefixes = [
            "d:\\mycode\\code_c\\c_multiple\\web_ui_agent\\logs",
            "d:/mycode/code_c/c_multiple/web_ui_agent/logs",
            "d:\\mycode\\code_c\\c_multiple\\web_ui_agent\\process",
            "d:/mycode/code_c/c_multiple/web_ui_agent/process",
        ]
        
        if not any(resolved_path.startswith(prefix.lower()) for prefix in allowed_prefixes):
            raise HTTPException(status_code=403, detail="Access denied")
        
        stat = path.stat()
        file_size = stat.st_size
        
        if file_size > 10 * 1024 * 1024:
            return {
                "content": None,
                "error": "File too large (max 10MB)",
                "size": file_size,
                "name": path.name,
                "type": path.suffix
            }
        
        if path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                content = json.load(f)
            return {
                "content": content,
                "format": "json",
                "size": file_size,
                "name": path.name,
                "type": path.suffix
            }
        else:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return {
                "content": content,
                "format": "text",
                "size": file_size,
                "name": path.name,
                "type": path.suffix
            }
    
    except json.JSONDecodeError:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {
            "content": content,
            "format": "text",
            "size": file_size,
            "name": path.name,
            "type": path.suffix
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/files/all")
async def get_all_files():
    """
    获取所有文件（日志、过程、性能文件）
    
    按任务分组返回，使用智能时间匹配
    将相近时间（120秒内）的文件归为同一任务
    
    结构：
    <某个任务>
    ├── logs (日志文件: agent_*.log, session_*.json)
    ├── process (过程文件)
    └── performance (性能文件: perf_*.json)
    """
    # 第一步：收集所有任务ID
    all_task_ids = set()
    
    # 从日志文件收集
    if LOGS_DIR.exists():
        for file_path in LOGS_DIR.iterdir():
            if file_path.is_file():
                task_id = extract_task_id(file_path.name)
                if task_id:
                    all_task_ids.add(task_id)
    
    # 从性能文件收集
    if PERFORMANCE_DIR.exists():
        for file_path in PERFORMANCE_DIR.iterdir():
            if file_path.is_file() and file_path.suffix == ".json":
                task_id = extract_task_id(file_path.name)
                if task_id:
                    all_task_ids.add(task_id)
    
    # 从过程目录收集
    if PROCESS_DIR.exists():
        for task_dir in PROCESS_DIR.iterdir():
            if task_dir.is_dir():
                task_id = task_dir.name
                if re.match(r'\d{8}_\d{6}', task_id):
                    all_task_ids.add(task_id)
    
    # 第二步：智能分组 - 将相近时间的任务ID合并
    task_id_mapping = group_task_ids_by_time(list(all_task_ids), threshold_seconds=120)
    
    # 第三步：按分组后的任务ID组织文件
    task_groups = {}
    
    # 处理日志文件
    if LOGS_DIR.exists():
        for file_path in LOGS_DIR.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                file_type = "log"
                
                if "session" in file_path.name:
                    file_type = "session"
                elif "test_results" in file_path.name:
                    file_type = "test"
                
                original_task_id = extract_task_id(file_path.name)
                if original_task_id:
                    # 使用分组后的代表task_id
                    grouped_task_id = task_id_mapping.get(original_task_id, original_task_id)
                    
                    if grouped_task_id not in task_groups:
                        task_groups[grouped_task_id] = {
                            "task_id": grouped_task_id,
                            "task_time": grouped_task_id.replace("_", " "),
                            "logs": [],
                            "process": [],
                            "performance": []
                        }
                    
                    task_groups[grouped_task_id]["logs"].append({
                        "name": file_path.name,
                        "path": str(file_path),
                        "type": file_type,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "category": "logs"
                    })
    
    # 处理性能文件
    if PERFORMANCE_DIR.exists():
        for file_path in PERFORMANCE_DIR.iterdir():
            if file_path.is_file() and file_path.suffix == ".json":
                stat = file_path.stat()
                original_task_id = extract_task_id(file_path.name)
                
                if original_task_id:
                    grouped_task_id = task_id_mapping.get(original_task_id, original_task_id)
                    
                    if grouped_task_id not in task_groups:
                        task_groups[grouped_task_id] = {
                            "task_id": grouped_task_id,
                            "task_time": grouped_task_id.replace("_", " "),
                            "logs": [],
                            "process": [],
                            "performance": []
                        }
                    
                    task_groups[grouped_task_id]["performance"].append({
                        "name": file_path.name,
                        "path": str(file_path),
                        "type": "performance",
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "category": "performance"
                    })
    
    # 处理过程文件
    if PROCESS_DIR.exists():
        for task_dir in PROCESS_DIR.iterdir():
            if task_dir.is_dir():
                original_task_id = task_dir.name
                if re.match(r'\d{8}_\d{6}', original_task_id):
                    grouped_task_id = task_id_mapping.get(original_task_id, original_task_id)
                    
                    if grouped_task_id not in task_groups:
                        task_groups[grouped_task_id] = {
                            "task_id": grouped_task_id,
                            "task_time": grouped_task_id.replace("_", " "),
                            "logs": [],
                            "process": [],
                            "performance": []
                        }
                    
                    for file_path in task_dir.iterdir():
                        if file_path.is_file():
                            stat = file_path.stat()
                            file_type = "process"
                            
                            if "action" in file_path.name:
                                file_type = "action"
                            elif "decision" in file_path.name:
                                file_type = "decision"
                            elif "elements" in file_path.name:
                                file_type = "elements"
                            
                            task_groups[grouped_task_id]["process"].append({
                                "name": file_path.name,
                                "path": str(file_path),
                                "type": file_type,
                                "size": stat.st_size,
                                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                                "category": "process"
                            })
    
    # 排序文件
    for task_id in task_groups:
        task_groups[task_id]["logs"].sort(key=lambda x: x["name"], reverse=True)
        task_groups[task_id]["process"].sort(key=lambda x: x["name"])
        task_groups[task_id]["performance"].sort(key=lambda x: x["name"], reverse=True)
    
    # 按任务ID倒序排列
    sorted_groups = sorted(task_groups.values(), key=lambda x: x["task_id"], reverse=True)
    
    return {"groups": sorted_groups}


# ================================================================================
# WebSocket 路由
# ================================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 连接端点"""
    await websocket.accept()
    agent_state.websocket_clients.append(websocket)
    
    try:
        # 发送初始状态
        await websocket.send_json({
            "type": "state_update",
            "payload": agent_state.get_state_dict()
        })
        
        # 发送连接成功消息
        await websocket.send_json({
            "type": "connection_status",
            "payload": {"connected": True}
        })
        
        # 发送最新截图（如果有）
        if agent_state.latest_screenshot:
            await websocket.send_json({
                "type": "screenshot",
                "payload": {
                    "screenshot": agent_state.latest_screenshot,
                    "url": agent_state.current_url
                }
            })
        
        # 保持连接并处理消息
        while True:
            try:
                # 使用 receive_text 或 receive_json，处理连接关闭的情况
                raw_message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # 30秒超时
                )
                
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                
                msg_type = message.get("type")
                payload = message.get("payload", {})
                
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                
                elif msg_type == "get_state":
                    await websocket.send_json({
                        "type": "state_update",
                        "payload": agent_state.get_state_dict()
                    })
                
                elif msg_type == "get_screenshot":
                    await websocket.send_json({
                        "type": "screenshot",
                        "payload": {
                            "screenshot": agent_state.latest_screenshot,
                            "url": agent_state.current_url
                        }
                    })
                
                elif msg_type == "mouse_click":
                    x = payload.get("x", 0)
                    y = payload.get("y", 0)
                    await agent_state.click(x, y)
                
                elif msg_type == "type_text":
                    text = payload.get("text", "")
                    await agent_state.type_text(text)
                    
            except asyncio.TimeoutError:
                # 发送心跳保持连接
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except:
                    break
                continue
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"WebSocket message error: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if websocket in agent_state.websocket_clients:
            agent_state.websocket_clients.remove(websocket)


# ================================================================================
# Agent 自动执行逻辑（模拟执行）
# ================================================================================

async def auto_execute_agent():
    """
    自动执行 Agent 任务（模拟执行）
    
    【注意】此函数仅用于 /api/agent/start 端点的模拟执行
    当使用 /api/command/execute 端点时，不会启动此函数
    """
    while True:
        # 只有在 command_status 不是 running 时才执行模拟
        # 这样可以避免与 execute_main_py 的冲突
        if agent_state.status == "running" and agent_state.command_status != "running":
            # 检查是否已完成
            if agent_state.current_step >= agent_state.max_steps:
                await asyncio.sleep(0.5)
                continue
            
            await asyncio.sleep(2)
            
            if agent_state.status != "running":
                continue
            
            # 再次检查 command_status，确保没有真正的命令在执行
            if agent_state.command_status == "running":
                continue
            
            agent_state.current_step += 1
            
            # 模拟执行动作
            actions = [
                ("Navigating to target URL...", lambda: agent_state.navigate_to("https://www.baidu.com")),
                ("Analyzing page structure...", lambda: asyncio.sleep(0.5)),
                ("Identifying interactive elements...", lambda: asyncio.sleep(0.5)),
                ("Clicking on search box...", lambda: agent_state.click(640, 300)),
                ("Typing search query...", lambda: agent_state.type_text(agent_state.objective)),
                ("Pressing Enter...", lambda: agent_state.press_key("Enter")),
                ("Waiting for results...", lambda: asyncio.sleep(2)),
                ("Scrolling down page...", lambda: agent_state.page.evaluate("window.scrollBy(0, 300)") if agent_state.page else asyncio.sleep(0.5)),
                ("Clicking on result...", lambda: asyncio.sleep(0.5)),
                ("Extracting data...", lambda: asyncio.sleep(0.5)),
            ]
            
            if agent_state.current_step <= len(actions):
                action_name, action_func = actions[agent_state.current_step - 1]
                
                try:
                    await action_func()
                    agent_state.last_action = action_name
                    agent_state.step_description = f"[Step {agent_state.current_step}] {action_name}"
                    agent_state.add_log(action_name, "info")
                except Exception as e:
                    agent_state.add_log(f"Action failed: {str(e)}", "error")
                
                await agent_state.broadcast_state()
            
            # 检查是否完成
            if agent_state.current_step >= agent_state.max_steps:
                agent_state.status = "completed"
                agent_state.last_action = "Task completed successfully"
                agent_state.add_log("Task completed successfully", "success")
                await agent_state.stop_screenshot_stream()
                await agent_state.broadcast_state()
                await agent_state.broadcast({
                    "type": "status_change",
                    "payload": {"status": "completed"}
                })
        
        await asyncio.sleep(0.5)


# ================================================================================
# 主入口
# ================================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("Web UI Agent Server")
    print("=" * 50)
    print("API文档: http://localhost:8000/docs")
    print("前端地址: http://localhost:5173")
    print("=" * 50)
    
    uvicorn.run(
        "web_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # 禁用热重载，避免 Windows 上的多进程问题
        log_level="info"
    )
