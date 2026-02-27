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
    ACTION_TIMEOUT, PAGE_LOAD_TIMEOUT, MAX_STEPS,
    DEFAULT_TASK_COMPLEXITY, DEFAULT_PROGRESS_LEVEL,
    PROGRESS_STAGNATION_DEFAULT, DEFAULT_INTERVENTION_PAUSED,
    DEFAULT_FAST_MODE, DEFAULT_STEPS_EXTENSION, MIN_REMAINING_STEPS_THRESHOLD
)
from state import AgentState, create_initial_state
from nodes import (
    perception_node, reasoning_node, action_node, should_continue,
    AgentContext
)
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
        
        self.context = AgentContext()
        
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
            return perception_node(state, self.page, self.context)
        
        def reasoning_wrapper(state: AgentState) -> dict:
            return reasoning_node(state, self.llm, self.context)
        
        def action_wrapper(state: AgentState) -> dict:
            return action_node(state, self.page, self.context)
        
        def should_continue_wrapper(state: AgentState) -> str:
            return should_continue(state, self.context)
        
        graph = StateGraph(AgentState)
        
        graph.add_node("perception", perception_wrapper)
        graph.add_node("reasoning", reasoning_wrapper)
        graph.add_node("action", action_wrapper)
        
        graph.set_entry_point("perception")
        
        graph.add_edge("perception", "reasoning")
        graph.add_edge("reasoning", "action")
        graph.add_conditional_edges(
            "action",
            should_continue_wrapper,
            {
                "perception": "perception",
                "end": END
            }
        )
        
        return graph.compile()
    
    def _init_browser(self, storage_state: dict = None):
        """
        初始化浏览器
        
        【设计思路】
        使用 Playwright 的同步 API 启动浏览器。我们设置：
        1. headless=False - 显示浏览器窗口，便于观察执行过程
        2. slow_mo - 减慢操作速度，便于观察
        3. storage_state - 恢复浏览器会话状态（cookies、localStorage等）
        """
        print("🌐 正在启动浏览器...")
        
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=False,
            slow_mo=100
        )
        
        if storage_state:
            print("🔄 正在恢复浏览器会话状态...")
            context = self.browser.new_context(storage_state=storage_state)
            self.page = context.new_page()
            print("✅ 浏览器会话状态已恢复")
        else:
            self.page = self.browser.new_page()
        
        self.page.set_default_timeout(ACTION_TIMEOUT)
        
        self.context.set_page(self.page)
        
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
        termination_reason = state.get('termination_reason', '')
        progress_ratio = state.get('progress_ratio', 0)
        max_steps = state.get('max_steps', MAX_STEPS)
        
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
        
        termination_info = ""
        if termination_reason:
            termination_info = f"""
                <div class='warning'>
                    <strong>🛑 终止原因：</strong>{termination_reason}
                </div>
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
                .progress-bar {{
                    background-color: #e9ecef;
                    border-radius: 10px;
                    height: 20px;
                    overflow: hidden;
                }}
                .progress-fill {{
                    background-color: #28a745;
                    height: 100%;
                    width: {progress_ratio * 100}%;
                    transition: width 0.3s ease;
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
                        <span class="info-value">{step_count} / {max_steps}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">完成进度：</span>
                        <span class="info-value">{progress_ratio:.1%}</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill"></div>
                    </div>
                </div>
                
                {termination_info}
                
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
    
    def run(self, objective: str, start_url: str = None, 
            keep_browser_open: bool = True,
            max_steps: int = None,
            resume_from_checkpoint: str = None) -> AgentState:
        """
        运行 Agent 执行任务
        
        【参数】
        objective: str - 用户目标描述
        start_url: str - 起始页面 URL（可选）
        keep_browser_open: bool - 任务完成后是否保持浏览器打开（默认 True）
        max_steps: int - 最大步骤限制（可选，默认使用配置值）
        resume_from_checkpoint: str - 从检查点恢复的ID（可选）
        
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
        
        checkpoint_data = None
        storage_state = None
        if resume_from_checkpoint:
            checkpoint_data = self.context.checkpoint_manager.load_checkpoint(
                resume_from_checkpoint
            )
            if checkpoint_data:
                storage_state = checkpoint_data.storage_state
                if storage_state:
                    print("📦 发现保存的浏览器会话状态")
        
        self._init_browser(storage_state=storage_state)
        
        try:
            if checkpoint_data:
                initial_state = checkpoint_data.state
                
                initial_state.setdefault("task_complexity", DEFAULT_TASK_COMPLEXITY.value)
                initial_state.setdefault("progress_level", DEFAULT_PROGRESS_LEVEL)
                initial_state.setdefault("adjusted_stagnation_threshold", PROGRESS_STAGNATION_DEFAULT)
                initial_state.setdefault("intervention_paused", DEFAULT_INTERVENTION_PAUSED)
                initial_state.setdefault("fast_mode", DEFAULT_FAST_MODE)
                
                self.context.step_manager = self.context.step_manager.from_dict(
                    checkpoint_data.step_manager
                )
                self.context.completion_evaluator = self.context.completion_evaluator.from_dict(
                    checkpoint_data.completion_evaluator
                )
                self.context.termination_manager = self.context.termination_manager.from_dict(
                    checkpoint_data.termination_manager
                )
                
                if max_steps and max_steps > self.context.step_manager.current_max_steps:
                    self.context.step_manager.current_max_steps = max_steps
                    print(f"📊 使用命令行指定的最大步骤: {max_steps}")
                else:
                    saved_step_count = initial_state.get("step_count", 0)
                    remaining_steps = self.context.step_manager.current_max_steps - saved_step_count
                    if remaining_steps < MIN_REMAINING_STEPS_THRESHOLD:
                        new_max = saved_step_count + DEFAULT_STEPS_EXTENSION
                        self.context.step_manager.adjust_max_steps(
                            reason="恢复检查点时自动扩展（剩余步骤不足）",
                            target_steps=new_max,
                            current_step=saved_step_count
                        )
                
                initial_state["max_steps"] = self.context.step_manager.current_max_steps
                
                saved_url = initial_state.get("current_url", "")
                if saved_url and saved_url != "about:blank" and not saved_url.startswith("data:"):
                    print(f"🌐 导航到检查点页面: {saved_url}")
                    try:
                        self.page.goto(saved_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
                        try:
                            self.page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                        except Exception:
                            print("⚠️ 网络未完全空闲，继续执行...")
                            self.page.wait_for_load_state("load", timeout=5000)
                        initial_state["current_url"] = self.page.url
                    except Exception as e:
                        print(f"⚠️ 导航到检查点页面失败: {e}")
                
                print(f"✅ 已从检查点恢复: {resume_from_checkpoint}")
                print(f"📊 恢复后最大步骤: {self.context.step_manager.current_max_steps}")
                print(f"📝 已执行步骤: {initial_state.get('step_count', 0)}")
            elif resume_from_checkpoint:
                print("⚠️ 检查点加载失败，使用初始状态")
                if max_steps:
                    self.context.step_manager.current_max_steps = max_steps
                initial_state = create_initial_state(
                    objective=objective,
                    current_url="",
                    max_steps=self.context.step_manager.current_max_steps
                )
            else:
                if max_steps:
                    self.context.step_manager.current_max_steps = max_steps
                    
                if start_url:
                    print(f"🌐 导航到起始页面: {start_url}")
                    self.page.goto(start_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
                    try:
                        self.page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
                    except Exception:
                        print("⚠️ 网络未完全空闲，继续执行...")
                        self.page.wait_for_load_state("load", timeout=5000)
                
                initial_state = create_initial_state(
                    objective=objective,
                    current_url=self.page.url,
                    max_steps=self.context.step_manager.current_max_steps
                )
            
            self.context.initialize(objective, start_url or "")
            
            final_state = self.graph.invoke(initial_state)
            
            self._print_summary(final_state)
            
            self.context.logger.log_session_end(
                success=final_state.get('is_done', False),
                step_count=final_state.get('step_count', 0),
                duration=self.context.termination_manager.get_elapsed_time(),
                reason=final_state.get('termination_reason', '')
            )
            
            if keep_browser_open:
                self._display_result_in_browser(final_state)
                self._wait_for_user_close()
            else:
                self._close_browser()
            
            self.context.cleanup()
            
            return final_state
            
        except Exception as e:
            print(f"\n❌ 执行过程中发生错误: {e}")
            self.context.logger.log_error(str(e), 0)
            if keep_browser_open:
                print("\n💡 浏览器保持打开，您可以查看错误现场")
                print("   按 Enter 键关闭浏览器...")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    pass
            self._close_browser()
            self.context.cleanup()
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
        print(f"📊 最大步骤: {state.get('max_steps', MAX_STEPS)}")
        print(f"📈 完成进度: {state.get('progress_ratio', 0):.1%}")
        print(f"🎯 任务状态: {'已完成' if state['is_done'] else '未完成'}")
        
        if state.get("termination_reason"):
            print(f"🛑 终止原因: {state['termination_reason']}")
        
        if state.get("error_message"):
            print(f"⚠️ 最后错误: {state['error_message']}")
        
        print(f"💾 检查点: {state.get('saved_checkpoint_id', '无')}")
        
        print("\n📜 执行历史:")
        for entry in state["history"]:
            step = entry.get("step", "?")
            action = entry.get("action_type", "?")
            result = entry.get("result", "?")[:50]
            print(f"   步骤{step}: {action} -> {result}")
        
        print("\n" + self.context.step_manager.get_adjustment_summary())
        print("\n" + self.context.completion_evaluator.get_completion_summary())
        print("\n" + self.context.logger.get_step_summary())
    
    def list_checkpoints(self, limit: int = 5):
        """列出可用的检查点"""
        self.context.checkpoint_manager.display_checkpoints(limit)
    
    def cleanup_old_checkpoints(self, max_age_hours: int = 24, keep_count: int = 5):
        """清理过期检查点"""
        self.context.checkpoint_manager.cleanup_old_checkpoints(max_age_hours, keep_count)
