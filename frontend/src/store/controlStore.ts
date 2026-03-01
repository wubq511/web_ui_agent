/**
 * ================================================================================
 * 控制面板状态管理模块 - 管理控制面板的 UI 状态和用户操作
 * ================================================================================
 *
 * 【模块概述】
 * 管理控制面板的 UI 状态，包括 Agent 控制状态（运行/暂停/停止）、
 * 选中的模型、任务目标等。与 AgentStore 配合，前者管数据，本模块管控制。
 *
 * 【设计思路】
 * 1. 将控制逻辑与数据状态分离，职责更清晰
 * 2. 提供便捷的控制方法（startAgent, pauseAgent 等）
 * 3. 状态变化时自动同步到后端
 * 4. 支持撤销/重置操作
 *
 * 【状态流转】
 * idle -> running -> paused -> running -> completed
 *   |       |         |         |
 *   v       v         v         v
 * stopped <-+---------+---------+
 *
 * 【使用示例】
 * ```tsx
 * const { state, startAgent, pauseAgent } = useControl();
 *
 * // 启动 Agent
 * startAgent();
 *
 * // 检查状态
 * if (state.status === 'running') {
 *   console.log('Agent is running');
 * }
 * ```
 * ================================================================================
 */

import React, { createContext, useContext, useReducer } from 'react';
import type { ReactNode } from 'react';
import type { AgentStatus } from '../types';

/**
 * 控制面板状态接口
 *
 * 【字段说明】
 * - status: Agent 运行状态
 * - selectedModel: 当前选中的模型 ID
 * - objective: 用户输入的任务目标
 * - isConnected: 是否与后端建立连接
 * - isPaused: 是否处于暂停状态（冗余字段，便于快速判断）
 */
interface ControlState {
  status: AgentStatus;
  selectedModel: string;
  objective: string;
  isConnected: boolean;
  isPaused: boolean;
}

/**
 * 初始状态
 *
 * 【默认值】
 * - status: idle - 初始为空闲状态
 * - selectedModel: gemini-3-flash-preview - 默认使用 Gemini 模型
 * - objective: 空字符串 - 等待用户输入
 * - isConnected: false - 初始未连接
 * - isPaused: false - 初始未暂停
 */
const initialState: ControlState = {
  status: 'idle',
  selectedModel: 'gemini-3-flash-preview',
  objective: '',
  isConnected: false,
  isPaused: false,
};

/**
 * Action 类型定义
 *
 * 【Action 分类】
 * 1. 状态设置类: SET_STATUS, SET_MODEL, SET_OBJECTIVE, SET_CONNECTED, SET_PAUSED
 * 2. 控制操作类: START_AGENT, PAUSE_AGENT, RESUME_AGENT, STOP_AGENT, RESET_AGENT
 * 3. 批量更新类: UPDATE_STATE
 */
export type ControlAction =
  | { type: 'SET_STATUS'; payload: AgentStatus }
  | { type: 'SET_MODEL'; payload: string }
  | { type: 'SET_OBJECTIVE'; payload: string }
  | { type: 'SET_CONNECTED'; payload: boolean }
  | { type: 'SET_PAUSED'; payload: boolean }
  | { type: 'START_AGENT' }
  | { type: 'PAUSE_AGENT' }
  | { type: 'RESUME_AGENT' }
  | { type: 'STOP_AGENT' }
  | { type: 'RESET_AGENT' }
  | { type: 'UPDATE_STATE'; payload: Partial<ControlState> };

/**
 * Reducer 函数
 *
 * 【处理逻辑】
 * - 控制类 Action 会同时更新多个相关字段
 * - 例如 START_AGENT 会设置 status 为 running，isPaused 为 false
 *
 * @param state 当前状态
 * @param action 要执行的动作
 * @returns 新状态
 */
function controlReducer(state: ControlState, action: ControlAction): ControlState {
  switch (action.type) {
    case 'SET_STATUS':
      return { ...state, status: action.payload };
    case 'SET_MODEL':
      return { ...state, selectedModel: action.payload };
    case 'SET_OBJECTIVE':
      return { ...state, objective: action.payload };
    case 'SET_CONNECTED':
      return { ...state, isConnected: action.payload };
    case 'SET_PAUSED':
      return { ...state, isPaused: action.payload };
    case 'START_AGENT':
      return { ...state, status: 'running', isPaused: false };
    case 'PAUSE_AGENT':
      return { ...state, status: 'paused', isPaused: true };
    case 'RESUME_AGENT':
      return { ...state, status: 'running', isPaused: false };
    case 'STOP_AGENT':
      return { ...state, status: 'stopped', isPaused: false };
    case 'RESET_AGENT':
      return { ...initialState, isConnected: state.isConnected };
    case 'UPDATE_STATE':
      return { ...state, ...action.payload };
    default:
      return state;
  }
}

/**
 * Context 类型定义
 *
 * 【扩展说明】
 * 除了 state 和 dispatch，还提供了便捷的控制方法
 */
interface ControlContextType {
  state: ControlState;
  dispatch: React.Dispatch<ControlAction>;
  // 便捷方法 - 封装了常用的控制操作
  startAgent: () => void;
  pauseAgent: () => void;
  resumeAgent: () => void;
  stopAgent: () => void;
  resetAgent: () => void;
  selectModel: (modelId: string) => void;
  setObjective: (objective: string) => void;
}

/**
 * 创建 Context
 */
const ControlContext = createContext<ControlContextType | undefined>(undefined);

/**
 * ControlProvider 组件
 *
 * 【功能说明】
 * 为子组件提供控制面板状态和控制方法
 *
 * 【提供的便捷方法】
 * - startAgent: 启动 Agent
 * - pauseAgent: 暂停 Agent
 * - resumeAgent: 恢复 Agent
 * - stopAgent: 停止 Agent
 * - resetAgent: 重置所有状态
 * - selectModel: 选择模型
 * - setObjective: 设置任务目标
 *
 * @param children 子组件
 */
export function ControlProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(controlReducer, initialState);

  /**
   * 便捷方法实现
   *
   * 【设计说明】
   * 这些方法封装了 dispatch 调用，使组件代码更简洁
   * 例如：startAgent() 代替 dispatch({ type: 'START_AGENT' })
   */
  const startAgent = () => dispatch({ type: 'START_AGENT' });
  const pauseAgent = () => dispatch({ type: 'PAUSE_AGENT' });
  const resumeAgent = () => dispatch({ type: 'RESUME_AGENT' });
  const stopAgent = () => dispatch({ type: 'STOP_AGENT' });
  const resetAgent = () => dispatch({ type: 'RESET_AGENT' });
  const selectModel = (modelId: string) =>
    dispatch({ type: 'SET_MODEL', payload: modelId });
  const setObjective = (objective: string) =>
    dispatch({ type: 'SET_OBJECTIVE', payload: objective });

  return React.createElement(
    ControlContext.Provider,
    {
      value: {
        state,
        dispatch,
        startAgent,
        pauseAgent,
        resumeAgent,
        stopAgent,
        resetAgent,
        selectModel,
        setObjective,
      },
    },
    children
  );
}

/**
 * useControl Hook
 *
 * 【功能说明】
 * 在函数组件中访问控制面板状态和控制方法
 *
 * 【使用示例】
 * ```tsx
 * const ControlButton = () => {
 *   const { state, startAgent, pauseAgent } = useControl();
 *
 *   return (
 *     <button onClick={state.status === 'running' ? pauseAgent : startAgent}>
 *       {state.status === 'running' ? 'Pause' : 'Start'}
 *     </button>
 *   );
 * };
 * ```
 *
 * @throws 如果在 Provider 外使用会抛出错误
 */
export function useControl() {
  const context = useContext(ControlContext);
  if (context === undefined) {
    throw new Error('useControl must be used within a ControlProvider');
  }
  return context;
}

/**
 * Action Creators
 *
 * 【功能说明】
 * 提供创建 action 对象的工厂函数
 *
 * 【使用场景】
 * 当需要在组件外创建 action 时使用，例如中间件、异步操作中
 */
export const controlActions = {
  setStatus: (status: AgentStatus): ControlAction => ({
    type: 'SET_STATUS',
    payload: status,
  }),
  setModel: (modelId: string): ControlAction => ({
    type: 'SET_MODEL',
    payload: modelId,
  }),
  setObjective: (objective: string): ControlAction => ({
    type: 'SET_OBJECTIVE',
    payload: objective,
  }),
  setConnected: (connected: boolean): ControlAction => ({
    type: 'SET_CONNECTED',
    payload: connected,
  }),
  setPaused: (paused: boolean): ControlAction => ({
    type: 'SET_PAUSED',
    payload: paused,
  }),
  startAgent: (): ControlAction => ({ type: 'START_AGENT' }),
  pauseAgent: (): ControlAction => ({ type: 'PAUSE_AGENT' }),
  resumeAgent: (): ControlAction => ({ type: 'RESUME_AGENT' }),
  stopAgent: (): ControlAction => ({ type: 'STOP_AGENT' }),
  resetAgent: (): ControlAction => ({ type: 'RESET_AGENT' }),
  updateState: (updates: Partial<ControlState>): ControlAction => ({
    type: 'UPDATE_STATE',
    payload: updates,
  }),
};
