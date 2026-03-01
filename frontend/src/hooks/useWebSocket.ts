/**
 * ================================================================================
 * WebSocket Hook 模块 - 管理 WebSocket 连接和消息处理（模拟版本）
 * ================================================================================
 *
 * 【模块概述】
 * 提供 React Hook 用于管理模拟 WebSocket 连接，自动处理连接建立、消息接收和断开清理。
 *
 * 【功能说明】
 * 1. useWebSocket: 主 Hook，自动连接模拟 WebSocket 并处理各种消息类型
 * 2. useScreenshot: 专门用于订阅截图更新的 Hook
 * ================================================================================
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { wsClient } from '../services/api';
import { useControl } from '../store/controlStore';
import { useAgent } from '../store/agentStore';
import { useLogs } from '../store/logStore';
import type { AgentState, LogEntry } from '../types';

/**
 * useWebSocket Hook
 *
 * 【功能说明】
 * 自动连接模拟 WebSocket 并处理各种消息类型，与全局状态管理集成。
 */
export function useWebSocket() {
  const { dispatch: controlDispatch } = useControl();
  const { dispatch: agentDispatch } = useAgent();
  const { addLog } = useLogs();

  const unsubscribeRef = useRef<(() => void)[]>([]);

  /**
   * 处理状态更新消息
   */
  const handleStateUpdate = useCallback((state: AgentState) => {
    agentDispatch({ type: 'UPDATE_STATE', payload: state });
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
    controlDispatch({
      type: 'SET_STATUS',
      payload: status.status as 'idle' | 'running' | 'paused' | 'stopped' | 'completed' | 'error',
    });
  }, [controlDispatch]);

  /**
   * 处理截图更新消息
   */
  const handleScreenshot = useCallback((data: { screenshot: string; url: string }) => {
    agentDispatch({ type: 'SET_CURRENT_URL', payload: data.url });
  }, [agentDispatch]);

  /**
   * 组件挂载时建立连接
   */
  useEffect(() => {
    // 连接模拟 WebSocket
    wsClient.connect();

    // 订阅各种消息类型（使用泛型指定类型）
    const unsubState = wsClient.on<AgentState>('state_update', handleStateUpdate);
    const unsubLog = wsClient.on<LogEntry>('log', handleLog);
    const unsubStatus = wsClient.on<{ status: string }>('status_change', handleStatusChange);
    const unsubScreenshot = wsClient.on<{ screenshot: string; url: string }>('screenshot', handleScreenshot);

    // 保存取消订阅函数
    unsubscribeRef.current = [
      unsubState,
      unsubLog,
      unsubStatus,
      unsubScreenshot,
    ];

    // 组件卸载时清理
    return () => {
      unsubscribeRef.current.forEach((unsub) => unsub());
      wsClient.disconnect();
    };
  }, [handleStateUpdate, handleLog, handleStatusChange, handleScreenshot]);

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
    const unsubscribe = wsClient.on<{ screenshot: string; url: string }>('screenshot', (data) => {
      setScreenshot(data.screenshot);
      setUrl(data.url);
    });

    return () => unsubscribe();
  }, []);

  return { screenshot, url };
}
