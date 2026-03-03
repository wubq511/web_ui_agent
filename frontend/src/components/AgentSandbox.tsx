/**
 * AgentSandbox组件
 * 左列：显示Agent的执行状态和步骤信息
 */

import React from 'react';
import { useAgent } from '../store/agentStore';
import { useControl } from '../store/controlStore';
import { Footprints, MousePointer2, Target, Layers, Shield, CheckCircle, XCircle } from 'lucide-react';

/**
 * 任务复杂度配置
 * 
 * 【设计说明】
 * 定义4个复杂度级别对应的颜色和显示文本
 * 颜色从绿色(simple)平滑过渡到红色(very_complex)
 */
const COMPLEXITY_CONFIG = {
  simple: {
    label: 'Simple',
    textColor: 'text-green-400',
    bgColor: 'bg-green-500',
    borderColor: 'border-green-500/30',
    description: 'Basic tasks like search, click, open page',
  },
  medium: {
    label: 'Medium',
    textColor: 'text-yellow-400',
    bgColor: 'bg-yellow-500',
    borderColor: 'border-yellow-500/30',
    description: 'Tasks like login, fill form, select options',
  },
  complex: {
    label: 'Complex',
    textColor: 'text-orange-400',
    bgColor: 'bg-orange-500',
    borderColor: 'border-orange-500/30',
    description: 'Tasks like purchase, submit order, send email',
  },
  very_complex: {
    label: 'Very Complex',
    textColor: 'text-red-400',
    bgColor: 'bg-red-500',
    borderColor: 'border-red-500/30',
    description: 'Batch operations, multi-step workflows',
  },
  inactive: {
    label: '---',
    textColor: 'text-slate-500',
    bgColor: 'bg-slate-700',
    borderColor: 'border-slate-700/30',
    description: 'No task is currently running',
  },
} as const;

type ComplexityLevel = keyof typeof COMPLEXITY_CONFIG;

/**
 * 判断任务是否处于活动状态
 * 
 * 【活动状态】
 * - running: 正在执行
 * - paused: 已暂停
 * 
 * 【非活动状态】
 * - idle: 空闲
 * - completed: 已完成
 * - stopped: 已停止
 * - error: 出错
 */
function isTaskActive(status: string): boolean {
  return status === 'running' || status === 'paused';
}

/**
 * 获取复杂度配置
 */
function getComplexityConfig(complexity: string, isActive: boolean): typeof COMPLEXITY_CONFIG[ComplexityLevel] {
  if (!isActive) {
    return COMPLEXITY_CONFIG.inactive;
  }
  return COMPLEXITY_CONFIG[complexity as ComplexityLevel] || COMPLEXITY_CONFIG.simple;
}

/**
 * 获取进度条颜色
 * 根据复杂度级别返回对应的颜色数组
 */
function getProgressbarColors(complexity: string, isActive: boolean): string[] {
  if (!isActive) {
    return ['bg-slate-700', 'bg-slate-700', 'bg-slate-700', 'bg-slate-700'];
  }
  const colors = {
    simple: ['bg-green-500', 'bg-slate-700', 'bg-slate-700', 'bg-slate-700'],
    medium: ['bg-green-500', 'bg-yellow-500', 'bg-slate-700', 'bg-slate-700'],
    complex: ['bg-green-500', 'bg-yellow-500', 'bg-orange-500', 'bg-slate-700'],
    very_complex: ['bg-green-500', 'bg-yellow-500', 'bg-orange-500', 'bg-red-500'],
    inactive: ['bg-slate-700', 'bg-slate-700', 'bg-slate-700', 'bg-slate-700'],
  };
  return colors[complexity as ComplexityLevel] || colors.simple;
}

const AgentSandbox: React.FC = () => {
  const { state } = useAgent();
  const { state: controlState } = useControl();
  
  const isActive = isTaskActive(controlState.status);
  const complexityConfig = getComplexityConfig(state.taskComplexity, isActive);
  const progressbarColors = getProgressbarColors(state.taskComplexity, isActive);
  
  const progressPercent = Math.round(state.progressRatio * 100);

  return (
    <div className="flex flex-col h-full gap-4">
      {/* 标题区域 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-blue-400" />
          <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
            AGENT STATUS
          </h2>
        </div>
        
        {/* 步骤进度指示器 */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-slate-800/50 border border-white/5">
            <Target className="w-3 h-3 text-slate-400" />
            <span className="text-xs text-slate-400">
              Step {state.currentStep} / {state.maxSteps}
            </span>
          </div>
        </div>
      </div>

      {/* 步骤描述卡片 */}
      <div className="grid grid-cols-2 gap-3">
        {/* 当前步骤 */}
        <div className="glass rounded-lg p-3 border border-white/5 hover:border-white/10 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <Footprints className="w-3.5 h-3.5 text-blue-400" />
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Current Step
            </span>
          </div>
          <p className="text-sm text-slate-200 leading-relaxed line-clamp-2">
            {state.stepDescription || 'Agent is ready to start'}
          </p>
        </div>

        {/* 最近动作 */}
        <div className="glass rounded-lg p-3 border border-white/5 hover:border-white/10 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <MousePointer2 className="w-3.5 h-3.5 text-purple-400" />
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Last Action
            </span>
          </div>
          <p className="text-sm text-slate-200 leading-relaxed line-clamp-2">
            {state.lastAction}
          </p>
        </div>
      </div>

      {/* 任务复杂度指示 */}
      <div className={`flex flex-col gap-2 px-3 py-2.5 rounded-lg bg-slate-800/30 border ${complexityConfig.borderColor} transition-all duration-300`}>
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
            Task Complexity
          </span>
          <span className={`text-sm font-semibold capitalize ${complexityConfig.textColor} transition-colors duration-300`}>
            {complexityConfig.label}
          </span>
        </div>
        
        <div className="flex gap-1 w-full">
          {[0, 1, 2, 3].map((level) => (
            <div
              key={level}
              className={`flex-1 h-2 rounded-full transition-all duration-300 ${progressbarColors[level]}`}
            />
          ))}
        </div>
        
        <p className="text-[10px] text-slate-500 leading-relaxed">
          {complexityConfig.description}
        </p>
      </div>

      {/* 新功能区域：凭证管理器状态 + 任务完成度 */}
      <div className="grid grid-cols-2 gap-3">
        {/* 凭证管理器登录状态 */}
        <div className="glass rounded-lg p-3 border border-white/5 hover:border-white/10 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            {state.credentialManagerLoggedIn ? (
              <Shield className="w-4 h-4 text-green-400" />
            ) : (
              <XCircle className="w-4 h-4 text-slate-500" />
            )}
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Credential Manager
            </span>
          </div>
          <div className="flex items-center gap-2">
            {state.credentialManagerLoggedIn ? (
              <>
                <CheckCircle className="w-4 h-4 text-green-400" />
                <span className="text-xs text-green-400 font-medium">Logged In</span>
              </>
            ) : (
              <>
                <XCircle className="w-4 h-4 text-slate-500" />
                <span className="text-xs text-slate-500 font-medium">Not Logged In</span>
              </>
            )}
          </div>
        </div>

        {/* 任务完成度进度条 */}
        <div className="glass rounded-lg p-3 border border-white/5 hover:border-white/10 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-blue-400" />
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Task Progress
            </span>
          </div>
          
          {/* 进度条 */}
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
              <div 
                className="h-full bg-blue-500 transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <span className="text-xs text-slate-300 font-medium min-w-[2.5rem]">
              {progressPercent}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentSandbox;
