/**
 * ================================================================================
 * 类型定义模块 - Web UI Agent 前端类型系统
 * ================================================================================
 *
 * 【模块概述】
 * 定义整个前端应用使用的 TypeScript 类型，确保类型安全，便于开发和维护。
 *
 * 【设计思路】
 * 1. 集中管理所有类型定义，避免类型分散在各地
 * 2. 与后端 API 数据结构保持一致
 * 3. 使用明确的命名，提高代码可读性
 * ================================================================================
 */

/**
 * Agent 运行状态类型
 *
 * 【状态说明】
 * - idle: 空闲状态，等待用户输入
 * - running: 正在执行任务
 * - paused: 任务被暂停
 * - stopped: 任务被停止
 * - completed: 任务已完成
 * - error: 发生错误
 */
export type AgentStatus = 'idle' | 'running' | 'paused' | 'stopped' | 'completed' | 'error';

/**
 * 日志级别类型
 *
 * 【级别说明】
 * - info: 普通信息
 * - success: 成功信息（绿色显示）
 * - warning: 警告信息（黄色显示）
 * - error: 错误信息（红色显示）
 */
export type LogLevel = 'info' | 'success' | 'warning' | 'error';

/**
 * 日志条目接口
 *
 * 【字段说明】
 * - id: 唯一标识符，用于 React key
 * - timestamp: 时间戳，格式为 HH:MM:SS
 * - level: 日志级别
 * - message: 日志内容
 * - details: 详细信息（可选）
 */
export interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  message: string;
  details?: string;
}

/**
 * 模型配置接口
 *
 * 【字段说明】
 * - id: 模型唯一标识
 * - name: 模型显示名称
 * - description: 模型描述
 * - priority: 优先级（数字越小优先级越高）
 * - tags: 模型特点标签
 * - maxTokens: 最大 token 数
 * - supportsVision: 是否支持视觉
 * - supportsAutoSwitch: 是否支持自动切换
 */
export interface ModelConfig {
  id: string;
  name: string;
  description: string;
  priority: number;
  tags: string[];
  maxTokens: number;
  supportsVision: boolean;
  supportsAutoSwitch: boolean;
}

/**
 * Agent 状态接口
 *
 * 【设计说明】
 * 与后端 AgentState 保持一致，用于存储 Agent 的完整状态
 *
 * 【字段说明】
 * - objective: 任务目标
 * - currentUrl: 当前页面 URL
 * - currentStep: 当前步骤数
 * - maxSteps: 最大步骤数
 * - lastAction: 最近执行的动作
 * - stepDescription: 当前步骤描述
 * - isDone: 是否已完成
 * - errorMessage: 错误信息
 * - progressRatio: 进度比例（0-1）
 * - stagnationCount: 停滞计数
 * - taskComplexity: 任务复杂度
 * - popupDetected: 是否检测到弹窗
 * - loginFormDetected: 是否检测到登录表单
 */
export interface AgentState {
  objective: string;
  currentUrl: string;
  currentStep: number;
  maxSteps: number;
  lastAction: string;
  stepDescription: string;
  isDone: boolean;
  errorMessage: string | null;
  progressRatio: number;
  stagnationCount: number;
  taskComplexity: string;
  popupDetected: boolean;
  loginFormDetected: boolean;
}

/**
 * 控制面板状态接口
 *
 * 【字段说明】
 * - objective: 用户输入的任务目标
 * - selectedModel: 选中的模型 ID
 * - status: 当前 Agent 状态
 */
export interface ControlState {
  objective: string;
  selectedModel: string;
  status: AgentStatus;
}

/**
 * 浏览器视口状态接口
 *
 * 【字段说明】
 * - screenshot: 截图的 base64 数据
 * - url: 当前页面 URL
 * - title: 页面标题
 * - cursorPosition: 鼠标光标位置（百分比坐标）
 */
export interface ViewportState {
  screenshot: string | null;
  url: string;
  title: string;
  cursorPosition: { x: number; y: number } | null;
}

/**
 * WebSocket 消息接口
 *
 * 【消息类型】
 * - state_update: 状态更新
 * - log: 日志消息
 * - screenshot: 截图更新
 * - action: 动作执行
 * - error: 错误信息
 * - status_change: 状态变化
 */
export interface WebSocketMessage {
  type: 'state_update' | 'log' | 'screenshot' | 'action' | 'error' | 'status_change';
  payload: unknown;
  timestamp: string;
}

/**
 * 执行动作接口
 *
 * 【字段说明】
 * - type: 动作类型
 * - description: 动作描述
 * - timestamp: 执行时间
 * - success: 是否成功
 */
export interface Action {
  type: string;
  description: string;
  timestamp: string;
  success: boolean;
}
