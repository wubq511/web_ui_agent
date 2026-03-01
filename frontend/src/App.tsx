/**
 * ================================================================================
 * 主应用组件 - Web UI Agent Control Center
 * ================================================================================
 *
 * 【应用概述】
 * Web UI Agent 的控制中心前端应用，提供直观的界面来控制和监控 Agent 的执行。
 * 使用模拟数据，不与后端交互。
 *
 * 【功能模块】
 * 1. Header: 顶部导航栏，显示 Logo 和 Agent 状态
 * 2. Agent Sandbox: 显示当前步骤和最近动作
 * 3. Live View: 浏览器实时视口，显示 Agent 操作过程（模拟）
 * 4. Control Panel: 控制面板，设置任务目标、选择模型、控制执行
 * 5. Log Panel: 日志面板，显示执行日志
 * ================================================================================
 */

import React from 'react';
import Header from './components/Header';
import AgentSandbox from './components/AgentSandbox';
import LiveView from './components/LiveView';
import ControlPanel from './components/ControlPanel';
import LogPanel from './components/LogPanel';
import { AgentProvider } from './store/agentStore';
import { ControlProvider } from './store/controlStore';
import { LogProvider } from './store/logStore';
import { useWebSocket } from './hooks/useWebSocket';
import './App.css';

/**
 * 主内容组件
 */
const MainContent: React.FC = () => {
  // 初始化模拟 WebSocket 连接
  useWebSocket();

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

        {/* 右列：Control Panel + Log (占 1/3 宽度) */}
        <div className="flex-1 flex flex-col gap-4 min-w-0 max-w-md">
          {/* Control Panel - 控制面板 */}
          <ControlPanel />

          {/* Log Panel - 日志面板 */}
          <div className="flex-1 min-h-0">
            <LogPanel />
          </div>
        </div>
      </main>

      {/* 底部状态栏 */}
      <footer className="glass-strong h-8 px-4 flex items-center justify-between border-t border-white/5">
        {/* 左侧：版本信息 */}
        <div className="flex items-center gap-4 text-[10px] text-slate-500">
          <span>Web UI Agent v0.8.2</span>
          <span className="w-px h-3 bg-white/10" />
          <span className="text-yellow-400">Mock Mode</span>
        </div>
        {/* 右侧：连接状态 */}
        <div className="flex items-center gap-4 text-[10px] text-slate-500">
          <span>Mock Connection</span>
          <div className="w-1.5 h-1.5 rounded-full bg-yellow-500 animate-pulse" />
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
          <MainContent />
        </LogProvider>
      </ControlProvider>
    </AgentProvider>
  );
}

export default App;
