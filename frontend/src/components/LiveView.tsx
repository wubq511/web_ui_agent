/**
 * ================================================================================
 * LiveView 组件 - 浏览器实时视口
 * ================================================================================
 *
 * 【组件概述】
 * 实时显示浏览器页面截图，让用户可以看到 Agent 的操作过程。
 * 通过 WebSocket 接收后端推送的截图流。
 *
 * 【功能说明】
 * - 接收 WebSocket 实时截图流
 * - 显示当前页面 URL
 * - 支持全屏模式
 * - 显示加载状态和帧率信息
 * ================================================================================
 */

import React, { useState, useEffect, useRef } from 'react';
import { Monitor, Maximize2, Minimize2, ExternalLink, Image as ImageIcon, RefreshCw } from 'lucide-react';
import { wsClient } from '../services/api';

const LiveView: React.FC = () => {
  // 截图数据
  const [screenshot, setScreenshot] = useState<string | null>(null);
  // 当前 URL
  const [currentUrl, setCurrentUrl] = useState<string>('about:blank');
  // 是否全屏
  const [isFullscreen, setIsFullscreen] = useState(false);
  // 是否加载中
  const [isLoading, setIsLoading] = useState(false);
  // 最后更新时间
  const [lastUpdate, setLastUpdate] = useState<string>('');
  // 帧率显示
  const [fps, setFps] = useState<number>(0);
  // 连接状态
  const [isConnected, setIsConnected] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const frameCountRef = useRef<number>(0);
  const lastFpsUpdateRef = useRef<number>(Date.now());

  /**
   * 订阅 WebSocket 截图消息
   */
  useEffect(() => {
    // 订阅截图更新
    const unsubscribe = wsClient.on(
      'screenshot',
      (data: { screenshot: string; url: string; timestamp?: string }) => {
        if (data.screenshot) {
          setScreenshot(data.screenshot);
          setIsLoading(false);
          setLastUpdate(new Date().toLocaleTimeString());
          
          // 计算帧率
          frameCountRef.current++;
          const now = Date.now();
          if (now - lastFpsUpdateRef.current >= 1000) {
            setFps(frameCountRef.current);
            frameCountRef.current = 0;
            lastFpsUpdateRef.current = now;
          }
        }
        if (data.url) {
          setCurrentUrl(data.url);
        }
      }
    );

    // 订阅连接状态
    const unsubConnection = wsClient.on('connection_status', (data: { connected: boolean }) => {
      setIsConnected(data.connected);
    });

    return () => {
      unsubscribe();
      unsubConnection();
    };
  }, []);

  // 切换全屏
  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  // 打开当前 URL
  const openUrl = () => {
    if (currentUrl && currentUrl !== 'about:blank') {
      window.open(currentUrl, '_blank');
    }
  };

  return (
    <div
      ref={containerRef}
      className={`flex flex-col ${
        isFullscreen
          ? 'fixed inset-0 z-[100] bg-slate-950/95 backdrop-blur-xl p-6'
          : 'h-full'
      }`}
    >
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Monitor className="w-4 h-4 text-blue-400" />
          <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
            Live View
          </h3>
          {/* 连接状态指示器 */}
          <div className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] ${
            isConnected 
              ? 'bg-green-500/20 text-green-400' 
              : 'bg-red-500/20 text-red-400'
          }`}>
            <div className={`w-1.5 h-1.5 rounded-full ${
              isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'
            }`} />
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
          {/* 帧率显示 */}
          {fps > 0 && (
            <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-400">
              {fps} FPS
            </span>
          )}
          {lastUpdate && (
            <span className="text-[10px] text-slate-500">
              Updated: {lastUpdate}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* URL显示 */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-800/50 border border-white/5 max-w-xs">
            <span className="text-xs text-slate-400 truncate">
              {currentUrl || 'about:blank'}
            </span>
            <button
              onClick={openUrl}
              className="p-1 rounded hover:bg-white/5 transition-colors"
              title="Open in new tab"
            >
              <ExternalLink className="w-3 h-3 text-slate-500 hover:text-slate-300" />
            </button>
          </div>

          {/* 全屏按钮 */}
          <button
            onClick={toggleFullscreen}
            className="p-2 rounded-lg bg-slate-800/50 border border-white/5 hover:bg-slate-700/50 hover:border-white/10 transition-all"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? (
              <Minimize2 className="w-4 h-4 text-slate-400" />
            ) : (
              <Maximize2 className="w-4 h-4 text-slate-400" />
            )}
          </button>
        </div>
      </div>

      {/* 视口内容 */}
      <div className="flex-1 relative rounded-xl overflow-hidden bg-slate-900 border border-white/10 shadow-2xl">
        {/* 浏览器窗口装饰 */}
        <div className="absolute top-0 left-0 right-0 h-8 bg-slate-800/80 border-b border-white/5 flex items-center px-3 gap-2 z-10">
          {/* 窗口控制按钮 */}
          <div className="flex gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
          </div>
          {/* 地址栏 */}
          <div className="flex-1 mx-4">
            <div className="h-5 rounded bg-slate-700/50 flex items-center px-2">
              <span className="text-[10px] text-slate-500 truncate">
                {currentUrl || 'about:blank'}
              </span>
            </div>
          </div>
        </div>

        {/* 截图显示区域 */}
        <div className="absolute inset-0 top-8 flex items-center justify-center bg-slate-950">
          {screenshot ? (
            <>
              {/* 加载指示器 */}
              {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-950/50 z-10">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
                    <span className="text-xs text-slate-500">Loading...</span>
                  </div>
                </div>
              )}

              {/* 截图图片 */}
              <img
                src={screenshot}
                alt="Browser Screenshot"
                className="max-w-full max-h-full object-contain"
                onLoad={() => setIsLoading(false)}
              />
            </>
          ) : (
            /* 空状态 */
            <div className="flex flex-col items-center gap-4 text-slate-600">
              <div className="w-16 h-16 rounded-2xl bg-slate-800/50 flex items-center justify-center border border-white/5">
                <ImageIcon className="w-8 h-8 text-slate-500" />
              </div>
              <div className="text-center">
                <p className="text-sm text-slate-500">No screenshot available</p>
                <p className="text-xs text-slate-600 mt-1">
                  Start the agent to see live view
                </p>
              </div>
              {!isConnected && (
                <div className="flex items-center gap-2 text-xs text-yellow-500 mt-2">
                  <RefreshCw className="w-3 h-3 animate-spin" />
                  Waiting for connection...
                </div>
              )}
            </div>
          )}
        </div>

        {/* 状态覆盖层 */}
        <div className="absolute bottom-4 right-4 flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-slate-900/80 border border-white/10 backdrop-blur-sm">
            <div className={`w-1.5 h-1.5 rounded-full ${
              isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'
            }`} />
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">
              {isConnected ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
        </div>
      </div>

      {/* 全屏时的关闭按钮 */}
      {isFullscreen && (
        <button
          onClick={toggleFullscreen}
          className="absolute top-6 right-6 p-2 rounded-lg bg-slate-800/80 border border-white/10 hover:bg-slate-700/80 transition-all z-50"
        >
          <Minimize2 className="w-5 h-5 text-slate-400" />
        </button>
      )}
    </div>
  );
};

export default LiveView;
