/**
 * ================================================================================
 * WebSocket Hook 模块 - 管理 WebSocket 连接和消息处理
 * ================================================================================
 *
 * 【模块概述】
 * 提供 React Hook 用于管理 WebSocket 连接，自动处理连接建立、消息接收和断开清理。
 *
 * 【功能说明】
 * 1. useWebSocket: 主 Hook，自动连接 WebSocket 并处理各种消息类型
 * 2. useScreenshot: 专门用于订阅截图更新的 Hook
 * 3. useCommandOutput: 订阅命令输出更新
 * ================================================================================
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { wsClient, apiClient } from '../services/api';
import { useControl } from '../store/controlStore';
import { useAgent } from '../store/agentStore';
import { useLogs } from '../store/logStore';
import { useTerminal } from '../store/terminalStore';
import type { AgentState, LogEntry, TerminalLine } from '../types';

/**
 * useWebSocket Hook
 *
 * 【功能说明】
 * 自动连接 WebSocket 并处理各种消息类型，与全局状态管理集成。
 */
export function useWebSocket() {
  const { dispatch: controlDispatch } = useControl();
  const { dispatch: agentDispatch } = useAgent();
  const { addLog } = useLogs();
  const { addLine, setWaitingForInput, clearTerminal, setProcessing } = useTerminal();

  const unsubscribeRef = useRef<(() => void)[]>([]);
  
  // 用于防止状态冲突的标记
  const isTransitioningRef = useRef(false);
  const transitionTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * 处理状态更新消息
   */
  const handleStateUpdate = useCallback((state: AgentState) => {
    console.log('[WebSocket] Received state_update:', state);
    agentDispatch({ type: 'UPDATE_STATE', payload: state });
  }, [agentDispatch]);

  /**
   * 处理复杂度更新消息
   * 
   * 【功能说明】
   * 当后端评估的任务复杂度发生变化时，实时更新前端显示
   * 确保更新延迟不超过300ms
   */
  const handleComplexityUpdate = useCallback((data: { taskComplexity: string; timestamp: string }) => {
    console.log('[WebSocket] Received complexity_update:', data);
    agentDispatch({ type: 'SET_TASK_COMPLEXITY', payload: data.taskComplexity });
  }, [agentDispatch]);

  /**
   * 处理日志消息
   */
  const handleLog = useCallback((log: LogEntry) => {
    if (!log || typeof log !== 'object') {
      console.warn('Received invalid log data:', log);
      return;
    }
    const message = log.message || 'No message content';
    const level = log.level || 'info';
    addLog(message, level, log.details);
  }, [addLog]);

  /**
   * 处理状态变化消息
   */
  const handleStatusChange = useCallback((status: { status: string }) => {
    // 如果正在过渡中，忽略可能冲突的状态消息
    if (isTransitioningRef.current) {
      console.log('[WebSocket] Ignoring status change during transition:', status.status);
      return;
    }
    controlDispatch({
      type: 'SET_STATUS',
      payload: status.status as 'idle' | 'running' | 'paused' | 'stopped' | 'completed' | 'error',
    });
    
    // 注意：不再在这里重置状态，让 handleCommandStatus 和 handleStateUpdate 来处理
    // 状态重置逻辑已移到 handleCommandStatus 中
  }, [controlDispatch]);

  /**
   * 处理截图更新消息
   */
  const handleScreenshot = useCallback((data: { screenshot: string; url: string }) => {
    agentDispatch({ type: 'SET_CURRENT_URL', payload: data.url });
  }, [agentDispatch]);

  /**
   * 处理命令输出消息
   */
  const handleCommandOutput = useCallback((data: { line: string; timestamp: string }) => {
    // 将命令输出作为日志显示
    addLog(data.line, 'info');
  }, [addLog]);

  /**
   * 处理命令状态消息
   * 
   * 【功能增强】
   * 当命令完成、停止或出错时，重置 Agent 状态到默认值
   */
  const handleCommandStatus = useCallback((data: { 
    status: string; 
    exit_code: number | null;
    output_count: number;
    duration: number;
  }) => {
    // 标记正在过渡
    isTransitioningRef.current = true;
    
    // 清除之前的超时
    if (transitionTimeoutRef.current) {
      clearTimeout(transitionTimeoutRef.current);
    }
    
    // 500ms 后解除过渡标记
    transitionTimeoutRef.current = setTimeout(() => {
      isTransitioningRef.current = false;
    }, 500);
    
    if (data.status === 'completed') {
      controlDispatch({ type: 'SET_STATUS', payload: 'completed' });
      addLog(`Command completed with exit code: ${data.exit_code}`, data.exit_code === 0 ? 'success' : 'error');
      setProcessing(false);
      setWaitingForInput(false, '');
      // 重置 Agent 状态到默认值
      agentDispatch({ 
        type: 'UPDATE_STATE', 
        payload: {
          lastAction: 'Waiting to start...',
          stepDescription: 'Agent is ready',
          currentStep: 0,
          progressRatio: 0,
          taskComplexity: 'simple',
        }
      });
    } else if (data.status === 'error') {
      controlDispatch({ type: 'SET_STATUS', payload: 'error' });
      addLog('Command execution failed', 'error');
      setProcessing(false);
      setWaitingForInput(false, '');
      // 重置 Agent 状态到默认值
      agentDispatch({ 
        type: 'UPDATE_STATE', 
        payload: {
          lastAction: 'Waiting to start...',
          stepDescription: 'Agent is ready',
          currentStep: 0,
          progressRatio: 0,
          taskComplexity: 'simple',
        }
      });
    } else if (data.status === 'running') {
      controlDispatch({ type: 'SET_STATUS', payload: 'running' });
      setProcessing(true);
    } else if (data.status === 'stopped') {
      controlDispatch({ type: 'SET_STATUS', payload: 'stopped' });
      addLog('Command stopped', 'warning');
      setProcessing(false);
      setWaitingForInput(false, '');
      // 重置 Agent 状态到默认值
      agentDispatch({ 
        type: 'UPDATE_STATE', 
        payload: {
          lastAction: 'Waiting to start...',
          stepDescription: 'Agent is ready',
          currentStep: 0,
          progressRatio: 0,
          taskComplexity: 'simple',
        }
      });
    }
  }, [controlDispatch, addLog, setProcessing, setWaitingForInput, agentDispatch]);

  /**
   * 处理连接状态变化
   */
  const handleConnectionStatus = useCallback((data: { connected: boolean }) => {
    controlDispatch({ type: 'SET_CONNECTED', payload: data.connected });
    if (data.connected) {
      addLog('Connected to backend server', 'success');
    } else {
      addLog('Disconnected from backend server', 'warning');
    }
  }, [controlDispatch, addLog]);

  /**
   * 处理终端行消息
   */
  const handleTerminalLine = useCallback((data: unknown) => {
    const line = data as TerminalLine;
    addLine(line.content, line.type as TerminalLine['type']);
  }, [addLine]);

  /**
   * 处理输入请求消息
   */
  const handleInputRequired = useCallback((data: unknown) => {
    const payload = data as { waiting: boolean; prompt: string };
    setWaitingForInput(payload.waiting, payload.prompt);
  }, [setWaitingForInput]);

  /**
   * 处理终端清空消息
   */
  const handleTerminalCleared = useCallback(() => {
    clearTerminal();
  }, [clearTerminal]);

  /**
   * 组件挂载时建立连接
   */
  useEffect(() => {
    // 连接 WebSocket（wsClient 内部会检查是否已连接）
    wsClient.connect();

    // 初始化时从后端获取当前状态
    const fetchInitialState = async () => {
      try {
        const health = await apiClient.healthCheck();
        if (health.agent_status) {
          controlDispatch({
            type: 'SET_STATUS',
            payload: health.agent_status as 'idle' | 'running' | 'paused' | 'stopped' | 'completed' | 'error',
          });
        }
      } catch (error) {
        console.warn('[WebSocket] Failed to fetch initial state:', error);
      }
    };
    fetchInitialState();

    // 订阅各种消息类型
    const unsubState = wsClient.on('state_update', handleStateUpdate);
    const unsubLog = wsClient.on('log', handleLog);
    const unsubStatus = wsClient.on('status_change', handleStatusChange);
    const unsubScreenshot = wsClient.on('screenshot', handleScreenshot);
    const unsubCommandOutput = wsClient.on('command_output', handleCommandOutput);
    const unsubCommandStatus = wsClient.on('command_status', handleCommandStatus);
    const unsubConnection = wsClient.on('connection_status', handleConnectionStatus);
    const unsubTerminalLine = wsClient.on('terminal_line', handleTerminalLine);
    const unsubInputRequired = wsClient.on('input_required', handleInputRequired);
    const unsubTerminalCleared = wsClient.on('terminal_cleared', handleTerminalCleared);
    const unsubComplexityUpdate = wsClient.on('complexity_update', handleComplexityUpdate);

    // 保存取消订阅函数
    unsubscribeRef.current = [
      unsubState,
      unsubLog,
      unsubStatus,
      unsubScreenshot,
      unsubCommandOutput,
      unsubCommandStatus,
      unsubConnection,
      unsubTerminalLine,
      unsubInputRequired,
      unsubTerminalCleared,
      unsubComplexityUpdate,
    ];

    // 组件卸载时清理（不主动断开，让 wsClient 管理连接生命周期）
    return () => {
      unsubscribeRef.current.forEach((unsub) => unsub());
    };
  }, [handleStateUpdate, handleLog, handleStatusChange, handleScreenshot, 
      handleCommandOutput, handleCommandStatus, handleConnectionStatus, handleTerminalLine,
      handleInputRequired, handleTerminalCleared, handleComplexityUpdate, controlDispatch]);

  return {
    isConnected: wsClient.checkIsConnected(),
    send: wsClient.send.bind(wsClient),
  };
}

/**
 * useScreenshot Hook
 */
export function useScreenshot() {
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [url, setUrl] = useState<string>('');

  useEffect(() => {
    const unsubscribe = wsClient.on('screenshot', (data: { screenshot: string; url: string }) => {
      setScreenshot(data.screenshot);
      setUrl(data.url);
    });

    return () => unsubscribe();
  }, []);

  return { screenshot, url };
}

/**
 * useCommandOutput Hook
 *
 * 【功能说明】
 * 订阅命令输出，用于在终端组件中显示
 */
export function useCommandOutput() {
  const [output, setOutput] = useState<string[]>([]);
  const [status, setStatus] = useState<string>('idle');

  useEffect(() => {
    const unsubOutput = wsClient.on('command_output', (data: { line: string }) => {
      setOutput(prev => {
        const newOutput = [...prev, data.line];
        // 保留最近 200 行
        return newOutput.slice(-200);
      });
    });

    const unsubStatus = wsClient.on('command_status', (data: { status: string }) => {
      setStatus(data.status);
    });

    return () => {
      unsubOutput();
      unsubStatus();
    };
  }, []);

  const clearOutput = useCallback(() => {
    setOutput([]);
  }, []);

  return { output, status, clearOutput };
}
