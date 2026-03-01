/**
 * LogPanel组件
 * 日志面板：显示Agent的执行日志
 */

import React, { useRef, useEffect } from 'react';
import {
  ScrollText,
  Trash2,
  RefreshCw,
  Info,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  List,
} from 'lucide-react';
import { useLogs } from '../store/logStore';
import type { LogLevel } from '../types';

const LogPanel: React.FC = () => {
  const { state, clearLogs } = useLogs();
  const logsEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到最新日志
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [state.logs]);

  // 获取日志级别图标
  const getLogIcon = (level: LogLevel) => {
    switch (level) {
      case 'success':
        return <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />;
      case 'warning':
        return <AlertTriangle className="w-3.5 h-3.5 text-yellow-400" />;
      case 'error':
        return <XCircle className="w-3.5 h-3.5 text-red-400" />;
      case 'info':
      default:
        return <Info className="w-3.5 h-3.5 text-blue-400" />;
    }
  };

  // 获取日志级别样式
  const getLogStyle = (level: LogLevel) => {
    switch (level) {
      case 'success':
        return 'border-l-green-500/50 bg-green-500/5';
      case 'warning':
        return 'border-l-yellow-500/50 bg-yellow-500/5';
      case 'error':
        return 'border-l-red-500/50 bg-red-500/5';
      case 'info':
      default:
        return 'border-l-blue-500/50 bg-blue-500/5';
    }
  };

  // 获取日志级别标签
  const getLogLabel = (level: LogLevel) => {
    switch (level) {
      case 'success':
        return (
          <span className="text-[10px] font-medium text-green-400">SUCCESS</span>
        );
      case 'warning':
        return (
          <span className="text-[10px] font-medium text-yellow-400">WARN</span>
        );
      case 'error':
        return (
          <span className="text-[10px] font-medium text-red-400">ERROR</span>
        );
      case 'info':
      default:
        return (
          <span className="text-[10px] font-medium text-blue-400">INFO</span>
        );
    }
  };

  return (
    <div className="glass rounded-xl p-4 border border-white/10 flex flex-col h-full">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ScrollText className="w-4 h-4 text-blue-400" />
          <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
            Action Log
          </h3>
          <span className="text-xs text-slate-500">({state.logs.length})</span>
        </div>

        <div className="flex items-center gap-1">
          {/* 刷新按钮 */}
          <button
            onClick={() => window.location.reload()}
            className="p-1.5 rounded-md hover:bg-white/5 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
          </button>

          {/* 清空按钮 */}
          <button
            onClick={clearLogs}
            className="p-1.5 rounded-md hover:bg-white/5 transition-colors"
            title="Clear logs"
          >
            <Trash2 className="w-3.5 h-3.5 text-slate-500" />
          </button>
        </div>
      </div>

      {/* 日志列表 */}
      <div className="flex-1 overflow-y-auto min-h-0 -mx-4 px-4">
        {state.logs.length === 0 ? (
          // 空状态
          <div className="flex flex-col items-center justify-center h-32 text-slate-600">
            <List className="w-8 h-8 mb-2 opacity-50" />
            <p className="text-xs text-slate-500">No logs yet</p>
            <p className="text-[10px] text-slate-600 mt-1">
              Start the agent to see logs
            </p>
          </div>
        ) : (
          <div className="space-y-1.5">
            {state.logs.map((log, index) => (
              <div
                key={log.id}
                className={`group flex items-start gap-2 p-2.5 rounded-lg border-l-2 ${getLogStyle(
                  log.level
                )} hover:bg-white/5 transition-all animate-slide-up`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {/* 图标 */}
                <div className="flex-shrink-0 mt-0.5">{getLogIcon(log.level)}</div>

                {/* 内容 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    {getLogLabel(log.level)}
                    <span className="text-[10px] text-slate-500">
                      {log.timestamp}
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed break-words">
                    {log.message || <span className="text-slate-500 italic">No message content</span>}
                  </p>
                  {log.details && (
                    <p className="text-[10px] text-slate-500 mt-1 line-clamp-2">
                      {log.details}
                    </p>
                  )}
                </div>
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        )}
      </div>

      {/* 底部统计 */}
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-white/5">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-blue-400" />
            <span className="text-[10px] text-slate-500">
              {state.logs.filter((l) => l.level === 'info').length}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
            <span className="text-[10px] text-slate-500">
              {state.logs.filter((l) => l.level === 'success').length}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-yellow-400" />
            <span className="text-[10px] text-slate-500">
              {state.logs.filter((l) => l.level === 'warning').length}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-red-400" />
            <span className="text-[10px] text-slate-500">
              {state.logs.filter((l) => l.level === 'error').length}
            </span>
          </div>
        </div>

        <span className="text-[10px] text-slate-600">
          Max {state.maxLogs} logs
        </span>
      </div>
    </div>
  );
};

export default LogPanel;
