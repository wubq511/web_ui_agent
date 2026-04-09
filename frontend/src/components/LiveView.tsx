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
import { MonitorPlay, Maximize2, Minimize2, ExternalLink, RefreshCw } from 'lucide-react';
import { wsClient } from '../services/api';
import HudPanel from './HudPanel';

const LiveView: React.FC = () => {
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [currentUrl, setCurrentUrl] = useState<string>('about:blank');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  
  const [fps, setFps] = useState<number>(0);
  const [isConnected, setIsConnected] = useState(false);

  
  const frameCountRef = useRef<number>(0);
  const lastFpsUpdateRef = useRef<number>(Date.now());

  useEffect(() => {
    const unsubscribe = wsClient.on(
      'screenshot',
      (data: { screenshot: string; url: string; timestamp?: string }) => {
        if (data.screenshot) {
          setScreenshot(data.screenshot);
          setIsLoading(false);
          
          
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

    const unsubConnection = wsClient.on('connection_status', (data: { connected: boolean }) => {
      setIsConnected(data.connected);
    });

    return () => {
      unsubscribe();
      unsubConnection();
    };
  }, []);

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  const openUrl = () => {
    if (currentUrl && currentUrl !== 'about:blank') {
      window.open(currentUrl, '_blank');
    }
  };

  const headerActions = (
    <div className="flex items-center gap-2 md:gap-4">
      {fps > 0 && (
        <span className="font-mono text-[10px] text-[#00FFA3]">
          {fps} FPS
        </span>
      )}
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] text-[#94A3B8] max-w-[120px] md:max-w-[200px] truncate" title={currentUrl}>
          {currentUrl || 'about:blank'}
        </span>
        <button
          onClick={openUrl}
          className="text-[#94A3B8] hover:text-[#00E5FF] transition-colors"
          title="Open in new tab"
        >
          <ExternalLink size={12} />
        </button>
      </div>
      <button
        onClick={toggleFullscreen}
        className="text-[#94A3B8] hover:text-[#00E5FF] transition-colors ml-2"
        title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
      >
        {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
      </button>
    </div>
  );

  return (
    <HudPanel 
      title="LIVE FEED" 
      icon={<MonitorPlay size={16} />} 
      className={`flex-1 ${isFullscreen ? 'fixed inset-4 z-[100]' : ''}`}
      bodyClassName="p-4"
      headerActions={headerActions}
    >
      <div className="absolute inset-4 border border-[#1a1e2b] bg-[#050507] flex items-center justify-center overflow-hidden group">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,229,255,0.05),transparent)]" />
        
        {screenshot ? (
          <>
            {isLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/50 z-10">
                <div className="w-8 h-8 border-2 border-[#00E5FF]/30 border-t-[#00E5FF] rounded-full animate-spin" />
              </div>
            )}
            <img
              src={screenshot}
              alt="Browser Screenshot"
              className="max-w-full max-h-full object-contain relative z-10"
              onLoad={() => setIsLoading(false)}
            />
          </>
        ) : (
          <div className="text-center relative z-10">
            <MonitorPlay className="mx-auto mb-4 text-[#1a1e2b] group-hover:text-[#00E5FF]/50 transition-colors" size={48} />
            <p className="font-mono text-xs text-[#94A3B8]">
              {isConnected ? 'AWAITING VIDEO STREAM...' : 'OFFLINE'}
            </p>
            {!isConnected && (
              <div className="flex items-center justify-center gap-2 text-[10px] text-[#FF3366] mt-2 font-mono">
                <RefreshCw className="w-3 h-3 animate-spin" />
                WAITING FOR CONNECTION
              </div>
            )}
          </div>
        )}

        <div className="absolute top-4 left-4 w-4 h-4 border-t border-l border-[#00E5FF]/30 pointer-events-none" />
        <div className="absolute top-4 right-4 w-4 h-4 border-t border-r border-[#00E5FF]/30 pointer-events-none" />
        <div className="absolute bottom-4 left-4 w-4 h-4 border-b border-l border-[#00E5FF]/30 pointer-events-none" />
        <div className="absolute bottom-4 right-4 w-4 h-4 border-b border-r border-[#00E5FF]/30 pointer-events-none" />
      </div>
    </HudPanel>
  );
};

export default LiveView;
