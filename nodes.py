"""
================================================================================
节点模块 - LangGraph 图的节点实现
================================================================================

【模块概述】
实现 LangGraph 状态图的三个核心节点：
1. Perception Node（感知模块）- Agent 的"眼睛"
2. Reasoning Node（决策模块）- Agent 的"大脑"
3. Action Node（执行模块）- Agent 的"双手"

【支持的操作类型】
- click: 左键单击
- double_click: 双击
- right_click: 右键点击
- hover: 鼠标悬停
- drag: 拖拽元素
- type: 输入文字
- type_slowly: 逐字输入（模拟人工）
- press: 按下键盘按键
- hotkey: 组合快捷键
- select: 下拉选择
- check: 勾选复选框/单选框
- uncheck: 取消勾选
- scroll: 滚动页面
- scroll_to: 滚动到指定元素
- goto: 导航到 URL
- wait: 等待
- screenshot: 截图
- done: 任务完成

【设计思路】
每个节点是一个纯函数，接收状态并返回状态更新。这种设计使得：
1. 节点易于测试（输入输出明确）
2. 节点可以独立开发和调试
3. 便于后续扩展新的节点类型
================================================================================
"""

import time
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("⚠️ psutil 未安装，资源监控功能不可用。安装方法: pip install psutil")
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from playwright.sync_api import Page
from bs4 import BeautifulSoup, Tag

from state import AgentState
from config import ACTION_TIMEOUT, PAGE_LOAD_TIMEOUT, MAX_STEPS
from utils import parse_json_from_response, get_element_xpath, get_element_selector, _is_valid_css_id, _escape_css_selector

from step_manager import StepManager
from completion_evaluator import CompletionEvaluator, CompletionStatus, ProgressLevel
from termination_manager import TerminationManager, TerminationReason
from config import TaskComplexity
from user_interaction import UserInteractionManager, UserCommand
from checkpoint_manager import CheckpointManager
from agent_logger import AgentLogger, StepLog, DecisionLog, ResourceLog
from output_handler import get_output_handler
from console_formatter import (
    print_step_separator, print_perception, print_decision,
    print_action_success, print_action_warning, print_action_error,
    print_checkpoint_saved, print_session_saved, print_task_complete,
    print_task_terminated, print_progress_hint, print_maybe_complete, print_separator
)


SYSTEM_PROMPT = """你是一个专业的网页操作助手(web-ui-agent)。你的任务是分析当前网页状态，决定下一步操作来完成用户目标。

## 你的能力

### 鼠标操作
1. **click**: 左键单击元素（最常用的点击操作）
2. **double_click**: 双击元素（用于选中文字、打开文件等）
3. **right_click**: 右键点击元素（打开上下文菜单）
4. **hover**: 鼠标悬停在元素上（触发下拉菜单、提示等）
5. **drag**: 拖拽元素到另一个位置（需要 target_id 和 value，value 为目标位置描述）

### 文本输入操作
6. **type**: 在输入框中输入文字（清空后输入，适合表单填写）
7. **type_slowly**: 逐字输入文字（模拟人工输入，适合需要触发事件的场景）
8. **press**: 按下单个按键（如 Enter、Tab、Escape、ArrowDown 等）
9. **hotkey**: 组合快捷键（如 Ctrl+C、Ctrl+V、Ctrl+A 等）

### 选择操作
10. **select**: 下拉选择框选择选项（value 为选项文本或值）
11. **check**: 勾选复选框或单选框
12. **uncheck**: 取消勾选复选框

### 页面操作
13. **scroll**: 滚动页面（value 格式："down/100" 向下滚100像素，"up/200" 向上，"bottom" 底部，"top" 顶部）
14. **scroll_to**: 滚动到指定元素（使元素可见）
15. **goto**: 导航到指定 URL
16. **wait**: 等待指定时间（value 为毫秒数，如 "2000" 等待2秒）
17. **screenshot**: 截取当前页面截图（value 为截图说明）

### 任务控制
18. **done**: 表示任务已完成

## 输出格式要求
你必须以严格的 JSON 格式输出，不要包含任何其他文字：
```json
{
    "thought": "你的思考过程，分析当前状态和下一步应该做什么",
    "action_type": "操作类型",
    "target_id": 目标元素的数字ID（用于需要元素的操作）,
    "value": "操作参数（输入内容、按键、选项等）"
}
```

## ⚠️ 重要：弹窗/模态框优先处理原则

**当检测到弹窗或模态框时，必须优先处理弹窗内容！**

弹窗检测标志：
- 元素有 `[弹窗内]` 标记
- 元素有 `frame` 属性（表示在iframe中）
- 元素有 `priority: high` 标记

弹窗处理规则：
1. **登录弹窗**：如果检测到登录弹窗（包含用户名/手机号输入框、密码/验证码输入框、登录按钮），必须优先完成登录
2. **确认弹窗**：如果有确认/取消按钮，根据任务需要选择点击
3. **提示弹窗**：如果有关闭按钮，可以点击关闭或根据提示操作

## ⚠️ 重要：登录场景处理指南

**登录场景识别**：
当元素列表中出现以下组合时，表示检测到登录界面：
- 用户名/手机号输入框：`placeholder` 包含 "手机号"、"用户名"、"账号"、"phone"、"username"
- 密码/验证码输入框：`placeholder` 包含 "密码"、"验证码"、"password"、"code"
- 登录按钮：`text` 包含 "登录"、"登入"、"login"、"sign in"

**登录操作流程**（必须按顺序执行）：
1. **首先检查登录弹窗是否已打开**：查看是否有 `[弹窗内]` 或 `frame` 属性的登录相关元素
2. **如果弹窗已打开**：
   a. 找到用户名/手机号输入框，执行 type 操作输入账号
   b. 找到密码/验证码输入框，执行 type 操作输入密码/验证码
   c. 如果有"获取验证码"按钮，先点击获取验证码，等待用户输入
   d. 点击登录按钮
3. **如果弹窗未打开**：
   a. 找到"登录"或"请登录"按钮/链接
   b. 点击打开登录弹窗
   c. 等待弹窗加载后，按上述流程操作

**登录注意事项**：
- 登录元素可能在 iframe 中，注意查看元素的 `frame` 属性
- 如果用户提供了账号密码，必须使用用户提供的账号密码
- 登录失败时，检查是否需要验证码，可能需要人工干预
- 不要重复点击"登录"按钮，如果弹窗已打开就直接填写表单

## 元素识别指南
元素列表中每个元素包含以下信息：
- 文本内容：按钮或链接上显示的文字，可能包含多个来源（如 title、aria-label）
- 属性信息：id、class、role、href 等帮助识别元素功能
- 类型标记：[可点击]、[可输入]、[弹窗内]、[高优先级] 等
- **当前值(current_value)**：输入框的实际值，如果非空表示已填写内容
- **frame属性**：如果元素在iframe中，会显示frame信息

**识别技巧**：
1. 如果元素文本为空但有 title 或 aria-label，这些属性会显示在文本中
2. 注意元素的 id 和 class，通常包含功能关键词（如 "write"、"send"、"compose"、"login"）
3. 对于邮箱系统，"写信"按钮通常位于左上角，id 或 class 可能包含 "write"、"compose" 等
4. 如果找不到明确的目标按钮，可以尝试点击可能相关的元素
5. **优先处理带有 [弹窗内] 或 [高优先级] 标记的元素**

**重要：输入框值检查**：
- 每个输入框元素都有 `current_value` 字段，显示当前实际值
- 如果 `current_value` 非空，说明该输入框已填写内容，**不要重复填写**
- 只有当 `current_value` 为空或需要修改时，才执行 type 操作
- 例如：收件人输入框的 `current_value` 已有 "test@example.com"，则无需再填写

**重要：邮件正文填写**：
- 邮件正文通常在 iframe 编辑器中，元素类型为 `iframe`
- 填写正文的正确方法：**直接对 iframe 元素执行 type 操作**，系统会自动处理
- 例如：发现 iframe 元素 [55] 是正文编辑器，执行 `{"action_type": "type", "target_id": 55, "value": "正文内容"}`
- **不要先 click 再 type**，直接对 iframe 执行 type 即可
- 如果 iframe 元素有 "editor" 或 "APP-editor" 等关键词，通常是正文编辑器

## 决策原则
1. **优先处理弹窗和登录界面**，不要忽略弹窗继续其他操作
2. 仔细分析用户目标和当前页面状态
3. 选择最合适的操作类型，不要只用 click 和 type
4. **填写表单前先检查 current_value，避免重复填写已有内容**
5. 表单填写后通常需要按 Enter 提交，使用 press 操作
6. 下拉菜单选项使用 select 操作
7. 需要触发悬停效果时使用 hover 操作
8. 如果遇到错误，尝试其他方法
9. 确认任务完成后才输出 done
10. 每次只执行一个动作"""

VALID_ACTIONS = [
    "click", "double_click", "right_click", "hover", "drag",
    "type", "type_slowly", "press", "hotkey",
    "select", "check", "uncheck",
    "scroll", "scroll_to", "goto", "wait", "screenshot",
    "done"
]


class AgentContext:
    """
    Agent上下文 - 管理所有辅助模块
    
    【设计思路】
    将所有辅助模块集中管理，便于节点访问和状态同步
    """
    
    def __init__(self):
        self.step_manager = StepManager()
        self.completion_evaluator = CompletionEvaluator()
        self.termination_manager = TerminationManager()
        self.user_interaction = UserInteractionManager()
        self.checkpoint_manager = CheckpointManager()
        self.logger = AgentLogger()
        
        self.page = None
        self._current_state: AgentState = None
        
        self._initialized = False
        self._pending_state_updates: dict = {}
        self._pending_checkpoint_save: bool = False
    
    def set_page(self, page) -> None:
        """设置页面引用"""
        self.page = page
    
    def set_current_state(self, state: AgentState) -> None:
        """设置当前状态引用"""
        self._current_state = state
    
    def initialize(self, objective: str, start_url: str = ""):
        """初始化所有模块"""
        self.termination_manager.start()
        self.user_interaction.start()
        self.logger.log_session_start(objective, start_url)
        self._initialized = True
        
        self._setup_user_callbacks()
    
    def set_pending_state_updates(self, updates: dict) -> None:
        """设置待处理的状态更新"""
        self._pending_state_updates.update(updates)
    
    def get_and_clear_pending_updates(self) -> dict:
        """获取并清除待处理的状态更新"""
        updates = self._pending_state_updates.copy()
        self._pending_state_updates.clear()
        return updates
    
    def _setup_user_callbacks(self) -> None:
        """设置用户交互回调"""
        def on_extend_steps(params: dict) -> dict:
            increment = params.get("value", 5)
            new_max = self.step_manager.adjust_max_steps(
                reason="用户请求扩展",
                target_steps=self.step_manager.current_max_steps + increment,
                current_step=0
            )
            return {"message": f"步骤限制已扩展到 {new_max}", "new_max": new_max}
        
        def on_reduce_steps(params: dict) -> dict:
            decrement = params.get("value", 5)
            new_max = self.step_manager.adjust_max_steps(
                reason="用户请求减少",
                target_steps=self.step_manager.current_max_steps - decrement,
                current_step=0
            )
            return {"message": f"步骤限制已减少到 {new_max}", "new_max": new_max}
        
        def on_show_status(params: dict) -> dict:
            return {"message": self.user_interaction.get_status_display()}
        
        def on_save_checkpoint(params: dict) -> dict:
            if self._current_state is None:
                return {"message": "无法保存：当前状态不可用"}
            
            try:
                checkpoint_id = self.save_checkpoint(self._current_state)
                return {"message": f"检查点已保存: {checkpoint_id}"}
            except Exception as e:
                return {"message": f"保存检查点失败: {e}"}
        
        def on_load_checkpoint(params: dict) -> dict:
            checkpoints = self.checkpoint_manager.list_checkpoints(limit=5)
            if not checkpoints:
                return {"message": "没有可用的检查点"}
            msg = "可用检查点:\n"
            for cp in checkpoints:
                msg += f"  - {cp.checkpoint_id}\n"
            msg += "使用 python main.py --resume <checkpoint_id> 恢复"
            return {"message": msg}
        
        def on_set_timeout(params: dict) -> dict:
            timeout_value = params.get("value", 300)
            if isinstance(timeout_value, str):
                try:
                    timeout_value = int(timeout_value)
                except ValueError:
                    timeout_value = 300
            self.termination_manager.task_timeout = timeout_value
            return {"message": f"任务超时时间已设置为 {timeout_value} 秒"}
        
        def on_abort(params: dict) -> dict:
            self.termination_manager.request_user_abort()
            return {"message": "已请求终止任务"}
        
        def on_intervene(params: dict) -> dict:
            duration = params.get("value", 60)
            if isinstance(duration, str):
                try:
                    duration = int(duration)
                except ValueError:
                    duration = 60
            success = self.termination_manager.request_intervention(duration)
            self.completion_evaluator.set_intervention_pause(duration)
            if success:
                return {"message": f"已启动人工干预，终止倒计时暂停 {duration} 秒"}
            else:
                return {"message": "人工干预功能未启用"}
        
        def on_fast_mode(params: dict) -> dict:
            current = self.termination_manager.fast_mode
            self.termination_manager.enable_fast_mode(not current)
            status = "启用" if not current else "禁用"
            return {"message": f"快速模式已{status}，无进展阈值: {self.termination_manager.adjusted_stagnation_threshold}"}
        
        self.user_interaction.register_callback(UserCommand.EXTEND_STEPS, on_extend_steps)
        self.user_interaction.register_callback(UserCommand.REDUCE_STEPS, on_reduce_steps)
        self.user_interaction.register_callback(UserCommand.SHOW_STATUS, on_show_status)
        self.user_interaction.register_callback(UserCommand.SAVE_CHECKPOINT, on_save_checkpoint)
        self.user_interaction.register_callback(UserCommand.LOAD_CHECKPOINT, on_load_checkpoint)
        self.user_interaction.register_callback(UserCommand.SET_TIMEOUT, on_set_timeout)
        self.user_interaction.register_callback(UserCommand.ABORT, on_abort)
        self.user_interaction.register_callback(UserCommand.INTERVENE, on_intervene)
        self.user_interaction.register_callback(UserCommand.FAST_MODE, on_fast_mode)
    
    def process_user_commands(self):
        """处理用户命令"""
        responses = self.user_interaction.process_commands(show_prompt=True)
        for response in responses:
            self.logger.log_user_interaction(
                "command", 
                response.message
            )
            print(f"💬 {response.message}")
    
    def update_status(self, state: AgentState):
        """更新状态显示"""
        status = {
            "objective": state.get("objective", ""),
            "step_count": state.get("step_count", 0),
            "max_steps": self.step_manager.current_max_steps,
            "progress": state.get("progress_ratio", 0),
            "elapsed_time": self.termination_manager.get_elapsed_time(),
            "status": "进行中" if not state.get("is_done") else "已完成"
        }
        self.user_interaction.update_status(status)
    
    def save_checkpoint(self, state: AgentState) -> str:
        """保存检查点"""
        storage_state = None
        if self.page:
            try:
                storage_state = self.page.context.storage_state()
                print("💾 已保存浏览器会话状态")
            except Exception as e:
                print(f"⚠️ 保存浏览器会话状态失败: {e}")
        
        return self.checkpoint_manager.save_checkpoint(
            state=state,
            step_manager=self.step_manager.to_dict(),
            completion_evaluator=self.completion_evaluator.to_dict(),
            termination_manager=self.termination_manager.to_dict(),
            user_interaction=self.user_interaction.to_dict(),
            storage_state=storage_state
        )
    
    def log_resource_usage(self, step: int):
        """记录资源使用"""
        if HAS_PSUTIL:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            cpu_percent = process.cpu_percent(interval=0.1)
        else:
            memory_mb = 0.0
            cpu_percent = 0.0
        
        resource_log = ResourceLog(
            step=step,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            elapsed_time=self.termination_manager.get_elapsed_time()
        )
        self.logger.log_resource(resource_log)
    
    def cleanup(self):
        """清理资源"""
        self.user_interaction.stop()
        self.logger.save_session_log()


def perception_node(state: AgentState, page: Page, context: AgentContext) -> dict:
    """
    Perception Node - 感知模块（Agent 的"眼睛"）
    
    【核心职责】
    这个节点负责"看"当前页面，提取所有可交互的元素。
    
    【工作流程】
    1. 等待页面稳定（包括弹窗加载）
    2. 获取当前页面的 HTML 内容
    3. 使用 BeautifulSoup 解析 HTML
    4. 提取所有可交互元素
    5. 提取 iframe 内的元素（新增）
    6. 使用 Playwright 验证元素是否真正可见
    7. 为每个元素分配唯一 ID 并提取关键信息
    8. 检测弹窗/模态框状态
    9. 组织成元素字典返回
    
    【参数】
    state: AgentState - 当前状态
    page: Page - Playwright 页面对象
    context: AgentContext - Agent上下文
    
    【返回值】
    dict: 状态更新字典
    """
    context.set_current_state(state)
    context.process_user_commands()
    context.user_interaction.wait_if_paused()
    
    pending_updates = context.get_and_clear_pending_updates()
    
    current_url = page.url
    
    output_handler = get_output_handler()
    next_step = state.get("step_count", 0) + 1
    output_handler.start_step(next_step)
    
    print_step_separator(next_step, state.get("max_steps", MAX_STEPS))
    
    def wait_for_popup_iframe(page: Page, timeout: int = 3000) -> bool:
        """
        等待登录弹窗iframe加载完成
        
        【设计思路】
        登录弹窗通常在点击登录按钮后动态加载iframe，
        需要等待iframe加载完成才能正确提取其中的元素。
        
        【参数】
        page: Playwright 页面对象
        timeout: 超时时间（毫秒）
        
        【返回值】
        bool: 是否检测到登录iframe
        """
        login_iframe_selectors = [
            "iframe[id*='login']",
            "iframe[name*='login']",
            "iframe[src*='login']",
            "iframe[src*='passport']",
            "iframe.login-iframe",
            "iframe#login2025-content"
        ]
        
        for selector in login_iframe_selectors:
            try:
                iframe = page.frame_locator(selector)
                body = iframe.locator("body")
                if body.is_visible(timeout=500):
                    print(f"   ⏳ 检测到登录iframe: {selector}")
                    page.wait_for_timeout(500)
                    return True
            except Exception:
                continue
        
        return False
    
    last_history = state.get("history", [])[-1] if state.get("history") else None
    if last_history and last_history.get("action_type") == "click":
        target_text = ""
        target_id = last_history.get("target_id")
        if target_id:
            prev_elements = state.get("elements_dict", {})
            if target_id in prev_elements:
                target_text = prev_elements[target_id].get("text", "").lower()
        
        login_keywords = ["登录", "登入", "login", "sign in", "请登录", "你好，请登录"]
        if any(kw in target_text for kw in login_keywords):
            print("   ⏳ 等待登录弹窗加载...")
            wait_for_popup_iframe(page, timeout=3000)
    
    try:
        html_content = page.content()
    except Exception as e:
        print(f"❌ 获取页面 HTML 失败: {e}")
        context.logger.log_error(str(e), state.get("step_count", 0))
        return {
            "elements_dict": {},
            "current_url": current_url,
            "error_message": f"获取页面内容失败: {str(e)}"
        }
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    interactive_tags = ['a', 'button', 'input', 'select', 'textarea']
    
    elements_dict: dict[int, dict] = {}
    element_id = 1
    seen_selectors = set()
    
    popup_detected = False
    login_form_detected = False
    login_elements = {"username": None, "password": None, "submit": None, "sms_code": None, "get_code_btn": None}
    
    def is_login_username_field(element: Tag, element_text: str, placeholder: str) -> bool:
        """
        判断元素是否是登录用户名/手机号输入框
        
        【识别策略】
        1. placeholder 包含关键词
        2. id/name 属性包含关键词
        3. class 属性包含关键词
        """
        keywords = ['手机号', '用户名', '账号', 'phone', 'username', 'account', 'mobile', 'mobile-number']
        
        if placeholder:
            for kw in keywords:
                if kw.lower() in placeholder.lower():
                    return True
        
        for attr in ['id', 'name']:
            attr_val = element.get(attr, '')
            if attr_val:
                for kw in keywords:
                    if kw.lower() in attr_val.lower():
                        return True
        
        class_attr = element.get('class', [])
        if isinstance(class_attr, list):
            class_str = ' '.join(class_attr).lower()
        else:
            class_str = str(class_attr).lower()
        for kw in keywords:
            if kw.lower() in class_str:
                return True
        
        return False
    
    def is_login_password_field(element: Tag, element_text: str, placeholder: str) -> bool:
        """
        判断元素是否是登录密码/验证码输入框
        
        【识别策略】
        1. placeholder 包含关键词
        2. id/name 属性包含关键词
        3. type 属性为 password
        """
        password_keywords = ['密码', 'password', 'pwd']
        code_keywords = ['验证码', 'code', 'captcha', 'sms']
        
        element_type = element.get('type', '')
        if element_type == 'password':
            return True
        
        if placeholder:
            for kw in password_keywords + code_keywords:
                if kw.lower() in placeholder.lower():
                    return True
        
        for attr in ['id', 'name']:
            attr_val = element.get(attr, '')
            if attr_val:
                for kw in password_keywords + code_keywords:
                    if kw.lower() in attr_val.lower():
                        return True
        
        return False
    
    def is_login_submit_button(element: Tag, element_text: str) -> bool:
        """
        判断元素是否是登录提交按钮
        
        【识别策略】
        1. 文本包含"登录"关键词
        2. id/name/class 包含登录关键词
        """
        login_keywords = ['登录', '登入', 'login', 'sign in', 'signin', 'submit']
        
        if element_text:
            for kw in login_keywords:
                if kw.lower() in element_text.lower():
                    return True
        
        for attr in ['id', 'name', 'class']:
            attr_val = element.get(attr, '')
            if isinstance(attr_val, list):
                attr_val = ' '.join(attr_val)
            if attr_val:
                for kw in login_keywords:
                    if kw.lower() in attr_val.lower():
                        return True
        
        return False
    
    def is_get_code_button(element: Tag, element_text: str) -> bool:
        """
        判断元素是否是"获取验证码"按钮
        """
        code_keywords = ['获取验证码', '发送验证码', 'get code', 'send code', '发送', '获取']
        
        if element_text:
            for kw in code_keywords:
                if kw.lower() in element_text.lower():
                    return True
        
        for attr in ['id', 'name', 'class']:
            attr_val = element.get(attr, '')
            if isinstance(attr_val, list):
                attr_val = ' '.join(attr_val)
            if attr_val:
                for kw in code_keywords:
                    if kw.lower() in attr_val.lower():
                        return True
        
        return False
    
    def extract_element_text(element: Tag) -> str:
        """
        提取元素的完整文本信息，包括多种来源
        
        【策略】
        1. 直接文本内容
        2. title 属性
        3. aria-label 属性
        4. alt 属性（图片）
        5. placeholder 属性
        6. value 属性（按钮）
        7. href 属性（链接，提取最后一段）
        8. 递归提取子元素文本
        """
        texts = []
        
        direct_text = element.get_text(strip=True)
        if direct_text:
            texts.append(direct_text)
        
        if element.get('title'):
            texts.append(element.get('title'))
        
        if element.get('aria-label'):
            texts.append(element.get('aria-label'))
        
        if element.get('alt'):
            texts.append(element.get('alt'))
        
        if element.get('placeholder'):
            texts.append(element.get('placeholder'))
        
        element_type = element.get('type', '')
        if element_type in ['button', 'submit', 'reset']:
            value = element.get('value', '')
            if value:
                texts.append(value)
        
        href = element.get('href', '')
        if href and not href.startswith(('javascript:', '#')):
            href_text = href.rstrip('/').split('/')[-1]
            if href_text and len(href_text) < 50:
                texts.append(href_text)
        
        for child in element.find_all(['span', 'i', 'em', 'strong', 'b', 'img']):
            child_text = child.get('title') or child.get('alt') or child.get('aria-label')
            if child_text:
                texts.append(child_text)
        
        unique_texts = []
        seen = set()
        for t in texts:
            t_clean = t.strip()
            if t_clean and t_clean not in seen:
                unique_texts.append(t_clean)
                seen.add(t_clean)
        
        return ' | '.join(unique_texts[:3]) if unique_texts else ''
    
    def get_input_current_value(element: Tag, page: Page, selector: str, xpath: str, frame_info: dict = None) -> str:
        """
        获取输入框的当前实际值（通过 Playwright 动态获取）
        
        【设计思路】
        HTML 中的 value 属性只反映初始值，不反映用户输入后的值。
        需要通过 Playwright 的 input_value() 方法获取实际值。
        
        【参数】
        element: Tag - BeautifulSoup 元素对象
        page: Page - Playwright 页面对象
        selector: str - CSS 选择器
        xpath: str - XPath 路径
        frame_info: dict - iframe 信息（可选）
        
        【返回值】
        str: 输入框的当前值，如果获取失败或非输入框则返回空字符串
        """
        tag_name = element.name
        element_type = element.get('type', '')
        
        if tag_name not in ['input', 'textarea']:
            return ''
        
        if element_type in ['submit', 'button', 'image', 'file', 'hidden']:
            return ''
        
        try:
            fixed_selector = _escape_css_selector(selector)
            if frame_info:
                frame = page.frame_locator(frame_info['frame_selector'])
                locator = frame.locator(fixed_selector).first
            else:
                locator = page.locator(fixed_selector).first
            
            if locator.is_visible(timeout=500):
                current_value = locator.input_value(timeout=500)
                return current_value if current_value else ''
        except Exception:
            try:
                if frame_info:
                    frame = page.frame_locator(frame_info['frame_selector'])
                    locator = frame.locator(f"xpath={xpath}").first
                else:
                    locator = page.locator(f"xpath={xpath}").first
                
                if locator.is_visible(timeout=500):
                    current_value = locator.input_value(timeout=500)
                    return current_value if current_value else ''
            except Exception:
                pass
        
        return ''
    
    def extract_element_attributes(element: Tag) -> dict:
        """
        提取元素的关键属性，帮助识别元素功能
        """
        attrs = {}
        
        if element.get('id'):
            attrs['id'] = element.get('id')
        
        if element.get('class'):
            classes = element.get('class')
            if isinstance(classes, list):
                attrs['class'] = ' '.join(classes[:3])
        
        if element.get('href'):
            attrs['href'] = element.get('href')[:100]
        
        if element.get('role'):
            attrs['role'] = element.get('role')
        
        if element.get('data-testid'):
            attrs['data-testid'] = element.get('data-testid')
        
        if element.get('data-action'):
            attrs['data-action'] = element.get('data-action')
        
        return attrs
    
    def is_interactive_element(element: Tag) -> tuple[bool, str]:
        """
        判断元素是否可交互，返回 (是否可交互, 交互类型)
        
        【策略】
        1. 标准交互标签（a, button, input, select, textarea）
        2. 带有 onclick 属性的元素
        3. 带有 role="button" 或 role="link" 的元素
        4. 带有 tabindex 的元素
        5. 特定 class 名称暗示可交互
        """
        tag_name = element.name
        
        if tag_name in ['a', 'button']:
            return True, 'click'
        
        if tag_name == 'input':
            input_type = element.get('type', 'text')
            if input_type in ['submit', 'button', 'image']:
                return True, 'click'
            return True, 'input'
        
        if tag_name == 'select':
            return True, 'select'
        
        if tag_name == 'textarea':
            return True, 'input'
        
        if element.get('onclick') or element.get('ng-click') or element.get('@click'):
            return True, 'click'
        
        role = element.get('role', '')
        if role in ['button', 'link', 'tab', 'menuitem', 'option', 'checkbox', 'radio']:
            return True, 'click'
        
        if element.get('tabindex'):
            return True, 'click'
        
        class_attr = element.get('class', [])
        if isinstance(class_attr, str):
            class_attr = class_attr.split()
        
        click_keywords = ['btn', 'button', 'click', 'link', 'nav', 'menu', 'action']
        for cls in class_attr:
            cls_lower = cls.lower()
            for keyword in click_keywords:
                if keyword in cls_lower:
                    return True, 'click'
        
        return False, ''
    
    def extract_elements_from_soup(soup_obj: BeautifulSoup, frame_info: dict = None):
        """
        从 BeautifulSoup 对象中提取可交互元素
        
        【参数】
        soup_obj: BeautifulSoup 解析对象
        frame_info: iframe 信息（可选），包含 frame_name 或 frame_url
        """
        nonlocal element_id
        
        all_tags = soup_obj.find_all(True)
        
        for element in all_tags:
            if not isinstance(element, Tag):
                continue
            
            is_interactive, interaction_type = is_interactive_element(element)
            
            if not is_interactive and element.name not in interactive_tags:
                continue
            
            style = element.get('style', '')
            if 'display: none' in style or 'visibility: hidden' in style:
                continue
            
            element_id_attr = element.get('id', '')
            element_name = element.get('name', '')
            element_type = element.get('type', '')
            
            selector = get_element_selector(element)
            xpath = get_element_xpath(element)
            
            selector_key = f"{frame_info.get('frame_name', 'main')}:{selector}" if frame_info else selector
            if selector_key in seen_selectors:
                continue
            
            is_visible = False
            try:
                if frame_info:
                    frame = page.frame_locator(frame_info['frame_selector'])
                    locator = frame.locator(selector).first
                else:
                    locator = page.locator(selector).first
                is_visible = locator.is_visible(timeout=1000)
            except Exception:
                try:
                    if frame_info:
                        frame = page.frame_locator(frame_info['frame_selector'])
                        locator = frame.locator(f"xpath={xpath}").first
                    else:
                        locator = page.locator(f"xpath={xpath}").first
                    is_visible = locator.is_visible(timeout=1000)
                except Exception:
                    is_visible = False
            
            if not is_visible:
                continue
            
            seen_selectors.add(selector_key)
            
            tag_name = element.name
            is_clickable = tag_name in ['a', 'button'] or \
                          (tag_name == 'input' and element_type in ['submit', 'button', 'image']) or \
                          interaction_type == 'click'
            is_input = tag_name in ['input', 'textarea'] and \
                      element_type not in ['submit', 'button', 'image']
            is_selectable = tag_name == 'select'
            is_checkable = tag_name == 'input' and element_type in ['checkbox', 'radio']
            
            if tag_name == 'iframe':
                class_attr = element.get('class', '')
                if isinstance(class_attr, list):
                    class_attr = ' '.join(class_attr)
                if 'editor' in class_attr.lower() or 'contenteditable' in class_attr.lower():
                    is_input = True
                    is_clickable = True
            
            element_text = extract_element_text(element)
            element_attrs = extract_element_attributes(element)
            placeholder = element.get('placeholder', '')
            
            current_value = ''
            if is_input:
                current_value = get_input_current_value(element, page, selector, xpath, frame_info)
            
            is_login_element = False
            login_element_type = None
            priority = "normal"
            
            nonlocal popup_detected, login_form_detected, login_elements
            
            if frame_info:
                popup_detected = True
                priority = "high"
                
                if is_input:
                    if is_login_username_field(element, element_text, placeholder):
                        is_login_element = True
                        login_element_type = "username"
                        login_elements["username"] = element_id
                    elif is_login_password_field(element, element_text, placeholder):
                        is_login_element = True
                        login_element_type = "password"
                        login_elements["password"] = element_id
                
                if is_clickable:
                    if is_login_submit_button(element, element_text):
                        is_login_element = True
                        login_element_type = "submit"
                        login_elements["submit"] = element_id
                    elif is_get_code_button(element, element_text):
                        is_login_element = True
                        login_element_type = "get_code"
                        login_elements["get_code_btn"] = element_id
            
            if login_elements["username"] and (login_elements["password"] or login_elements["sms_code"]):
                login_form_detected = True
            
            element_info = {
                "type": tag_name,
                "input_type": element_type,
                "text": element_text[:100],
                "placeholder": placeholder,
                "current_value": current_value,
                "name": element_name,
                "id": element_id_attr,
                "xpath": xpath,
                "selector": selector,
                "is_clickable": is_clickable,
                "is_input": is_input,
                "is_selectable": is_selectable,
                "is_checkable": is_checkable,
                "attrs": element_attrs,
                "priority": priority,
                "is_login_element": is_login_element,
                "login_element_type": login_element_type
            }
            
            if frame_info:
                element_info["frame"] = frame_info
            
            if is_input or is_clickable or is_selectable or is_checkable or element_text:
                elements_dict[element_id] = element_info
                element_id += 1
    
    extract_elements_from_soup(soup)
    
    iframe_elements = soup.find_all('iframe')
    iframe_info_list = []
    
    for idx, iframe in enumerate(iframe_elements):
        if not isinstance(iframe, Tag):
            continue
        
        frame_name = iframe.get('name', '')
        frame_id = iframe.get('id', '')
        frame_src = iframe.get('src', '')
        
        frame_selector = None
        if frame_name:
            frame_selector = f"iframe[name='{frame_name}']"
        elif frame_id:
            escaped_id = frame_id.replace('.', '\\.').replace(':', '\\:')
            frame_selector = f"iframe#{escaped_id}"
        elif frame_src:
            safe_src = frame_src[:50].replace("'", "\\'")
            frame_selector = f"iframe[src*='{safe_src}']"
        else:
            frame_selector = f"iframe >> nth={idx}"
        
        frame_info = {
            "frame_name": frame_name or f"iframe_{idx}",
            "frame_id": frame_id,
            "frame_src": frame_src,
            "frame_selector": frame_selector
        }
        
        try:
            frame = page.frame_locator(frame_selector)
            frame_content = frame.locator("body").inner_html(timeout=2000)
            frame_soup = BeautifulSoup(frame_content, 'html.parser')
            
            extract_elements_from_soup(frame_soup, frame_info)
            iframe_info_list.append({
                "name": frame_name or frame_id or f"iframe_{idx}",
                "status": "success",
                "elements_count": "extracted"
            })
        except Exception as e:
            iframe_info_list.append({
                "name": frame_name or frame_id or f"iframe_{idx}",
                "status": "failed",
                "error": str(e)[:50]
            })
    
    saved_file = output_handler.write_elements(elements_dict, current_url, iframe_info_list)
    print_perception(len(elements_dict), saved_file)
    
    if popup_detected:
        print_action_warning("检测到弹窗/模态框")
    if login_form_detected:
        print_action_warning("检测到登录表单")
    
    context.logger.log_perception(len(elements_dict), current_url)
    
    complexity = context.step_manager.estimate_complexity(
        state.get("objective", ""),
        len(elements_dict),
        len(state.get("history", []))
    )
    
    if complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]:
        if context.step_manager.should_extend_steps(
            state.get("progress_ratio", 0),
            state.get("error_count", 0),
            state.get("consecutive_success", 0)
        ):
            context.step_manager.adjust_max_steps(
                reason=f"任务复杂度评估: {complexity.value}",
                complexity=complexity,
                current_step=state.get("step_count", 0)
            )
    
    return {
        "elements_dict": elements_dict,
        "current_url": current_url,
        "error_message": None,
        "max_steps": context.step_manager.current_max_steps,
        "popup_detected": popup_detected,
        "login_form_detected": login_form_detected,
        "login_elements": login_elements,
        **pending_updates
    }


def reasoning_node(state: AgentState, llm: ChatOpenAI, context: AgentContext) -> dict:
    """
    Reasoning Node - 决策模块（Agent 的"大脑"）
    
    【核心职责】
    基于当前状态和历史信息决定下一步动作。
    
    【参数】
    state: AgentState - 当前状态
    llm: ChatOpenAI - 大语言模型实例
    context: AgentContext - Agent上下文
    
    【返回值】
    dict: 状态更新字典
    """
    context.process_user_commands()
    context.user_interaction.wait_if_paused()
    
    output_handler = get_output_handler()
    
    popup_detected = state.get("popup_detected", False)
    login_form_detected = state.get("login_form_detected", False)
    login_elements = state.get("login_elements", {})
    
    elements_description = "当前页面可交互元素：\n"
    for eid, info in state["elements_dict"].items():
        text = info['text'] if info['text'] else info.get('placeholder', '[无文本]')
        flags = []
        if info['is_input']: flags.append("可输入")
        if info['is_clickable']: flags.append("可点击")
        if info['is_selectable']: flags.append("下拉选择")
        if info['is_checkable']: flags.append("可勾选")
        if info.get('frame'): flags.append("弹窗内")
        if info.get('priority') == "high": flags.append("高优先级")
        if info.get('is_login_element'): flags.append("登录元素")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        
        attrs_info = ""
        attrs = info.get('attrs', {})
        if attrs.get('id'):
            attrs_info += f", id={attrs['id']}"
        if attrs.get('class'):
            attrs_info += f", class={attrs['class'][:30]}"
        if attrs.get('role'):
            attrs_info += f", role={attrs['role']}"
        if attrs.get('href'):
            attrs_info += f", href={attrs['href'][:50]}"
        
        current_value = info.get('current_value', '')
        value_info = f", 当前值=\"{current_value}\"" if current_value else ""
        
        login_type_info = ""
        if info.get('login_element_type'):
            login_type_info = f" [登录{info['login_element_type']}]"
        
        elements_description += f"  [{eid}] {info['type']}: {text}{flag_str}{attrs_info}{value_info}{login_type_info}\n"
    
    history_text = "执行历史：\n"
    for h in state["history"][-5:]:
        history_text += f"  步骤{h.get('step', '?')}: {h.get('action_type', '?')} - {h.get('result', '?')}\n"
    
    if not state["history"]:
        history_text = "执行历史：暂无\n"
    
    user_prompt = f"""
## 用户目标
{state["objective"]}

## 当前页面 URL
{state["current_url"]}
"""

    if popup_detected:
        user_prompt += "\n## ⚠️ 重要：检测到弹窗/模态框\n"
        user_prompt += "当前页面存在弹窗或模态框，你必须优先处理弹窗内容！\n"
        user_prompt += "请查看带有 [弹窗内] 标记的元素，优先操作这些元素。\n"
    
    if login_form_detected:
        user_prompt += "\n## ⚠️ 重要：检测到登录表单\n"
        user_prompt += "当前页面存在登录表单，请按以下顺序操作：\n"
        if login_elements.get("username"):
            user_prompt += f"1. 在用户名/手机号输入框 [{login_elements['username']}] 中输入账号\n"
        if login_elements.get("get_code_btn"):
            user_prompt += f"2. 点击 [获取验证码] 按钮 [{login_elements['get_code_btn']}]\n"
            user_prompt += "3. 等待用户输入验证码（如果需要）\n"
        if login_elements.get("password"):
            user_prompt += f"2. 在密码/验证码输入框 [{login_elements['password']}] 中输入密码/验证码\n"
        if login_elements.get("submit"):
            user_prompt += f"最后：点击登录按钮 [{login_elements['submit']}]\n"
        
        objective = state.get("objective", "")
        import re
        phone_match = re.search(r'(?:账号|手机号|用户名)[：:]\s*(\d{11})', objective)
        password_match = re.search(r'(?:密码)[：:]\s*(\S+)', objective)
        if phone_match:
            user_prompt += f"\n检测到用户提供的账号: {phone_match.group(1)}\n"
        if password_match:
            user_prompt += f"检测到用户提供的密码: {password_match.group(1)}\n"
    
    user_prompt += f"""
## {elements_description}

## {history_text}
"""
    
    if state.get("error_message"):
        user_prompt += f"\n## ⚠️ 上一步出错\n{state['error_message']}\n请尝试其他方法。\n"
    
    user_prompt += "\n请输出你的决策（JSON格式）："
    
    start_time = time.time()
    
    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
        def call_llm():
            return llm.invoke(messages)
        
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(call_llm)
            
            while not future.done():
                context.process_user_commands()
                
                if context.user_interaction.is_aborted():
                    print("\n🛑 用户请求终止，取消 LLM 调用...")
                    return {
                        "history": state["history"],
                        "error_message": "用户终止任务",
                        "is_done": True,
                        "termination_reason": "user_abort"
                    }
                
                if context.user_interaction.is_paused():
                    context.user_interaction.wait_if_paused()
                    if context.user_interaction.is_aborted():
                        return {
                            "history": state["history"],
                            "error_message": "用户终止任务",
                            "is_done": True,
                            "termination_reason": "user_abort"
                        }
                
                time.sleep(0.05)
            
            response = future.result()
        
        response_text = response.content
        
        reasoning_time = (time.time() - start_time) * 1000
        
        decision = parse_json_from_response(response_text)
        
        required_fields = ["thought", "action_type"]
        for field in required_fields:
            if field not in decision:
                raise ValueError(f"决策缺少必要字段: {field}")
        
        if decision["action_type"] not in VALID_ACTIONS:
            raise ValueError(f"无效的动作类型: {decision['action_type']}")
        
        print_decision(
            decision["action_type"],
            decision.get("target_id"),
            decision.get("value")
        )
        
        output_handler.write_decision(decision, decision.get('thought', ''), state["step_count"] + 1)
        
        decision_log = DecisionLog(
            step=state["step_count"] + 1,
            llm_response=response_text[:500],
            parsed_decision=decision,
            reasoning_time_ms=reasoning_time
        )
        context.logger.log_decision(decision_log)
        
        history_entry = {
            "step": state["step_count"] + 1,
            "thought": decision.get("thought", ""),
            "action_type": decision["action_type"],
            "target_id": decision.get("target_id"),
            "value": decision.get("value"),
            "result": "待执行"
        }
        
        return {
            "history": state["history"] + [history_entry],
            "current_decision": decision,
            "error_message": None
        }
        
    except Exception as e:
        print_action_error(f"决策出错: {e}")
        context.logger.log_error(str(e), state["step_count"] + 1)
        error_entry = {
            "step": state["step_count"] + 1,
            "thought": f"决策出错: {str(e)}",
            "action_type": "error",
            "result": f"错误: {str(e)}"
        }
        return {
            "history": state["history"] + [error_entry],
            "error_message": f"决策模块错误: {str(e)}",
            "error_count": state.get("error_count", 0) + 1
        }


def _safe_wait_for_page(page: Page, timeout: int = ACTION_TIMEOUT):
    """
    安全的页面加载等待函数
    
    【策略】
    1. 首先尝试等待 networkidle 状态
    2. 如果超时，降级为等待 load 状态
    3. 如果仍然超时，只等待 domcontentloaded 状态
    
    【参数】
    page: Playwright 页面对象
    timeout: 超时时间（毫秒）
    """
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        try:
            page.wait_for_load_state("load", timeout=5000)
        except Exception:
            pass


def _get_locator(page: Page, element_info: dict):
    """
    获取元素定位器，尝试多种策略，支持 iframe 内元素
    
    【参数】
    page: Playwright 页面对象
    element_info: 元素信息字典，可能包含 frame 信息
    
    【返回值】
    Locator 或 None
    
    【选择器修复策略】
    1. 首先检查 CSS 选择器是否有效
    2. 如果 CSS 选择器无效（如以数字开头的ID），尝试修复
    3. 如果 CSS 选择器仍然失败，回退到 XPath
    """
    selector = element_info["selector"]
    xpath = element_info["xpath"]
    frame_info = element_info.get("frame")
    
    fixed_selector = _escape_css_selector(selector)
    if fixed_selector != selector:
        print(f"   🔧 选择器修复: {selector} -> {fixed_selector}")
        selector = fixed_selector
    
    loc_strategies = [selector, f"xpath={xpath}"]
    
    if frame_info:
        frame_selector = frame_info.get("frame_selector")
        if frame_selector:
            try:
                frame = page.frame_locator(frame_selector)
                for loc_strategy in loc_strategies:
                    try:
                        locator = frame.locator(loc_strategy).first
                        return locator
                    except Exception as e:
                        print(f"   ⚠️ 定位策略 '{loc_strategy}' 失败: {e}")
                        continue
            except Exception as e:
                print(f"   ⚠️ Frame 定位失败: {e}")
                pass
        return None
    
    for loc_strategy in loc_strategies:
        try:
            locator = page.locator(loc_strategy).first
            return locator
        except Exception as e:
            print(f"   ⚠️ 定位策略 '{loc_strategy}' 失败: {e}")
            continue
    return None


def _verify_input_value(locator, expected_value: str, max_retries: int = 3) -> tuple[bool, str]:
    """
    验证输入框的实际值是否与期望值一致
    
    【设计思路】
    填写内容后，需要验证内容是否真正写入输入框。
    由于某些网页可能有延迟或动态处理，需要多次重试验证。
    
    【参数】
    locator: Playwright Locator 对象
    expected_value: 期望输入的值
    max_retries: 最大重试次数
    
    【返回值】
    tuple[bool, str]: (是否验证通过, 实际值或错误信息)
    """
    import time
    
    for attempt in range(max_retries):
        try:
            time.sleep(0.1)
            actual_value = locator.input_value(timeout=1000)
            
            if actual_value == expected_value:
                return True, actual_value
            
            if actual_value.strip() == expected_value.strip():
                print(f"   ⚠️ 值匹配但存在空白差异: 期望='{expected_value}', 实际='{actual_value}'")
                return True, actual_value
            
            if actual_value and (expected_value in actual_value or actual_value in expected_value):
                print(f"   ⚠️ 值部分匹配: 期望='{expected_value}', 实际='{actual_value}'")
                return True, actual_value
            
            print(f"   🔄 验证重试 {attempt + 1}/{max_retries}: 期望='{expected_value}', 实际='{actual_value}'")
            
        except Exception as e:
            print(f"   ⚠️ 验证读取失败 (尝试 {attempt + 1}/{max_retries}): {e}")
    
    try:
        final_value = locator.input_value(timeout=1000)
        return False, final_value
    except Exception as e:
        return False, f"无法读取: {e}"


def _type_in_iframe_editor(page: Page, element_info: dict, value: str) -> tuple[bool, str]:
    """
    在 iframe 内的富文本编辑器中输入内容
    
    【设计思路】
    邮件系统通常使用 iframe 内的富文本编辑器（contenteditable），
    不能直接使用 fill() 方法。需要：
    1. 进入 iframe 内部
    2. 找到可编辑的 body 或 div 元素
    3. 使用 click + type 或 evaluate 注入内容
    
    【参数】
    page: Playwright 页面对象
    element_info: 元素信息字典，包含 iframe 选择器
    value: 要输入的内容
    
    【返回值】
    tuple[bool, str]: (是否成功, 结果消息)
    """
    frame_info = element_info.get("frame")
    selector = element_info.get("selector", "")
    
    if not frame_info and "iframe" in selector.lower():
        frame_selector = selector
    elif frame_info:
        frame_selector = frame_info.get("frame_selector", selector)
    else:
        return False, "不是 iframe 元素"
    
    try:
        frame = page.frame_locator(frame_selector)
        
        editable_selectors = [
            "body[contenteditable='true']",
            "div[contenteditable='true']",
            "body",
            "#editor",
            ".editor-content",
            "[role='textbox']"
        ]
        
        for edit_selector in editable_selectors:
            try:
                editor = frame.locator(edit_selector).first
                if editor.is_visible(timeout=1000):
                    editor.click(timeout=ACTION_TIMEOUT)
                    page.keyboard.type(value, delay=50)
                    
                    print(f"   ✅ 在 iframe 编辑器中输入成功")
                    return True, f"成功在 iframe 编辑器中输入 '{value}'"
            except Exception:
                continue
        
        try:
            frame_body = frame.locator("body").first
            frame_body.evaluate(f"el => el.innerHTML = '{value}'")
            print(f"   ✅ 通过 JavaScript 注入内容到 iframe")
            return True, f"成功注入内容到 iframe 编辑器"
        except Exception as e:
            print(f"   ⚠️ JavaScript 注入失败: {e}")
            
        return False, "无法找到 iframe 内的可编辑元素"
        
    except Exception as e:
        return False, f"iframe 操作失败: {e}"


def _is_iframe_editor(element_info: dict) -> bool:
    """
    判断元素是否是 iframe 编辑器
    
    【参数】
    element_info: 元素信息字典
    
    【返回值】
    bool: 是否是 iframe 编辑器
    """
    element_type = element_info.get("type", "")
    selector = element_info.get("selector", "").lower()
    
    if element_type == "iframe":
        return True
    
    if "iframe" in selector:
        return True
    
    if "editor" in selector or "contenteditable" in selector:
        return True
    
    attrs = element_info.get("attrs", {})
    class_attr = attrs.get("class", "").lower()
    if "editor" in class_attr or "contenteditable" in class_attr:
        return True
    
    return False


def action_node(state: AgentState, page: Page, context: AgentContext) -> dict:
    """
    Action Node - 执行模块（Agent 的"双手"）
    
    【核心职责】
    执行决策模块确定的动作，支持丰富的交互操作。
    
    【参数】
    state: AgentState - 当前状态
    page: Page - Playwright 页面对象
    context: AgentContext - Agent上下文
    
    【返回值】
    dict: 状态更新字典
    """
    context.process_user_commands()
    context.user_interaction.wait_if_paused()
    
    output_handler = get_output_handler()
    
    if not state["history"]:
        print("⚠️ 没有找到决策记录")
        return {"error_message": "没有可执行的决策"}
    
    last_entry = state["history"][-1]
    decision = {
        "action_type": last_entry.get("action_type"),
        "target_id": last_entry.get("target_id"),
        "value": last_entry.get("value")
    }
    
    action_type = decision.get("action_type")
    
    if action_type == "error":
        return {"error_message": "上一决策失败，需要重新决策"}
    
    new_history = state["history"].copy()
    step_start_time = time.time()
    
    def get_element_info(target_id):
        if not target_id:
            raise ValueError("需要提供目标元素 ID")
        element_info = state["elements_dict"].get(target_id)
        if not element_info:
            raise ValueError(f"找不到 ID 为 {target_id} 的元素")
        return element_info
    
    def try_action(action_func, action_name):
        """尝试执行动作，失败时返回错误"""
        try:
            result = action_func()
            duration = (time.time() - step_start_time) * 1000
            
            new_history[-1]["result"] = result
            
            step_log = StepLog(
                step=state["step_count"] + 1,
                action_type=action_name,
                target_id=decision.get("target_id"),
                value=decision.get("value"),
                thought=last_entry.get("thought", ""),
                result=result,
                duration_ms=duration
            )
            context.logger.log_step(step_log)
            
            output_handler.write_action_result(
                action_name, decision.get("target_id"),
                decision.get("value"), result, state["step_count"] + 1
            )
            
            context.termination_manager.record_success()
            
            print_action_success(action_name, duration)
            
            return {
                "history": new_history,
                "error_message": None,
                "step_count": state["step_count"] + 1,
                "consecutive_success": state.get("consecutive_success", 0) + 1
            }
        except Exception as e:
            duration = (time.time() - step_start_time) * 1000
            error_msg = f"{action_name}失败: {str(e)}"
            print_action_error(error_msg)
            new_history[-1]["result"] = error_msg
            
            context.logger.log_error(error_msg, state["step_count"] + 1)
            
            output_handler.write_action_result(
                action_name, decision.get("target_id"),
                decision.get("value"), error_msg, state["step_count"] + 1, str(e)
            )
            
            error_record = context.termination_manager.record_error(error_msg, state["step_count"] + 1)
            recovery_action = context.termination_manager.get_recovery_action(error_record.error_type)
            
            return {
                "history": new_history,
                "error_message": error_msg,
                "step_count": state["step_count"] + 1,
                "error_count": state.get("error_count", 0) + 1,
                "consecutive_success": 0
            }
    
    try:
        if action_type == "done":
            print("✅ 任务完成！")
            new_history[-1]["result"] = "任务完成"
            return {
                "is_done": True,
                "history": new_history,
                "error_message": None,
                "step_count": state["step_count"] + 1
            }
        
        elif action_type == "goto":
            def do_goto():
                url = decision.get("value", "")
                if not url:
                    raise ValueError("需要提供 URL")
                if not url.startswith("http"):
                    url = "https://" + url
                page.goto(url, timeout=PAGE_LOAD_TIMEOUT)
                _safe_wait_for_page(page)
                return f"成功导航到 {url}"
            return try_action(do_goto, "goto")
        
        elif action_type == "click":
            def do_click():
                element_info = get_element_info(decision.get("target_id"))
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.click(timeout=ACTION_TIMEOUT, force=True)
                _safe_wait_for_page(page)
                return f"成功点击元素 {decision.get('target_id')}"
            return try_action(do_click, "click")
        
        elif action_type == "double_click":
            def do_double_click():
                element_info = get_element_info(decision.get("target_id"))
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.dblclick(timeout=ACTION_TIMEOUT, force=True)
                return f"成功双击元素 {decision.get('target_id')}"
            return try_action(do_double_click, "double_click")
        
        elif action_type == "right_click":
            def do_right_click():
                element_info = get_element_info(decision.get("target_id"))
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.click(button="right", timeout=ACTION_TIMEOUT, force=True)
                return f"成功右键点击元素 {decision.get('target_id')}"
            return try_action(do_right_click, "right_click")
        
        elif action_type == "hover":
            def do_hover():
                element_info = get_element_info(decision.get("target_id"))
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.hover(timeout=ACTION_TIMEOUT, force=True)
                page.wait_for_timeout(500)
                return f"成功悬停在元素 {decision.get('target_id')}"
            return try_action(do_hover, "hover")
        
        elif action_type == "drag":
            def do_drag():
                element_info = get_element_info(decision.get("target_id"))
                target_desc = decision.get("value", "")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                target_locator = page.locator(target_desc).first
                locator.drag_to(target_locator, timeout=ACTION_TIMEOUT)
                return f"成功拖拽元素到 {target_desc}"
            return try_action(do_drag, "drag")
        
        elif action_type == "type":
            def do_type():
                element_info = get_element_info(decision.get("target_id"))
                value = decision.get("value", "")
                
                if _is_iframe_editor(element_info):
                    success, message = _type_in_iframe_editor(page, element_info, value)
                    if success:
                        return message
                    else:
                        raise ValueError(message)
                
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                
                max_retries = 3
                last_error = None
                for attempt in range(max_retries):
                    try:
                        locator.scroll_into_view_if_needed(timeout=5000)
                        locator.click(timeout=ACTION_TIMEOUT)
                        page.wait_for_timeout(100)
                        locator.fill(value, timeout=ACTION_TIMEOUT)
                        
                        verified, actual_value = _verify_input_value(locator, value)
                        
                        if verified:
                            return f"成功输入并验证 '{value}'"
                        else:
                            if attempt < max_retries - 1:
                                print(f"   🔄 输入验证失败，重试 {attempt + 2}/{max_retries}")
                                page.wait_for_timeout(200)
                                continue
                            return f"输入完成但验证有差异: 期望 '{value}', 实际 '{actual_value}'"
                    except Exception as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            print(f"   🔄 输入失败，重试 {attempt + 2}/{max_retries}: {e}")
                            page.wait_for_timeout(200)
                            continue
                
                raise ValueError(f"输入失败（重试{max_retries}次）: {last_error}")
            return try_action(do_type, "type")
        
        elif action_type == "type_slowly":
            def do_type_slowly():
                element_info = get_element_info(decision.get("target_id"))
                value = decision.get("value", "")
                
                if _is_iframe_editor(element_info):
                    success, message = _type_in_iframe_editor(page, element_info, value)
                    if success:
                        return message
                    else:
                        raise ValueError(message)
                
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.click(timeout=ACTION_TIMEOUT)
                for char in value:
                    page.keyboard.type(char, delay=100)
                
                verified, actual_value = _verify_input_value(locator, value)
                
                if verified:
                    return f"成功逐字输入并验证 '{value}'"
                else:
                    return f"逐字输入完成但验证有差异: 期望 '{value}', 实际 '{actual_value}'"
            return try_action(do_type_slowly, "type_slowly")
        
        elif action_type == "press":
            def do_press():
                key = decision.get("value", "Enter")
                page.keyboard.press(key)
                _safe_wait_for_page(page)
                return f"成功按下 {key}"
            return try_action(do_press, "press")
        
        elif action_type == "hotkey":
            def do_hotkey():
                keys = decision.get("value", "Control+C")
                key_list = keys.split("+")
                for key in key_list:
                    page.keyboard.down(key.strip())
                for key in reversed(key_list):
                    page.keyboard.up(key.strip())
                page.wait_for_timeout(300)
                return f"成功执行快捷键 {keys}"
            return try_action(do_hotkey, "hotkey")
        
        elif action_type == "select":
            def do_select():
                element_info = get_element_info(decision.get("target_id"))
                value = decision.get("value", "")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.select_option(label=value, timeout=ACTION_TIMEOUT)
                
                try:
                    selected = locator.input_value(timeout=1000)
                    if selected:
                        return f"成功选择并验证 '{value}'"
                    else:
                        return f"选择完成但无法验证"
                except Exception as e:
                    return f"选择完成但验证失败: {e}"
            return try_action(do_select, "select")
        
        elif action_type == "check":
            def do_check():
                element_info = get_element_info(decision.get("target_id"))
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.check(timeout=ACTION_TIMEOUT, force=True)
                return f"成功勾选元素 {decision.get('target_id')}"
            return try_action(do_check, "check")
        
        elif action_type == "uncheck":
            def do_uncheck():
                element_info = get_element_info(decision.get("target_id"))
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.uncheck(timeout=ACTION_TIMEOUT, force=True)
                return f"成功取消勾选元素 {decision.get('target_id')}"
            return try_action(do_uncheck, "uncheck")
        
        elif action_type == "scroll":
            def do_scroll():
                value = decision.get("value", "down/300")
                if value == "bottom":
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                elif value == "top":
                    page.evaluate("window.scrollTo(0, 0)")
                else:
                    parts = value.split("/")
                    direction = parts[0]
                    amount = int(parts[1]) if len(parts) > 1 else 300
                    if direction == "down":
                        page.mouse.wheel(0, amount)
                    elif direction == "up":
                        page.mouse.wheel(0, -amount)
                    elif direction == "right":
                        page.mouse.wheel(amount, 0)
                    elif direction == "left":
                        page.mouse.wheel(-amount, 0)
                page.wait_for_timeout(500)
                return f"成功滚动 {value}"
            return try_action(do_scroll, "scroll")
        
        elif action_type == "scroll_to":
            def do_scroll_to():
                element_info = get_element_info(decision.get("target_id"))
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.scroll_into_view_if_needed(timeout=ACTION_TIMEOUT)
                return f"成功滚动到元素 {decision.get('target_id')}"
            return try_action(do_scroll_to, "scroll_to")
        
        elif action_type == "wait":
            def do_wait():
                ms = int(decision.get("value", "1000"))
                page.wait_for_timeout(ms)
                return f"等待了 {ms} 毫秒"
            return try_action(do_wait, "wait")
        
        elif action_type == "screenshot":
            def do_screenshot():
                desc = decision.get("value", "页面截图")
                timestamp = int(page.evaluate("Date.now()"))
                path = f"screenshot_{timestamp}.png"
                page.screenshot(path=path)
                return f"截图已保存: {path}"
            return try_action(do_screenshot, "screenshot")
        
        else:
            raise ValueError(f"未知的动作类型: {action_type}")
    
    except Exception as e:
        error_msg = f"执行失败: {str(e)}"
        print(f"❌ {error_msg}")
        new_history[-1]["result"] = error_msg
        context.logger.log_error(error_msg, state["step_count"] + 1)
        return {
            "history": new_history,
            "error_message": error_msg,
            "step_count": state["step_count"] + 1,
            "error_count": state.get("error_count", 0) + 1,
            "consecutive_success": 0
        }


def should_continue(state: AgentState, context: AgentContext) -> str:
    """
    条件路由函数 - 决定图的下一步走向
    
    【参数】
    state: AgentState - 当前状态
    context: AgentContext - Agent上下文
    
    【返回值】
    str: 下一个节点的名称
    """
    context.process_user_commands()
    
    if context.user_interaction.is_aborted():
        print("\n🛑 用户请求终止任务")
        context.logger.log_termination("用户终止")
        context.set_pending_state_updates({
            "is_done": True,
            "termination_reason": "user_abort"
        })
        return "end"
    
    if state["is_done"]:
        print("\n🎉 任务已完成，结束循环")
        context.logger.log_termination("正常完成")
        return "end"
    
    fast_mode = state.get("fast_mode", False)
    current_step = state["step_count"]
    
    # 先更新 TerminationManager 的停滞阈值（基于当前步数）
    context.termination_manager._update_stagnation_threshold(current_step)
    
    # 获取当前动态阈值，传给 assess_completion
    current_stagnation_threshold = context.termination_manager.adjusted_stagnation_threshold
    
    assessment = context.completion_evaluator.assess_completion(
        objective=state["objective"],
        history=state.get("history", []),
        current_url=state.get("current_url", ""),
        is_done=False,
        fast_mode=fast_mode,
        stagnation_threshold=current_stagnation_threshold
    )
    
    if assessment.task_complexity != context.termination_manager.task_complexity:
        context.termination_manager.set_task_complexity(assessment.task_complexity)
        print(f"📊 任务复杂度更新: {assessment.task_complexity.value}, 停滞阈值: {context.termination_manager.adjusted_stagnation_threshold}")
    
    termination_check = context.termination_manager.check_all(
        current_step=state["step_count"],
        max_steps=state.get("max_steps", MAX_STEPS),
        error_count=state.get("error_count", 0),
        stagnation_count=assessment.stagnation_count,
        completion_status=assessment.status,
        progress_level=assessment.progress_level
    )
    
    state_updates = {
        "progress_ratio": assessment.progress_ratio,
        "stagnation_count": assessment.stagnation_count,
        "task_complexity": assessment.task_complexity.value,
        "progress_level": assessment.progress_level.value,
        "adjusted_stagnation_threshold": context.termination_manager.adjusted_stagnation_threshold
    }
    
    if termination_check.should_terminate:
        reason = termination_check.reason.value if termination_check.reason else "unknown"
        print(f"\n🛑 任务终止: {termination_check.message}")
        context.logger.log_termination(
            reason,
            termination_check.message
        )
        state_updates["termination_reason"] = reason
        state_updates["is_done"] = True
        context.set_pending_state_updates(state_updates)
        return "end"
    
    if context.checkpoint_manager.should_save_checkpoint(state["step_count"]):
        checkpoint_id = context.save_checkpoint(state)
        state_updates["saved_checkpoint_id"] = checkpoint_id
    
    context.log_resource_usage(state["step_count"])
    context.update_status(state)
    
    if assessment.status == CompletionStatus.LIKELY_COMPLETE:
        print(f"💡 任务可能已完成 (置信度: {assessment.confidence:.1%})")
    
    context.set_pending_state_updates(state_updates)
    
    return "perception"
