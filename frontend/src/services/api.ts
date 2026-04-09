/**
 * ================================================================================
 * API 服务模块 - 真实后端交互版本
 * ================================================================================
 *
 * 【模块概述】
 * 提供真实的 API 和 WebSocket 客户端，与后端 FastAPI 服务器交互。
 *
 * 【功能说明】
 * 1. HTTP API: 与后端 REST API 交互
 * 2. WebSocket: 实时接收状态更新和命令输出
 *
 * 【设计思路】
 * 1. 使用 fetch API 进行 HTTP 请求
 * 2. 使用原生 WebSocket 进行实时通信
 * 3. 提供类型安全的 API 接口
 * 4. 自动重连机制
 * ================================================================================
 */

import type { AgentState, LogEntry, FileInfo, TaskGroup, FileContentResponse, CustomLlmConfig, CustomLlmConfigInput, ModelConfig } from '../types';

// API 基础 URL
const API_BASE_URL = 'http://localhost:8000';
const WS_BASE_URL = 'ws://localhost:8000/ws';

/**
 * HTTP API 客户端类
 *
 * 【功能说明】
 * 提供与后端 API 交互的方法
 */
class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  /**
   * 发送 HTTP 请求
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const defaultHeaders: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP ${response.status}: ${response.statusText}`);
      }
      
      return await response.json();
    } catch (error) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('无法连接到后端服务器，请确保后端服务已启动 (python web_server.py)');
      }
      throw error;
    }
  }

  /**
   * 启动 Agent
   */
  async startAgent(objective: string, model: string): Promise<{ success: boolean; message: string }> {
    return this.request('/api/agent/start', {
      method: 'POST',
      body: JSON.stringify({ objective, model }),
    });
  }

  /**
   * 暂停 Agent
   */
  async pauseAgent(): Promise<{ success: boolean; message: string }> {
    return this.request('/api/agent/pause', {
      method: 'POST',
    });
  }

  /**
   * 恢复 Agent
   */
  async resumeAgent(): Promise<{ success: boolean; message: string }> {
    return this.request('/api/agent/resume', {
      method: 'POST',
    });
  }

  /**
   * 停止 Agent
   */
  async stopAgent(): Promise<{ success: boolean; message: string }> {
    return this.request('/api/agent/stop', {
      method: 'POST',
    });
  }

  /**
   * 重置 Agent
   */
  async resetAgent(): Promise<{ success: boolean; message: string }> {
    return this.request('/api/agent/reset', {
      method: 'POST',
    });
  }

  /**
   * 获取 Agent 状态
   */
  async getAgentState(): Promise<AgentState> {
    return this.request('/api/agent/state');
  }

  /**
   * 获取最新截图
   */
  async getScreenshot(): Promise<{ screenshot: string; url: string }> {
    return this.request('/api/agent/screenshot');
  }

  /**
   * 获取日志
   */
  async getLogs(limit: number = 50): Promise<LogEntry[]> {
    return this.request(`/api/agent/logs?limit=${limit}`);
  }

  /**
   * 发送用户输入
   */
  async sendUserInput(input: string): Promise<{ success: boolean; message: string }> {
    return this.request('/api/agent/input', {
      method: 'POST',
      body: JSON.stringify({ input }),
    });
  }

  /**
   * 获取终端输出
   */
  async getTerminalOutput(limit: number = 100): Promise<{
    lines: Array<{
      id: string;
      timestamp: string;
      type: string;
      content: string;
    }>;
    total: number;
    waitingForInput: boolean;
    inputPrompt: string;
  }> {
    return this.request(`/api/terminal/output?limit=${limit}`);
  }

  /**
   * 清空终端
   */
  async clearTerminal(): Promise<{ success: boolean; message: string }> {
    return this.request('/api/terminal/clear', {
      method: 'POST',
    });
  }

  /**
   * 获取可用模型列表
   */
  async getAvailableModels(): Promise<ModelConfig[]> {
    return this.request('/api/models');
  }

  async getCustomLlmConfigs(): Promise<{ configs: CustomLlmConfig[] }> {
    return this.request('/api/llm-configs');
  }

  async createCustomLlmConfig(payload: CustomLlmConfigInput): Promise<{ success: boolean; config: CustomLlmConfig }> {
    return this.request('/api/llm-configs', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async updateCustomLlmConfig(configId: string, payload: Partial<CustomLlmConfigInput>): Promise<{ success: boolean; config: CustomLlmConfig }> {
    return this.request(`/api/llm-configs/${configId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  async deleteCustomLlmConfig(configId: string): Promise<{ success: boolean; message: string }> {
    return this.request(`/api/llm-configs/${configId}`, {
      method: 'DELETE',
    });
  }

  /**
   * 健康检查
   */
  async healthCheck(): Promise<{ status: string; version: string; agent_status: string }> {
    return this.request('/api/health');
  }

  /**
   * 执行 python main.py 命令
   */
  async executeCommand(
    objective: string = '',
    url: string = '',
    maxSteps: number = 30,
    model: string = ''
  ): Promise<{ success: boolean; message: string; command?: string }> {
    return this.request('/api/command/execute', {
      method: 'POST',
      body: JSON.stringify({
        objective,
        url,
        max_steps: maxSteps,
        model,
      }),
    });
  }

  /**
   * 停止命令执行
   */
  async stopCommand(): Promise<{ success: boolean; message: string }> {
    return this.request('/api/command/stop', {
      method: 'POST',
    });
  }

  /**
   * 获取命令状态
   */
  async getCommandStatus(): Promise<{
    status: string;
    exit_code: number | null;
    output_count: number;
    duration: number;
    output: string[];
  }> {
    return this.request('/api/command/status');
  }

  /**
   * 获取命令输出
   */
  async getCommandOutput(limit: number = 100): Promise<{
    output: string[];
    total_lines: number;
  }> {
    return this.request(`/api/command/output?limit=${limit}`);
  }

  /**
   * 获取日志文件列表
   */
  async getLogFiles(): Promise<{ files: FileInfo[] }> {
    return this.request('/api/files/logs');
  }

  /**
   * 获取过程文件列表
   */
  async getProcessFiles(): Promise<{ groups: TaskGroup[] }> {
    return this.request('/api/files/process');
  }

  /**
   * 获取所有文件（日志和过程文件）
   */
  async getAllFiles(): Promise<{ groups: TaskGroup[] }> {
    return this.request('/api/files/all');
  }

  /**
   * 获取文件内容
   */
  async getFileContent(filePath: string): Promise<FileContentResponse> {
    const encodedPath = encodeURIComponent(filePath);
    return this.request(`/api/files/content?file_path=${encodedPath}`);
  }
}

/**
 * WebSocket 客户端类
 *
 * 【功能说明】
 * 管理与后端的 WebSocket 连接，接收实时消息
 */
class WebSocketClient {
  private url: string;
  private ws: WebSocket | null = null;
  private messageHandlers: Map<string, ((data: unknown) => void)[]> = new Map();
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 5;
  private reconnectDelay: number = 1000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(url: string) {
    this.url = url;
  }

  /**
   * 连接 WebSocket
   */
  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      console.log('[WebSocket] Already connected or connecting');
      return;
    }

    console.log('[WebSocket] Connecting to', this.url);
    
    try {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = () => {
        console.log('[WebSocket] Connected');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.emit('connected', {});
        this.emit('connection_status', { connected: true });
      };
      
      this.ws.onclose = (event) => {
        console.log('[WebSocket] Disconnected', event.code, event.reason);
        this.isConnected = false;
        this.emit('disconnected', { code: event.code, reason: event.reason });
        this.emit('connection_status', { connected: false });
        
        // 自动重连
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect();
        }
      };
      
      this.ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
        this.emit('error', { message: 'WebSocket connection error' });
      };
      
      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('[WebSocket] Failed to parse message:', error);
        }
      };
    } catch (error) {
      console.error('[WebSocket] Failed to create connection:', error);
      this.scheduleReconnect();
    }
  }

  /**
   * 安排重连
   */
  private scheduleReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    
    console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    
    this.isConnected = false;
    console.log('[WebSocket] Disconnected by client');
  }

  /**
   * 处理接收到的消息
   */
  private handleMessage(message: { type: string; payload?: unknown }): void {
    const { type, payload } = message;
    
    // 触发对应类型的处理器
    this.emit(type, payload);
    
    // 同时触发通用消息事件
    this.emit('message', message);
  }

  /**
   * 发送消息
   */
  send(type: string, payload: unknown = {}): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WebSocket] Cannot send: not connected');
      return;
    }
    
    const message = JSON.stringify({ type, payload });
    this.ws.send(message);
  }

  /**
   * 订阅消息
   */
  on<T = unknown>(event: string, handler: (data: T) => void): () => void {
    if (!this.messageHandlers.has(event)) {
      this.messageHandlers.set(event, []);
    }
    this.messageHandlers.get(event)!.push(handler as (data: unknown) => void);

    // 返回取消订阅函数
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
      handlers.forEach(handler => {
        try {
          handler(data);
        } catch (error) {
          console.error(`[WebSocket] Handler error for event "${event}":`, error);
        }
      });
    }
  }

  /**
   * 检查连接状态
   */
  checkIsConnected(): boolean {
    return this.isConnected && this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  /**
   * 获取连接详情
   */
  getConnectionInfo(): { connected: boolean; url: string; attempts: number } {
    return {
      connected: this.checkIsConnected(),
      url: this.url,
      attempts: this.reconnectAttempts,
    };
  }
}

// 创建并导出实例
export const apiClient = new ApiClient(API_BASE_URL);
export const wsClient = new WebSocketClient(WS_BASE_URL);

// 导出类以便测试
export { ApiClient, WebSocketClient };
