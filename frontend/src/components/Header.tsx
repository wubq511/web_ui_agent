/**
 * ================================================================================
 * Header 组件 - 顶部导航栏
 * ================================================================================
 *
 * 【组件概述】
 * 显示应用 Logo、标题和 Agent 运行状态。
 * 状态指示器带有呼吸灯动画效果。
 *
 * 【功能说明】
 * - 左侧：Logo 和标题（WEB UI AGENT | CONTROL CENTER）
 * - 右侧：版本号、状态标签（带呼吸动画）、系统健康指示
 *
 * 【状态显示】
 * - RUNNING: 绿色，带呼吸动画
 * - PAUSED: 黄色，静态
 * - STOPPED: 红色，静态
 * - COMPLETED: 蓝色，静态
 * - ERROR: 红色，静态
 * - IDLE: 灰色，静态
 *
 * 【使用示例】
 * ```tsx
 * <Header />
 * ```
 * ================================================================================
 */

import React from 'react';
import { Globe, Activity } from 'lucide-react';
import { useControl } from '../store/controlStore';

/**
 * Header 组件
 *
 * @returns 顶部导航栏 JSX 元素
 */
const Header: React.FC = () => {
  // 从 Context 获取控制状态
  const { state } = useControl();

  /**
   * 根据状态获取对应的样式配置
   *
   * @returns 包含背景色、文字色、状态点颜色、标签文本和动画状态的对象
   */
  const getStatusStyle = () => {
    switch (state.status) {
      case 'running':
        return {
          bg: 'bg-green-500/20',
          text: 'text-green-400',
          dot: 'bg-green-500',
          label: 'RUNNING',
          animate: true,
        };
      case 'paused':
        return {
          bg: 'bg-yellow-500/20',
          text: 'text-yellow-400',
          dot: 'bg-yellow-500',
          label: 'PAUSED',
          animate: false,
        };
      case 'stopped':
        return {
          bg: 'bg-red-500/20',
          text: 'text-red-400',
          dot: 'bg-red-500',
          label: 'STOPPED',
          animate: false,
        };
      case 'completed':
        return {
          bg: 'bg-blue-500/20',
          text: 'text-blue-400',
          dot: 'bg-blue-500',
          label: 'COMPLETED',
          animate: false,
        };
      case 'error':
        return {
          bg: 'bg-red-500/20',
          text: 'text-red-400',
          dot: 'bg-red-500',
          label: 'ERROR',
          animate: false,
        };
      default:
        return {
          bg: 'bg-slate-600/20',
          text: 'text-slate-400',
          dot: 'bg-slate-500',
          label: 'IDLE',
          animate: false,
        };
    }
  };

  // 获取当前状态的样式配置
  const statusStyle = getStatusStyle();

  return (
    <header className="glass-strong sticky top-0 z-50 h-14 px-6 flex items-center justify-between border-b border-white/5">
      {/* 左侧：Logo 和标题 */}
      <div className="flex items-center gap-3">
        {/* Logo 图标容器 */}
        <div className="relative">
          {/* 渐变背景图标 */}
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Globe className="w-5 h-5 text-white" />
          </div>
          {/* 装饰性光晕效果 */}
          <div className="absolute -inset-1 bg-gradient-to-br from-blue-500/20 to-purple-600/20 rounded-lg blur-sm -z-10" />
        </div>
        
        {/* 标题文本 */}
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold text-white tracking-tight">
            WEB UI AGENT
          </span>
          <span className="text-slate-500 text-sm">|</span>
          <span className="text-slate-400 text-sm font-medium tracking-wide">
            CONTROL CENTER
          </span>
        </div>
      </div>

      {/* 右侧：状态显示区域 */}
      <div className="flex items-center gap-4">
        {/* 状态指示器 */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">
            Status:
          </span>
          <div
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${statusStyle.bg} border border-white/5 transition-all duration-300`}
          >
            {/* 状态点 - 带呼吸动画 */}
            <div className="relative">
              {/* 主状态点 */}
              <div
                className={`w-2 h-2 rounded-full ${statusStyle.dot} ${
                  statusStyle.animate ? 'animate-pulse' : ''
                }`}
              />
              {/* 呼吸环效果 - 仅在运行状态显示 */}
              {statusStyle.animate && (
                <>
                  <div
                    className={`absolute inset-0 rounded-full ${statusStyle.dot} opacity-75 animate-ping`}
                    style={{ animationDuration: '2s' }}
                  />
                  <div
                    className={`absolute inset-0 rounded-full ${statusStyle.dot} opacity-50 animate-ping`}
                    style={{ animationDuration: '2s', animationDelay: '0.5s' }}
                  />
                </>
              )}
            </div>
            {/* 状态文字 */}
            <span
              className={`text-xs font-semibold uppercase tracking-wider ${statusStyle.text}`}
            >
              {statusStyle.label}
            </span>
          </div>
        </div>

        {/* 系统健康指示 */}
        <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-slate-800/50 border border-white/5">
          <Activity className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-xs text-slate-400">System OK</span>
        </div>
      </div>
    </header>
  );
};

export default Header;
