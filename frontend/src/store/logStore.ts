/**
 * ================================================================================
 * 日志状态管理模块 - 管理 Agent 的日志记录和显示
 * ================================================================================
 *
 * 【模块概述】
 * 管理 Agent 的执行日志，支持添加、查询、清空日志。
 * 日志按时间倒序排列，最多保留 100 条。
 *
 * 【设计思路】
 * 1. 日志存储在内存中，按时间倒序排列（最新的在前）
 * 2. 提供多种添加日志的便捷方法（addInfo, addSuccess 等）
 * 3. 限制最大日志数量，防止内存溢出
 * 4. 支持通过 WebSocket 实时广播日志
 *
 * 【日志级别】
 * - info: 普通信息（蓝色）
 * - success: 成功信息（绿色）
 * - warning: 警告信息（黄色）
 * - error: 错误信息（红色）
 *
 * 【使用示例】
 * ```tsx
 * const { addInfo, addSuccess, addError, clearLogs } = useLogs();
 *
 * // 添加日志
 * addInfo('Starting agent...');
 * addSuccess('Task completed');
 * addError('Connection failed', 'Timeout after 30s');
 *
 * // 清空日志
 * clearLogs();
 * ```
 * ================================================================================
 */

import React, { createContext, useContext, useReducer } from 'react';
import type { ReactNode } from 'react';
import type { LogEntry, LogLevel } from '../types';

/**
 * 日志状态接口
 *
 * 【字段说明】
 * - logs: 日志列表，按时间倒序排列
 * - maxLogs: 最大日志数量限制
 */
interface LogState {
  logs: LogEntry[];
  maxLogs: number;
}

/**
 * 初始状态
 *
 * 【默认值】
 * - logs: 空数组
 * - maxLogs: 100 条
 */
const initialState: LogState = {
  logs: [],
  maxLogs: 100,
};

/**
 * Action 类型定义
 *
 * 【Action 说明】
 * - ADD_LOG: 添加单条日志
 * - ADD_LOGS: 批量添加日志
 * - CLEAR_LOGS: 清空所有日志
 * - SET_MAX_LOGS: 设置最大日志数量
 * - REMOVE_OLD_LOGS: 删除超出的旧日志
 */
export type LogAction =
  | { type: 'ADD_LOG'; payload: LogEntry }
  | { type: 'ADD_LOGS'; payload: LogEntry[] }
  | { type: 'CLEAR_LOGS' }
  | { type: 'SET_MAX_LOGS'; payload: number }
  | { type: 'REMOVE_OLD_LOGS' };

/**
 * Reducer 函数
 *
 * 【处理逻辑】
 * - 添加日志时插入到列表头部（最新的在前）
 * - 超过最大数量时自动截断
 *
 * @param state 当前状态
 * @param action 要执行的动作
 * @returns 新状态
 */
function logReducer(state: LogState, action: LogAction): LogState {
  switch (action.type) {
    case 'ADD_LOG': {
      const newLogs = [action.payload, ...state.logs];
      // 限制日志数量
      if (newLogs.length > state.maxLogs) {
        return { ...state, logs: newLogs.slice(0, state.maxLogs) };
      }
      return { ...state, logs: newLogs };
    }
    case 'ADD_LOGS': {
      const newLogs = [...action.payload, ...state.logs];
      if (newLogs.length > state.maxLogs) {
        return { ...state, logs: newLogs.slice(0, state.maxLogs) };
      }
      return { ...state, logs: newLogs };
    }
    case 'CLEAR_LOGS':
      return { ...state, logs: [] };
    case 'SET_MAX_LOGS':
      return { ...state, maxLogs: action.payload };
    case 'REMOVE_OLD_LOGS':
      return { ...state, logs: state.logs.slice(0, state.maxLogs) };
    default:
      return state;
  }
}

/**
 * Context 类型定义
 *
 * 【扩展说明】
 * 除了 state 和 dispatch，还提供了便捷的日志添加方法
 */
interface LogContextType {
  state: LogState;
  dispatch: React.Dispatch<LogAction>;
  // 便捷方法
  addLog: (message: string, level: LogLevel, details?: string) => void;
  addInfo: (message: string, details?: string) => void;
  addSuccess: (message: string, details?: string) => void;
  addWarning: (message: string, details?: string) => void;
  addError: (message: string, details?: string) => void;
  clearLogs: () => void;
}

/**
 * 创建 Context
 */
const LogContext = createContext<LogContextType | undefined>(undefined);

/**
 * 生成唯一 ID
 *
 * 【格式】
 * 时间戳-随机数
 */
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * 格式化时间戳
 *
 * 【格式】
 * HH:MM:SS（24小时制）
 */
function formatTimestamp(): string {
  const now = new Date();
  return now.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * LogProvider 组件
 *
 * 【功能说明】
 * 为子组件提供日志状态和日志操作方法
 *
 * 【提供的便捷方法】
 * - addLog: 添加任意级别的日志
 * - addInfo: 添加信息日志
 * - addSuccess: 添加成功日志
 * - addWarning: 添加警告日志
 * - addError: 添加错误日志
 * - clearLogs: 清空所有日志
 *
 * @param children 子组件
 */
export function LogProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(logReducer, initialState);

  /**
   * 添加日志
   *
   * @param message 日志内容
   * @param level 日志级别
   * @param details 详细信息（可选）
   */
  const addLog = (message: string, level: LogLevel, details?: string) => {
    const logEntry: LogEntry = {
      id: generateId(),
      timestamp: formatTimestamp(),
      level,
      message,
      details,
    };
    dispatch({ type: 'ADD_LOG', payload: logEntry });
  };

  /**
   * 便捷方法：添加信息日志
   */
  const addInfo = (message: string, details?: string) =>
    addLog(message, 'info', details);

  /**
   * 便捷方法：添加成功日志
   */
  const addSuccess = (message: string, details?: string) =>
    addLog(message, 'success', details);

  /**
   * 便捷方法：添加警告日志
   */
  const addWarning = (message: string, details?: string) =>
    addLog(message, 'warning', details);

  /**
   * 便捷方法：添加错误日志
   */
  const addError = (message: string, details?: string) =>
    addLog(message, 'error', details);

  /**
   * 清空所有日志
   */
  const clearLogs = () => dispatch({ type: 'CLEAR_LOGS' });

  return React.createElement(
    LogContext.Provider,
    {
      value: {
        state,
        dispatch,
        addLog,
        addInfo,
        addSuccess,
        addWarning,
        addError,
        clearLogs,
      },
    },
    children
  );
}

/**
 * useLogs Hook
 *
 * 【功能说明】
 * 在函数组件中访问日志状态和日志操作方法
 *
 * 【使用示例】
 * ```tsx
 * const LogViewer = () => {
 *   const { state, addInfo, clearLogs } = useLogs();
 *
 *   return (
 *     <div>
 *       {state.logs.map(log => (
 *         <div key={log.id}>{log.message}</div>
 *       ))}
 *       <button onClick={clearLogs}>Clear</button>
 *     </div>
 *   );
 * };
 * ```
 *
 * @throws 如果在 Provider 外使用会抛出错误
 */
export function useLogs() {
  const context = useContext(LogContext);
  if (context === undefined) {
    throw new Error('useLogs must be used within a LogProvider');
  }
  return context;
}

/**
 * Action Creators
 *
 * 【功能说明】
 * 提供创建 action 对象的工厂函数
 */
export const logActions = {
  addLog: (entry: LogEntry): LogAction => ({
    type: 'ADD_LOG',
    payload: entry,
  }),
  addLogs: (entries: LogEntry[]): LogAction => ({
    type: 'ADD_LOGS',
    payload: entries,
  }),
  clearLogs: (): LogAction => ({ type: 'CLEAR_LOGS' }),
  setMaxLogs: (max: number): LogAction => ({
    type: 'SET_MAX_LOGS',
    payload: max,
  }),
  removeOldLogs: (): LogAction => ({ type: 'REMOVE_OLD_LOGS' }),
};
