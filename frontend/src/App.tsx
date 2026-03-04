/**
 * ================================================================================
 * 主应用组件 - Web UI Agent Control Center
 * ================================================================================
 *
 * 【应用概述】
 * Web UI Agent 的控制中心前端应用，提供直观的界面来控制和监控 Agent 的执行。
 * 与后端 API 交互，执行真实的 python main.py 命令。
 *
 * 【功能模块】
 * 1. Header: 顶部导航栏，显示 Logo 和 Agent 状态
 * 2. Agent Sandbox: 显示当前步骤和最近动作
 * 3. Live View: 浏览器实时视口，显示 Agent 操作过程
 * 4. Control Panel: 控制面板，设置任务目标、选择模型、控制执行
 * 5. Log Panel: 日志面板，显示执行日志
 * ================================================================================
 */

import React from 'react';
import Header from './components/Header';
import AgentSandbox from './components/AgentSandbox';
import LiveView from './components/LiveView';
import ControlPanel from './components/ControlPanel';
import FilePanel from './components/FilePanel';
import InteractiveTerminal from './components/InteractiveTerminal';
import { AgentProvider } from './store/agentStore';
import { ControlProvider, useControl } from './store/controlStore';
import { LogProvider } from './store/logStore';
import { TerminalProvider } from './store/terminalStore';
import { useWebSocket } from './hooks/useWebSocket';
import './App.css';

/**
 * 主内容组件
 * 
 * 【布局说明】
 * - 非运行状态：右列显示 ControlPanel + FilePanel
 * - 运行/暂停状态：右列显示 ControlPanel（精简模式）+ 扩展的 InteractiveTerminal
 * - 通过 isRunning 状态实现区域动态切换
 */
const MainContent: React.FC = () => {
  const { isConnected } = useWebSocket();
  const { state: controlState } = useControl();
  
  // 判断是否显示扩展终端模式
  // 只有 idle 和 stopped 状态才隐藏终端，其他状态（running、paused、error、completed）都保持显示
  const showTerminal = controlState.status !== 'idle' && controlState.status !== 'stopped';

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800">
      {/* 背景装饰 - 渐变光晕和网格 */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        {/* 渐变光晕 - 左上角蓝色 */}
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl" />
        {/* 渐变光晕 - 右下角紫色 */}
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl" />
        {/* 网格背景 */}
        <div
          className="absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage: `
              linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)
            `,
            backgroundSize: '50px 50px',
          }}
        />
      </div>

      {/* 顶部导航栏 */}
      <Header />

      {/* 主内容区域 - 双列布局 */}
      <main className="flex-1 flex gap-4 p-4 overflow-hidden relative z-10">
        {/* 左列：Agent Sandbox + Live View (占 2/3 宽度) */}
        <div className="flex-[2] flex flex-col gap-4 min-w-0">
          {/* Agent Sandbox - 显示执行状态 */}
          <div className="glass rounded-xl p-4 border border-white/10">
            <AgentSandbox />
          </div>

          {/* Live View - 浏览器实时视口 */}
          <div className="flex-1 glass rounded-xl p-4 border border-white/10 min-h-0">
            <LiveView />
          </div>
        </div>

        {/* 右列：根据运行状态动态切换布局 */}
        <div className="flex-1 flex flex-col gap-4 min-w-0 max-w-md">
          {/* Control Panel - 控制面板 */}
          <ControlPanel />

          {/* 动态区域：使用 CSS 控制显示/隐藏，避免组件卸载重挂载 */}
          <div className="flex-1 min-h-0 relative">
            {/* 文件面板 - 非运行状态显示 */}
            <div 
              className={`absolute inset-0 transition-opacity duration-200 ease-out ${
                showTerminal ? 'opacity-0 pointer-events-none' : 'opacity-100'
              }`}
            >
              <FilePanel />
            </div>
            
            {/* 终端面板 - 运行状态显示 */}
            <div 
              className={`absolute inset-0 transition-opacity duration-200 ease-out ${
                showTerminal ? 'opacity-100' : 'opacity-0 pointer-events-none'
              }`}
            >
              <div className="glass rounded-xl border border-white/10 h-full overflow-hidden">
                <InteractiveTerminal />
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* 底部状态栏 */}
      <footer className="glass-strong h-8 px-4 flex items-center justify-between border-t border-white/5">
        {/* 左侧：连接状态 */}
        <div className="flex items-center gap-4 text-[10px] text-slate-500">
          <span className={isConnected ? 'text-green-400' : 'text-red-400'}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        {/* 右侧：连接状态 */}
        <div className="flex items-center gap-4 text-[10px] text-slate-500">
          <span>Backend: localhost:8000</span>
          <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
        </div>
      </footer>
    </div>
  );
};

/**
 * 应用根组件
 */
function App() {
  return (
    <AgentProvider>
      <ControlProvider>
        <LogProvider>
          <TerminalProvider>
            <MainContent />
          </TerminalProvider>
        </LogProvider>
      </ControlProvider>
    </AgentProvider>
  );
}

export default App;
