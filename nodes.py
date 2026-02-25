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

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from playwright.sync_api import Page
from bs4 import BeautifulSoup, Tag

from state import AgentState
from config import ACTION_TIMEOUT, PAGE_LOAD_TIMEOUT, MAX_STEPS
from utils import parse_json_from_response, get_element_xpath, get_element_selector


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

## 决策原则
1. 仔细分析用户目标和当前页面状态
2. 选择最合适的操作类型，不要只用 click 和 type
3. 表单填写后通常需要按 Enter 提交，使用 press 操作
4. 下拉菜单选项使用 select 操作
5. 需要触发悬停效果时使用 hover 操作
6. 如果遇到错误，尝试其他方法
7. 确认任务完成后才输出 done
8. 每次只执行一个动作"""

VALID_ACTIONS = [
    "click", "double_click", "right_click", "hover", "drag",
    "type", "type_slowly", "press", "hotkey",
    "select", "check", "uncheck",
    "scroll", "scroll_to", "goto", "wait", "screenshot",
    "done"
]


def perception_node(state: AgentState, page: Page) -> dict:
    """
    Perception Node - 感知模块（Agent 的"眼睛"）
    
    【核心职责】
    这个节点负责"看"当前页面，提取所有可交互的元素。
    
    【工作流程】
    1. 获取当前页面的 HTML 内容
    2. 使用 BeautifulSoup 解析 HTML
    3. 提取所有可交互元素
    4. 使用 Playwright 验证元素是否真正可见
    5. 为每个元素分配唯一 ID 并提取关键信息
    6. 组织成元素字典返回
    
    【参数】
    state: AgentState - 当前状态
    page: Page - Playwright 页面对象
    
    【返回值】
    dict: 状态更新字典
    """
    print("\n" + "="*60)
    print("👁️  [感知模块] 正在分析页面...")
    print("="*60)
    
    current_url = page.url
    print(f"📍 当前页面: {current_url}")
    
    try:
        html_content = page.content()
        print("✅ 成功获取页面 HTML")
    except Exception as e:
        print(f"❌ 获取页面 HTML 失败: {e}")
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
    
    for tag_name in interactive_tags:
        elements = soup.find_all(tag_name)
        
        for element in elements:
            if not isinstance(element, Tag):
                continue
            
            style = element.get('style', '')
            if 'display: none' in style or 'visibility: hidden' in style:
                continue
            
            element_id_attr = element.get('id', '')
            element_name = element.get('name', '')
            element_type = element.get('type', '')
            
            selector = get_element_selector(element)
            xpath = get_element_xpath(element)
            
            if selector in seen_selectors:
                continue
            
            is_visible = False
            try:
                locator = page.locator(selector).first
                is_visible = locator.is_visible(timeout=1000)
            except Exception:
                try:
                    locator = page.locator(f"xpath={xpath}").first
                    is_visible = locator.is_visible(timeout=1000)
                except Exception:
                    is_visible = False
            
            if not is_visible:
                continue
            
            seen_selectors.add(selector)
            
            is_clickable = tag_name in ['a', 'button'] or \
                          (tag_name == 'input' and element_type in ['submit', 'button', 'image'])
            is_input = tag_name in ['input', 'textarea'] and \
                      element_type not in ['submit', 'button', 'image']
            is_selectable = tag_name == 'select'
            is_checkable = tag_name == 'input' and element_type in ['checkbox', 'radio']
            
            element_info = {
                "type": tag_name,
                "input_type": element_type,
                "text": element.get_text(strip=True)[:100],
                "placeholder": element.get('placeholder', ''),
                "name": element_name,
                "id": element_id_attr,
                "xpath": xpath,
                "selector": selector,
                "is_clickable": is_clickable,
                "is_input": is_input,
                "is_selectable": is_selectable,
                "is_checkable": is_checkable
            }
            
            if is_input or is_clickable or is_selectable or is_checkable or element_info['text']:
                elements_dict[element_id] = element_info
                element_id += 1
    
    print(f"📊 共发现 {len(elements_dict)} 个可交互元素（已验证可见性）")
    
    for eid, info in list(elements_dict.items())[:10]:
        text_preview = info['text'][:30] if info['text'] else info.get('placeholder', '')[:30]
        flags = []
        if info['is_input']: flags.append("可输入")
        if info['is_clickable']: flags.append("可点击")
        if info['is_selectable']: flags.append("下拉选择")
        if info['is_checkable']: flags.append("可勾选")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        print(f"   [{eid}] {info['type']}: {text_preview}{flag_str}")
    
    if len(elements_dict) > 10:
        print(f"   ... 还有 {len(elements_dict) - 10} 个元素")
    
    return {
        "elements_dict": elements_dict,
        "current_url": current_url,
        "error_message": None
    }


def reasoning_node(state: AgentState, llm: ChatOpenAI) -> dict:
    """
    Reasoning Node - 决策模块（Agent 的"大脑"）
    
    【核心职责】
    基于当前状态和历史信息决定下一步动作。
    
    【参数】
    state: AgentState - 当前状态
    llm: ChatOpenAI - 大语言模型实例
    
    【返回值】
    dict: 状态更新字典
    """
    print("\n" + "="*60)
    print("🧠 [决策模块] 正在思考下一步操作...")
    print("="*60)
    
    elements_description = "当前页面可交互元素：\n"
    for eid, info in state["elements_dict"].items():
        text = info['text'] if info['text'] else info.get('placeholder', '[无文本]')
        flags = []
        if info['is_input']: flags.append("可输入")
        if info['is_clickable']: flags.append("可点击")
        if info['is_selectable']: flags.append("下拉选择")
        if info['is_checkable']: flags.append("可勾选")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        elements_description += f"  [{eid}] {info['type']}: {text}{flag_str}\n"
    
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

## {elements_description}

## {history_text}
"""
    
    if state.get("error_message"):
        user_prompt += f"\n## ⚠️ 上一步出错\n{state['error_message']}\n请尝试其他方法。\n"
    
    user_prompt += "\n请输出你的决策（JSON格式）："
    
    print(f"🎯 目标: {state['objective']}")
    print(f"📝 已执行 {state['step_count']} 步")
    
    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
        response = llm.invoke(messages)
        response_text = response.content
        
        print(f"🤖 LLM 响应: ")
        
        decision = parse_json_from_response(response_text)
        
        required_fields = ["thought", "action_type"]
        for field in required_fields:
            if field not in decision:
                raise ValueError(f"决策缺少必要字段: {field}")
        
        if decision["action_type"] not in VALID_ACTIONS:
            raise ValueError(f"无效的动作类型: {decision['action_type']}")
        
        print(f"    💭 思考: {decision.get('thought', '无')}")
        print(f"    🎬 动作: {decision['action_type']}")
        if decision.get("target_id"):
            print(f"    🎯 目标元素: {decision['target_id']}")
        if decision.get("value"):
            print(f"    📝 值: {decision['value']}")
        
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
            "decision": decision,
            "error_message": None
        }
        
    except Exception as e:
        print(f"❌ 决策过程出错: {e}")
        error_entry = {
            "step": state["step_count"] + 1,
            "thought": f"决策出错: {str(e)}",
            "action_type": "error",
            "result": f"错误: {str(e)}"
        }
        return {
            "history": state["history"] + [error_entry],
            "error_message": f"决策模块错误: {str(e)}"
        }


def _get_locator(page: Page, element_info: dict):
    """获取元素定位器，尝试多种策略"""
    selector = element_info["selector"]
    xpath = element_info["xpath"]
    
    for loc_strategy in [selector, f"xpath={xpath}"]:
        try:
            locator = page.locator(loc_strategy).first
            return locator
        except Exception:
            continue
    return None


def action_node(state: AgentState, page: Page) -> dict:
    """
    Action Node - 执行模块（Agent 的"双手"）
    
    【核心职责】
    执行决策模块确定的动作，支持丰富的交互操作。
    
    【参数】
    state: AgentState - 当前状态
    page: Page - Playwright 页面对象
    
    【返回值】
    dict: 状态更新字典
    """
    print("\n" + "="*60)
    print("🤖 [执行模块] 正在执行动作...")
    print("="*60)
    
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
            new_history[-1]["result"] = result
            return {
                "history": new_history,
                "error_message": None,
                "step_count": state["step_count"] + 1
            }
        except Exception as e:
            error_msg = f"{action_name}失败: {str(e)}"
            print(f"❌ {error_msg}")
            new_history[-1]["result"] = error_msg
            return {
                "history": new_history,
                "error_message": error_msg,
                "step_count": state["step_count"] + 1
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
                print(f"🌐 导航到: {url}")
                page.goto(url, timeout=PAGE_LOAD_TIMEOUT)
                page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                print("✅ 页面加载完成")
                return f"成功导航到 {url}"
            return try_action(do_goto, "goto")
        
        elif action_type == "click":
            def do_click():
                element_info = get_element_info(decision.get("target_id"))
                print(f"👆 左键点击元素 [{decision.get('target_id')}]: {element_info['selector']}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.click(timeout=ACTION_TIMEOUT, force=True)
                page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                print("✅ 点击成功")
                return f"成功点击元素 {decision.get('target_id')}"
            return try_action(do_click, "click")
        
        elif action_type == "double_click":
            def do_double_click():
                element_info = get_element_info(decision.get("target_id"))
                print(f"👆👆 双击元素 [{decision.get('target_id')}]: {element_info['selector']}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.dblclick(timeout=ACTION_TIMEOUT, force=True)
                print("✅ 双击成功")
                return f"成功双击元素 {decision.get('target_id')}"
            return try_action(do_double_click, "double_click")
        
        elif action_type == "right_click":
            def do_right_click():
                element_info = get_element_info(decision.get("target_id"))
                print(f"👆 右键点击元素 [{decision.get('target_id')}]: {element_info['selector']}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.click(button="right", timeout=ACTION_TIMEOUT, force=True)
                print("✅ 右键点击成功")
                return f"成功右键点击元素 {decision.get('target_id')}"
            return try_action(do_right_click, "right_click")
        
        elif action_type == "hover":
            def do_hover():
                element_info = get_element_info(decision.get("target_id"))
                print(f"🖱️ 悬停在元素 [{decision.get('target_id')}]: {element_info['selector']}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.hover(timeout=ACTION_TIMEOUT, force=True)
                page.wait_for_timeout(500)
                print("✅ 悬停成功")
                return f"成功悬停在元素 {decision.get('target_id')}"
            return try_action(do_hover, "hover")
        
        elif action_type == "drag":
            def do_drag():
                element_info = get_element_info(decision.get("target_id"))
                target_desc = decision.get("value", "")
                print(f"🖱️ 拖拽元素 [{decision.get('target_id')}] 到: {target_desc}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                target_locator = page.locator(target_desc).first
                locator.drag_to(target_locator, timeout=ACTION_TIMEOUT)
                print("✅ 拖拽成功")
                return f"成功拖拽元素到 {target_desc}"
            return try_action(do_drag, "drag")
        
        elif action_type == "type":
            def do_type():
                element_info = get_element_info(decision.get("target_id"))
                value = decision.get("value", "")
                print(f"⌨️ 在元素 [{decision.get('target_id')}] 中输入: {value}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.fill(value, timeout=ACTION_TIMEOUT)
                print("✅ 输入成功")
                return f"成功输入 '{value}'"
            return try_action(do_type, "type")
        
        elif action_type == "type_slowly":
            def do_type_slowly():
                element_info = get_element_info(decision.get("target_id"))
                value = decision.get("value", "")
                print(f"⌨️ 逐字输入: {value}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.click(timeout=ACTION_TIMEOUT)
                for char in value:
                    page.keyboard.type(char, delay=100)
                print("✅ 逐字输入成功")
                return f"成功逐字输入 '{value}'"
            return try_action(do_type_slowly, "type_slowly")
        
        elif action_type == "press":
            def do_press():
                key = decision.get("value", "Enter")
                print(f"⌨️ 按下按键: {key}")
                page.keyboard.press(key)
                page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                print("✅ 按键成功")
                return f"成功按下 {key}"
            return try_action(do_press, "press")
        
        elif action_type == "hotkey":
            def do_hotkey():
                keys = decision.get("value", "Control+C")
                print(f"⌨️ 执行快捷键: {keys}")
                key_list = keys.split("+")
                for key in key_list:
                    page.keyboard.down(key.strip())
                for key in reversed(key_list):
                    page.keyboard.up(key.strip())
                page.wait_for_timeout(300)
                print("✅ 快捷键执行成功")
                return f"成功执行快捷键 {keys}"
            return try_action(do_hotkey, "hotkey")
        
        elif action_type == "select":
            def do_select():
                element_info = get_element_info(decision.get("target_id"))
                value = decision.get("value", "")
                print(f"📋 在下拉框 [{decision.get('target_id')}] 中选择: {value}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.select_option(label=value, timeout=ACTION_TIMEOUT)
                print("✅ 选择成功")
                return f"成功选择 '{value}'"
            return try_action(do_select, "select")
        
        elif action_type == "check":
            def do_check():
                element_info = get_element_info(decision.get("target_id"))
                print(f"☑️ 勾选元素 [{decision.get('target_id')}]: {element_info['selector']}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.check(timeout=ACTION_TIMEOUT, force=True)
                print("✅ 勾选成功")
                return f"成功勾选元素 {decision.get('target_id')}"
            return try_action(do_check, "check")
        
        elif action_type == "uncheck":
            def do_uncheck():
                element_info = get_element_info(decision.get("target_id"))
                print(f"☐ 取消勾选元素 [{decision.get('target_id')}]: {element_info['selector']}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.uncheck(timeout=ACTION_TIMEOUT, force=True)
                print("✅ 取消勾选成功")
                return f"成功取消勾选元素 {decision.get('target_id')}"
            return try_action(do_uncheck, "uncheck")
        
        elif action_type == "scroll":
            def do_scroll():
                value = decision.get("value", "down/300")
                print(f"📜 滚动页面: {value}")
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
                print("✅ 滚动成功")
                return f"成功滚动 {value}"
            return try_action(do_scroll, "scroll")
        
        elif action_type == "scroll_to":
            def do_scroll_to():
                element_info = get_element_info(decision.get("target_id"))
                print(f"📜 滚动到元素 [{decision.get('target_id')}]: {element_info['selector']}")
                locator = _get_locator(page, element_info)
                if not locator:
                    raise ValueError("无法定位元素")
                locator.scroll_into_view_if_needed(timeout=ACTION_TIMEOUT)
                print("✅ 滚动到元素成功")
                return f"成功滚动到元素 {decision.get('target_id')}"
            return try_action(do_scroll_to, "scroll_to")
        
        elif action_type == "wait":
            def do_wait():
                ms = int(decision.get("value", "1000"))
                print(f"⏳ 等待 {ms} 毫秒...")
                page.wait_for_timeout(ms)
                print("✅ 等待完成")
                return f"等待了 {ms} 毫秒"
            return try_action(do_wait, "wait")
        
        elif action_type == "screenshot":
            def do_screenshot():
                desc = decision.get("value", "页面截图")
                print(f"📸 截图: {desc}")
                timestamp = int(page.evaluate("Date.now()"))
                path = f"screenshot_{timestamp}.png"
                page.screenshot(path=path)
                print(f"✅ 截图已保存: {path}")
                return f"截图已保存: {path}"
            return try_action(do_screenshot, "screenshot")
        
        else:
            raise ValueError(f"未知的动作类型: {action_type}")
    
    except Exception as e:
        error_msg = f"执行失败: {str(e)}"
        print(f"❌ {error_msg}")
        new_history[-1]["result"] = error_msg
        return {
            "history": new_history,
            "error_message": error_msg,
            "step_count": state["step_count"] + 1
        }


def should_continue(state: AgentState) -> str:
    """
    条件路由函数 - 决定图的下一步走向
    
    【参数】
    state: AgentState - 当前状态
    
    【返回值】
    str: 下一个节点的名称
    """
    if state["is_done"]:
        print("\n🎉 任务已完成，结束循环")
        return "end"
    
    if state["step_count"] >= MAX_STEPS:
        print(f"\n⚠️ 已达到最大步数限制 ({MAX_STEPS} 步)，强制结束")
        return "end"
    
    return "perception"
