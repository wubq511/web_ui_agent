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
 */
const MainContent: React.FC = () => {
  const { isConnected } = useWebSocket();
  const { state: controlState } = useControl();
  
  const showTerminal = controlState.status !== 'idle' && controlState.status !== 'stopped';

  return (
    <div className="h-screen w-full flex flex-col relative z-0 bg-[#050507]">
      <div className="cyber-grid" />

      <Header />

      <main className="flex-1 p-2 md:p-4 flex flex-col lg:grid lg:grid-cols-12 lg:grid-rows-6 gap-4 overflow-y-auto lg:overflow-hidden z-10">
        
        <div className="col-span-1 lg:col-span-8 lg:row-span-6 flex flex-col gap-4 min-h-[60vh] lg:min-h-0">
          <AgentSandbox />
          <LiveView />
        </div>

        <div className="col-span-1 lg:col-span-4 lg:row-span-6 flex flex-col gap-4 min-h-[50vh] lg:min-h-0 overflow-hidden">
          <ControlPanel />

          <div className="flex-1 min-h-[300px] lg:min-h-0 relative">
            <div 
              className={`absolute inset-0 transition-opacity duration-200 ease-out flex flex-col ${
                showTerminal ? 'opacity-0 pointer-events-none' : 'opacity-100'
              }`}
            >
              <FilePanel />
            </div>
            
            <div 
              className={`absolute inset-0 transition-opacity duration-200 ease-out flex flex-col ${
                showTerminal ? 'opacity-100' : 'opacity-0 pointer-events-none'
              }`}
            >
              <InteractiveTerminal />
            </div>
          </div>
        </div>
      </main>

      <footer className="min-h-[2rem] px-4 md:px-6 py-2 flex flex-wrap items-center justify-between gap-2 border-t border-[#1a1e2b] bg-[#0a0b10]/90 backdrop-blur z-10 shrink-0 font-mono text-[10px] text-[#94A3B8]">
        <div className="flex items-center gap-4">
          <span className={isConnected ? 'text-[#00FFA3]' : 'text-[#FF3366]'}>
            {isConnected ? 'UPLINK SECURE' : 'UPLINK LOST'}
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span>HOST: LOCALHOST:8000</span>
          <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-[#00FFA3]' : 'bg-[#FF3366] animate-pulse'}`} />
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
