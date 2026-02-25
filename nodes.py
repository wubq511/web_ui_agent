"""
================================================================================
节点模块 - LangGraph 图的节点实现
================================================================================

【模块概述】
实现 LangGraph 状态图的三个核心节点：
1. Perception Node（感知模块）- Agent 的"眼睛"
2. Reasoning Node（决策模块）- Agent 的"大脑"
3. Action Node（执行模块）- Agent 的"双手"

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


def perception_node(state: AgentState, page: Page) -> dict:
    """
    Perception Node - 感知模块（Agent 的"眼睛"）
    
    【核心职责】
    这个节点负责"看"当前页面，提取所有可交互的元素。就像人类浏览网页时，
    我们的眼睛会扫描页面上的按钮、链接、输入框等元素一样。
    
    【工作流程】
    1. 获取当前页面的 HTML 内容
    2. 使用 BeautifulSoup 解析 HTML
    3. 提取所有可交互元素（<a>, <button>, <input>, <select>, <textarea>）
    4. 为每个元素分配唯一 ID 并提取关键信息
    5. 组织成元素字典返回
    
    【参数】
    state: AgentState - 当前状态
    page: Page - Playwright 页面对象
    
    【返回值】
    dict: 状态更新字典，包含 elements_dict 和 current_url
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
    
    for tag_name in interactive_tags:
        elements = soup.find_all(tag_name)
        
        for element in elements:
            if not isinstance(element, Tag):
                continue
            
            style = element.get('style', '')
            if 'display: none' in style or 'visibility: hidden' in style:
                continue
            
            element_info = {
                "type": tag_name,
                "text": element.get_text(strip=True)[:100],
                "placeholder": element.get('placeholder', ''),
                "name": element.get('name', ''),
                "id": element.get('id', ''),
                "xpath": get_element_xpath(element),
                "selector": get_element_selector(element),
                "is_clickable": tag_name in ['a', 'button'] or 
                               (tag_name == 'input' and element.get('type') in ['submit', 'button', 'image']),
                "is_input": tag_name in ['input', 'textarea'] and 
                           element.get('type', 'text') not in ['submit', 'button', 'image', 'checkbox', 'radio']
            }
            
            if element_info['is_input'] or element_info['is_clickable'] or element_info['text']:
                elements_dict[element_id] = element_info
                element_id += 1
    
    print(f"📊 共发现 {len(elements_dict)} 个可交互元素")
    
    for eid, info in list(elements_dict.items())[:10]:
        text_preview = info['text'][:30] if info['text'] else info.get('placeholder', '')[:30]
        print(f"   [{eid}] {info['type']}: {text_preview}")
    
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
    这个节点负责"思考"，基于当前状态和历史信息决定下一步动作。
    就像人类在操作网页时会思考"我应该点击这个按钮"或"我需要在这里输入文字"一样。
    
    【工作流程】
    1. 构建结构化提示词（包含目标、页面信息、历史记录等）
    2. 调用大语言模型获取决策
    3. 解析 LLM 返回的 JSON 格式决策
    4. 验证决策的有效性
    5. 返回状态更新
    
    【参数】
    state: AgentState - 当前状态
    llm: ChatOpenAI - 大语言模型实例
    
    【返回值】
    dict: 状态更新字典，包含决策信息和历史记录更新
    """
    print("\n" + "="*60)
    print("🧠 [决策模块] 正在思考下一步操作...")
    print("="*60)
    
    system_prompt = """你是一个专业的网页操作助手。你的任务是分析当前网页状态，决定下一步操作来完成用户目标。

## 你的能力
你可以执行以下操作：
1. **click**: 点击页面上的元素（按钮、链接等）
2. **type**: 在输入框中输入文字
3. **goto**: 导航到指定的 URL
4. **done**: 表示任务已完成

## 输出格式要求
你必须以严格的 JSON 格式输出，不要包含任何其他文字：
```json
{
    "thought": "你的思考过程，分析当前状态和下一步应该做什么",
    "action_type": "click|type|goto|done",
    "target_id": 目标元素的数字ID（用于click和type操作）,
    "value": "输入的内容或URL（用于type和goto操作）"
}
```

## 决策原则
1. 仔细分析用户目标和当前页面状态
2. 优先完成核心任务，不要被次要内容干扰
3. 如果遇到错误，尝试其他方法
4. 确认任务完成后才输出 done
5. 每次只执行一个动作"""

    elements_description = "当前页面可交互元素：\n"
    for eid, info in state["elements_dict"].items():
        text = info['text'] if info['text'] else info.get('placeholder', '[无文本]')
        elements_description += f"  [{eid}] {info['type']}: {text}"
        if info['is_input']:
            elements_description += " [可输入]"
        if info['is_clickable']:
            elements_description += " [可点击]"
        elements_description += "\n"
    
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
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = llm.invoke(messages)
        response_text = response.content
        
        print(f"🤖 LLM 响应: {response_text[:200]}...")
        
        decision = parse_json_from_response(response_text)
        
        required_fields = ["thought", "action_type"]
        for field in required_fields:
            if field not in decision:
                raise ValueError(f"决策缺少必要字段: {field}")
        
        valid_actions = ["click", "type", "goto", "done"]
        if decision["action_type"] not in valid_actions:
            raise ValueError(f"无效的动作类型: {decision['action_type']}")
        
        print(f"💭 思考: {decision.get('thought', '无')}")
        print(f"🎬 动作: {decision['action_type']}")
        if decision.get("target_id"):
            print(f"🎯 目标元素: {decision['target_id']}")
        if decision.get("value"):
            print(f"📝 值: {decision['value']}")
        
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


def action_node(state: AgentState, page: Page) -> dict:
    """
    Action Node - 执行模块（Agent 的"双手"）
    
    【核心职责】
    这个节点负责"执行"决策模块确定的动作。就像人类的手会点击按钮、
    在输入框中打字一样，这个模块通过 Playwright 控制浏览器执行实际操作。
    
    【工作流程】
    1. 从历史记录中获取最新决策
    2. 根据动作类型执行相应操作
    3. 捕获并处理所有可能的异常
    4. 更新状态（步数、错误信息等）
    
    【自我修复机制】
    当执行出错时，我们不会终止程序，而是：
    1. 将错误信息存入 error_message
    2. 允许下一轮循环继续执行
    3. 决策模块会根据错误信息调整策略
    
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
            url = decision.get("value", "")
            if not url:
                raise ValueError("goto 操作需要提供 URL")
            
            if not url.startswith("http"):
                url = "https://" + url
            
            print(f"🌐 导航到: {url}")
            page.goto(url, timeout=PAGE_LOAD_TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
            print("✅ 页面加载完成")
            new_history[-1]["result"] = f"成功导航到 {url}"
        
        elif action_type == "click":
            target_id = decision.get("target_id")
            if not target_id:
                raise ValueError("click 操作需要提供目标元素 ID")
            
            element_info = state["elements_dict"].get(target_id)
            if not element_info:
                raise ValueError(f"找不到 ID 为 {target_id} 的元素")
            
            selector = element_info["selector"]
            print(f"👆 点击元素 [{target_id}]: {selector}")
            
            try:
                page.click(selector, timeout=ACTION_TIMEOUT)
            except Exception:
                xpath = element_info["xpath"]
                print(f"   尝试使用 XPath: {xpath}")
                page.click(f"xpath={xpath}", timeout=ACTION_TIMEOUT)
            
            page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
            print("✅ 点击成功")
            new_history[-1]["result"] = f"成功点击元素 {target_id}"
        
        elif action_type == "type":
            target_id = decision.get("target_id")
            value = decision.get("value", "")
            
            if not target_id:
                raise ValueError("type 操作需要提供目标元素 ID")
            
            element_info = state["elements_dict"].get(target_id)
            if not element_info:
                raise ValueError(f"找不到 ID 为 {target_id} 的元素")
            
            selector = element_info["selector"]
            print(f"⌨️ 在元素 [{target_id}] 中输入: {value}")
            
            try:
                page.fill(selector, value, timeout=ACTION_TIMEOUT)
            except Exception:
                xpath = element_info["xpath"]
                print(f"   尝试使用 XPath: {xpath}")
                page.fill(f"xpath={xpath}", value, timeout=ACTION_TIMEOUT)
            
            print("✅ 输入成功")
            new_history[-1]["result"] = f"成功输入 '{value}'"
        
        else:
            raise ValueError(f"未知的动作类型: {action_type}")
        
        return {
            "history": new_history,
            "error_message": None,
            "step_count": state["step_count"] + 1
        }
        
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
    
    【设计思路】
    在 LangGraph 中，条件边（Conditional Edge）允许我们根据状态动态决定
    下一个要执行的节点。这个函数检查：
    1. 任务是否已完成（is_done == True）
    2. 是否超过最大步数（step_count >= MAX_STEPS）
    
    如果满足任一条件，则路由到 END 节点终止循环；
    否则，返回 "perception" 继续执行感知-决策-执行循环。
    
    【参数】
    state: AgentState - 当前状态
    
    【返回值】
    str: 下一个节点的名称（"perception" 或 "end"）
    """
    if state["is_done"]:
        print("\n🎉 任务已完成，结束循环")
        return "end"
    
    if state["step_count"] >= MAX_STEPS:
        print(f"\n⚠️ 已达到最大步数限制 ({MAX_STEPS} 步)，强制结束")
        return "end"
    
    return "perception"
