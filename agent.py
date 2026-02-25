"""
================================================================================
Agent 模块 - WebUIAgent 类实现
================================================================================

【模块概述】
封装 WebUIAgent 类，提供完整的 Agent 功能：
- 初始化大语言模型
- 管理浏览器生命周期
- 构建和执行 LangGraph 状态图

【设计思路】
将 Agent 封装为一个类，便于：
1. 管理浏览器生命周期
2. 初始化和配置各组件
3. 提供简洁的运行接口
================================================================================
"""

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from playwright.sync_api import sync_playwright, Page, Browser, Playwright

from config import (
    API_BASE_URL, MODEL_NAME, LLM_TIMEOUT, LLM_TEMPERATURE,
    ACTION_TIMEOUT, PAGE_LOAD_TIMEOUT
)
from state import AgentState, create_initial_state
from nodes import perception_node, reasoning_node, action_node, should_continue
from utils import get_api_key


class WebUIAgent:
    """
    WebUIAgent - Web UI 自动化代理类
    
    【使用示例】
    ```python
    agent = WebUIAgent()
    agent.run("在百度搜索 LangGraph 教程")
    ```
    """
    
    def __init__(self):
        """
        初始化 Agent
        
        【工作流程】
        1. 获取并验证 API 密钥
        2. 初始化大语言模型
        3. 构建状态图
        """
        print("🚀 正在初始化 Web UI Agent...")
        
        api_key = get_api_key()
        print("✅ API 密钥验证通过")
        
        self.llm = ChatOpenAI(
            model=MODEL_NAME,
            openai_api_key=api_key,
            openai_api_base=API_BASE_URL,
            timeout=LLM_TIMEOUT,
            temperature=LLM_TEMPERATURE
        )
        print(f"✅ 大语言模型已初始化: {MODEL_NAME}")
        
        self.playwright: Playwright = None
        self.browser: Browser = None
        self.page: Page = None
        
        self.graph = self._build_graph()
        print("✅ 状态图构建完成")
    
    def _build_graph(self) -> StateGraph:
        """
        构建 LangGraph 状态图
        
        【设计思路】
        LangGraph 使用状态图（StateGraph）来定义 Agent 的工作流程。
        我们需要：
        1. 创建节点（Node）- 每个节点是一个处理函数
        2. 定义边（Edge）- 节点之间的流转关系
        3. 设置入口点 - 图的起始节点
        
        【图的拓扑结构】
        START -> perception -> reasoning -> action -> [条件判断]
                                                        |
                    ┌──────────────────────────────────┘
                    |
                    └──> END (如果完成或超时)
                    └──> perception (如果继续)
        """
        
        def perception_wrapper(state: AgentState) -> dict:
            return perception_node(state, self.page)
        
        def reasoning_wrapper(state: AgentState) -> dict:
            return reasoning_node(state, self.llm)
        
        def action_wrapper(state: AgentState) -> dict:
            return action_node(state, self.page)
        
        graph = StateGraph(AgentState)
        
        graph.add_node("perception", perception_wrapper)
        graph.add_node("reasoning", reasoning_wrapper)
        graph.add_node("action", action_wrapper)
        
        graph.set_entry_point("perception")
        
        graph.add_edge("perception", "reasoning")
        graph.add_edge("reasoning", "action")
        graph.add_conditional_edges(
            "action",
            should_continue,
            {
                "perception": "perception",
                "end": END
            }
        )
        
        return graph.compile()
    
    def _init_browser(self):
        """
        初始化浏览器
        
        【设计思路】
        使用 Playwright 的同步 API 启动浏览器。我们设置：
        1. headless=False - 显示浏览器窗口，便于观察执行过程
        2. slow_mo - 减慢操作速度，便于观察
        """
        print("🌐 正在启动浏览器...")
        
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=False,
            slow_mo=100
        )
        self.page = self.browser.new_page()
        self.page.set_default_timeout(ACTION_TIMEOUT)
        
        print("✅ 浏览器启动成功")
    
    def _close_browser(self):
        """
        关闭浏览器
        
        【设计思路】
        在任务完成后，需要正确关闭浏览器和 Playwright 实例，
        释放资源并避免内存泄漏。
        """
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        
        print("✅ 浏览器已关闭")
    
    def run(self, objective: str, start_url: str = None) -> AgentState:
        """
        运行 Agent 执行任务
        
        【参数】
        objective: str - 用户目标描述
        start_url: str - 起始页面 URL（可选）
        
        【工作流程】
        1. 初始化浏览器
        2. 如果有起始 URL，导航到该页面
        3. 初始化状态
        4. 执行状态图
        5. 输出结果
        6. 关闭浏览器
        
        【返回值】
        AgentState: 最终状态
        """
        print("\n" + "═"*60)
        print("🎯 开始执行任务")
        print("═"*60)
        print(f"📋 目标: {objective}")
        if start_url:
            print(f"🌐 起始页面: {start_url}")
        print("═"*60 + "\n")
        
        self._init_browser()
        
        try:
            if start_url:
                print(f"🌐 导航到起始页面: {start_url}")
                self.page.goto(start_url, timeout=PAGE_LOAD_TIMEOUT)
                self.page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
            
            initial_state = create_initial_state(
                objective=objective,
                current_url=self.page.url
            )
            
            final_state = self.graph.invoke(initial_state)
            
            self._print_summary(final_state)
            
            return final_state
            
        except Exception as e:
            print(f"\n❌ 执行过程中发生错误: {e}")
            raise
        
        finally:
            self._close_browser()
    
    def _print_summary(self, state: AgentState):
        """
        打印执行结果汇总
        
        【参数】
        state: AgentState - 最终状态
        """
        print("\n" + "═"*60)
        print("📊 执行结果汇总")
        print("═"*60)
        print(f"✅ 总步数: {state['step_count']}")
        print(f"🎯 任务状态: {'已完成' if state['is_done'] else '未完成'}")
        
        if state.get("error_message"):
            print(f"⚠️ 最后错误: {state['error_message']}")
        
        print("\n📜 执行历史:")
        for entry in state["history"]:
            step = entry.get("step", "?")
            action = entry.get("action_type", "?")
            result = entry.get("result", "?")[:50]
            print(f"   步骤{step}: {action} -> {result}")
