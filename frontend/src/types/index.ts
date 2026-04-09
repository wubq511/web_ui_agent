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
 * - error: 发生错误（前端显示为 running）
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
  source?: 'builtin' | 'custom';
  provider?: string;
}

export interface CustomLlmConfig {
  id: string;
  display_name: string;
  provider: string;
  model_name: string;
  base_url: string;
  api_key_masked: string;
  description: string;
  max_tokens: number;
  supports_vision: boolean;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomLlmConfigInput {
  display_name: string;
  provider: string;
  model_name: string;
  base_url: string;
  api_key: string;
  description?: string;
  max_tokens?: number;
  supports_vision?: boolean;
  enabled?: boolean;
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
 * - credentialManagerLoggedIn: 凭证管理器是否已登录
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
  credentialManagerLoggedIn: boolean;
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

/**
 * 终端行类型
 *
 * 【类型说明】
 * - output: 普通输出
 * - error: 错误输出
 * - warning: 警告输出
 * - success: 成功输出
 * - prompt: 输入提示
 * - input: 用户输入
 * - system: 系统消息
 */
export type TerminalLineType = 'output' | 'error' | 'warning' | 'success' | 'prompt' | 'input' | 'system';

/**
 * 终端行接口
 *
 * 【字段说明】
 * - id: 唯一标识符
 * - timestamp: 时间戳
 * - type: 行类型
 * - content: 行内容
 */
export interface TerminalLine {
  id: string;
  timestamp: string;
  type: TerminalLineType;
  content: string;
}

/**
 * 终端状态接口
 *
 * 【字段说明】
 * - lines: 终端输出行
 * - waitingForInput: 是否等待用户输入
 * - inputPrompt: 输入提示信息
 */
export interface TerminalState {
  lines: TerminalLine[];
  waitingForInput: boolean;
  inputPrompt: string;
}

/**
 * 文件信息接口
 *
 * 【字段说明】
 * - name: 文件名
 * - path: 文件完整路径
 * - type: 文件类型 (log, session, performance, action, decision, elements)
 * - size: 文件大小（字节）
 * - modified: 最后修改时间
 * - category: 文件分类 (logs, process, performance)
 */
export interface FileInfo {
  name: string;
  path: string;
  type: string;
  size: number;
  modified: string;
  category: 'logs' | 'process' | 'performance';
}

/**
 * 任务分组接口
 *
 * 【字段说明】
 * - task_id: 任务唯一标识
 * - task_time: 任务时间描述
 * - logs: 日志文件列表
 * - process: 过程文件列表
 * - performance: 性能文件列表
 */
export interface TaskGroup {
  task_id: string;
  task_time: string;
  logs: FileInfo[];
  process: FileInfo[];
  performance: FileInfo[];
}

/**
 * 文件内容响应接口
 *
 * 【字段说明】
 * - content: 文件内容（JSON对象或字符串）
 * - format: 内容格式 (json, text)
 * - size: 文件大小
 * - name: 文件名
 * - type: 文件扩展名
 * - error: 错误信息（可选）
 */
export interface FileContentResponse {
  content: unknown | string | null;
  format: 'json' | 'text';
  size: number;
  name: string;
  type: string;
  error?: string;
}
