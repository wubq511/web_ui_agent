"""
================================================================================
Web UI Agent Web服务器
提供HTTP API和WebSocket服务供前端调用
实现真实的浏览器控制和高频截图流
================================================================================
"""

import asyncio
import sys

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
from config import AVAILABLE_MODELS, DEFAULT_MODEL


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
        self.last_action: str = "Waiting to start..."
        self.step_description: str = "Agent is ready"
        self.current_url: str = ""
        self.logs: List[Dict] = []
        self.websocket_clients: List[WebSocket] = []
        self.task_complexity: str = "simple"
        self.popup_detected: bool = False
        self.login_form_detected: bool = False
        
        # 浏览器相关
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        # 截图流控制 - 30fps
        self.screenshot_task: Optional[asyncio.Task] = None
        self.screenshot_interval: float = 0.033  # 33ms = 30fps
        self.latest_screenshot: Optional[str] = None
        self.is_capturing: bool = False
    
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
            "progressRatio": self.current_step / self.max_steps if self.max_steps > 0 else 0,
            "stagnationCount": 0,
            "taskComplexity": self.task_complexity,
            "popupDetected": self.popup_detected,
            "loginFormDetected": self.login_form_detected
        }
    
    async def launch_browser(self) -> bool:
        """
        启动浏览器
        
        Returns:
            启动成功返回 True，失败返回 False
        """
        if not PLAYWRIGHT_AVAILABLE:
            self.add_log("Playwright not available, browser not launched", "warning")
            return False
        
        try:
            self.add_log("Starting playwright...", "info")
            self.playwright = await async_playwright().start()
            self.add_log("Playwright started, launching chromium...", "info")
            
            # 启动 Chromium 浏览器（无头模式）
            # 在 Windows 上可能需要设置 executable_path
            try:
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
            except Exception as launch_error:
                # 如果启动失败，尝试打印更详细的错误
                import traceback
                error_detail = traceback.format_exc()
                print(f"[BROWSER LAUNCH ERROR] {error_detail}")
                self.add_log(f"Browser launch error: {str(launch_error)}", "error")
                raise
            
            self.add_log("Chromium launched, creating context...", "info")
            
            # 创建浏览器上下文
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720}
            )
            
            self.add_log("Context created, creating page...", "info")
            
            # 创建新页面
            self.page = await self.context.new_page()
            
            self.add_log("Browser launched successfully", "success")
            return True
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[BROWSER ERROR] {error_detail}")
            self.add_log(f"Failed to launch browser: {str(e)}", "error")
            return False
    
    async def close_browser(self):
        """关闭浏览器"""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            
            if self.context:
                await self.context.close()
                self.context = None
            
            if self.browser:
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            self.add_log("Browser closed", "info")
            
        except Exception as e:
            print(f"Error closing browser: {e}")
    
    async def start_screenshot_stream(self):
        """启动高频截图流 (30fps)"""
        self.is_capturing = True
        if self.screenshot_task:
            self.screenshot_task.cancel()
        
        self.screenshot_task = asyncio.create_task(self._screenshot_loop())
    
    async def stop_screenshot_stream(self):
        """停止截图流"""
        self.is_capturing = False
        if self.screenshot_task:
            self.screenshot_task.cancel()
            self.screenshot_task = None
    
    async def _screenshot_loop(self):
        """
        高频截图循环 - 30fps
        
        持续截取浏览器页面并广播给前端
        """
        while self.is_capturing:
            try:
                if self.page and self.status in ["running", "paused"]:
                    # 截取页面截图 - 使用较低质量以提高性能
                    screenshot_bytes = await self.page.screenshot(
                        type='jpeg',
                        quality=60,  # 降低质量以提高速度
                        full_page=False
                    )
                    
                    # 转换为 base64
                    screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                    
                    # 广播截图
                    await self.broadcast_screenshot(f"data:image/jpeg;base64,{screenshot_base64}")
                    
                    # 更新当前 URL
                    if self.page:
                        self.current_url = self.page.url
                
                await asyncio.sleep(self.screenshot_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Screenshot error: {e}")
                await asyncio.sleep(self.screenshot_interval)
    
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
    """暂停 Agent"""
    if agent_state.status != "running":
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Agent is not running"}
        )
    
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
    """恢复 Agent"""
    if agent_state.status != "paused":
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Agent is not paused"}
        )
    
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
    
    # 停止截图流
    await agent_state.stop_screenshot_stream()
    
    # 关闭浏览器
    await agent_state.close_browser()
    
    agent_state.status = "stopped"
    agent_state.last_action = "Agent stopped"
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
    # 停止截图流
    await agent_state.stop_screenshot_stream()
    
    # 关闭浏览器
    await agent_state.close_browser()
    
    agent_state.status = "idle"
    agent_state.current_step = 0
    agent_state.last_action = "Waiting to start..."
    agent_state.step_description = "Agent is ready"
    agent_state.objective = ""
    agent_state.current_url = ""
    agent_state.logs = []
    agent_state.latest_screenshot = None
    
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
    """发送用户输入"""
    agent_state.add_log(f"User input received: {request.input}", "info")
    return {"success": True}


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
                message = await websocket.receive_json()
                
                msg_type = message.get("type")
                payload = message.get("payload")
                
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
                    # 处理鼠标点击
                    x = payload.get("x", 0)
                    y = payload.get("y", 0)
                    await agent_state.click(x, y)
                
                elif msg_type == "type_text":
                    # 处理文本输入
                    text = payload.get("text", "")
                    await agent_state.type_text(text)
                    
            except Exception as e:
                print(f"WebSocket message error: {e}")
                break
                
    except WebSocketDisconnect:
        print("WebSocket disconnected")
    finally:
        if websocket in agent_state.websocket_clients:
            agent_state.websocket_clients.remove(websocket)


# ================================================================================
# Agent 自动执行逻辑（模拟执行）
# ================================================================================

async def auto_execute_agent():
    """自动执行 Agent 任务（模拟执行）"""
    while True:
        if agent_state.status == "running":
            # 检查是否已完成
            if agent_state.current_step >= agent_state.max_steps:
                await asyncio.sleep(0.5)
                continue
            
            await asyncio.sleep(2)
            
            if agent_state.status != "running":
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
