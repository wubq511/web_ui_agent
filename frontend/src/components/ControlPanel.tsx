/**
 * ================================================================================
 * ControlPanel 组件 - 控制面板
 * ================================================================================
 *
 * 【组件概述】
 * 提供 Agent 控制界面，包括目标输入、模型选择、运行控制等功能。
 * 使用模拟数据，不与后端交互。
 *
 * 【功能说明】
 * - 目标输入：设置 Agent 的任务目标
 * - 模型选择：选择使用的 AI 模型
 * - 控制按钮：Run/Pause/Stop/Reset 控制 Agent 执行
 * ================================================================================
 */

import React, { useState } from 'react';
import {
  Play,
  Pause,
  Square,
  RotateCcw,
  ChevronDown,
  Terminal,
  Sparkles,
} from 'lucide-react';
import { useControl } from '../store/controlStore';
import { useAgent } from '../store/agentStore';
import { useLogs } from '../store/logStore';
import { AVAILABLE_MODELS } from '../store/agentStore';
import { apiClient, wsClient } from '../services/api';

const ControlPanel: React.FC = () => {
  const { state: controlState, dispatch } = useControl();
  const { dispatch: agentDispatch } = useAgent();
  const { addInfo, addSuccess, addWarning, addError } = useLogs();

  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [localObjective, setLocalObjective] = useState(controlState.objective);
  const [isLoading, setIsLoading] = useState(false);

  // 获取当前选中的模型
  const selectedModel = AVAILABLE_MODELS.find(
    (m) => m.id === controlState.selectedModel
  );

  // 选择模型
  const handleModelSelect = (modelId: string) => {
    dispatch({ type: 'SET_MODEL', payload: modelId });
    setIsModelDropdownOpen(false);
    addInfo(`Model switched to ${modelId}`);
  };

  // 更新目标
  const handleObjectiveChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setLocalObjective(e.target.value);
    dispatch({ type: 'SET_OBJECTIVE', payload: e.target.value });
    agentDispatch({ type: 'SET_OBJECTIVE', payload: e.target.value });
  };

  // 运行 Agent - 使用模拟数据
  const handleRun = async () => {
    if (!localObjective.trim()) {
      addWarning('Please enter an objective before running');
      return;
    }

    setIsLoading(true);
    try {
      // 调用模拟 API
      const result = await apiClient.startAgent(
        localObjective,
        controlState.selectedModel
      );

      if (result.success) {
        dispatch({ type: 'START_AGENT' });
        addSuccess('Agent started', `Objective: ${localObjective}`);
        
        // 启动模拟 Agent（通过 WebSocket 客户端）
        wsClient.startMockAgent(localObjective);
      } else {
        addError('Failed to start agent', result.message);
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unknown error';
      addError('Failed to start agent', errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  // 暂停/继续 Agent - 使用模拟数据
  const handlePauseResume = async () => {
    setIsLoading(true);
    try {
      if (controlState.isPaused) {
        // 恢复 Agent
        const result = await apiClient.resumeAgent();
        if (result.success) {
          dispatch({ type: 'RESUME_AGENT' });
          wsClient.resumeMockAgent();
          addInfo('Agent resumed');
        } else {
          addError('Failed to resume agent', result.message);
        }
      } else {
        // 暂停 Agent
        const result = await apiClient.pauseAgent();
        if (result.success) {
          dispatch({ type: 'PAUSE_AGENT' });
          wsClient.pauseMockAgent();
          addWarning('Agent paused');
        } else {
          addError('Failed to pause agent', result.message);
        }
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unknown error';
      addError('Failed to pause/resume agent', errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  // 停止 Agent - 使用模拟数据
  const handleStop = async () => {
    setIsLoading(true);
    try {
      const result = await apiClient.stopAgent();
      if (result.success) {
        dispatch({ type: 'STOP_AGENT' });
        wsClient.stopMockAgent();
        addWarning('Agent stopped by user');
      } else {
        addError('Failed to stop agent', result.message);
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unknown error';
      addError('Failed to stop agent', errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  // 重置 Agent - 使用模拟数据
  const handleReset = async () => {
    setIsLoading(true);
    try {
      const result = await apiClient.resetAgent();
      if (result.success) {
        dispatch({ type: 'RESET_AGENT' });
        wsClient.resetMockAgent();
        setLocalObjective('');
        addInfo('Agent reset');
      } else {
        addError('Failed to reset agent', result.message);
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unknown error';
      addError('Failed to reset agent', errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  // 判断按钮状态
  const isRunning = controlState.status === 'running';
  const isPaused = controlState.status === 'paused';
  const isIdle = controlState.status === 'idle';
  const isStopped = controlState.status === 'stopped';

  return (
    <div className="glass rounded-xl p-4 border border-white/10">
      {/* 标题 */}
      <div className="flex items-center gap-2 mb-4">
        <Terminal className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
          Control Panel
        </h3>
        <span className="text-[10px] px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400">
          Mock Mode
        </span>
      </div>

      {/* 目标输入区域 */}
      <div className="mb-4">
        <label className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
          Set Agent Goal
        </label>
        <textarea
          value={localObjective}
          onChange={handleObjectiveChange}
          placeholder="Enter your task objective here... (e.g., Search for gaming laptops under $1200 on Amazon and add the best one to cart)"
          className="w-full h-24 px-3 py-2.5 rounded-lg bg-slate-900/80 border border-white/10 text-sm text-slate-200 placeholder-slate-600 resize-none focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all"
          disabled={isRunning && !isPaused}
        />
      </div>

      {/* 控制按钮组 */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {/* Run/Resume 按钮 */}
        <button
          onClick={handleRun}
          disabled={(isRunning && !isPaused) || isLoading}
          className={`flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg font-medium text-xs uppercase tracking-wider transition-all duration-200 ${
            (isRunning && !isPaused) || isLoading
              ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
              : 'bg-gradient-to-r from-blue-600 to-blue-500 text-white hover:from-blue-500 hover:to-blue-400 shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 animate-glow'
          }`}
        >
          {isLoading ? (
            <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5" />
          )}
          {isPaused ? 'Resume' : 'Run'}
        </button>

        {/* Pause/Continue 按钮 */}
        <button
          onClick={handlePauseResume}
          disabled={(!isRunning && !isPaused) || isLoading}
          className={`flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg font-medium text-xs uppercase tracking-wider transition-all duration-200 ${
            (!isRunning && !isPaused) || isLoading
              ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
              : isPaused
              ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 hover:bg-yellow-500/30'
              : 'bg-slate-800 text-slate-300 border border-white/10 hover:bg-slate-700 hover:border-white/20'
          }`}
        >
          {isPaused ? (
            <>
              <Play className="w-3.5 h-3.5" />
              Continue
            </>
          ) : (
            <>
              <Pause className="w-3.5 h-3.5" />
              Pause
            </>
          )}
        </button>

        {/* Stop 按钮 */}
        <button
          onClick={handleStop}
          disabled={isIdle || isStopped || isLoading}
          className={`flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg font-medium text-xs uppercase tracking-wider transition-all duration-200 ${
            isIdle || isStopped || isLoading
              ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
              : 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30'
          }`}
        >
          <Square className="w-3.5 h-3.5" />
          Stop
        </button>

        {/* Reset 按钮 */}
        <button
          onClick={handleReset}
          disabled={isLoading}
          className={`flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg bg-slate-800 text-slate-300 border border-white/10 font-medium text-xs uppercase tracking-wider hover:bg-slate-700 hover:border-white/20 transition-all duration-200 ${
            isLoading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Reset
        </button>
      </div>

      {/* 模型选择下拉菜单 */}
      <div className="relative">
        <label className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
          Model Select
        </label>
        <button
          onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}
          className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg bg-slate-900/80 border border-white/10 text-sm text-slate-200 hover:border-white/20 transition-all"
        >
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-400" />
            <span>{selectedModel?.name || 'Select Model'}</span>
          </div>
          <ChevronDown
            className={`w-4 h-4 text-slate-500 transition-transform duration-200 ${
              isModelDropdownOpen ? 'rotate-180' : ''
            }`}
          />
        </button>

        {/* 下拉菜单 */}
        {isModelDropdownOpen && (
          <div className="absolute top-full left-0 right-0 mt-1 py-1 rounded-lg bg-slate-800 border border-white/10 shadow-xl z-50 animate-fade-in">
            {AVAILABLE_MODELS.map((model) => (
              <button
                key={model.id}
                onClick={() => handleModelSelect(model.id)}
                className={`w-full px-3 py-2.5 text-left hover:bg-white/5 transition-colors ${
                  model.id === controlState.selectedModel
                    ? 'bg-blue-500/10 border-l-2 border-blue-500'
                    : ''
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-200">{model.name}</span>
                  {model.supportsVision && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400">
                      Vision
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                  {model.description}
                </p>
                <div className="flex gap-1 mt-1.5">
                  {model.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 当前模型信息 */}
      <div className="mt-3 p-2.5 rounded-lg bg-slate-900/50 border border-white/5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">Max Tokens:</span>
          <span className="text-slate-300">
            {selectedModel?.maxTokens.toLocaleString()}
          </span>
        </div>
        <div className="flex items-center justify-between text-xs mt-1">
          <span className="text-slate-500">Auto Switch:</span>
          <span
            className={`${
              selectedModel?.supportsAutoSwitch
                ? 'text-green-400'
                : 'text-red-400'
            }`}
          >
            {selectedModel?.supportsAutoSwitch ? 'Enabled' : 'Disabled'}
          </span>
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;
