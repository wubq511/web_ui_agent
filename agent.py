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
        手动关闭浏览器
        
        【设计思路】
        在用户确认查看完信息后，手动调用此方法关闭浏览器和 Playwright 实例，
        释放资源并避免内存泄漏。
        """
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        
        self.page = None
        self.browser = None
        self.playwright = None
        
        print("✅ 浏览器已关闭")
    
    def _display_result_in_browser(self, state: AgentState):
        """
        在浏览器中展示任务结果摘要
        
        【设计思路】
        任务完成后，在浏览器中打开一个新页面展示执行结果，
        方便用户查看任务详情和操作记录。
        """
        if not self.browser:
            return
        
        result_page = self.browser.new_page()
        
        step_count = state['step_count']
        is_done = state['is_done']
        error_message = state.get('error_message', '')
        history = state.get('history', [])
        objective = state.get('objective', '未知任务')
        
        status_icon = "✅" if is_done else "⚠️"
        status_text = "已完成" if is_done else "未完成"
        status_color = "#28a745" if is_done else "#ffc107"
        
        history_rows = ""
        for entry in history:
            step = entry.get('step', '?')
            action = entry.get('action_type', '?')
            result = entry.get('result', '?')
            thought = entry.get('thought', '')
            history_rows += f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{step}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;"><code>{action}</code></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{result[:100]}{'...' if len(result) > 100 else ''}</td>
                </tr>
            """
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>任务执行结果 - Web UI Agent</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    max-width: 900px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    padding: 30px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                    padding-bottom: 20px;
                    border-bottom: 2px solid #e0e0e0;
                }}
                .status-badge {{
                    display: inline-block;
                    padding: 8px 20px;
                    border-radius: 20px;
                    font-size: 18px;
                    font-weight: bold;
                    background-color: {status_color};
                    color: white;
                }}
                .info-card {{
                    background-color: #f8f9fa;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 15px 0;
                }}
                .info-item {{
                    display: flex;
                    margin: 10px 0;
                }}
                .info-label {{
                    font-weight: bold;
                    min-width: 100px;
                    color: #555;
                }}
                .info-value {{
                    color: #333;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }}
                th {{
                    background-color: #007bff;
                    color: white;
                    padding: 12px 8px;
                    border: 1px solid #ddd;
                    text-align: left;
                }}
                tr:nth-child(even) {{
                    background-color: #f8f9fa;
                }}
                tr:hover {{
                    background-color: #e9ecef;
                }}
                .warning {{
                    background-color: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 15px;
                    margin: 15px 0;
                    border-radius: 4px;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e0e0e0;
                    color: #666;
                }}
                .close-hint {{
                    background-color: #d1ecf1;
                    border-left: 4px solid #17a2b8;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎯 Web UI Agent 任务执行结果</h1>
                    <div class="status-badge">{status_icon} {status_text}</div>
                </div>
                
                <div class="info-card">
                    <h3>📋 任务信息</h3>
                    <div class="info-item">
                        <span class="info-label">目标：</span>
                        <span class="info-value">{objective}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">总步数：</span>
                        <span class="info-value">{step_count}</span>
                    </div>
                </div>
                
                {"<div class='warning'><strong>⚠️ 错误信息：</strong>" + error_message + "</div>" if error_message else ""}
                
                <div class="close-hint">
                    <strong>💡 提示：</strong>任务已完成，您可以查看上方信息。如需关闭浏览器，请返回终端按 <kbd>Enter</kbd> 键或关闭此窗口。
                </div>
                
                <h3>📜 执行历史</h3>
                <table>
                    <thead>
                        <tr>
                            <th style="width: 80px;">步骤</th>
                            <th style="width: 150px;">操作类型</th>
                            <th>执行结果</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history_rows}
                    </tbody>
                </table>
                
                <div class="footer">
                    <p>Web UI Agent 自动化任务执行完成</p>
                    <p>浏览器将保持打开状态，您可以随时查看页面内容</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        result_page.set_content(html_content)
        print("📊 任务结果已在浏览器中展示")
    
    def _wait_for_user_close(self):
        """
        等待用户手动确认关闭浏览器
        
        【设计思路】
        任务完成后，保持浏览器打开，等待用户在终端按 Enter 键后关闭。
        这样用户有足够时间查看浏览器中的信息内容。
        """
        print("\n" + "═"*60)
        print("💡 任务已完成，浏览器保持打开状态")
        print("   您可以在浏览器中查看任务执行结果")
        print("   按 Enter 键关闭浏览器并退出程序...")
        print("═"*60)
        
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        
        self._close_browser()
    
    def run(self, objective: str, start_url: str = None, keep_browser_open: bool = True) -> AgentState:
        """
        运行 Agent 执行任务
        
        【参数】
        objective: str - 用户目标描述
        start_url: str - 起始页面 URL（可选）
        keep_browser_open: bool - 任务完成后是否保持浏览器打开（默认 True）
        
        【工作流程】
        1. 初始化浏览器
        2. 如果有起始 URL，导航到该页面
        3. 初始化状态
        4. 执行状态图
        5. 输出结果
        6. 在浏览器中展示结果（如果 keep_browser_open 为 True）
        7. 等待用户确认后关闭浏览器（如果 keep_browser_open 为 True）
        
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
            
            if keep_browser_open:
                self._display_result_in_browser(final_state)
                self._wait_for_user_close()
            else:
                self._close_browser()
            
            return final_state
            
        except Exception as e:
            print(f"\n❌ 执行过程中发生错误: {e}")
            if keep_browser_open:
                print("\n💡 浏览器保持打开，您可以查看错误现场")
                print("   按 Enter 键关闭浏览器...")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    pass
            self._close_browser()
            raise
    
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
