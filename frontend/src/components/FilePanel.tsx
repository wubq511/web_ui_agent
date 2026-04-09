/**
 * FilePanel组件
 * 文件面板：展示日志文件和过程记录文件
 * 
 * 【功能说明】
 * 1. 按任务分组展示文件列表
 * 2. 同一任务的日志和过程文件放在一起
 * 3. 支持点击文件查看内容
 * 4. 文件类型视觉区分
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  FolderOpen,
  FileText,
  FileJson,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  X,
  FileCode,
  Activity,
  Brain,
  MousePointerClick,
  FileSearch,
  Loader2,
  XCircle,
  Folder,
  File,
} from 'lucide-react';
import { apiClient } from '../services/api';
import HudPanel from './HudPanel';
import type { TaskGroup, FileInfo, FileContentResponse } from '../types';

const FilePanel: React.FC = () => {
  const [groups, setGroups] = useState<TaskGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [selectedFile, setSelectedFile] = useState<FileInfo | null>(null);
  const [fileContent, setFileContent] = useState<FileContentResponse | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.getAllFiles();
      setGroups(response.groups || []);
      
      if (response.groups?.[0]?.task_id) {
        setExpandedTasks(new Set([response.groups[0].task_id]));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load files');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const toggleTask = (taskId: string) => {
    setExpandedTasks(prev => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  };

  const toggleCategory = (key: string) => {
    setExpandedCategories(prev => {
      const newSet = new Set(prev);
      if (newSet.has(key)) {
        newSet.delete(key);
      } else {
        newSet.add(key);
      }
      return newSet;
    });
  };

  const handleFileClick = async (file: FileInfo) => {
    setSelectedFile(file);
    setContentLoading(true);
    setFileContent(null);
    
    try {
      const content = await apiClient.getFileContent(file.path);
      setFileContent(content);
    } catch (err) {
      setFileContent({
        content: err instanceof Error ? err.message : 'Failed to load file content',
        format: 'text',
        size: 0,
        name: file.name,
        type: file.type,
        error: 'Failed to load file content'
      });
    } finally {
      setContentLoading(false);
    }
  };

  const closeFileViewer = () => {
    setSelectedFile(null);
    setFileContent(null);
  };

  const getFileIcon = (type: string) => {
    switch (type) {
      case 'log':
        return <FileText className="w-4 h-4 text-blue-400" />;
      case 'session':
        return <FileCode className="w-4 h-4 text-purple-400" />;
      case 'performance':
        return <Activity className="w-4 h-4 text-yellow-400" />;
      case 'action':
        return <MousePointerClick className="w-4 h-4 text-green-400" />;
      case 'decision':
        return <Brain className="w-4 h-4 text-orange-400" />;
      case 'elements':
        return <FileSearch className="w-4 h-4 text-[#00E5FF]" />;
      case 'json':
        return <FileJson className="w-4 h-4 text-pink-400" />;
      case 'test':
        return <FileText className="w-4 h-4 text-emerald-400" />;
      default:
        return <File className="w-4 h-4 text-[#94A3B8]" />;
    }
  };

  const getFileTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      log: 'LOG',
      session: 'SESSION',
      performance: 'PERF',
      action: 'ACTION',
      decision: 'DECISION',
      elements: 'ELEMENTS',
      json: 'JSON',
      test: 'TEST',
    };
    return labels[type] || 'FILE';
  };

  const getFileTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      log: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
      session: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
      performance: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
      action: 'text-green-400 bg-green-500/10 border-green-500/30',
      decision: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
      elements: 'text-[#00E5FF] bg-cyan-500/10 border-[#00E5FF]/30',
      json: 'text-pink-400 bg-pink-500/10 border-pink-500/30',
      test: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
    };
    return colors[type] || 'text-[#94A3B8] bg-slate-500/10 border-slate-500/30';
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const renderContent = () => {
    if (!fileContent) return null;
    
    if (fileContent.error) {
      return (
        <div className="text-red-400 text-sm p-4">
          {fileContent.error}
        </div>
    );
  }

    if (fileContent.format === 'json' && typeof fileContent.content === 'object') {
      return (
        <pre className="text-xs text-[#94A3B8] overflow-auto max-h-[60vh] p-4 bg-black/40 rounded-lg">
          {JSON.stringify(fileContent.content, null, 2)}
        </pre>
      );
    }

    return (
      <pre className="text-xs text-[#94A3B8] overflow-auto max-h-[60vh] p-4 bg-black/40 rounded-lg whitespace-pre-wrap break-words">
        {String(fileContent.content)}
      </pre>
    );
  };

  const renderFileItem = (file: FileInfo) => (
    <button
      key={file.path}
      onClick={() => handleFileClick(file)}
      className="w-full flex items-center gap-2 p-2 pl-10 hover:bg-[#00E5FF]/10 transition-colors text-left border-b border-[#1a1e2b] last:border-b-0"
    >
      {getFileIcon(file.type)}
      <div className="flex-1 min-w-0">
        <p className="text-xs text-[#94A3B8] truncate">
          {file.name}
        </p>
        <div className="flex items-center gap-2 mt-0.5">
          <span className={`text-[9px] px-1 py-0.5 rounded ${getFileTypeColor(file.type)}`}>
            {getFileTypeLabel(file.type)}
          </span>
          <span className="text-[9px] text-[#64748B]">
            {formatFileSize(file.size)}
          </span>
        </div>
      </div>
    </button>
  );

  const renderCategory = (
    category: 'logs' | 'process' | 'performance',
    files: FileInfo[],
    taskId: string
  ) => {
    if (files.length === 0) return null;
    
    const categoryKey = `${taskId}-${category}`;
    const isExpanded = expandedCategories.has(categoryKey);
    
    let categoryIcon;
    let categoryLabel;
    let categoryColor;
    
    if (category === 'logs') {
      categoryIcon = <FileText className="w-3.5 h-3.5 text-blue-400" />;
      categoryLabel = 'Logs';
      categoryColor = 'text-blue-400';
    } else if (category === 'process') {
      categoryIcon = <Folder className="w-3.5 h-3.5 text-green-400" />;
      categoryLabel = 'Process';
      categoryColor = 'text-green-400';
    } else {
      categoryIcon = <Activity className="w-3.5 h-3.5 text-yellow-400" />;
      categoryLabel = 'Performance';
      categoryColor = 'text-yellow-400';
    }
    
    return (
      <div className="border-t border-[#1a1e2b]">
        <button
          onClick={() => toggleCategory(categoryKey)}
          className="w-full flex items-center gap-2 p-2 pl-6 hover:bg-[#00E5FF]/10 transition-colors text-left"
        >
          {isExpanded ? (
            <ChevronDown className="w-3 h-3 text-[#64748B]" />
          ) : (
            <ChevronRight className="w-3 h-3 text-[#64748B]" />
          )}
          {categoryIcon}
          <span className={`text-[11px] font-medium ${categoryColor}`}>
            {categoryLabel}
          </span>
          <span className="text-[10px] text-[#64748B] bg-slate-700/50 px-1.5 py-0.5 rounded ml-auto">
            {files.length}
          </span>
        </button>
        
        {isExpanded && (
          <div className="border-t border-[#1a1e2b]">
            {files.map(renderFileItem)}
          </div>
        )}
      </div>
    );
  };

  const totalFiles = groups.reduce((acc, g) => acc + g.logs.length + g.process.length + g.performance.length, 0);

  if (selectedFile) {
    return (
      <HudPanel
      title="File Viewer"
      icon={<FileText className="w-4 h-4" />}
      className="h-full"
      bodyClassName="flex flex-col p-4"
      headerActions={
        <button
          onClick={closeFileViewer}
          className="p-1.5 rounded-md hover:bg-[#00E5FF]/10 transition-colors"
        >
          <X className="w-4 h-4 text-[#64748B]" />
        </button>
      }
    >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <button
              onClick={closeFileViewer}
              className="p-1 rounded hover:bg-[#00E5FF]/10 transition-colors flex-shrink-0"
            >
              <ChevronRight className="w-4 h-4 text-[#00E5FF] rotate-180" />
            </button>
            {getFileIcon(selectedFile.type)}
            <span className="text-sm font-medium text-[#E2E8F0] font-mono truncate">
              {selectedFile.name}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 mb-3 text-[10px] text-[#64748B]">
          <span className={`px-1.5 py-0.5 rounded border ${getFileTypeColor(selectedFile.type)}`}>
            {getFileTypeLabel(selectedFile.type)}
          </span>
          <span>{formatFileSize(selectedFile.size)}</span>
          <span>{selectedFile.modified}</span>
        </div>

        <div className="flex-1 overflow-hidden">
          {contentLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />
            </div>
          ) : (
            renderContent()
          )}
        </div>
      </HudPanel>
    );
  }

  return (
    <HudPanel
      title="File Explorer"
      icon={<FolderOpen className="w-4 h-4" />}
      className="h-full"
      bodyClassName="flex flex-col p-4"
      headerActions={
        <button
          onClick={fetchFiles}
          disabled={loading}
          className="p-1.5 rounded-md hover:bg-[#00E5FF]/10 transition-colors disabled:opacity-50"
          title="Refresh files"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-[#00E5FF] ${loading ? 'animate-spin' : ''}`} />
        </button>
      }
    >
      <div className="flex items-center justify-between mb-3 border-b border-[#1a1e2b] pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-[#94A3B8] font-mono">
            {totalFiles} FILES SCANNED
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 -mx-4 px-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-32">
            <Loader2 className="w-6 h-6 text-blue-400 animate-spin mb-2" />
            <p className="text-xs text-[#64748B]">Loading files...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-32 text-red-400">
            <XCircle className="w-8 h-8 mb-2 opacity-50" />
            <p className="text-xs">{error}</p>
          </div>
        ) : groups.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-[#475569]">
            <FolderOpen className="w-8 h-8 mb-2 opacity-50" />
            <p className="text-xs text-[#64748B]">No files found</p>
            <p className="text-[10px] text-[#475569] mt-1">
              Run the agent to generate files
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {groups.map(group => (
              <div key={group.task_id} className="rounded-lg border border-[#1a1e2b] overflow-hidden">
                <button
                  onClick={() => toggleTask(group.task_id)}
                  className="w-full flex items-center gap-2 p-2.5 hover:bg-[#00E5FF]/10 transition-colors text-left"
                >
                  {expandedTasks.has(group.task_id) ? (
                    <ChevronDown className="w-4 h-4 text-[#94A3B8]" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-[#94A3B8]" />
                  )}
                  <span className="text-xs font-medium text-[#94A3B8] truncate flex-1">
                    {group.task_time}
                  </span>
                  <span className="text-[10px] text-[#64748B] bg-slate-700/50 px-1.5 py-0.5 rounded">
                    {group.logs.length + group.process.length + group.performance.length}
                  </span>
                </button>

                {expandedTasks.has(group.task_id) && (
                  <>
                    {renderCategory('logs', group.logs, group.task_id)}
                    {renderCategory('process', group.process, group.task_id)}
                    {renderCategory('performance', group.performance, group.task_id)}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 mt-3 pt-3 border-t border-[#1a1e2b]">
        <div className="flex items-center gap-2 text-[10px] text-[#64748B]">
          <span>{groups.length} tasks</span>
          <span className="w-px h-3 bg-white/10" />
          <span>{totalFiles} files</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1" title="Log files">
            <div className="w-1.5 h-1.5 rounded-full bg-blue-400" />
          </div>
          <div className="flex items-center gap-1" title="Process files">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
          </div>
          <div className="flex items-center gap-1" title="Session files">
            <div className="w-1.5 h-1.5 rounded-full bg-purple-400" />
          </div>
          <div className="flex items-center gap-1" title="Performance files">
            <div className="w-1.5 h-1.5 rounded-full bg-yellow-400" />
          </div>
        </div>
      </div>
    </HudPanel>
  );
};

export default FilePanel;
