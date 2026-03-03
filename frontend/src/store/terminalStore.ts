/**
 * ================================================================================
 * 终端状态管理模块 - 管理交互式终端的状态
 * ================================================================================
 *
 * 【模块概述】
 * 管理交互式终端的状态，包括终端输出行、等待输入状态、输入提示等。
 *
 * 【设计思路】
 * 1. 维护终端输出行的列表
 * 2. 跟踪是否等待用户输入
 * 3. 提供添加行、清空终端等操作
 * 4. 与 WebSocket 消息同步
 *
 * 【状态流转】
 * 正常输出 -> 检测到输入提示 -> 等待输入 -> 用户提交 -> 继续输出
 * ================================================================================
 */

import React, { createContext, useContext, useReducer, useCallback } from 'react';
import type { ReactNode } from 'react';
import type { TerminalLine, TerminalLineType } from '../types';

/**
 * 终端状态接口
 */
interface TerminalState {
  lines: TerminalLine[];
  waitingForInput: boolean;
  inputPrompt: string;
  isProcessing: boolean;
}

/**
 * 初始状态
 */
const initialState: TerminalState = {
  lines: [],
  waitingForInput: false,
  inputPrompt: '',
  isProcessing: false,
};

/**
 * Action 类型定义
 */
export type TerminalAction =
  | { type: 'ADD_LINE'; payload: { line: TerminalLine } }
  | { type: 'SET_WAITING_FOR_INPUT'; payload: { waiting: boolean; prompt: string } }
  | { type: 'SET_PROCESSING'; payload: boolean }
  | { type: 'CLEAR_TERMINAL' }
  | { type: 'SET_LINES'; payload: TerminalLine[] };

/**
 * Reducer 函数
 */
function terminalReducer(state: TerminalState, action: TerminalAction): TerminalState {
  switch (action.type) {
    case 'ADD_LINE':
      return {
        ...state,
        lines: [...state.lines, action.payload.line].slice(-500),
      };
    case 'SET_WAITING_FOR_INPUT':
      return {
        ...state,
        waitingForInput: action.payload.waiting,
        inputPrompt: action.payload.prompt,
        isProcessing: false,
      };
    case 'SET_PROCESSING':
      return {
        ...state,
        isProcessing: action.payload,
      };
    case 'CLEAR_TERMINAL':
      return {
        ...initialState,
      };
    case 'SET_LINES':
      return {
        ...state,
        lines: action.payload.slice(-500),
      };
    default:
      return state;
  }
}

/**
 * Context 类型定义
 */
interface TerminalContextType {
  state: TerminalState;
  dispatch: React.Dispatch<TerminalAction>;
  addLine: (content: string, lineType: TerminalLineType) => void;
  setWaitingForInput: (waiting: boolean, prompt?: string) => void;
  setProcessing: (processing: boolean) => void;
  clearTerminal: () => void;
}

/**
 * 创建 Context
 */
const TerminalContext = createContext<TerminalContextType | undefined>(undefined);

/**
 * TerminalProvider 组件
 */
export function TerminalProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(terminalReducer, initialState);

  const addLine = useCallback((content: string, lineType: TerminalLineType) => {
    const line: TerminalLine = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
      type: lineType,
      content,
    };
    dispatch({ type: 'ADD_LINE', payload: { line } });
  }, []);

  const setWaitingForInput = useCallback((waiting: boolean, prompt: string = '') => {
    dispatch({ type: 'SET_WAITING_FOR_INPUT', payload: { waiting, prompt } });
  }, []);

  const setProcessing = useCallback((processing: boolean) => {
    dispatch({ type: 'SET_PROCESSING', payload: processing });
  }, []);

  const clearTerminal = useCallback(() => {
    dispatch({ type: 'CLEAR_TERMINAL' });
  }, []);

  return React.createElement(
    TerminalContext.Provider,
    {
      value: {
        state,
        dispatch,
        addLine,
        setWaitingForInput,
        setProcessing,
        clearTerminal,
      },
    },
    children
  );
}

/**
 * useTerminal Hook
 */
export function useTerminal() {
  const context = useContext(TerminalContext);
  if (context === undefined) {
    throw new Error('useTerminal must be used within a TerminalProvider');
  }
  return context;
}

/**
 * Action Creators
 */
export const terminalActions = {
  addLine: (line: TerminalLine): TerminalAction => ({
    type: 'ADD_LINE',
    payload: { line },
  }),
  setWaitingForInput: (waiting: boolean, prompt: string = ''): TerminalAction => ({
    type: 'SET_WAITING_FOR_INPUT',
    payload: { waiting, prompt },
  }),
  setProcessing: (processing: boolean): TerminalAction => ({
    type: 'SET_PROCESSING',
    payload: processing,
  }),
  clearTerminal: (): TerminalAction => ({
    type: 'CLEAR_TERMINAL',
  }),
  setLines: (lines: TerminalLine[]): TerminalAction => ({
    type: 'SET_LINES',
    payload: lines,
  }),
};
