import React, { useEffect, useMemo, useState } from 'react';
import {
  ChevronDown,
  Globe,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Save,
  Settings,
  Sparkles,
  Square,
  Trash2,
  Pencil,
  X,
} from 'lucide-react';

import { useControl } from '../store/controlStore';
import { useAgent } from '../store/agentStore';
import { useLogs } from '../store/logStore';
import { useTerminal } from '../store/terminalStore';
import { apiClient } from '../services/api';
import type { CustomLlmConfig, CustomLlmConfigInput, ModelConfig } from '../types';
import HudPanel from './HudPanel';

const emptyConfigForm = (): CustomLlmConfigInput => ({
  display_name: '',
  provider: 'openai-compatible',
  model_name: '',
  base_url: '',
  api_key: '',
  description: '',
  max_tokens: 8192,
  supports_vision: false,
  enabled: true,
});

const ControlPanel: React.FC = () => {
  const { state: controlState, dispatch } = useControl();
  const { dispatch: agentDispatch } = useAgent();
  const { addInfo, addSuccess, addWarning, addError } = useLogs();
  const { clearTerminal } = useTerminal();

  const [availableModels, setAvailableModels] = useState<ModelConfig[]>([]);
  const [customConfigs, setCustomConfigs] = useState<CustomLlmConfig[]>([]);
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [isApiConfigOpen, setIsApiConfigOpen] = useState(false);
  const [isConfigLoading, setIsConfigLoading] = useState(false);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [editingConfigId, setEditingConfigId] = useState<string | null>(null);
  const [localObjective, setLocalObjective] = useState(controlState.objective);
  const [localUrl, setLocalUrl] = useState('https://www.baidu.com');
  const [isLoading, setIsLoading] = useState(false);
  const [configForm, setConfigForm] = useState<CustomLlmConfigInput>(emptyConfigForm);

  const isRunning = controlState.status === 'running';
  const isPaused = controlState.status === 'paused';
  const isIdle = controlState.status === 'idle';
  const isStopped = controlState.status === 'stopped';
  const showExpandedTerminal = !isIdle && !isStopped;

  const selectedModel = useMemo(
    () => availableModels.find((model) => model.id === controlState.selectedModel) ?? null,
    [availableModels, controlState.selectedModel]
  );

  const loadModelData = async () => {
    setIsConfigLoading(true);
    try {
      const [models, configResponse] = await Promise.all([
        apiClient.getAvailableModels(),
        apiClient.getCustomLlmConfigs(),
      ]);
      setAvailableModels(models);
      setCustomConfigs(configResponse.configs);
      if (models.length === 0) {
        dispatch({ type: 'SET_MODEL', payload: '' });
        setIsApiConfigOpen(true);
      } else if (!models.some((model) => model.id === controlState.selectedModel)) {
        dispatch({ type: 'SET_MODEL', payload: models[0].id });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '加载大模型配置失败';
      addWarning(`API 配置加载失败: ${message}`);
    } finally {
      setIsConfigLoading(false);
    }
  };

  useEffect(() => {
    void loadModelData();
  }, []);

  const resetConfigForm = () => {
    setConfigForm(emptyConfigForm());
    setEditingConfigId(null);
  };

  const handleModelSelect = (modelId: string) => {
    dispatch({ type: 'SET_MODEL', payload: modelId });
    setIsModelDropdownOpen(false);
    addInfo(`Model switched to ${modelId}`);
  };

  const handleObjectiveChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setLocalObjective(e.target.value);
    dispatch({ type: 'SET_OBJECTIVE', payload: e.target.value });
    agentDispatch({ type: 'SET_OBJECTIVE', payload: e.target.value });
  };

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalUrl(e.target.value);
  };

  const handleConfigFieldChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const target = e.currentTarget;
    const { name, value, type } = target;
    if (type === 'checkbox' && target instanceof HTMLInputElement) {
      setConfigForm((prev) => ({ ...prev, [name]: target.checked }));
      return;
    }
    setConfigForm((prev) => ({
      ...prev,
      [name]: name === 'max_tokens' ? Number(value || 0) : value,
    }));
  };

  const handleEditConfig = (config: CustomLlmConfig) => {
    setEditingConfigId(config.id);
    setIsApiConfigOpen(true);
    setConfigForm({
      display_name: config.display_name,
      provider: config.provider,
      model_name: config.model_name,
      base_url: config.base_url,
      api_key: '',
      description: config.description,
      max_tokens: config.max_tokens,
      supports_vision: config.supports_vision,
      enabled: config.enabled,
    });
  };

  const handleDeleteConfig = async (config: CustomLlmConfig) => {
    if (!window.confirm(`确认删除配置“${config.display_name}”吗？`)) {
      return;
    }

    try {
      await apiClient.deleteCustomLlmConfig(config.id);
      addSuccess(`已删除配置 ${config.display_name}`);
      await loadModelData();
      if (editingConfigId === config.id) {
        resetConfigForm();
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '删除配置失败';
      addError('删除自定义模型配置失败', message);
    }
  };

  const handleSaveConfig = async () => {
    if (!configForm.display_name.trim() || !configForm.model_name.trim() || !configForm.base_url.trim()) {
      addWarning('请完整填写配置名称、模型名称和 Base URL');
      return;
    }

    if (!editingConfigId && !configForm.api_key.trim()) {
      addWarning('新建配置时必须填写 API Key');
      return;
    }

    setIsSavingConfig(true);
    try {
      if (editingConfigId) {
        const payload: Partial<CustomLlmConfigInput> = {
          display_name: configForm.display_name,
          provider: configForm.provider,
          model_name: configForm.model_name,
          base_url: configForm.base_url,
          description: configForm.description,
          max_tokens: configForm.max_tokens,
          supports_vision: configForm.supports_vision,
          enabled: configForm.enabled,
        };
        if (configForm.api_key.trim()) {
          payload.api_key = configForm.api_key;
        }
        await apiClient.updateCustomLlmConfig(editingConfigId, payload);
        addSuccess(`已更新配置 ${configForm.display_name}`);
      } else {
        await apiClient.createCustomLlmConfig({
          ...configForm,
          api_key: configForm.api_key.trim(),
        });
        addSuccess(`已创建配置 ${configForm.display_name}`);
      }
      resetConfigForm();
      await loadModelData();
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存配置失败';
      addError('保存自定义模型配置失败', message);
    } finally {
      setIsSavingConfig(false);
    }
  };

  const handleRun = async () => {
    if (!localObjective.trim()) {
      addWarning('Please enter an objective before running');
      return;
    }

    if (!controlState.selectedModel) {
      addWarning('请先在 API CONFIG 中添加并选择一条自定义模型配置');
      setIsApiConfigOpen(true);
      return;
    }

    setIsLoading(true);

    try {
      const result = await apiClient.executeCommand(
        localObjective,
        localUrl,
        30,
        controlState.selectedModel
      );

      if (result.success) {
        dispatch({ type: 'START_AGENT' });
        addSuccess('Command started', `python main.py -o "${localObjective.substring(0, 50)}..."`);
      } else {
        addError('Failed to start command', result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      addError('Failed to start command', errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePauseResume = async () => {
    setIsLoading(true);
    try {
      if (controlState.isPaused) {
        const result = await apiClient.resumeAgent();
        if (result.success) {
          dispatch({ type: 'RESUME_AGENT' });
          addInfo('Agent resumed');
        } else {
          addError('Failed to resume agent', result.message);
        }
      } else {
        const result = await apiClient.pauseAgent();
        if (result.success) {
          dispatch({ type: 'PAUSE_AGENT' });
          addWarning('Agent paused');
        } else {
          addError('Failed to pause agent', result.message);
        }
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      addError('Failed to pause/resume agent', errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStop = async () => {
    setIsLoading(true);
    try {
      const cmdResult = await apiClient.stopCommand();
      const agentResult = await apiClient.stopAgent();

      if (cmdResult.success || agentResult.success) {
        dispatch({ type: 'STOP_AGENT' });
        addWarning('Agent stopped by user');
      } else {
        addError('Failed to stop agent', cmdResult.message || agentResult.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      addError('Failed to stop agent', errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = async () => {
    setIsLoading(true);
    try {
      const result = await apiClient.resetAgent();
      if (result.success) {
        dispatch({ type: 'RESET_AGENT' });
        setLocalObjective('');
        clearTerminal();
        addInfo('Agent reset');
      } else {
        addError('Failed to reset agent', result.message);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      addError('Failed to reset agent', errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const headerActions = (
    <>
      {isRunning && !isPaused && (
        <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-[#00FFA3]">
          <div className="w-1.5 h-1.5 rounded-full bg-[#00FFA3] animate-pulse" />
          <span>Running</span>
        </div>
      )}
      {isPaused && (
        <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-[#EAB308]">
          <div className="w-1.5 h-1.5 rounded-full bg-[#EAB308]" />
          <span>Paused</span>
        </div>
      )}
    </>
  );

  return (
    <HudPanel
      title="COMMAND CENTER"
      icon={<Settings size={16} />}
      className="flex-1 min-h-0"
      headerActions={headerActions}
      bodyClassName="p-4 flex min-h-0 flex-col gap-4 overflow-hidden"
    >
      <div className="flex-1 min-h-0 overflow-y-auto -mx-4 px-4">
        {!showExpandedTerminal && (
          <div className="space-y-4 pb-1">
          <div>
            <label className="mb-1 block text-[10px] uppercase text-[#94A3B8]">Target Objective</label>
            <textarea
              value={localObjective}
              onChange={handleObjectiveChange}
              className="w-full resize-none border border-[#1a1e2b] bg-black/40 p-2 text-sm font-mono text-[#E2E8F0] transition-colors focus:border-[#00E5FF] focus:outline-none"
              rows={3}
              placeholder="Enter objective..."
              disabled={isRunning && !isPaused}
            />
          </div>

          <div>
            <label className="mb-1 block text-[10px] uppercase text-[#94A3B8]">Starting URL</label>
            <div className="flex items-center border border-[#1a1e2b] bg-black/40 transition-colors focus-within:border-[#00E5FF]">
              <Globe className="ml-2 h-4 w-4 shrink-0 text-[#94A3B8]" />
              <input
                type="url"
                value={localUrl}
                onChange={handleUrlChange}
                placeholder="https://www.example.com"
                className="w-full bg-transparent p-2 text-sm font-mono text-[#E2E8F0] focus:outline-none"
                disabled={isRunning && !isPaused}
              />
            </div>
          </div>

          <div className="relative">
            <label className="mb-1 block text-[10px] uppercase text-[#94A3B8]">Model Select</label>
            <button
              onClick={() => availableModels.length > 0 && setIsModelDropdownOpen((prev) => !prev)}
              disabled={availableModels.length === 0}
              className="flex w-full items-center justify-between border border-[#1a1e2b] bg-black/40 p-2 text-sm text-[#E2E8F0] transition-colors hover:border-[#00E5FF] disabled:cursor-not-allowed disabled:text-[#64748B]"
            >
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-[#00E5FF]" />
                <span className="font-mono">{selectedModel?.name || '请先创建自定义模型'}</span>
              </div>
              <ChevronDown
                className={`h-4 w-4 text-[#94A3B8] transition-transform duration-200 ${
                  isModelDropdownOpen ? 'rotate-180' : ''
                }`}
              />
            </button>

            {isModelDropdownOpen && (
              <div className="absolute left-0 right-0 top-full z-[100] mt-1 max-h-60 overflow-y-auto border border-[#1a1e2b] bg-[#0a0b10] py-1 shadow-xl animate-fade-in">
                {availableModels.map((model) => (
                  <button
                    key={model.id}
                    onClick={() => handleModelSelect(model.id)}
                    className={`w-full px-3 py-2.5 text-left transition-colors hover:bg-[#1a1e2b]/50 ${
                      model.id === controlState.selectedModel
                        ? 'border-l-2 border-[#00E5FF] bg-[#00E5FF]/10'
                        : ''
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-mono text-[#E2E8F0]">{model.name}</span>
                      <div className="flex items-center gap-1">
                        {model.source === 'custom' && (
                          <span className="border border-[#00FFA3]/30 bg-[#00FFA3]/10 px-1.5 py-0.5 text-[10px] text-[#00FFA3]">
                            CUSTOM
                          </span>
                        )}
                        {model.supportsVision && (
                          <span className="border border-[#B52BFF]/30 bg-[#B52BFF]/10 px-1.5 py-0.5 text-[10px] text-[#B52BFF]">
                            VISION
                          </span>
                        )}
                      </div>
                    </div>
                    <p className="mt-1 line-clamp-1 text-[10px] uppercase text-[#94A3B8]">
                      {model.description}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="border border-[#1a1e2b] bg-black/30">
            <button
              onClick={() => setIsApiConfigOpen((prev) => !prev)}
              className="flex w-full items-center justify-between px-3 py-2 text-left"
            >
              <div>
                <div className="text-[10px] uppercase text-[#94A3B8]">API Config</div>
                <div className="text-xs text-[#E2E8F0]">OpenAI 兼容接口 / 多 Provider 持久化</div>
              </div>
              <div className="flex items-center gap-2">
                {isConfigLoading && <span className="text-[10px] text-[#94A3B8]">SYNCING</span>}
                <ChevronDown className={`h-4 w-4 text-[#94A3B8] ${isApiConfigOpen ? 'rotate-180' : ''}`} />
              </div>
            </button>

            {isApiConfigOpen && (
                <div className="space-y-3 border-t border-[#1a1e2b] px-3 py-3">
                <div className="text-[10px] text-[#94A3B8]">
                  当前运行链路只认这里创建的自定义 API 配置，不使用预设 URL。
                </div>

                <div className="space-y-2">
                  {customConfigs.length === 0 ? (
                    <div className="border border-dashed border-[#1a1e2b] px-3 py-3 text-xs text-[#64748B]">
                      还没有自定义 Provider。请先新增一条配置，否则无法启动任务。
                    </div>
                  ) : (
                    customConfigs.map((config) => (
                      <div key={config.id} className="border border-[#1a1e2b] bg-black/40 px-3 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-mono text-[#E2E8F0]">{config.display_name}</span>
                              <span className="border border-[#00FFA3]/30 bg-[#00FFA3]/10 px-1.5 py-0.5 text-[10px] text-[#00FFA3]">
                                {config.enabled ? 'ENABLED' : 'DISABLED'}
                              </span>
                            </div>
                            <div className="mt-1 text-[11px] text-[#94A3B8]">{config.model_name}</div>
                            <div className="mt-1 truncate text-[11px] text-[#64748B]">{config.base_url}</div>
                            <div className="mt-1 text-[11px] text-[#64748B]">{config.api_key_masked}</div>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleEditConfig(config)}
                              className="rounded border border-[#1a1e2b] p-2 text-[#94A3B8] transition-colors hover:border-[#00E5FF] hover:text-[#00E5FF]"
                              title="编辑配置"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => handleDeleteConfig(config)}
                              className="rounded border border-[#1a1e2b] p-2 text-[#94A3B8] transition-colors hover:border-[#FF3366] hover:text-[#FF3366]"
                              title="删除配置"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-[10px] uppercase text-[#94A3B8]">Provider Name</label>
                    <input
                      name="display_name"
                      value={configForm.display_name}
                      onChange={handleConfigFieldChange}
                      className="w-full border border-[#1a1e2b] bg-black/40 px-3 py-2 text-sm font-mono text-[#E2E8F0] focus:border-[#00E5FF] focus:outline-none"
                      placeholder="例如 OpenRouter / Moonshot"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[10px] uppercase text-[#94A3B8]">Model Name</label>
                    <input
                      name="model_name"
                      value={configForm.model_name}
                      onChange={handleConfigFieldChange}
                      className="w-full border border-[#1a1e2b] bg-black/40 px-3 py-2 text-sm font-mono text-[#E2E8F0] focus:border-[#00E5FF] focus:outline-none"
                      placeholder="例如 openai/gpt-4o-mini"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="mb-1 block text-[10px] uppercase text-[#94A3B8]">Base URL</label>
                    <input
                      name="base_url"
                      value={configForm.base_url}
                      onChange={handleConfigFieldChange}
                      className="w-full border border-[#1a1e2b] bg-black/40 px-3 py-2 text-sm font-mono text-[#E2E8F0] focus:border-[#00E5FF] focus:outline-none"
                      placeholder="https://api.example.com/v1"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="mb-1 block text-[10px] uppercase text-[#94A3B8]">API Key</label>
                    <input
                      name="api_key"
                      type="password"
                      value={configForm.api_key}
                      onChange={handleConfigFieldChange}
                      className="w-full border border-[#1a1e2b] bg-black/40 px-3 py-2 text-sm font-mono text-[#E2E8F0] focus:border-[#00E5FF] focus:outline-none"
                      placeholder={editingConfigId ? '留空则保持当前密钥' : 'sk-...'}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[10px] uppercase text-[#94A3B8]">Max Tokens</label>
                    <input
                      name="max_tokens"
                      type="number"
                      min={1}
                      value={configForm.max_tokens}
                      onChange={handleConfigFieldChange}
                      className="w-full border border-[#1a1e2b] bg-black/40 px-3 py-2 text-sm font-mono text-[#E2E8F0] focus:border-[#00E5FF] focus:outline-none"
                    />
                  </div>
                  <div className="flex items-center gap-2 pt-6 text-sm text-[#E2E8F0]">
                    <input
                      id="supports_vision"
                      name="supports_vision"
                      type="checkbox"
                      checked={configForm.supports_vision ?? false}
                      onChange={handleConfigFieldChange}
                    />
                    <label htmlFor="supports_vision">Supports vision</label>
                  </div>
                  <div className="md:col-span-2">
                    <label className="mb-1 block text-[10px] uppercase text-[#94A3B8]">Description</label>
                    <textarea
                      name="description"
                      value={configForm.description}
                      onChange={handleConfigFieldChange}
                      rows={2}
                      className="w-full resize-none border border-[#1a1e2b] bg-black/40 px-3 py-2 text-sm font-mono text-[#E2E8F0] focus:border-[#00E5FF] focus:outline-none"
                      placeholder="例如 OpenAI-compatible 自托管网关"
                    />
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={handleSaveConfig}
                    disabled={isSavingConfig}
                    className="flex items-center gap-2 border border-[#00FFA3]/30 bg-[#00FFA3]/10 px-3 py-2 text-xs font-bold uppercase text-[#00FFA3] transition-colors hover:bg-[#00FFA3]/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {editingConfigId ? <Save className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
                    <span>{editingConfigId ? 'Update Config' : 'Add Config'}</span>
                  </button>
                  {(editingConfigId || configForm.display_name || configForm.base_url || configForm.model_name || configForm.api_key) && (
                    <button
                      onClick={resetConfigForm}
                      className="flex items-center gap-2 border border-[#1a1e2b] px-3 py-2 text-xs font-bold uppercase text-[#94A3B8] transition-colors hover:border-[#FF3366] hover:text-[#FF3366]"
                    >
                      <X className="h-3.5 w-3.5" />
                      <span>Cancel</span>
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
          </div>
        )}

        {showExpandedTerminal && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 pb-1">
            <div className="flex flex-col justify-between border border-[#1a1e2b] bg-black/40 p-3">
              <span className="text-[10px] uppercase text-[#94A3B8]">Target</span>
              <span className="truncate text-sm font-mono text-[#E2E8F0]" title={localObjective}>
                {localObjective}
              </span>
            </div>
            <div className="flex flex-col justify-between border border-[#1a1e2b] bg-black/40 p-3">
              <span className="text-[10px] uppercase text-[#94A3B8]">Model</span>
              <span className="truncate text-sm font-mono text-[#00E5FF]">{selectedModel?.name || '未配置'}</span>
            </div>
          </div>
        )}
      </div>

      <div className="mt-auto grid shrink-0 grid-cols-2 gap-2 border-t border-[#1a1e2b] pt-3 lg:grid-cols-4">
        <button
          onClick={handleRun}
          disabled={(isRunning && !isPaused) || isLoading || !controlState.selectedModel}
          className={`flex flex-col items-center justify-center border py-2 transition-colors ${
            (isRunning && !isPaused) || isLoading || !controlState.selectedModel
              ? 'cursor-not-allowed border-[#1a1e2b] bg-black/20 text-[#475569]'
              : 'border-[#00FFA3]/30 bg-[#00FFA3]/10 text-[#00FFA3] hover:bg-[#00FFA3]/20'
          }`}
        >
          {isLoading ? (
            <div className="mb-1 h-4 w-4 animate-spin rounded-full border-2 border-[#00FFA3]/30 border-t-[#00FFA3]" />
          ) : (
            <Play size={16} className="mb-1" />
          )}
          <span className="text-[10px] font-bold uppercase">Start</span>
        </button>

        <button
          onClick={handlePauseResume}
          disabled={(!isRunning && !isPaused) || isLoading}
          className={`flex flex-col items-center justify-center border py-2 transition-colors ${
            (!isRunning && !isPaused) || isLoading
              ? 'cursor-not-allowed border-[#1a1e2b] bg-black/20 text-[#475569]'
              : isPaused
                ? 'border-[#EAB308]/30 bg-[#EAB308]/10 text-[#EAB308] hover:bg-[#EAB308]/20'
                : 'border-[#FF3366]/30 bg-[#FF3366]/10 text-[#FF3366] hover:bg-[#FF3366]/20'
          }`}
        >
          {isPaused ? <Play size={16} className="mb-1" /> : <Pause size={16} className="mb-1" />}
          <span className="text-[10px] font-bold uppercase">{isPaused ? 'Continue' : 'Pause'}</span>
        </button>

        <button
          onClick={handleStop}
          disabled={isIdle || isStopped || isLoading}
          className={`flex flex-col items-center justify-center border py-2 transition-colors ${
            isIdle || isStopped || isLoading
              ? 'cursor-not-allowed border-[#1a1e2b] bg-black/20 text-[#475569]'
              : 'border-[#FF3366]/30 bg-[#FF3366]/10 text-[#FF3366] hover:bg-[#FF3366]/20'
          }`}
        >
          <Square size={16} className="mb-1" />
          <span className="text-[10px] font-bold uppercase">Stop</span>
        </button>

        <button
          onClick={handleReset}
          disabled={isLoading}
          className={`flex flex-col items-center justify-center border border-[#94A3B8]/30 bg-[#94A3B8]/10 py-2 text-[#94A3B8] transition-colors hover:bg-[#94A3B8]/20 ${
            isLoading ? 'cursor-not-allowed opacity-50' : ''
          }`}
        >
          <RotateCcw size={16} className="mb-1" />
          <span className="text-[10px] font-bold uppercase">Reset</span>
        </button>
      </div>
    </HudPanel>
  );
};

export default ControlPanel;
