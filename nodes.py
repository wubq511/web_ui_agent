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
from typing import Optional, Dict, List, Any, Tuple
import concurrent.futures
from functools import lru_cache
import hashlib
import json
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from playwright.sync_api import Page
from bs4 import BeautifulSoup, Tag

from state import AgentState
from config import ACTION_TIMEOUT, PAGE_LOAD_TIMEOUT, MAX_STEPS
from utils import parse_json_from_response, get_element_xpath, get_element_selector, _is_valid_css_id, _escape_css_selector, validate_url
from cache_utils import get_selector_cache, get_prompt_cache, cached_result

from step_manager import StepManager
from completion_evaluator import CompletionEvaluator, CompletionStatus, ProgressLevel
from termination_manager import TerminationManager, TerminationReason
from config import TaskComplexity
from user_interaction import UserInteractionManager, UserCommand
from checkpoint_manager import CheckpointManager
from agent_logger import AgentLogger, StepLog, DecisionLog, ResourceLog
from output_handler import get_output_handler
from performance_monitor import get_performance_monitor, measure_time
from console_formatter import (
    print_step_separator, print_perception, print_decision,
    print_action_success, print_action_warning, print_action_error,
    print_checkpoint_saved, print_session_saved, print_task_complete,
    print_task_terminated, print_progress_hint, print_maybe_complete, print_separator
)

try:
    from model_manager import get_model_manager
    HAS_MODEL_MANAGER = True
except ImportError:
    HAS_MODEL_MANAGER = False

try:
    from credential_manager import CredentialManager, AuthenticationError, CredentialNotFoundError
    HAS_CREDENTIAL_MANAGER = True
except ImportError:
    HAS_CREDENTIAL_MANAGER = False
    CredentialManager = None


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

## 🚨 强制：弹窗/模态框优先处理原则

**当检测到弹窗或模态框时，必须优先处理弹窗内容，禁止进行其他操作！**

**关键规则：**
1. **弹窗会遮挡页面其他元素，导致无法点击弹窗外的元素！**
2. **检测到登录弹窗时，必须完成登录后才能进行搜索、浏览等其他操作！**
3. **禁止在登录完成前尝试搜索或点击页面其他元素！**

弹窗检测标志：
- 提示中出现 "🚨【强制】必须先完成登录！"
- 元素有 `[弹窗内]` 标记
- 元素有 `frame` 属性（表示在iframe中）
- 元素有 `priority: high` 标记
- 元素列表中出现 "【登录弹窗-优先】" 分隔符

弹窗处理规则：
1. **登录弹窗（最高优先级）**：
   - 如果提示"🚨【强制】必须先完成登录！"，**必须立即执行登录操作**
   - **禁止**在登录完成前进行搜索、浏览等其他操作
   - 按照提示的步骤顺序完成登录
   - 登录成功后（弹窗关闭或页面跳转）才能进行其他操作
2. **确认弹窗**：如果有确认/取消按钮，根据任务需要选择点击
3. **提示弹窗**：如果有关闭按钮，可以点击关闭或根据提示操作

## ⚠️ 重要：登录场景处理指南

**登录场景识别**：
当元素列表中出现以下组合时，表示检测到登录界面：
- 用户名/手机号输入框：`placeholder` 包含 "手机号"、"用户名"、"账号"、"phone"、"username"
- 密码/验证码输入框：`placeholder` 包含 "密码"、"验证码"、"password"、"code"
- 登录按钮：`text` 包含 "登录"、"登入"、"login"、"sign in"

**登录操作流程**（必须按顺序执行，不能跳过）：
1. **首先检查登录弹窗是否已打开**：查看是否有 "=== 🔐 登录弹窗内元素 ===" 分隔符
2. **检查登录模式**：
   - 如果提示"检测到密码，但当前是短信登录模式"，**必须先点击密码登录切换按钮**
   - 切换后才能输入账号密码
3. **如果弹窗已打开**：
   a. 【重要】如果需要密码登录但当前是短信模式，先点击"密码登录"切换按钮
   b. 找到用户名/手机号输入框，执行 type 操作输入账号
   c. 如果有"获取验证码"按钮，点击获取验证码
   d. 找到密码/验证码输入框，执行 type 操作输入密码/验证码
   e. 点击登录按钮
4. **如果弹窗未打开**：
   a. 找到"登录"或"请登录"按钮/链接
   b. 点击打开登录弹窗
   c. 等待弹窗加载后，按上述流程操作

**登录模式切换**：
- 某些网站（如京东）有"短信登录"和"密码登录"两种模式
- 如果用户提供了密码但当前是短信登录模式，**必须先切换到密码登录模式**
- 查找并点击"密码登录"标签/按钮进行切换
- 切换成功后再输入账号密码

**登录完成检测**：
- 登录成功后，登录弹窗通常会关闭或跳转页面
- 如果页面URL从登录页面（如 passport.jd.com）跳转到正常页面（如 www.jd.com），表示登录成功
- 登录成功后才能执行搜索等其他操作
- **在登录弹窗关闭之前，不要尝试搜索或其他操作！**

**登录注意事项**：
- 登录元素可能在 iframe 中，注意查看元素的 `frame` 属性
- 如果用户提供了账号密码，必须使用用户提供的账号密码
- 登录失败时，检查是否需要验证码，可能需要人工干预
- **不要尝试操作弹窗外的元素，它们被弹窗遮挡无法点击！**
- **登录完成前不要进行搜索等其他操作！**

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

**重要：邮件元素识别**：
- 带有 [邮件] 标记的元素是邮件相关功能，优先级较高
- 收件人输入框：text 包含"收件人"，class 包含 "editableAddr" 或 "recipient"
- 主题输入框：text 包含"主题"，name 或 id 包含 "subject"
- 正文编辑器：类型为 iframe，class 包含 "editor" 或 "APP-editor"
- **填写邮件时，请按顺序：收件人 → 主题 → 正文**

## 🚨 重要：任务完成检测

**在执行 done 操作前，必须确认任务已经真正完成！**

### 邮件发送任务完成标志：
- 页面显示"发送成功"、"已发送"、"发送完成"等提示
- 页面显示"已成功发送到收件人"等确认信息
- URL 变化：从写信页面跳转到收件箱或其他页面
- 发送按钮变为禁用状态或消失

### 检测任务完成的方法：
1. **查看页面文本**：搜索"成功"、"完成"、"已发送"等关键词
2. **检查 URL 变化**：任务完成后通常会跳转页面
3. **检查元素状态**：目标元素是否已填写、按钮是否已点击
4. **避免重复操作**：如果页面已显示成功提示，不要再执行相同操作

### 常见错误：
- ❌ 看到成功提示后仍继续填写表单
- ❌ 任务已完成但没有输出 done
- ❌ 没有确认成功就输出 done

**正确做法**：
1. 仔细检查页面是否显示成功提示
2. 确认目标操作已完成（如邮件已发送）
3. 然后输出 done 结束任务

**重要：邮件正文填写**：
- 邮件正文通常在 iframe 编辑器中，元素类型为 `iframe`
- 填写正文的正确方法：**直接对 iframe 元素执行 type 操作**，系统会自动处理
- 例如：发现 iframe 元素 [55] 是正文编辑器，执行 `{"action_type": "type", "target_id": 55, "value": "正文内容"}`
- **不要先 click 再 type**，直接对 iframe 执行 type 即可
- 如果 iframe 元素有 "editor" 或 "APP-editor" 等关键词，通常是正文编辑器

**重要：选择正确的输入框**：
- 页面上可能有多个输入框，必须选择正确的目标
- 使用元素的 text、placeholder、class、id 等属性来识别
- **特异性(specificity)分数越高，选择器越精确**
- 优先选择带有明确标识（如"收件人"、"主题"）的输入框
- 避免使用通用选择器（如 `.nui-ipt-input`）匹配的元素

## 搜索框识别指南
**电商网站（京东、淘宝等）搜索框特征**：
1. 通常位于页面顶部，靠近 Logo
2. class 或 id 包含 "search"、"keyword"、"query" 等关键词
3. 旁边有搜索按钮（🔍图标或"搜索"文字）
4. 元素标记为 [输入] 类型

**搜索操作建议**：
1. 先找到搜索输入框（带有 [输入] 标记且 class/id 包含搜索关键词）
2. 使用 type 操作输入搜索关键词
3. 使用 click 点击搜索按钮，或使用 press 操作按 Enter
4. 等待页面加载结果

## 截图信息利用
- 页面截图路径会显示在提示中
- 截图可用于确认页面布局和元素位置
- 如果元素列表中没有找到目标，考虑截图可能显示的内容

## 决策原则
1. **优先处理弹窗和登录界面**，不要忽略弹窗继续其他操作
2. 仔细分析用户目标和当前页面状态
3. 选择最合适的操作类型，不要只用 click 和 type
4. **填写表单前先检查 current_value，避免重复填写已有内容**
5. 表单填写后通常需要按 Enter 提交，使用 press 操作
6. 下拉菜单选项使用 select 操作
7. 需要触发悬停效果时使用 hover 操作
8. 如果遇到错误，尝试其他方法
9. **避免无意义的重复滚动**，如果多次滚动没有新元素出现，尝试其他操作
10. 确认任务完成后才输出 done
11. 每次只执行一个动作"""

VALID_ACTIONS = [
    "click", "double_click", "right_click", "hover", "drag",
    "type", "type_slowly", "press", "hotkey",
    "select", "check", "uncheck",
    "scroll", "scroll_to", "goto", "wait", "screenshot",
    "done"
]

# 操作所需参数配置
ACTION_REQUIREMENTS = {
    "click": {"requires_target": True, "requires_value": False},
    "double_click": {"requires_target": True, "requires_value": False},
    "right_click": {"requires_target": True, "requires_value": False},
    "hover": {"requires_target": True, "requires_value": False},
    "drag": {"requires_target": True, "requires_value": True},
    "type": {"requires_target": True, "requires_value": True},
    "type_slowly": {"requires_target": True, "requires_value": True},
    "press": {"requires_target": False, "requires_value": True},
    "hotkey": {"requires_target": False, "requires_value": True},
    "select": {"requires_target": True, "requires_value": True},
    "check": {"requires_target": True, "requires_value": False},
    "uncheck": {"requires_target": True, "requires_value": False},
    "scroll": {"requires_target": False, "requires_value": True},
    "scroll_to": {"requires_target": True, "requires_value": False},
    "goto": {"requires_target": False, "requires_value": True},
    "wait": {"requires_target": False, "requires_value": True},
    "screenshot": {"requires_target": False, "requires_value": False},
    "done": {"requires_target": False, "requires_value": False},
}


def validate_decision(decision: dict) -> tuple[bool, str]:
    """
    验证决策的完整性和有效性
    
    【设计思路】
    根据不同的操作类型，验证所需的参数是否完整。
    这可以提前发现无效决策，避免执行时出错。
    
    【参数】
    decision: 包含 action_type, target_id, value 的决策字典
    
    【返回值】
    tuple[bool, str]: (是否有效, 错误信息)
    """
    if not decision:
        return False, "决策为空"
    
    action_type = decision.get("action_type")
    
    if not action_type:
        return False, "缺少 action_type 字段"
    
    if action_type not in VALID_ACTIONS:
        return False, f"无效的操作类型: {action_type}，有效类型: {', '.join(VALID_ACTIONS)}"
    
    requirements = ACTION_REQUIREMENTS.get(action_type, {})
    target_id = decision.get("target_id")
    value = decision.get("value")
    
    if requirements.get("requires_target") and target_id is None:
        return False, f"操作 '{action_type}' 需要目标元素 ID (target_id)"
    
    if requirements.get("requires_value") and not value:
        return False, f"操作 '{action_type}' 需要参数值 (value)"
    
    if action_type == "goto":
        if not value or (not value.startswith("http") and not value.startswith("https")):
            if value and "." in value:
                pass
            else:
                return False, f"goto 操作需要有效的 URL，当前值: {value}"
    
    if action_type == "scroll":
        valid_scroll_patterns = ["up/", "down/", "left/", "right/", "top", "bottom"]
        if value:
            is_valid = any(value.startswith(p) for p in valid_scroll_patterns[:4]) or value in ["top", "bottom"]
            if not is_valid:
                return False, f"scroll 操作的 value 格式无效，应为 'direction/amount' 或 'top/bottom'，当前值: {value}"
    
    if action_type == "wait":
        if value:
            try:
                ms = int(value)
                if ms < 0 or ms > 60000:
                    return False, f"wait 操作的时间应在 0-60000 毫秒之间，当前值: {value}"
            except ValueError:
                return False, f"wait 操作的 value 应为数字（毫秒），当前值: {value}"
    
    if action_type == "press":
        valid_keys = ["Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowUp", "ArrowDown", 
                      "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown", "Space",
                      "Control", "Alt", "Shift", "Meta"]
        if value and value not in valid_keys and len(value) == 1:
            pass
        elif value and value not in valid_keys:
            return False, f"press 操作的按键值可能无效: {value}"
    
    return True, ""


def _extract_platform_from_url(url: str) -> str:
    """
    从 URL 中提取平台名称
    
    【参数】
    url: 页面 URL
    
    【返回值】
    平台名称
    """
    import re
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        
        domain = re.sub(r'^www\.', '', domain)
        
        domain_parts = domain.split('.')
        if domain_parts:
            platform = domain_parts[0]
        else:
            platform = domain
        
        platform_mapping = {
            'taobao': '淘宝',
            'tmall': '天猫',
            'jd': '京东',
            'baidu': '百度',
            'qq': 'QQ',
            'weixin': '微信',
            'weibo': '微博',
            'zhihu': '知乎',
            'bilibili': 'B站',
            'douyin': '抖音',
            'taobao': '淘宝',
            'alipay': '支付宝',
            '163': '163邮箱',
            '126': '126邮箱',
            'gmail': 'Google',
            'google': 'Google',
            'github': 'GitHub',
            'microsoft': 'Microsoft',
            'outlook': 'Outlook',
            'aliyun': '阿里云',
            'cloud': '云服务',
        }
        
        for key, value in platform_mapping.items():
            if key in platform.lower():
                return value
        
        return platform.capitalize() if platform else "未知平台"
        
    except Exception:
        return "未知平台"


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
        
        self.credential_manager: CredentialManager = None
        self._credential_logged_in: bool = False
        
        # 连接错误追踪（用于在多次连接错误后进行等待）
        self._consecutive_connection_errors: int = 0
        self._last_connection_error_time: float = 0
        self._connection_error_wait_until: float = 0
    
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
        
        def on_credential_login(params: dict) -> dict:
            if not HAS_CREDENTIAL_MANAGER:
                return {"message": "凭证管理模块不可用，请确保已安装 cryptography 库"}
            
            print("\n🔐 请输入凭证管理器主密码:")
            try:
                import getpass
                master_password = getpass.getpass("主密码: ")
                if self.login_credential_manager(master_password):
                    return {"message": "凭证管理器登录成功"}
                else:
                    return {"message": "凭证管理器登录失败"}
            except Exception as e:
                return {"message": f"登录失败: {e}"}
        
        def on_credential_add(params: dict) -> dict:
            if not self._credential_logged_in:
                return {"message": "请先使用 'cred_login' 登录凭证管理器"}
            
            try:
                print("\n📝 添加新账号凭证")
                platform = input("平台/服务名称: ").strip()
                username = input("用户名/账号: ").strip()
                
                import getpass
                password = getpass.getpass("密码: ")
                
                alias = input("别名（可选）: ").strip()
                notes = input("备注（可选）: ").strip()
                tags_str = input("标签（逗号分隔，可选）: ").strip()
                tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
                
                cred = self.credential_manager.add_credential(
                    platform=platform,
                    username=username,
                    password=password,
                    alias=alias,
                    notes=notes,
                    tags=tags
                )
                return {"message": f"凭证添加成功: {platform} - {username} (ID: {cred.id[:8]}...)"}
            except Exception as e:
                return {"message": f"添加凭证失败: {e}"}
        
        def on_credential_list(params: dict) -> dict:
            if not self._credential_logged_in:
                return {"message": "请先使用 'cred_login' 登录凭证管理器"}
            
            try:
                creds = self.credential_manager.list_all_credentials()
                if not creds:
                    return {"message": "暂无保存的凭证"}
                
                msg = f"\n📋 已保存 {len(creds)} 条凭证:\n"
                for cred in creds:
                    msg += f"  - [{cred['id'][:8]}] {cred['platform']}: {cred['username']}"
                    if cred.get('alias'):
                        msg += f" ({cred['alias']})"
                    msg += "\n"
                return {"message": msg}
            except Exception as e:
                return {"message": f"获取凭证列表失败: {e}"}
        
        def on_credential_search(params: dict) -> dict:
            if not self._credential_logged_in:
                return {"message": "请先使用 'cred_login' 登录凭证管理器"}
            
            try:
                keyword = params.get("value", "")
                if not keyword:
                    keyword = input("搜索关键词: ").strip()
                
                creds = self.credential_manager.search_credentials(keyword=keyword)
                if not creds:
                    return {"message": f"未找到匹配 '{keyword}' 的凭证"}
                
                msg = f"\n🔍 找到 {len(creds)} 条匹配凭证:\n"
                for cred in creds:
                    msg += f"  - [{cred['id'][:8]}] {cred['platform']}: {cred['username']}\n"
                return {"message": msg}
            except Exception as e:
                return {"message": f"搜索凭证失败: {e}"}
        
        def on_credential_delete(params: dict) -> dict:
            if not self._credential_logged_in:
                return {"message": "请先使用 'cred_login' 登录凭证管理器"}
            
            try:
                cred_id = params.get("value", "")
                if not cred_id:
                    cred_id = input("要删除的凭证ID: ").strip()
                
                confirm = input(f"确认删除凭证 {cred_id}? (y/n): ").strip().lower()
                if confirm != 'y':
                    return {"message": "已取消删除"}
                
                self.credential_manager.delete_credential(cred_id)
                return {"message": f"凭证 {cred_id} 已删除"}
            except Exception as e:
                return {"message": f"删除凭证失败: {e}"}
        
        def on_credential_status(params: dict) -> dict:
            status = self.get_credential_status()
            if not status.get("available"):
                return {"message": f"凭证管理器不可用: {status.get('reason', '未知原因')}"}
            
            msg = f"\n🔐 凭证管理器状态:\n"
            msg += f"  - 已登录: {'是' if status.get('logged_in') else '否'}\n"
            msg += f"  - 凭证数量: {status.get('credential_count', 0)}\n"
            msg += f"  - 平台数量: {status.get('platform_count', 0)}\n"
            return {"message": msg}
        
        def on_model_switch(params: dict) -> dict:
            if not HAS_MODEL_MANAGER:
                return {"message": "模型管理模块不可用"}
            
            model_manager = get_model_manager()
            if not model_manager:
                return {"message": "模型管理器未初始化"}
            
            model_id = params.get("value", "")
            if not model_id:
                return {"message": "请指定模型ID，例如: switch gemini-3-flash-preview"}
            
            if model_manager.switch_model(model_id):
                return {"message": f"模型已切换到: {model_id}"}
            else:
                return {"message": f"模型切换失败，可用模型: {', '.join(model_manager.get_available_models().keys())}"}
        
        def on_model_list(params: dict) -> dict:
            if not HAS_MODEL_MANAGER:
                return {"message": "模型管理模块不可用"}
            
            model_manager = get_model_manager()
            if not model_manager:
                return {"message": "模型管理器未初始化"}
            
            return {"message": model_manager.list_models()}
        
        def on_model_status(params: dict) -> dict:
            if not HAS_MODEL_MANAGER:
                return {"message": "模型管理模块不可用"}
            
            model_manager = get_model_manager()
            if not model_manager:
                return {"message": "模型管理器未初始化"}
            
            return {"message": model_manager.get_status_display()}
        
        self.user_interaction.register_callback(UserCommand.EXTEND_STEPS, on_extend_steps)
        self.user_interaction.register_callback(UserCommand.REDUCE_STEPS, on_reduce_steps)
        self.user_interaction.register_callback(UserCommand.SHOW_STATUS, on_show_status)
        self.user_interaction.register_callback(UserCommand.SAVE_CHECKPOINT, on_save_checkpoint)
        self.user_interaction.register_callback(UserCommand.LOAD_CHECKPOINT, on_load_checkpoint)
        self.user_interaction.register_callback(UserCommand.SET_TIMEOUT, on_set_timeout)
        self.user_interaction.register_callback(UserCommand.ABORT, on_abort)
        self.user_interaction.register_callback(UserCommand.INTERVENE, on_intervene)
        self.user_interaction.register_callback(UserCommand.FAST_MODE, on_fast_mode)
        self.user_interaction.register_callback(UserCommand.CREDENTIAL_LOGIN, on_credential_login)
        self.user_interaction.register_callback(UserCommand.CREDENTIAL_ADD, on_credential_add)
        self.user_interaction.register_callback(UserCommand.CREDENTIAL_LIST, on_credential_list)
        self.user_interaction.register_callback(UserCommand.CREDENTIAL_SEARCH, on_credential_search)
        self.user_interaction.register_callback(UserCommand.CREDENTIAL_DELETE, on_credential_delete)
        self.user_interaction.register_callback(UserCommand.CREDENTIAL_STATUS, on_credential_status)
        self.user_interaction.register_callback(UserCommand.MODEL_SWITCH, on_model_switch)
        self.user_interaction.register_callback(UserCommand.MODEL_LIST, on_model_list)
        self.user_interaction.register_callback(UserCommand.MODEL_STATUS, on_model_status)
    
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
        if self.credential_manager and self._credential_logged_in:
            self.credential_manager.logout()
    
    def init_credential_manager(self) -> bool:
        """
        初始化凭证管理器
        
        【返回值】
        bool: 是否成功初始化
        """
        if not HAS_CREDENTIAL_MANAGER:
            print("⚠️ 凭证管理模块不可用")
            return False
        
        if self.credential_manager is not None:
            return True
        
        try:
            self.credential_manager = CredentialManager()
            return True
        except Exception as e:
            print(f"⚠️ 初始化凭证管理器失败: {e}")
            return False
    
    def login_credential_manager(self, master_password: str) -> bool:
        """
        登录凭证管理器
        
        【参数】
        master_password: 主密码
        
        【返回值】
        bool: 是否登录成功
        """
        if not self.init_credential_manager():
            return False
        
        try:
            if not self.credential_manager.is_setup_complete():
                print("🔐 首次使用凭证管理器，正在初始化...")
                self.credential_manager.setup(master_password)
                print("✅ 凭证管理器初始化成功")
            else:
                self.credential_manager.login(master_password)
            
            self._credential_logged_in = True
            return True
        except AuthenticationError as e:
            print(f"❌ 凭证管理器认证失败: {e}")
            return False
        except Exception as e:
            print(f"❌ 凭证管理器登录失败: {e}")
            return False
    
    def get_credential_for_platform(self, platform: str) -> Optional[Dict[str, str]]:
        """
        获取指定平台的凭证（用于自动填充）
        
        【参数】
        platform: 平台名称
        
        【返回值】
        包含用户名和密码的字典，未找到返回 None
        """
        if not self._credential_logged_in or self.credential_manager is None:
            return None
        
        try:
            cred = self.credential_manager.auto_fill_for_platform(platform)
            if cred:
                print(f"🔐 已从凭证库获取 {platform} 的账号信息")
                return cred
        except Exception as e:
            print(f"⚠️ 获取凭证失败: {e}")
        
        return None
    
    def get_credential_status(self) -> Dict[str, Any]:
        """
        获取凭证管理器状态
        
        【返回值】
        状态信息字典
        """
        if not HAS_CREDENTIAL_MANAGER:
            return {"available": False, "reason": "模块未安装"}
        
        if self.credential_manager is None:
            return {"available": False, "reason": "未初始化"}
        
        status = self.credential_manager.get_status()
        status["logged_in"] = self._credential_logged_in
        return status
    
    def record_connection_error(self) -> float:
        """
        记录连接错误，返回需要等待的时间（秒）
        
        【设计思路】
        当连续出现连接错误时，采用渐进式等待策略：
        - 第1次错误：等待 2 秒
        - 连续2次错误：等待 5 秒
        - 连续3次错误：等待 10 秒
        - 连续4次及以上：等待 15 秒
        
        【返回值】
        float: 需要等待的秒数
        """
        current_time = time.time()
        
        # 如果距离上次错误超过 30 秒，重置计数（说明连接已恢复）
        if current_time - self._last_connection_error_time > 30:
            self._consecutive_connection_errors = 0
        
        self._consecutive_connection_errors += 1
        self._last_connection_error_time = current_time
        
        # 计算等待时间（渐进式）
        # 连续次数 -> 等待秒数
        wait_times = {
            1: 2,   # 第1次：2秒
            2: 5,   # 连续2次：5秒
            3: 10,  # 连续3次：10秒
        }
        # 连续4次及以上：15秒
        wait_seconds = wait_times.get(self._consecutive_connection_errors, 15)
        
        # 设置等待截止时间
        self._connection_error_wait_until = current_time + wait_seconds
        
        return wait_seconds
    
    def should_wait_for_connection(self) -> tuple[bool, float]:
        """
        检查是否需要等待连接恢复
        
        【返回值】
        tuple[bool, float]: (是否需要等待, 剩余等待秒数)
        """
        current_time = time.time()
        
        if current_time < self._connection_error_wait_until:
            remaining = self._connection_error_wait_until - current_time
            return True, remaining
        
        return False, 0
    
    def reset_connection_error_count(self):
        """
        重置连接错误计数（在成功连接后调用）
        """
        self._consecutive_connection_errors = 0
        self._connection_error_wait_until = 0


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
    _perf_start = time.perf_counter()
    
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
            "iframe#login2025-content",
            "iframe[id*='Login']",
            "iframe[id*='popup']",
            "iframe[class*='login']",
            "iframe[class*='dialog']"
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
    
    def check_login_popup_exists(page: Page) -> bool:
        """
        检查页面是否存在登录弹窗（不等待，立即检查）
        
        【设计思路】
        某些网站（如京东）在页面加载时会自动弹出登录弹窗，
        需要主动检测是否存在登录弹窗。
        
        【参数】
        page: Playwright 页面对象
        
        【返回值】
        bool: 是否存在登录弹窗
        """
        login_popup_selectors = [
            "iframe#login2025-content",
            "iframe[id*='login']",
            "iframe[src*='passport']",
            "div[id*='login-dialog']",
            "div[class*='login-popup']",
            "div[class*='login-modal']",
            "#login-dialog-wrap"
        ]
        
        for selector in login_popup_selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=200):
                    print(f"   🔍 检测到登录弹窗元素: {selector}")
                    return True
            except Exception:
                continue
        
        return False
    
    login_popup_exists = check_login_popup_exists(page)
    if login_popup_exists:
        print("   ⏳ 检测到登录弹窗，等待加载...")
        wait_for_popup_iframe(page, timeout=3000)
    
    last_history = state.get("history", [])[-1] if state.get("history") else None
    if last_history and last_history.get("action_type") == "click":
        target_text = ""
        target_id = last_history.get("target_id")
        if target_id:
            target_id_int = int(target_id) if isinstance(target_id, (int, float, str)) and str(target_id).isdigit() else target_id
            prev_elements = state.get("elements_dict", {})
            if target_id_int in prev_elements:
                target_text = prev_elements[target_id_int].get("text", "").lower()
        
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
    
    # 需要人工干预的标记
    need_manual_intervention = False
    manual_intervention_reason = []
    captcha_detected = False
    sms_code_input_detected = False
    
    # 检测遮罩层（mask）- 新增功能
    # 遮罩层通常表示有弹窗显示
    mask_detected = False
    mask_selector = None
    
    # 查找所有可能的遮罩层
    mask_selectors = [
        "div.nui-mask", 
        ".nui-mask", 
        "div[class*='mask']", 
        "div[class*='overlay']",
        "div[class*='modal-backdrop']",
        "div.js-component-component.nui-mask"
    ]
    
    for selector in mask_selectors:
        try:
            mask_elements = soup.select(selector)
            if mask_elements:
                # 检查遮罩层是否可见
                for mask in mask_elements:
                    style = mask.get('style', '')
                    if 'display: none' not in style and 'visibility: hidden' not in style:
                        mask_detected = True
                        mask_selector = selector
                        popup_detected = True  # 遮罩层存在表示有弹窗
                        print(f"   🚨 检测到遮罩层: {selector}")
                        break
                if mask_detected:
                    break
        except Exception:
            continue
    
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
    
    def is_captcha_element(element: Tag, element_text: str, placeholder: str) -> bool:
        """
        判断元素是否是验证码相关元素（需要人工干预）
        
        包括：
        - 图形验证码输入框
        - 滑块验证
        - 短信验证码输入框（需要用户手动输入）
        """
        captcha_keywords = [
            '验证码', 'captcha', 'verify', 'verification',
            '图形验证', '滑块', '拖动', '拖拽',
            '安全验证', '人机验证', '身份验证'
        ]
        
        # 检查文本
        if element_text:
            for kw in captcha_keywords:
                if kw.lower() in element_text.lower():
                    return True
        
        # 检查placeholder
        if placeholder:
            for kw in captcha_keywords:
                if kw.lower() in placeholder.lower():
                    return True
        
        # 检查class和id属性
        for attr in ['id', 'class', 'name']:
            attr_val = element.get(attr, '')
            if isinstance(attr_val, list):
                attr_val = ' '.join(attr_val)
            if attr_val:
                for kw in captcha_keywords:
                    if kw.lower() in attr_val.lower():
                        return True
        
        return False
    
    def is_sms_code_input(element: Tag, element_text: str, placeholder: str) -> bool:
        """
        判断元素是否是短信验证码输入框（需要用户手动输入验证码）
        """
        sms_keywords = ['短信验证码', '手机验证码', 'sms code', '短信码', '验证码']
        
        # 检查placeholder
        if placeholder:
            for kw in sms_keywords:
                if kw.lower() in placeholder.lower():
                    return True
        
        # 检查文本
        if element_text:
            for kw in sms_keywords:
                if kw.lower() in element_text.lower():
                    return True
        
        return False
    
    def is_email_recipient_input(element: Tag, element_text: str, placeholder: str) -> bool:
        """
        判断元素是否是邮件收件人输入框
        
        【识别策略】
        1. text 或 placeholder 包含"收件人"关键词
        2. class 属性包含 "editableAddr" 或 "recipient" 等关键词
        3. role 属性为 combobox 且与收件人相关
        """
        recipient_keywords = ['收件人', 'recipient', 'to:', '发送给']
        
        combined_text = f"{element_text} {placeholder}".lower()
        for kw in recipient_keywords:
            if kw.lower() in combined_text:
                return True
        
        class_attr = element.get('class', '')
        if isinstance(class_attr, list):
            class_attr = ' '.join(class_attr)
        if class_attr:
            class_keywords = ['editableAddr', 'recipient', 'nui-editableAddr', 'js-component-email']
            for kw in class_keywords:
                if kw.lower() in class_attr.lower():
                    return True
        
        role = element.get('role', '')
        if role == 'combobox':
            name_attr = element.get('name', '')
            id_attr = element.get('id', '')
            if any(kw in (name_attr + id_attr).lower() for kw in ['to', 'recipient', '收件人']):
                return True
        
        return False
    
    def is_email_subject_input(element: Tag, element_text: str, placeholder: str) -> bool:
        """
        判断元素是否是邮件主题输入框
        
        【识别策略】
        1. text 或 placeholder 包含"主题"关键词
        2. name 属性包含 "subject"
        3. id 属性包含 "subject" 或 "theme"
        """
        subject_keywords = ['主题', 'subject', 'title', '标题']
        
        combined_text = f"{element_text} {placeholder}".lower()
        for kw in subject_keywords:
            if kw.lower() in combined_text:
                return True
        
        name_attr = element.get('name', '').lower()
        id_attr = element.get('id', '').lower()
        
        if 'subject' in name_attr or 'subject' in id_attr:
            return True
        if 'theme' in name_attr or 'theme' in id_attr:
            return True
        
        return False
    
    def is_email_editor_iframe(element: Tag) -> bool:
        """
        判断元素是否是邮件正文编辑器 iframe
        
        【识别策略】
        1. class 属性包含 "editor" 或 "APP-editor"
        2. id 属性包含 "editor"
        3. 是 iframe 元素且与编辑相关
        """
        if element.name != 'iframe':
            return False
        
        class_attr = element.get('class', '')
        if isinstance(class_attr, list):
            class_attr = ' '.join(class_attr)
        
        editor_keywords = ['editor', 'APP-editor', 'compose', 'content-editable']
        
        for kw in editor_keywords:
            if kw.lower() in class_attr.lower():
                return True
        
        id_attr = element.get('id', '').lower()
        for kw in editor_keywords:
            if kw.lower() in id_attr:
                return True
        
        return False
    
    def get_element_specificity(selector: str, element: Tag) -> int:
        """
        计算元素选择器的特异性分数
        
        【设计思路】
        特异性越高，选择器越精确，越不容易选错元素。
        - ID 选择器 (#id): 100 分
        - 带属性的选择器 ([attr=value]): 50 分
        - class 选择器 (.class): 10 分
        - 通用选择器 (input, div): 1 分
        
        【返回值】
        int: 特异性分数，越高越好
        """
        score = 0
        
        if selector.startswith('#'):
            score += 100
        elif '[' in selector and '=' in selector:
            score += 50
        elif selector.startswith('.'):
            parts = selector.split('.')
            score += len(parts) * 10
        else:
            score += 1
        
        id_attr = element.get('id', '')
        if id_attr and len(id_attr) > 5:
            score += 50
        
        class_attr = element.get('class', '')
        if isinstance(class_attr, list):
            class_attr = ' '.join(class_attr)
        if class_attr and len(class_attr) > 10:
            score += 20
        
        return score
    
    def is_element_likely_in_popup(element: Tag) -> bool:
        """
        判断元素是否可能在弹窗内
        【策略】
        1. 检查元素的 class/id 是否包含弹窗相关关键词
        2. 检查父元素是否有弹窗相关特征
        3. 检查元素文本是否包含确认、取消、确定等弹窗常见按钮文字
        """
        # 弹窗相关关键词
        popup_keywords = [
            'popup', 'modal', 'dialog', 'confirm', 'alert', 
            '提示', '确认', '确定', '取消', '关闭',
            'nui-dialog', 'nui-pop', 'nui-layer'
        ]
        
        # 检查元素本身的属性
        element_id = element.get('id', '').lower()
        element_class = element.get('class', [])
        if isinstance(element_class, list):
            element_class_str = ' '.join(element_class).lower()
        else:
            element_class_str = str(element_class).lower()
        
        for kw in popup_keywords:
            if kw in element_id or kw in element_class_str:
                return True
        
        # 检查元素文本是否是弹窗常见按钮
        element_text = element.get_text(strip=True).lower()
        popup_button_texts = ['确定', '取消', '关闭', '确认', 'ok', 'cancel', 'close', 'yes', 'no']
        if element_text in popup_button_texts:
            return True
        
        # 检查父元素（最多检查3层）
        parent = element.parent
        for _ in range(3):
            if parent is None or parent.name is None:
                break
            parent_id = parent.get('id', '').lower()
            parent_class = parent.get('class', [])
            if isinstance(parent_class, list):
                parent_class_str = ' '.join(parent_class).lower()
            else:
                parent_class_str = str(parent_class).lower()
            
            for kw in popup_keywords:
                if kw in parent_id or kw in parent_class_str:
                    return True
            parent = parent.parent
        
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
        获取输入框的当前实际值（通过 Playwright 动态获取）- 性能优化版
        
        【设计思路】
        HTML 中的 value 属性只反映初始值，不反映用户输入后的值。
        需要通过 Playwright 的 input_value() 方法获取实际值。
        优化：使用更短的超时和更快的获取策略。
        
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
            
            if locator.is_visible(timeout=200):
                current_value = locator.input_value(timeout=200)
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
        6. 搜索框相关元素（京东、淘宝等电商网站）
        7. contenteditable 元素（富文本编辑器）
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
        
        # 检测 contenteditable 元素（富文本编辑器、搜索框等）
        if element.get('contenteditable') == 'true':
            return True, 'input'
        
        if element.get('onclick') or element.get('ng-click') or element.get('@click'):
            return True, 'click'
        
        role = element.get('role', '')
        if role in ['button', 'link', 'tab', 'menuitem', 'option', 'checkbox', 'radio', 'searchbox', 'textbox']:
            if role == 'searchbox':
                return True, 'input'
            return True, 'click'
        
        if element.get('tabindex'):
            return True, 'click'
        
        class_attr = element.get('class', [])
        if isinstance(class_attr, str):
            class_attr = class_attr.split()
        
        # 点击类关键词
        click_keywords = ['btn', 'button', 'click', 'link', 'nav', 'menu', 'action']
        for cls in class_attr:
            cls_lower = cls.lower()
            for keyword in click_keywords:
                if keyword in cls_lower:
                    return True, 'click'
        
        # 搜索框相关关键词（电商网站常用）
        search_keywords = [
            'search', 'searchbox', 'search-input', 'search-box',
            'searchbar', 'search-bar', 'search-input',
            'keyword', 'key-word',  # 京东搜索框常用
            'query', 'q-input',
            'header-search', 'top-search', 'nav-search',
            's-combobox-input',  # 淘宝搜索
            'textbox', 'text-box'
        ]
        for cls in class_attr:
            cls_lower = cls.lower()
            for keyword in search_keywords:
                if keyword in cls_lower:
                    return True, 'input'
        
        # 检测 id/name/placeholder 中包含搜索关键词的元素
        for attr in ['id', 'name', 'placeholder']:
            attr_val = element.get(attr, '')
            if attr_val:
                attr_lower = attr_val.lower()
                if any(kw in attr_lower for kw in ['搜索', 'search', 'keyword', '关键词']):
                    return True, 'input'
        
        return False, ''
    
    def check_element_visibility_batch(page: Page, elements_to_check: List[Tuple[Tag, str, str, dict]], 
                                        timeout: int = 300) -> Dict[str, bool]:
        """
        批量检查元素可见性（性能优化版v2）
        
        【设计思路】
        1. 使用单次JavaScript调用批量获取所有主页面元素可见性
        2. 使用缓存避免重复检查相同选择器
        3. 并行处理iframe元素检查
        4. 使用更高效的选择器验证策略
        
        【参数】
        page: Playwright 页面对象
        elements_to_check: 待检查的元素列表 [(element, selector, xpath, frame_info), ...]
        timeout: 单个元素检查超时时间（毫秒）
        
        【返回值】
        Dict[str, bool]: selector -> is_visible 的映射
        """
        visibility_map = {}
        selector_cache = get_selector_cache()
        
        main_page_elements = []
        iframe_elements = []
        
        for element, selector, xpath, frame_info in elements_to_check:
            if frame_info:
                iframe_elements.append((element, selector, xpath, frame_info))
            else:
                cached = selector_cache.get_selector_visibility(selector)
                if cached is not None:
                    visibility_map[selector] = cached
                else:
                    main_page_elements.append((element, selector, xpath))
        
        if main_page_elements:
            try:
                selectors_js = [sel for _, sel, _ in main_page_elements]
                js_code = """
                (selectors) => {
                    const results = {};
                    const len = selectors.length;
                    for (let i = 0; i < len; i++) {
                        const sel = selectors[i];
                        try {
                            const el = document.querySelector(sel);
                            if (el) {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    const style = window.getComputedStyle(el);
                                    results[sel] = style.display !== 'none' && 
                                                   style.visibility !== 'hidden' &&
                                                   parseFloat(style.opacity) > 0;
                                } else {
                                    results[sel] = false;
                                }
                            } else {
                                results[sel] = false;
                            }
                        } catch(e) {
                            results[sel] = false;
                        }
                    }
                    return results;
                }
                """
                js_results = page.evaluate(js_code, selectors_js)
                visibility_map.update(js_results)
                
                for selector, is_visible in js_results.items():
                    selector_cache.set_selector_visibility(selector, is_visible)
                    
            except Exception:
                for element, selector, xpath in main_page_elements:
                    try:
                        locator = page.locator(selector).first
                        is_visible = locator.is_visible(timeout=timeout)
                        visibility_map[selector] = is_visible
                        selector_cache.set_selector_visibility(selector, is_visible)
                    except Exception:
                        visibility_map[selector] = False
        
        if iframe_elements:
            for element, selector, xpath, frame_info in iframe_elements:
                frame_selector = frame_info.get('frame_selector')
                if not frame_selector:
                    visibility_map[selector] = False
                    continue
                try:
                    frame = page.frame_locator(frame_selector)
                    locator = frame.locator(selector).first
                    visibility_map[selector] = locator.is_visible(timeout=timeout)
                except Exception:
                    visibility_map[selector] = False
        
        return visibility_map

    def extract_elements_from_soup(soup_obj: BeautifulSoup, frame_info: dict = None):
        """
        从 BeautifulSoup 对象中提取可交互元素
        
        【参数】
        soup_obj: BeautifulSoup 解析对象
        frame_info: iframe 信息（可选），包含 frame_name 或 frame_url
        """
        nonlocal element_id
        
        all_tags = soup_obj.find_all(True)
        
        elements_to_check = []
        element_data_map = {}
        
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
            
            elements_to_check.append((element, selector, xpath, frame_info))
            element_data_map[selector] = {
                'element': element,
                'selector_key': selector_key,
                'element_id_attr': element_id_attr,
                'element_name': element_name,
                'element_type': element_type,
                'interaction_type': interaction_type
            }
        
        visibility_map = check_element_visibility_batch(page, elements_to_check, timeout=300)
        
        for element, selector, xpath, frame_info in elements_to_check:
            is_visible = visibility_map.get(selector, False)
            
            if not is_visible:
                continue
            
            data = element_data_map[selector]
            selector_key = data['selector_key']
            element_id_attr = data['element_id_attr']
            element_name = data['element_name']
            element_type = data['element_type']
            interaction_type = data['interaction_type']
            
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
            
            nonlocal popup_detected, login_form_detected, login_elements, mask_detected
            
            # 如果检测到遮罩层，检查元素是否可能在弹窗内
            if mask_detected:
                if is_element_likely_in_popup(element):
                    priority = "high"
                    popup_detected = True
                    print(f"   🔔 检测到弹窗内元素: {selector}")
            
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
            
            # 检测验证码元素（需要人工干预）
            if is_input and is_captcha_element(element, element_text, placeholder):
                captcha_detected = True
                need_manual_intervention = True
                if "图形验证码" not in manual_intervention_reason:
                    manual_intervention_reason.append("图形验证码")
                print(f"   🔐 检测到验证码元素: {selector}")
            
            # 检测短信验证码输入框（需要用户手动输入）
            if is_input and is_sms_code_input(element, element_text, placeholder):
                sms_code_input_detected = True
                need_manual_intervention = True
                if "短信验证码" not in manual_intervention_reason:
                    manual_intervention_reason.append("短信验证码")
                print(f"   📱 检测到短信验证码输入框: {selector}")
            
            is_email_element = False
            email_element_type = None
            
            if is_input:
                if is_email_recipient_input(element, element_text, placeholder):
                    is_email_element = True
                    email_element_type = "recipient"
                    priority = "high"
                    print(f"   📧 检测到收件人输入框: {selector}")
                elif is_email_subject_input(element, element_text, placeholder):
                    is_email_element = True
                    email_element_type = "subject"
                    priority = "high"
                    print(f"   📧 检测到主题输入框: {selector}")
            
            if is_email_editor_iframe(element):
                is_email_element = True
                email_element_type = "body_editor"
                is_input = True
                is_clickable = True
                priority = "high"
                print(f"   📧 检测到邮件正文编辑器: {selector}")
            
            specificity_score = get_element_specificity(selector, element)
            
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
                "login_element_type": login_element_type,
                "is_email_element": is_email_element,
                "email_element_type": email_element_type,
                "specificity": specificity_score
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
    
    # 智能截图：只在需要时截图
    screenshot_path = None
    should_screenshot = False
    screenshot_reason = ""
    
    # 获取历史记录
    history = state.get("history", [])
    last_action = history[-1] if history else None
    
    # 计算连续滚动次数（检测是否在盲目滚动寻找元素）
    consecutive_scrolls = 0
    for h in reversed(history[-5:]):
        if h.get("action_type") == "scroll":
            consecutive_scrolls += 1
        else:
            break
    
    # 截图触发条件：
    # 1. 首次加载页面（没有历史记录）
    if not history:
        should_screenshot = True
        screenshot_reason = "首次加载页面"
    
    # 2. 检测到弹窗/登录表单
    elif popup_detected or login_form_detected:
        should_screenshot = True
        screenshot_reason = "检测到弹窗/登录表单"
    
    # 3. 上一步是 click 操作（页面可能发生变化）
    elif last_action and last_action.get("action_type") == "click":
        should_screenshot = True
        screenshot_reason = "点击操作后页面可能变化"
    
    # 4. 用户明确请求截图
    elif last_action and last_action.get("action_type") == "screenshot":
        should_screenshot = True
        screenshot_reason = "用户请求截图"
    
    # 5. 发生错误后
    elif state.get("error_message"):
        should_screenshot = True
        screenshot_reason = "发生错误后记录现场"
    
    # 6. 连续滚动2次以上（可能在寻找元素，需要截图辅助）
    elif consecutive_scrolls >= 2:
        should_screenshot = True
        screenshot_reason = f"连续滚动{consecutive_scrolls}次未找到目标"
    
    # 7. 停滞计数增加（任务进度停滞）
    elif state.get("stagnation_count", 0) > 0 and state.get("stagnation_count", 0) % 2 == 0:
        # 每隔2次停滞截图一次
        should_screenshot = True
        screenshot_reason = f"任务停滞({state.get('stagnation_count')}次)"
    
    # 8. 上一步是 goto 操作（新页面）
    elif last_action and last_action.get("action_type") == "goto":
        should_screenshot = True
        screenshot_reason = "导航到新页面"
    
    # 9. 上一步是 type 操作（验证输入是否正确）
    elif last_action and last_action.get("action_type") in ["type", "type_slowly"]:
        should_screenshot = True
        screenshot_reason = "输入操作后验证结果"
    
    if should_screenshot:
        try:
            import os
            from datetime import datetime
            screenshot_dir = "screenshots"
            if not os.path.exists(screenshot_dir):
                os.makedirs(screenshot_dir)
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp_str}.png"
            screenshot_path = os.path.join(screenshot_dir, filename)
            page.screenshot(path=screenshot_path)
            print(f"   📸 截图 ({screenshot_reason}): {filename}")
        except Exception as e:
            print(f"   ⚠️ 截图失败: {e}")
    else:
        # 复用上一次的截图路径（如果有）
        screenshot_path = state.get("screenshot_path")
    
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
    
    _perf_duration = (time.perf_counter() - _perf_start) * 1000
    get_performance_monitor().record("perception", _perf_duration, {"elements": len(elements_dict)})
    
    return {
        "elements_dict": elements_dict,
        "current_url": current_url,
        "error_message": None,
        "max_steps": context.step_manager.current_max_steps,
        "popup_detected": popup_detected,
        "mask_detected": mask_detected,
        "login_form_detected": login_form_detected,
        "login_elements": login_elements,
        "screenshot_path": screenshot_path,
        "consecutive_scrolls": consecutive_scrolls,
        "need_manual_intervention": need_manual_intervention,
        "manual_intervention_reason": manual_intervention_reason,
        "captcha_detected": captcha_detected,
        "sms_code_input_detected": sms_code_input_detected,
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
    _perf_start = time.perf_counter()
    
    context.process_user_commands()
    context.user_interaction.wait_if_paused()
    
    # 检查是否需要人工干预
    need_manual_intervention = state.get("need_manual_intervention", False)
    manual_intervention_reason = state.get("manual_intervention_reason", [])
    captcha_detected = state.get("captcha_detected", False)
    sms_code_input_detected = state.get("sms_code_input_detected", False)
    
    if need_manual_intervention:
        print("\n" + "="*60)
        print("⚠️  检测到需要人工干预的情况！")
        print("="*60)
        
        if captcha_detected:
            print("🔐 检测到验证码元素，需要您手动完成验证")
        if sms_code_input_detected:
            print("📱 检测到短信验证码输入框，需要您手动输入验证码")
        
        print(f"\n📋 需要人工处理的原因: {', '.join(manual_intervention_reason)}")
        print("\n💡 请在浏览器中完成以下操作：")
        print("   1. 完成图形验证码/滑块验证")
        print("   2. 输入短信验证码")
        print("   3. 或其他需要人工处理的操作")
        print("\n⏳ 完成后请按 Enter 键继续...")
        
        try:
            input()
            print("✅ 用户已确认，继续执行任务...")
        except KeyboardInterrupt:
            print("\n🛑 用户请求终止任务")
            return {
                "history": state["history"],
                "error_message": "用户终止任务",
                "is_done": True,
                "termination_reason": "user_abort"
            }
        
        # 重置标记
        need_manual_intervention = False
        manual_intervention_reason = []
    
    # 检查进度停滞是否达到阈值
    stagnation_count = state.get("stagnation_count", 0)
    stagnation_threshold = state.get("adjusted_stagnation_threshold", 5)
    
    if stagnation_count >= stagnation_threshold:
        print("\n" + "="*60)
        print("⚠️  检测到任务进度停滞！")
        print("="*60)
        print(f"📊 停滞计数: {stagnation_count}/{stagnation_threshold}")
        print(f"📋 任务目标: {state.get('objective', '未知')}")
        print(f"🌐 当前页面: {state.get('current_url', '未知')}")
        print("\n💡 可能的原因：")
        print("   1. 页面加载缓慢或网络问题")
        print("   2. 需要登录或验证码")
        print("   3. 页面结构与预期不符")
        print("   4. 任务目标需要更多步骤")
        print("\n🔧 建议操作：")
        print("   1. 检查浏览器页面状态")
        print("   2. 手动完成需要登录/验证的步骤")
        print("   3. 调整任务目标或提供更多信息")
        print("   4. 输入 'continue' 继续执行")
        print("\n⏳ 处理完成后请按 Enter 键继续...")
        
        try:
            user_input = input()
            if user_input.lower() in ['exit', 'quit', 'abort']:
                print("🛑 用户请求终止任务")
                return {
                    "history": state["history"],
                    "error_message": "用户终止任务",
                    "is_done": True,
                    "termination_reason": "user_abort"
                }
            print("✅ 用户确认继续，重置停滞计数...")
        except KeyboardInterrupt:
            print("\n🛑 用户请求终止任务")
            return {
                "history": state["history"],
                "error_message": "用户终止任务",
                "is_done": True,
                "termination_reason": "user_abort"
            }
        
        # 重置停滞计数
        stagnation_count = 0
        # 立即更新状态中的停滞计数
        state = {**state, "stagnation_count": 0}
        # 同时重置评估器中的停滞计数
        context.completion_evaluator.stagnation_count = 0
    
    need_wait, remaining_wait = context.should_wait_for_connection()
    if need_wait:
        print(f"⏳ 连接错误恢复中，等待 {remaining_wait:.1f} 秒后重试...")
        wait_start = time.time()
        while time.time() - wait_start < remaining_wait:
            context.process_user_commands()
            
            if context.user_interaction.is_aborted():
                return {
                    "history": state["history"],
                    "error_message": "用户终止任务",
                    "is_done": True,
                    "termination_reason": "user_abort"
                }
            
            time.sleep(0.5)
        print("⏳ 等待完成，继续尝试...")
    
    output_handler = get_output_handler()
    
    popup_detected = state.get("popup_detected", False)
    mask_detected = state.get("mask_detected", False)
    login_form_detected = state.get("login_form_detected", False)
    login_elements = state.get("login_elements", {})
    consecutive_scrolls = state.get("consecutive_scrolls", 0)
    
    MAX_ELEMENTS = 50
    MAX_OTHER_ELEMENTS = 30
    
    login_elements_list = []
    other_elements_list = []
    
    for eid, info in state["elements_dict"].items():
        if len(login_elements_list) + len(other_elements_list) >= MAX_ELEMENTS:
            break
        
        text = (info['text'][:50] if info['text'] else info.get('placeholder', '[无文本]')[:30]) if info.get('text') or info.get('placeholder') else '[无文本]'
        
        flags = []
        if info.get('is_input'): flags.append("输入")
        if info.get('is_clickable'): flags.append("点击")
        if info.get('is_selectable'): flags.append("选择")
        if info.get('frame'): flags.append("弹窗")
        if info.get('is_login_element'): flags.append("登录")
        if info.get('is_email_element'): flags.append("邮件")
        flag_str = f"[{','.join(flags)}]" if flags else ""
        
        attrs = info.get('attrs', {})
        attrs_info = f"#{attrs['id'][:20]}" if attrs.get('id') else (f".{attrs['class'][:20]}" if attrs.get('class') else "")
        
        current_value = info.get('current_value', '')
        value_info = f"=\"{current_value[:20]}\"" if current_value else ""
        
        email_type_info = f"[{info['email_element_type']}]" if info.get('email_element_type') else ""
        
        login_type_info = f"[{info['login_element_type']}]" if info.get('login_element_type') else ""
        
        element_line = f"[{eid}]{info['type']}:{text}{flag_str}{attrs_info}{value_info}{email_type_info}{login_type_info}"
        
        # 如果检测到遮罩层，优先显示高优先级元素
        if mask_detected:
            if info.get('priority') == "high":
                if len(login_elements_list) < 20:
                    login_elements_list.append(element_line)
            elif len(other_elements_list) < MAX_OTHER_ELEMENTS:
                other_elements_list.append(element_line)
        elif info.get('frame') or info.get('is_login_element') or info.get('is_email_element') or info.get('priority') == "high":
            if len(login_elements_list) < 20:
                login_elements_list.append(element_line)
        elif len(other_elements_list) < MAX_OTHER_ELEMENTS:
            other_elements_list.append(element_line)
    
    elements_parts = []
    if login_elements_list:
        if mask_detected:
            elements_parts.append("【弹窗元素-优先】\n" + "\n".join(login_elements_list))
        else:
            elements_parts.append("【登录弹窗-优先】\n" + "\n".join(login_elements_list))
    if other_elements_list:
        elements_parts.append("【页面元素】\n" + "\n".join(other_elements_list[:30]))
    elements_description = "元素:\n" + "\n".join(elements_parts) + "\n"
    
    # 检测任务是否已完成（自动检测成功标志）
    task_completed = False
    completion_reason = ""
    objective = state.get("objective", "")
    elements_text = " ".join(other_elements_list + login_elements_list).lower()
    
    # 检测邮件发送成功
    if "发邮件" in objective or "发送邮件" in objective or "写邮件" in objective:
        success_keywords = ["发送成功", "已发送", "发送完成", "已成功发送", "成功发送到收件人"]
        for kw in success_keywords:
            if kw in elements_text:
                task_completed = True
                completion_reason = f"检测到成功标志: '{kw}'"
                break
    
    # 检测登录成功
    if "登录" in objective:
        # 登录成功通常会跳转页面或显示用户信息
        if "欢迎" in elements_text or "退出" in elements_text:
            task_completed = True
            completion_reason = "检测到登录成功标志"
    
    if task_completed:
        user_prompt = f"目标: {state['objective']}\nURL: {state['current_url']}\n"
        user_prompt += f"\n🎉【重要】检测到任务可能已完成！\n"
        user_prompt += f"📋 原因: {completion_reason}\n"
        user_prompt += f"✅ 请确认任务是否真正完成，如果完成请输出 done\n"
        user_prompt += f"❌ 如果任务未完成，请继续执行\n\n"
    else:
        user_prompt = f"目标: {state['objective']}\nURL: {state['current_url']}\n"
    
    history = state.get("history", [])
    if history:
        history_text = "历史:\n" + "\n".join(
            f"{h.get('step', '?')}:{h.get('action_type', '?')}->{h.get('result', '?')[:40]}"
            for h in history[-3:]
        ) + "\n"
    else:
        history_text = "历史: 无\n"
    
    user_prompt = f"目标: {state['objective']}\nURL: {state['current_url']}\n"
    
    # 添加截图路径信息（增强提示）
    screenshot_path = state.get("screenshot_path")
    if screenshot_path:
        import os
        screenshot_filename = os.path.basename(screenshot_path)
        user_prompt += f"📸 页面截图: {screenshot_filename}\n"
        
        # 根据截图原因给出不同的提示
        if consecutive_scrolls >= 2:
            user_prompt += "⚠️ 已连续滚动多次，请查看截图确认目标元素位置！\n"
        elif state.get("stagnation_count", 0) > 0:
            user_prompt += "⚠️ 任务进度停滞，请查看截图分析页面状态！\n"
        else:
            user_prompt += "💡 截图已保存，可参考页面布局定位元素\n"

    if popup_detected:
        user_prompt += "⚠️弹窗遮挡!只操作[弹窗]标记元素\n"
    
    if mask_detected:
        user_prompt += "🚨【强制】检测到页面遮罩层！必须优先处理遮罩层下的弹窗！\n"
        user_prompt += "⚠️ 遮罩层会阻挡页面其他元素的点击！\n"
        user_prompt += "⚠️ 请寻找并点击高优先级元素（如确定、取消、关闭等按钮）来处理弹窗！\n"
        user_prompt += "❌ 在处理完弹窗之前，禁止进行其他操作！\n\n"

    if login_form_detected:
        user_prompt += "🚨【强制】必须先完成登录！🚨\n"
        user_prompt += "⚠️ 检测到登录弹窗，必须优先完成登录操作！\n"
        user_prompt += "❌ 在登录完成前，禁止进行搜索、浏览等其他操作！\n\n"
        
        # 检查是否提供了密码（从目标文本或凭证库）
        objective = state.get("objective", "")
        import re
        phone_match = re.search(r'(?:账号|手机号|用户名)[：:]\s*(\d{11})', objective)
        password_match = re.search(r'(?:密码)[：:]\s*(\S+)', objective)
        
        has_password_in_objective = bool(password_match)
        
        # 检查凭证库中是否有密码
        current_url = state.get("current_url", "")
        platform_name = _extract_platform_from_url(current_url)
        print(f"   [调试] 当前URL: {current_url}, 提取的平台名称: {platform_name}")
        
        # 尝试多种平台名称匹配
        cred = None
        if context._credential_logged_in:
            # 首先尝试精确匹配
            cred = context.get_credential_for_platform(platform_name)
            
            # 如果没找到，尝试别名匹配
            if not cred:
                # 126邮箱的别名
                if '126' in platform_name.lower() or '126' in current_url.lower():
                    aliases = ['126邮箱', '网易邮箱', '126', '网易', 'netease']
                    for alias in aliases:
                        cred = context.get_credential_for_platform(alias)
                        if cred:
                            print(f"   [调试] 通过别名 '{alias}' 找到凭证")
                            break
                # 163邮箱的别名
                elif '163' in platform_name.lower() or '163' in current_url.lower():
                    aliases = ['163邮箱', '网易邮箱', '163', '网易', 'netease']
                    for alias in aliases:
                        cred = context.get_credential_for_platform(alias)
                        if cred:
                            print(f"   [调试] 通过别名 '{alias}' 找到凭证")
                            break
        
        print(f"   [调试] 凭证获取结果: {cred is not None}")
        has_password_in_credential = cred is not None and bool(cred.get('password'))
        
        has_password = has_password_in_objective or has_password_in_credential
        
        # 简化的登录流程 - 不区分短信/密码登录模式
        user_prompt += f"🚨 强制登录步骤（必须完成）：\n"
        if login_elements.get("username"):
            user_prompt += f"步骤1: type id={login_elements['username']} 输入账号\n"
        
        # 根据页面实际情况选择输入方式
        if login_elements.get("password"):
            user_prompt += f"步骤2: type id={login_elements['password']} 输入密码\n"
        elif login_elements.get("get_code_btn"):
            user_prompt += f"步骤2: click id={login_elements['get_code_btn']} 获取验证码\n"
        
        if login_elements.get("submit"):
            user_prompt += f"步骤3: click id={login_elements['submit']} 登录\n"
        
        user_prompt += f"\n✅ 登录成功后才能进行其他操作！\n"
        
        # 明确区分登录账号和任务目标中的邮箱
        objective = state.get("objective", "")
        
        # 检测是否是发邮件任务
        is_email_task = False
        if "发邮件" in objective or "发送邮件" in objective or "写邮件" in objective:
            is_email_task = True
            user_prompt += f"\n📧【重要】检测到发邮件任务！\n"
            user_prompt += f"🚨【绝对禁止】绝对不要把任务目标中的目标邮箱当作登录账号！\n"
            user_prompt += f"✅【正确做法】任务目标中的邮箱是【收件人邮箱】，登录后才需要填写！\n"
            user_prompt += f"✅【登录要求】必须使用凭证库中提供的邮箱账号密码进行登录！\n\n"
        
        if phone_match:
            user_prompt += f"账号:{phone_match.group(1)}\n"
        if password_match:
            user_prompt += f"密码:{password_match.group(1)}\n"
        
        # 优先使用凭证库中的账号（无论任务目标中是否有邮箱）
        if cred and cred.get('username'):
            user_prompt += f"✅ 已从凭证库获取登录账号信息:\n"
            user_prompt += f"【登录账号】:{cred['username']}\n"
            user_prompt += f"【登录密码】:{cred['password']}\n"
            user_prompt += f"🚨 强制要求：必须使用上述凭证库中的账号密码进行登录！\n"
            user_prompt += f"🚨 禁止使用任务目标中的邮箱作为登录账号！\n"
        else:
            # 没有凭证，需要用户手动输入
            print("\n" + "="*60)
            print("⚠️  检测到登录场景，但未找到凭证！")
            print("="*60)
            print(f"📋 目标平台: {platform_name}")
            print(f"🌐 当前页面: {current_url}")
            print("\n💡 请在浏览器中手动输入账号密码进行登录")
            print("   或者按 Enter 键让 Agent 尝试其他操作")
            print("\n⏳ 完成登录后请按 Enter 键继续...")
            
            try:
                user_input = input()
                if user_input.lower() in ['exit', 'quit', 'abort']:
                    print("🛑 用户请求终止任务")
                    return {
                        "history": state["history"],
                        "error_message": "用户终止任务",
                        "is_done": True,
                        "termination_reason": "user_abort"
                    }
                print("✅ 用户确认继续...")
            except KeyboardInterrupt:
                print("\n🛑 用户请求终止任务")
                return {
                    "history": state["history"],
                    "error_message": "用户终止任务",
                    "is_done": True,
                    "termination_reason": "user_abort"
                }
            
            # 告诉LLM等待用户完成登录
            user_prompt += f"\n🚨【重要】未找到凭证库中的账号密码！\n"
            user_prompt += f"⚠️ 用户已手动完成登录或需要跳过登录步骤\n"
            user_prompt += f"❌ 禁止编造账号密码！\n"
            user_prompt += f"✅ 如果登录未完成，请尝试其他方式或跳过\n"
    
    user_prompt += f"\n{elements_description}\n{history_text}\n"
    
    if state.get("error_message"):
        user_prompt += f"错误:{state['error_message'][:50]}\n"
    
    user_prompt += "\n输出JSON决策:"
    
    start_time = time.time()
    
    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
        # 检查用户命令
        context.process_user_commands()
        
        if context.user_interaction.is_aborted():
            print("\n🛑 用户请求终止...")
            return {
                "history": state["history"],
                "error_message": "用户终止任务",
                "is_done": True,
                "termination_reason": "user_abort"
            }
        
        # 直接调用LLM（不使用ThreadPoolExecutor，避免greenlet线程冲突）
        response = llm.invoke(messages)
        
        response_text = response.content
        
        # 成功获取响应，重置连接错误计数
        context.reset_connection_error_count()
        
        reasoning_time = (time.time() - start_time) * 1000
        
        # 记录模型调用成功
        if HAS_MODEL_MANAGER:
            model_manager = get_model_manager()
            if model_manager:
                current_model = model_manager.get_current_model()
                model_manager.record_success(current_model, reasoning_time)
        
        decision = parse_json_from_response(response_text)
        
        required_fields = ["thought", "action_type"]
        missing_fields = [field for field in required_fields if field not in decision]
        if missing_fields:
            raise ValueError(f"决策缺少必要字段: {', '.join(missing_fields)}")
        
        is_valid, error_msg = validate_decision(decision)
        if not is_valid:
            raise ValueError(f"决策验证失败: {error_msg}")
        
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
        error_str = str(e).lower()
        
        # 记录模型调用失败，并尝试自动切换模型
        if HAS_MODEL_MANAGER:
            model_manager = get_model_manager()
            if model_manager:
                current_model = model_manager.get_current_model()
                switched = model_manager.record_failure(current_model)
                if switched:
                    print(f"🔄 已自动切换到备用模型: {model_manager.get_current_model()}")
        
        # 检测是否是连接错误
        is_connection_error = any(keyword in error_str for keyword in [
            'connection error', 'connection refused', 'connection reset', 
            'connection timed out', 'timeout', 'network error',
            'connect error', 'socket error', 'api connection',
            '服务不可用', '连接错误', '网络错误'
        ])
        
        if is_connection_error:
            wait_seconds = context.record_connection_error()
            print_action_error(f"连接错误 (第 {context._consecutive_connection_errors} 次)，将等待 {wait_seconds} 秒后重试")
        else:
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


def _human_like_mouse_move(page: Page, locator, steps: int = 10, fast_mode: bool = False):
    """
    模拟人类的鼠标移动轨迹（性能优化版v2）
    
    【设计思路】
    人类的鼠标移动不是直线，而是带有随机波动的曲线。
    这个函数模拟自然的鼠标移动轨迹。
    快速模式下直接移动，减少延迟以提升性能。
    
    【参数】
    page: Playwright 页面对象
    locator: 目标元素定位器
    steps: 移动步数（越多越自然但越慢）
    fast_mode: 快速模式，减少延迟
    """
    import random
    
    if fast_mode:
        try:
            box = locator.bounding_box(timeout=1000)
            if box:
                target_x = box['x'] + box['width'] / 2
                target_y = box['y'] + box['height'] / 2
                page.mouse.move(target_x, target_y)
        except Exception:
            pass
        return
    
    try:
        box = locator.bounding_box(timeout=2000)
        if not box:
            return
        
        target_x = box['x'] + box['width'] / 2
        target_y = box['y'] + box['height'] / 2
        
        optimized_steps = max(3, steps // 2)
        control_x = target_x + random.randint(-30, 30)
        control_y = target_y + random.randint(-30, 30)
        
        for i in range(optimized_steps + 1):
            t = i / optimized_steps
            x = (1 - t) ** 2 * (target_x - 50) + 2 * (1 - t) * t * control_x + t ** 2 * target_x
            y = (1 - t) ** 2 * (target_y - 50) + 2 * (1 - t) * t * control_y + t ** 2 * target_y
            
            x += random.randint(-1, 1)
            y += random.randint(-1, 1)
            
            page.mouse.move(x, y)
            page.wait_for_timeout(random.randint(3, 8))
    except Exception:
        pass


def _human_like_typing(page: Page, locator, text: str, fast_mode: bool = False):
    """
    模拟人类的打字行为（性能优化版v2）
    
    【设计思路】
    人类的打字不是匀速的，而是有随机延迟的，
    偶尔还会有停顿和错误修正。
    快速模式下使用直接填充以提升性能。
    
    【参数】
    page: Playwright 页面对象
    locator: 输入框定位器
    text: 要输入的文本
    fast_mode: 快速模式，使用直接填充
    """
    import random
    
    if fast_mode:
        try:
            locator.click(timeout=1000)
            locator.fill(text, timeout=2000)
        except Exception:
            # 点击失败，直接填充
            try:
                locator.fill(text, timeout=2000)
            except:
                # 最后尝试force填充
                locator.fill(text, force=True, timeout=2000)
        return
    
    try:
        # 尝试点击，处理遮挡情况
        try:
            locator.click(timeout=3000)
        except Exception:
            # 点击失败，尝试force点击或直接填充
            try:
                locator.click(force=True, timeout=2000)
            except:
                pass
        
        page.wait_for_timeout(random.randint(50, 100))
        
        # 清空并填充
        locator.fill("")
        page.wait_for_timeout(random.randint(30, 50))
        
        locator.fill(text)
        page.wait_for_timeout(random.randint(30, 50))
            
    except Exception:
        # 尝试使用force填充
        try:
            locator.fill(text, force=True, timeout=3000)
        except:
            # 最后尝试键盘输入
            try:
                for char in text:
                    page.keyboard.type(char, delay=random.randint(20, 50))
            except:
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
    
    【验证策略】
    1. 完全匹配：最严格的验证
    2. 忽略空白匹配：处理前后空格差异
    3. 部分匹配（仅警告）：只用于特殊情况
    
    【参数】
    locator: Playwright Locator 对象
    expected_value: 期望输入的值
    max_retries: 最大重试次数
    
    【返回值】
    tuple[bool, str]: (是否验证通过, 实际值或错误信息)
    """
    if not expected_value:
        try:
            actual_value = locator.input_value(timeout=1000)
            return actual_value == "", actual_value
        except Exception as e:
            return False, f"无法读取: {e}"
    
    for attempt in range(max_retries):
        try:
            time.sleep(0.1 * (attempt + 1))
            actual_value = locator.input_value(timeout=1000)
            
            if actual_value == expected_value:
                return True, actual_value
            
            if actual_value.strip() == expected_value.strip():
                print(f"   ⚠️ 值匹配但存在空白差异: 期望='{expected_value}', 实际='{actual_value}'")
                return True, actual_value
            
            if len(actual_value) > 0 and len(expected_value) > 0:
                if actual_value == expected_value[:len(actual_value)]:
                    print(f"   ⚠️ 值被截断: 期望长度={len(expected_value)}, 实际长度={len(actual_value)}")
                    if attempt < max_retries - 1:
                        continue
                    return False, actual_value
                
                if expected_value in actual_value:
                    print(f"   ⚠️ 期望值是实际值的子集: 期望='{expected_value}', 实际='{actual_value}'")
                    return True, actual_value
                
                if actual_value in expected_value and len(actual_value) >= len(expected_value) * 0.8:
                    print(f"   ⚠️ 实际值是期望值的子集（覆盖{len(actual_value)/len(expected_value)*100:.0f}%）")
                    return True, actual_value
            
            print(f"   🔄 验证重试 {attempt + 1}/{max_retries}: 期望='{expected_value[:30]}...', 实际='{actual_value[:30]}...'")
            
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
    
    fast_mode = state.get("fast_mode", False) or context.termination_manager.fast_mode
    
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
        
        try:
            target_id_int = int(target_id) if isinstance(target_id, (int, float, str)) and str(target_id).isdigit() else target_id
        except (ValueError, TypeError) as e:
            raise ValueError(f"无效的目标元素 ID 格式: {target_id}, 错误: {e}")
        
        element_info = state["elements_dict"].get(target_id_int)
        if not element_info:
            available_ids = list(state["elements_dict"].keys())[:10]
            raise ValueError(f"找不到 ID 为 {target_id} 的元素，可用 ID: {available_ids}...")
        
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
                is_valid, result = validate_url(url)
                if not is_valid:
                    raise ValueError(result)
                url = result
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
                _human_like_mouse_move(page, locator, fast_mode=fast_mode)
                if not fast_mode:
                    import random
                    page.wait_for_timeout(random.randint(50, 100))
                locator.click(timeout=ACTION_TIMEOUT)
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
                
                # 检查元素是否在iframe中
                is_in_iframe = element_info.get("frame") is not None
                
                _human_like_mouse_move(page, locator, fast_mode=fast_mode)
                if not fast_mode:
                    import random
                    page.wait_for_timeout(random.randint(50, 100))
                
                max_retries = 2 if fast_mode else 3
                last_error = None
                for attempt in range(max_retries):
                    try:
                        locator.scroll_into_view_if_needed(timeout=3000)
                        
                        # 尝试点击，如果失败则使用force点击或直接填充
                        try:
                            locator.click(timeout=5000)
                            if not fast_mode:
                                page.wait_for_timeout(random.randint(100, 200))
                        except Exception as click_error:
                            # 点击失败，可能是元素被遮挡
                            print(f"   ⚠️ 点击失败，尝试直接填充: {str(click_error)[:50]}")
                            # 尝试使用force点击
                            try:
                                locator.click(force=True, timeout=3000)
                                if not fast_mode:
                                    page.wait_for_timeout(random.randint(100, 200))
                            except:
                                # force点击也失败，直接使用fill
                                pass
                        
                        # 对于iframe中的元素，使用更简单的输入方式
                        if is_in_iframe:
                            # 先清空
                            locator.fill("")
                            page.wait_for_timeout(100)
                            # 直接填充
                            locator.fill(value)
                            page.wait_for_timeout(100)
                        else:
                            _human_like_typing(page, locator, value, fast_mode=fast_mode)
                        
                        verified, actual_value = _verify_input_value(locator, value, max_retries=2 if fast_mode else 3)
                        
                        if verified:
                            # 额外验证：检查是否输入到了正确的元素
                            element_type = element_info.get("email_element_type", "")
                            specificity = element_info.get("specificity", 0)
                            
                            # 如果是邮件元素但特异性分数过低，给出警告
                            if element_type and specificity < 50:
                                print(f"   ⚠️ 警告：选择的元素特异性较低({specificity}分)，可能不是最佳选择")
                                print(f"   💡 建议：优先选择带有明确标识（如'收件人'、'主题'）的输入框")
                            
                            # 如果是收件人输入框，验证值是否为邮箱格式
                            if element_type == "recipient" and "@" not in actual_value:
                                print(f"   ⚠️ 警告：收件人输入框的值似乎不是有效的邮箱地址")
                            
                            return f"成功输入并验证 '{value}'"
                        else:
                            if attempt < max_retries - 1:
                                print(f"   🔄 输入验证失败，重试 {attempt + 2}/{max_retries}")
                                page.wait_for_timeout(100)
                                continue
                            return f"输入完成但验证有差异: 期望 '{value}', 实际 '{actual_value}'"
                    except Exception as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            print(f"   🔄 输入失败，重试 {attempt + 2}/{max_retries}: {e}")
                            page.wait_for_timeout(100)
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
                import os
                from datetime import datetime
                desc = decision.get("value", "页面截图")
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_dir = "screenshots"
                if not os.path.exists(screenshot_dir):
                    os.makedirs(screenshot_dir)
                    print(f"   📁 已创建截图文件夹: {screenshot_dir}")
                filename = f"screenshot_{timestamp_str}.png"
                path = os.path.join(screenshot_dir, filename)
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
