/**
 * ================================================================================
 * API 服务模块 - 模拟数据版本（无后端交互）
 * ================================================================================
 *
 * 【模块概述】
 * 提供模拟的 API 和 WebSocket 客户端，用于前端开发和测试。
 * 所有数据都是本地生成的模拟数据，不与后端交互。
 *
 * 【功能说明】
 * 1. 模拟 HTTP API: 返回模拟的成功响应
 * 2. 模拟 WebSocket: 通过定时器模拟实时状态更新
 *
 * 【设计思路】
 * 1. 保持与真实 API 相同的接口，方便后续切换回真实后端
 * 2. 使用定时器模拟 WebSocket 消息推送
 * 3. 提供类型安全的 API 接口
 * ================================================================================
 */

import type { AgentState, LogEntry } from '../types';

// 模拟延迟时间（毫秒）
const MOCK_DELAY = 500;

/**
 * 模拟 HTTP API 客户端类
 *
 * 【功能说明】
 * 提供与真实 API 相同的接口，但返回模拟数据
 */
class ApiClient {
  // baseUrl 保留用于将来可能的扩展
  private _baseUrl: string;

  constructor(baseUrl: string) {
    this._baseUrl = baseUrl;
  }

  /**
   * 模拟延迟
   */
  private delay(ms: number = MOCK_DELAY): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * 启动 Agent（模拟）
   */
  async startAgent(objective: string, model: string): Promise<{ success: boolean; message: string }> {
    await this.delay();
    console.log('[Mock API] startAgent called:', { objective, model });
    return { success: true, message: `Agent started with objective: ${objective}` };
  }

  /**
   * 暂停 Agent（模拟）
   */
  async pauseAgent(): Promise<{ success: boolean; message: string }> {
    await this.delay();
    console.log('[Mock API] pauseAgent called');
    return { success: true, message: 'Agent paused' };
  }

  /**
   * 恢复 Agent（模拟）
   */
  async resumeAgent(): Promise<{ success: boolean; message: string }> {
    await this.delay();
    console.log('[Mock API] resumeAgent called');
    return { success: true, message: 'Agent resumed' };
  }

  /**
   * 停止 Agent（模拟）
   */
  async stopAgent(): Promise<{ success: boolean; message: string }> {
    await this.delay();
    console.log('[Mock API] stopAgent called');
    return { success: true, message: 'Agent stopped' };
  }

  /**
   * 重置 Agent（模拟）
   */
  async resetAgent(): Promise<{ success: boolean; message: string }> {
    await this.delay();
    console.log('[Mock API] resetAgent called');
    return { success: true, message: 'Agent reset' };
  }

  /**
   * 获取 Agent 状态（模拟）
   */
  async getAgentState(): Promise<AgentState> {
    await this.delay();
    return {
      objective: '',
      currentUrl: 'about:blank',
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
  }

  /**
   * 获取最新截图（模拟）
   */
  async getScreenshot(): Promise<{ screenshot: string; url: string }> {
    await this.delay();
    return { screenshot: '', url: 'about:blank' };
  }

  /**
   * 获取日志（模拟）
   */
  async getLogs(_limit: number = 50): Promise<LogEntry[]> {
    await this.delay();
    return [];
  }

  /**
   * 发送用户输入（模拟）
   */
  async sendUserInput(input: string): Promise<{ success: boolean }> {
    await this.delay();
    console.log('[Mock API] sendUserInput called:', input);
    return { success: true };
  }

  /**
   * 获取可用模型列表（模拟）
   */
  async getAvailableModels(): Promise<{ id: string; name: string; description: string }[]> {
    await this.delay();
    return [
      { id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash', description: 'Fast and efficient model' },
      { id: 'gemini-3-pro-preview', name: 'Gemini 3 Pro', description: 'Advanced reasoning model' },
    ];
  }

  /**
   * 健康检查（模拟）
   */
  async healthCheck(): Promise<{ status: string; version: string }> {
    await this.delay();
    return { status: 'healthy', version: '1.0.0-mock' };
  }
}

/**
 * 模拟 WebSocket 客户端类
 *
 * 【功能说明】
 * 模拟 WebSocket 连接，通过定时器推送模拟消息
 */
class WebSocketClient {
  // url 保留用于将来可能的扩展
  private _url: string;
  private messageHandlers: Map<string, ((data: unknown) => void)[]> = new Map();
  private intervalId: number | null = null;
  private isConnected: boolean = false;
  private mockState: {
    status: 'idle' | 'running' | 'paused' | 'stopped' | 'completed';
    currentStep: number;
    maxSteps: number;
    objective: string;
    currentUrl: string;
  } = {
    status: 'idle',
    currentStep: 0,
    maxSteps: 15,
    objective: '',
    currentUrl: 'about:blank',
  };

  constructor(url: string) {
    this._url = url;
  }

  /**
   * 连接 WebSocket（模拟）
   */
  connect(): void {
    console.log('[Mock WebSocket] Connecting...');
    
    // 模拟连接成功
    setTimeout(() => {
      this.isConnected = true;
      console.log('[Mock WebSocket] Connected');
      this.emit('connected', {});
    }, 100);
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this.isConnected = false;
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    console.log('[Mock WebSocket] Disconnected');
  }

  /**
   * 发送消息（模拟）
   */
  send(type: string, payload: unknown): void {
    console.log('[Mock WebSocket] Send:', { type, payload });
    
    // 处理特定消息类型
    if (type === 'ping') {
      this.emit('pong', {});
    }
  }

  /**
   * 订阅消息
   */
  on<T = unknown>(event: string, handler: (data: T) => void): () => void {
    if (!this.messageHandlers.has(event)) {
      this.messageHandlers.set(event, []);
    }
    this.messageHandlers.get(event)!.push(handler as (data: unknown) => void);

    return () => {
      const handlers = this.messageHandlers.get(event);
      if (handlers) {
        const index = handlers.indexOf(handler as (data: unknown) => void);
        if (index > -1) {
          handlers.splice(index, 1);
        }
      }
    };
  }

  /**
   * 触发事件
   */
  private emit(event: string, data: unknown): void {
    const handlers = this.messageHandlers.get(event);
    if (handlers) {
      handlers.forEach(handler => handler(data));
    }
  }

  /**
   * 检查连接状态
   */
  checkIsConnected(): boolean {
    return this.isConnected;
  }

  /**
   * 开始模拟 Agent 运行
   */
  startMockAgent(objective: string): void {
    this.mockState.status = 'running';
    this.mockState.objective = objective;
    this.mockState.currentStep = 0;
    this.mockState.currentUrl = 'https://www.google.com';

    // 发送状态变化
    this.emit('status_change', { status: 'running' });
    
    // 发送初始日志
    this.emit('log', {
      id: `log-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      level: 'success',
      message: `Agent started: ${objective}`,
    });

    // 模拟步骤执行
    this.intervalId = window.setInterval(() => {
      if (this.mockState.status !== 'running') return;
      
      if (this.mockState.currentStep < this.mockState.maxSteps) {
        this.mockState.currentStep++;
        
        // 发送状态更新
        this.emit('state_update', {
          objective: this.mockState.objective,
          currentUrl: this.mockState.currentUrl,
          currentStep: this.mockState.currentStep,
          maxSteps: this.mockState.maxSteps,
          lastAction: `Executing step ${this.mockState.currentStep}`,
          stepDescription: `Step ${this.mockState.currentStep}: Analyzing page...`,
          isDone: false,
          errorMessage: null,
          progressRatio: this.mockState.currentStep / this.mockState.maxSteps,
          stagnationCount: 0,
          taskComplexity: 'simple',
          popupDetected: false,
          loginFormDetected: false,
        });

        // 发送日志
        this.emit('log', {
          id: `log-${Date.now()}`,
          timestamp: new Date().toLocaleTimeString(),
          level: 'info',
          message: `Step ${this.mockState.currentStep}: Analyzing page elements...`,
        });

        // 发送模拟截图
        this.emit('screenshot', {
          screenshot: this.generateMockScreenshot(),
          url: this.mockState.currentUrl,
        });
      } else {
        // 完成
        this.mockState.status = 'completed';
        this.emit('status_change', { status: 'completed' });
        this.emit('log', {
          id: `log-${Date.now()}`,
          timestamp: new Date().toLocaleTimeString(),
          level: 'success',
          message: 'Task completed successfully!',
        });
        
        if (this.intervalId) {
          clearInterval(this.intervalId);
          this.intervalId = null;
        }
      }
    }, 2000);
  }

  /**
   * 暂停模拟 Agent
   */
  pauseMockAgent(): void {
    this.mockState.status = 'paused';
    this.emit('status_change', { status: 'paused' });
    this.emit('log', {
      id: `log-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      level: 'warning',
      message: 'Agent paused by user',
    });
  }

  /**
   * 恢复模拟 Agent
   */
  resumeMockAgent(): void {
    this.mockState.status = 'running';
    this.emit('status_change', { status: 'running' });
    this.emit('log', {
      id: `log-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      level: 'info',
      message: 'Agent resumed',
    });
  }

  /**
   * 停止模拟 Agent
   */
  stopMockAgent(): void {
    this.mockState.status = 'stopped';
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.emit('status_change', { status: 'stopped' });
    this.emit('log', {
      id: `log-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      level: 'warning',
      message: 'Agent stopped by user',
    });
  }

  /**
   * 重置模拟 Agent
   */
  resetMockAgent(): void {
    this.mockState = {
      status: 'idle',
      currentStep: 0,
      maxSteps: 15,
      objective: '',
      currentUrl: 'about:blank',
    };
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.emit('status_change', { status: 'idle' });
    this.emit('log', {
      id: `log-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      level: 'info',
      message: 'Agent reset',
    });
  }

  /**
   * 生成模拟截图（简单的 SVG 图像）
   */
  private generateMockScreenshot(): string {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">
        <rect width="100%" height="100%" fill="#1e293b"/>
        <text x="50%" y="50%" font-family="Arial" font-size="24" fill="#94a3b8" text-anchor="middle">
          Mock Browser View - Step ${this.mockState.currentStep}
        </text>
        <text x="50%" y="60%" font-family="Arial" font-size="16" fill="#64748b" text-anchor="middle">
          ${this.mockState.currentUrl}
        </text>
      </svg>
    `;
    return `data:image/svg+xml;base64,${btoa(svg)}`;
  }
}

// 创建模拟实例
const API_BASE_URL = 'http://localhost:8000';
const WS_BASE_URL = 'ws://localhost:8000/ws';

export const apiClient = new ApiClient(API_BASE_URL);
export const wsClient = new WebSocketClient(WS_BASE_URL);

// 导出类以便测试
export { ApiClient, WebSocketClient };
