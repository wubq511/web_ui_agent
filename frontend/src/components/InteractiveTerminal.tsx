/**
 * ================================================================================
 * InteractiveTerminal 组件 - 交互式终端窗口
 * ================================================================================
 *
 * 【组件概述】
 * 提供交互式终端界面，用于显示命令输出和接收用户输入。
 *
 * 【功能说明】
 * 1. 显示终端输出行（支持不同类型的颜色区分）
 * 2. 等待用户输入时显示输入框
 * 3. 支持回车提交输入
 * 4. 实时滚动到最新输出
 * 5. 清晰的视觉状态指示
 * ================================================================================
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Loader2, Terminal, AlertCircle, CheckCircle, Info, XCircle } from 'lucide-react';
import { useTerminal } from '../store/terminalStore';
import { apiClient } from '../services/api';
import HudPanel from './HudPanel';
import type { TerminalLine } from '../types';

/**
 * 终端行组件
 */
const TerminalLineItem: React.FC<{ line: TerminalLine }> = ({ line }) => {
  const getLineStyle = () => {
    switch (line.type) {
      case 'error':
        return 'text-red-400 bg-red-500/10';
      case 'warning':
        return 'text-yellow-400 bg-yellow-500/10';
      case 'success':
        return 'text-green-400 bg-green-500/10';
      case 'prompt':
        return 'text-[#00E5FF] bg-cyan-500/10 font-medium';
      case 'input':
        return 'text-blue-400 bg-blue-500/10';
      case 'system':
        return 'text-[#94A3B8] bg-slate-500/10 italic';
      default:
        return 'text-[#94A3B8]';
    }
  };

  const getLineIcon = () => {
    switch (line.type) {
      case 'error':
        return <XCircle className="w-3 h-3 flex-shrink-0" />;
      case 'warning':
        return <AlertCircle className="w-3 h-3 flex-shrink-0" />;
      case 'success':
        return <CheckCircle className="w-3 h-3 flex-shrink-0" />;
      case 'prompt':
        return <Info className="w-3 h-3 flex-shrink-0" />;
      case 'system':
        return <Terminal className="w-3 h-3 flex-shrink-0" />;
      default:
        return null;
    }
  };

  return (
    <div className={`flex items-start gap-2 px-3 py-1.5 ${getLineStyle()}`}>
      {getLineIcon()}
      <span className="text-[10px] text-[#64748B] font-mono flex-shrink-0">
        {line.timestamp}
      </span>
      <span className="text-sm font-mono break-all whitespace-pre-wrap">
        {line.content}
      </span>
    </div>
  );
};

/**
 * 交互式终端组件
 */
const InteractiveTerminal: React.FC = () => {
  const { state, setProcessing, addLine, clearTerminal } = useTerminal();
  const [userInput, setUserInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPassword, setIsPassword] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const terminalRef = useRef<HTMLDivElement>(null);

  const { lines, waitingForInput, inputPrompt, isProcessing } = state;

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [lines]);

  useEffect(() => {
    if (waitingForInput && inputRef.current) {
      inputRef.current.focus();
      const lastLines = lines.slice(-5);
      const recentOutput = lastLines.map(l => l.content.toLowerCase()).join(' ');
      const promptLower = inputPrompt.toLowerCase();
      
      const isPasswordField = 
        promptLower.includes('password') || 
        promptLower.includes('密码') ||
        recentOutput.includes('password') ||
        recentOutput.includes('密码');
      setIsPassword(isPasswordField);
    }
  }, [waitingForInput, inputPrompt, lines]);

  const handleSubmit = useCallback(async () => {
    if (!waitingForInput || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setProcessing(true);

    try {
      const response = await apiClient.sendUserInput(userInput);
      
      if (response.success) {
        setUserInput('');
      } else {
        addLine(`Error: ${response.message}`, 'error');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      addLine(`Failed to submit input: ${errorMessage}`, 'error');
    } finally {
      setIsSubmitting(false);
    }
  }, [userInput, waitingForInput, isSubmitting, setProcessing, addLine]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  return (
    <HudPanel
      title="Interactive Terminal"
      icon={<Terminal className="w-4 h-4" />}
      className="h-full"
      bodyClassName="flex flex-col"
      headerActions={
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
          {isProcessing && (
            <div className="flex items-center gap-1.5 text-xs text-yellow-400">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span className="font-mono">Processing...</span>
            </div>
          )}
          {waitingForInput && (
            <div className="flex items-center gap-1.5 text-xs text-[#00E5FF] animate-pulse">
              <span className="font-mono">Waiting for input</span>
            </div>
          )}
          <button
            onClick={clearTerminal}
            className="text-xs font-mono text-[#64748B] hover:text-[#94A3B8] transition-colors"
          >
            CLEAR
          </button>
        </div>
      }
    >
      <div
        ref={terminalRef}
        className="flex-1 overflow-y-auto bg-transparent font-mono text-sm"
      >
        {lines.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[#475569]">
            <div className="text-center">
              <Terminal className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-xs">Terminal output will appear here</p>
            </div>
          </div>
        ) : (
          <div className="py-2">
            {lines.map((line) => (
              <TerminalLineItem key={line.id} line={line} />
            ))}
          </div>
        )}
      </div>

      {waitingForInput && (
        <div className="border-t border-[#00E5FF]/30 bg-[#00E5FF]/5 p-3">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-[#00E5FF] animate-pulse" />
            <span className="text-xs text-[#00E5FF] font-medium">
              {inputPrompt || 'Please enter your input:'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              type={isPassword ? 'password' : 'text'}
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isPassword ? '••••••••' : 'Type your input...'}
              className="flex-1 min-w-[120px] w-full sm:w-auto px-3 py-2 rounded-lg bg-black/60 border border-[#00E5FF]/30 text-sm text-[#E2E8F0] placeholder-slate-500 focus:outline-none focus:border-[#00E5FF] focus:ring-1 focus:ring-[#00E5FF]/20 transition-all"
              disabled={isSubmitting}
            />
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className={`flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg font-medium text-xs uppercase tracking-wider transition-all duration-200 ${
                isSubmitting
                  ? 'bg-slate-800 text-[#64748B] cursor-not-allowed'
                  : 'bg-gradient-to-r from-[#00E5FF]/80 to-[#00E5FF]/50 text-white hover:from-[#00E5FF] hover:to-[#00E5FF]/80 shadow-lg shadow-[#00E5FF]/25'
              }`}
            >
              {isSubmitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Send className="w-3.5 h-3.5" />
              )}
              Send
            </button>
          </div>
          <p className="text-[10px] text-[#64748B] mt-1.5">
            Press Enter to submit or click Send button
          </p>
        </div>
      )}
    </HudPanel>
  );
};

export default InteractiveTerminal;
