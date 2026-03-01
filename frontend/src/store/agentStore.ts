/**
 * ================================================================================
 * Agent 状态管理模块 - 管理 Agent 的核心状态
 * ================================================================================
 *
 * 【模块概述】
 * 使用 React Context + useReducer 实现全局状态管理，存储 Agent 的运行状态、
 * 当前步骤、执行动作等信息。
 *
 * 【设计思路】
 * 1. 使用 Context API 实现跨组件状态共享，避免 prop drilling
 * 2. 使用 useReducer 管理复杂状态逻辑，便于追踪状态变化
 * 3. 状态结构与后端保持一致，便于数据同步
 * 4. 提供 Action Creators，规范状态修改方式
 *
 * 【使用示例】
 * ```tsx
 * // 在组件中使用
 * const { state, dispatch } = useAgent();
 *
 * // 更新状态
 * dispatch(actions.setCurrentStep(5));
 * dispatch(actions.updateState({ lastAction: 'Clicked button' }));
 * ```
 * ================================================================================
 */

import React, { createContext, useContext, useReducer } from 'react';
import type { ReactNode } from 'react';
import type { AgentState, AgentStatus, ModelConfig } from '../types';

/**
 * 可用模型列表
 *
 * 【数据来源】
 * 与后端 config.py 中的 AVAILABLE_MODELS 保持一致
 *
 * 【模型说明】
 * - gemini-3-flash-preview: 默认模型，速度快成本低
 * - kimi-k2.5: 中文理解能力强
 * - claude-opus-4-6: 推理能力强，适合复杂任务
 * - doubao-1.6-pro: 多模态能力强
 * - minimax-text-01: 长文本处理能力强
 */
export const AVAILABLE_MODELS: ModelConfig[] = [
  {
    id: 'gemini-3-flash-preview',
    name: 'Gemini 3 Flash Preview',
    description: 'Google Gemini 3 Flash 预览版，速度快，成本低',
    priority: 1,
    tags: ['fast', 'cost-effective', 'general'],
    maxTokens: 8192,
    supportsVision: false,
    supportsAutoSwitch: true,
  },
  {
    id: 'kimi-k2.5',
    name: 'Kimi K2.5',
    description: 'Moonshot Kimi K2.5，中文理解能力强',
    priority: 2,
    tags: ['chinese', 'balanced', 'general'],
    maxTokens: 8192,
    supportsVision: true,
    supportsAutoSwitch: true,
  },
  {
    id: 'claude-opus-4-6',
    name: 'Claude Opus 4.6',
    description: 'Anthropic Claude Opus 4.6，推理能力强，适合复杂任务',
    priority: 3,
    tags: ['reasoning', 'complex-tasks', 'high-quality'],
    maxTokens: 8192,
    supportsVision: true,
    supportsAutoSwitch: false,
  },
  {
    id: 'doubao-1.6-pro',
    name: 'Doubao 1.6 Pro',
    description: '字节跳动豆包 1.6 Pro，多模态能力强',
    priority: 4,
    tags: ['multimodal', 'vision', 'general'],
    maxTokens: 4096,
    supportsVision: true,
    supportsAutoSwitch: true,
  },
  {
    id: 'minimax-text-01',
    name: 'MiniMax Text 01',
    description: 'MiniMax Text 01，长文本处理能力强',
    priority: 5,
    tags: ['long-context', 'general'],
    maxTokens: 8192,
    supportsVision: false,
    supportsAutoSwitch: true,
  },
];

/**
 * Agent 初始状态
 *
 * 【默认值说明】
 * - currentStep: 0 表示尚未开始
 * - maxSteps: 15 默认最大步骤数
 * - status: 初始为 idle 状态
 * - taskComplexity: 默认为 simple
 */
const initialState: AgentState = {
  objective: '',
  currentUrl: '',
  currentStep: 0,
  maxSteps: 15,
  lastAction: 'Waiting to start...',
  stepDescription: 'Agent is ready',
  isDone: false,
  errorMessage: null,
  progressRatio: 0,
  stagnationCount: 0,
  taskComplexity: 'simple',
  popupDetected: false,
  loginFormDetected: false,
};

/**
 * Action 类型定义
 *
 * 【Action 说明】
 * - SET_OBJECTIVE: 设置任务目标
 * - SET_STATUS: 设置 Agent 状态
 * - SET_CURRENT_STEP: 设置当前步骤
 * - SET_MAX_STEPS: 设置最大步骤数
 * - SET_LAST_ACTION: 设置最近动作
 * - SET_STEP_DESCRIPTION: 设置步骤描述
 * - SET_CURRENT_URL: 设置当前 URL
 * - SET_PROGRESS_RATIO: 设置进度比例
 * - SET_ERROR: 设置错误信息
 * - SET_TASK_COMPLEXITY: 设置任务复杂度
 * - SET_POPUP_DETECTED: 设置弹窗检测状态
 * - SET_LOGIN_FORM_DETECTED: 设置登录表单检测状态
 * - RESET_STATE: 重置状态为初始值
 * - UPDATE_STATE: 批量更新状态
 */
export type AgentAction =
  | { type: 'SET_OBJECTIVE'; payload: string }
  | { type: 'SET_STATUS'; payload: AgentStatus }
  | { type: 'SET_CURRENT_STEP'; payload: number }
  | { type: 'SET_MAX_STEPS'; payload: number }
  | { type: 'SET_LAST_ACTION'; payload: string }
  | { type: 'SET_STEP_DESCRIPTION'; payload: string }
  | { type: 'SET_CURRENT_URL'; payload: string }
  | { type: 'SET_PROGRESS_RATIO'; payload: number }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_TASK_COMPLEXITY'; payload: string }
  | { type: 'SET_POPUP_DETECTED'; payload: boolean }
  | { type: 'SET_LOGIN_FORM_DETECTED'; payload: boolean }
  | { type: 'RESET_STATE' }
  | { type: 'UPDATE_STATE'; payload: Partial<AgentState> };

/**
 * Reducer 函数
 *
 * 【功能说明】
 * 根据 action 类型更新状态，遵循 Redux  reducer 模式
 *
 * @param state 当前状态
 * @param action 要执行的动作
 * @returns 新状态
 */
function agentReducer(state: AgentState, action: AgentAction): AgentState {
  switch (action.type) {
    case 'SET_OBJECTIVE':
      return { ...state, objective: action.payload };
    case 'SET_STATUS':
      return { ...state, isDone: action.payload === 'completed' };
    case 'SET_CURRENT_STEP':
      return { ...state, currentStep: action.payload };
    case 'SET_MAX_STEPS':
      return { ...state, maxSteps: action.payload };
    case 'SET_LAST_ACTION':
      return { ...state, lastAction: action.payload };
    case 'SET_STEP_DESCRIPTION':
      return { ...state, stepDescription: action.payload };
    case 'SET_CURRENT_URL':
      return { ...state, currentUrl: action.payload };
    case 'SET_PROGRESS_RATIO':
      return { ...state, progressRatio: action.payload };
    case 'SET_ERROR':
      return { ...state, errorMessage: action.payload };
    case 'SET_TASK_COMPLEXITY':
      return { ...state, taskComplexity: action.payload };
    case 'SET_POPUP_DETECTED':
      return { ...state, popupDetected: action.payload };
    case 'SET_LOGIN_FORM_DETECTED':
      return { ...state, loginFormDetected: action.payload };
    case 'RESET_STATE':
      return initialState;
    case 'UPDATE_STATE':
      return { ...state, ...action.payload };
    default:
      return state;
  }
}

/**
 * Context 类型定义
 */
interface AgentContextType {
  state: AgentState;
  dispatch: React.Dispatch<AgentAction>;
}

/**
 * 创建 Context
 *
 * 【说明】
 * 初始值为 undefined，在 Provider 中设置实际值
 */
const AgentContext = createContext<AgentContextType | undefined>(undefined);

/**
 * AgentProvider 组件
 *
 * 【功能说明】
 * 为子组件提供 Agent 状态上下文
 *
 * @param children 子组件
 */
export function AgentProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(agentReducer, initialState);

  return React.createElement(
    AgentContext.Provider,
    { value: { state, dispatch } },
    children
  );
}

/**
 * useAgent Hook
 *
 * 【功能说明】
 * 在函数组件中访问 Agent 状态和 dispatch 函数
 *
 * 【使用示例】
 * ```tsx
 * const MyComponent = () => {
 *   const { state, dispatch } = useAgent();
 *   return <div>{state.currentStep}</div>;
 * };
 * ```
 *
 * @throws 如果在 Provider 外使用会抛出错误
 */
export function useAgent() {
  const context = useContext(AgentContext);
  if (context === undefined) {
    throw new Error('useAgent must be used within an AgentProvider');
  }
  return context;
}

/**
 * Action Creators
 *
 * 【功能说明】
 * 提供创建 action 对象的工厂函数，规范 action 创建方式
 *
 * 【使用示例】
 * ```tsx
 * dispatch(actions.setCurrentStep(5));
 * dispatch(actions.updateState({ lastAction: 'Clicked' }));
 * ```
 */
export const actions = {
  setObjective: (objective: string): AgentAction => ({
    type: 'SET_OBJECTIVE',
    payload: objective,
  }),
  setStatus: (status: AgentStatus): AgentAction => ({
    type: 'SET_STATUS',
    payload: status,
  }),
  setCurrentStep: (step: number): AgentAction => ({
    type: 'SET_CURRENT_STEP',
    payload: step,
  }),
  setMaxSteps: (steps: number): AgentAction => ({
    type: 'SET_MAX_STEPS',
    payload: steps,
  }),
  setLastAction: (action: string): AgentAction => ({
    type: 'SET_LAST_ACTION',
    payload: action,
  }),
  setStepDescription: (description: string): AgentAction => ({
    type: 'SET_STEP_DESCRIPTION',
    payload: description,
  }),
  setCurrentUrl: (url: string): AgentAction => ({
    type: 'SET_CURRENT_URL',
    payload: url,
  }),
  setProgressRatio: (ratio: number): AgentAction => ({
    type: 'SET_PROGRESS_RATIO',
    payload: ratio,
  }),
  setError: (error: string | null): AgentAction => ({
    type: 'SET_ERROR',
    payload: error,
  }),
  setTaskComplexity: (complexity: string): AgentAction => ({
    type: 'SET_TASK_COMPLEXITY',
    payload: complexity,
  }),
  setPopupDetected: (detected: boolean): AgentAction => ({
    type: 'SET_POPUP_DETECTED',
    payload: detected,
  }),
  setLoginFormDetected: (detected: boolean): AgentAction => ({
    type: 'SET_LOGIN_FORM_DETECTED',
    payload: detected,
  }),
  resetState: (): AgentAction => ({ type: 'RESET_STATE' }),
  updateState: (updates: Partial<AgentState>): AgentAction => ({
    type: 'UPDATE_STATE',
    payload: updates,
  }),
};
