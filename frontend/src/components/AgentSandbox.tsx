/**
 * AgentSandbox组件
 * 左列：显示Agent的执行状态和步骤信息
 */

import React from 'react';
import { useAgent } from '../store/agentStore';
import { useControl } from '../store/controlStore';
import { Activity, Shield, XCircle } from 'lucide-react';
import HudPanel from './HudPanel';

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

function isTaskActive(status: string): boolean {
  return status === 'running' || status === 'paused';
}

function getComplexityConfig(complexity: string, isActive: boolean): typeof COMPLEXITY_CONFIG[ComplexityLevel] {
  if (!isActive) {
    return COMPLEXITY_CONFIG.inactive;
  }
  return COMPLEXITY_CONFIG[complexity as ComplexityLevel] || COMPLEXITY_CONFIG.simple;
}

function getProgressbarColors(complexity: string, isActive: boolean): string[] {
  if (!isActive) {
    return ['bg-slate-700', 'bg-slate-700', 'bg-slate-700', 'bg-slate-700'];
  }
  const colors = {
    simple: ['bg-[#00FFA3]', 'bg-[#1a1e2b]', 'bg-[#1a1e2b]', 'bg-[#1a1e2b]'],
    medium: ['bg-[#00FFA3]', 'bg-[#EAB308]', 'bg-[#1a1e2b]', 'bg-[#1a1e2b]'],
    complex: ['bg-[#00FFA3]', 'bg-[#EAB308]', 'bg-[#F97316]', 'bg-[#1a1e2b]'],
    very_complex: ['bg-[#00FFA3]', 'bg-[#EAB308]', 'bg-[#F97316]', 'bg-[#FF3366]'],
    inactive: ['bg-[#1a1e2b]', 'bg-[#1a1e2b]', 'bg-[#1a1e2b]', 'bg-[#1a1e2b]'],
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
    <HudPanel title="AGENT SANDBOX" icon={<Activity size={16} />} className="shrink-0 h-auto" bodyClassName="p-4 flex flex-col gap-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="border border-[#1a1e2b] bg-black/40 p-3 flex flex-col justify-between min-h-[96px]">
          <span className="text-[10px] text-[#94A3B8] uppercase">Current Step</span>
          <span className="font-mono text-sm text-[#00E5FF] line-clamp-2" title={state.stepDescription}>
            {state.stepDescription || 'Agent is ready to start'}
          </span>
        </div>
        
        <div className="border border-[#1a1e2b] bg-black/40 p-3 flex flex-col justify-between min-h-[96px]">
          <span className="text-[10px] text-[#94A3B8] uppercase flex items-center justify-between">
            Step Progress
            <span className={`text-[9px] font-bold ${complexityConfig.textColor}`}>{complexityConfig.label}</span>
          </span>
          <div className="flex items-end gap-2">
            <span className="font-display text-2xl text-[#00FFA3]">{(state.currentStep || 0).toString().padStart(2, '0')}</span>
            <span className="text-xs text-[#94A3B8] pb-1">/ {(state.maxSteps || 0).toString().padStart(2, '0')}</span>
          </div>
          <div className="flex gap-1 w-full mt-2 h-1">
            {[0, 1, 2, 3].map((level) => (
              <div
                key={level}
                className={`flex-1 h-full rounded-none transition-all duration-300 ${progressbarColors[level]}`}
              />
            ))}
          </div>
        </div>
        
        <div className="border border-[#1a1e2b] bg-black/40 p-3 flex flex-col justify-between min-h-[96px]">
          <span className="text-[10px] text-[#94A3B8] uppercase">Last Action</span>
          <span className="font-mono text-sm text-[#B52BFF] line-clamp-2" title={state.lastAction}>
            {state.lastAction || '---'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border border-[#1a1e2b] bg-black/40 p-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {state.credentialManagerLoggedIn ? (
              <Shield className="w-4 h-4 text-[#00FFA3]" />
            ) : (
              <XCircle className="w-4 h-4 text-[#94A3B8]" />
            )}
            <span className="text-[10px] text-[#94A3B8] uppercase">Credential Manager</span>
          </div>
          <div className="flex items-center gap-2">
            {state.credentialManagerLoggedIn ? (
              <span className="text-[10px] text-[#00FFA3] font-bold uppercase">Logged In</span>
            ) : (
              <span className="text-[10px] text-[#94A3B8] font-bold uppercase">Not Logged In</span>
            )}
          </div>
        </div>

        <div className="border border-[#1a1e2b] bg-black/40 p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] text-[#94A3B8] uppercase">Task Progress</span>
            <span className="text-[10px] text-[#E2E8F0] font-bold">{progressPercent}%</span>
          </div>
          <div className="h-1 w-full bg-[#1a1e2b]">
            <div 
              className="h-full bg-[#00E5FF] transition-all duration-300" 
              style={{ width: `${progressPercent}%` }} 
            />
          </div>
        </div>
      </div>
    </HudPanel>
  );
};

export default AgentSandbox;
