/**
 * AgentSandbox组件
 * 左列：显示Agent的执行状态和步骤信息
 */

import React from 'react';
import { useAgent } from '../store/agentStore';
import { Footprints, MousePointer2, Target, Layers } from 'lucide-react';

const AgentSandbox: React.FC = () => {
  const { state } = useAgent();

  return (
    <div className="flex flex-col h-full gap-4">
      {/* 标题区域 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-blue-400" />
          <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
            Agent Sandbox
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
      <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-slate-800/30 border border-white/5">
        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
          Task Complexity:
        </span>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-medium capitalize ${
              state.taskComplexity === 'simple'
                ? 'text-green-400'
                : state.taskComplexity === 'medium'
                ? 'text-yellow-400'
                : 'text-red-400'
            }`}
          >
            {state.taskComplexity}
          </span>
          {/* 复杂度指示条 */}
          <div className="flex gap-0.5">
            {[1, 2, 3].map((level) => (
              <div
                key={level}
                className={`w-4 h-1 rounded-full transition-all duration-300 ${
                  (state.taskComplexity === 'simple' && level === 1) ||
                  (state.taskComplexity === 'medium' && level <= 2) ||
                  state.taskComplexity === 'complex'
                    ? level === 1
                      ? 'bg-green-500'
                      : level === 2
                      ? 'bg-yellow-500'
                      : 'bg-red-500'
                    : 'bg-slate-700'
                }`}
              />
            ))}
          </div>
        </div>
      </div>

      {/* 检测状态指示 */}
      <div className="flex items-center gap-3">
        {/* 弹窗检测 */}
        <div
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300 ${
            state.popupDetected
              ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
              : 'bg-slate-800/50 text-slate-500 border border-white/5'
          }`}
        >
          <div
            className={`w-1.5 h-1.5 rounded-full ${
              state.popupDetected ? 'bg-orange-400 animate-pulse' : 'bg-slate-600'
            }`}
          />
          Popup Detected
        </div>

        {/* 登录表单检测 */}
        <div
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300 ${
            state.loginFormDetected
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
              : 'bg-slate-800/50 text-slate-500 border border-white/5'
          }`}
        >
          <div
            className={`w-1.5 h-1.5 rounded-full ${
              state.loginFormDetected ? 'bg-blue-400 animate-pulse' : 'bg-slate-600'
            }`}
          />
          Login Form
        </div>
      </div>
    </div>
  );
};

export default AgentSandbox;
