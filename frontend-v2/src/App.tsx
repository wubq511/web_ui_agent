import React, { useState, useEffect } from 'react';
import { Terminal, Activity, MonitorPlay, FileCode2, Play, Pause, Square, Settings, Cpu, HardDrive } from 'lucide-react';
import { motion } from 'framer-motion';

// HUD Panel Component
const HudPanel: React.FC<{ title: string; icon: React.ReactNode; children: React.ReactNode; className?: string }> = ({ title, icon, children, className = '' }) => (
  <div className={`hud-panel flex flex-col ${className}`}>
    <div className="hud-corner-tl" />
    <div className="hud-corner-br" />
    <div className="flex items-center gap-2 px-4 py-2 border-b border-[#1a1e2b] bg-black/40">
      <span className="text-[#00E5FF]">{icon}</span>
      <h2 className="font-display font-semibold text-sm tracking-widest text-[#E2E8F0] uppercase">{title}</h2>
    </div>
    <div className="flex-1 overflow-auto p-4 relative">
      {children}
    </div>
  </div>
);

function App() {
  const [agentStatus, setAgentStatus] = useState<'idle' | 'running' | 'paused'>('idle');
  const [logs, setLogs] = useState<string[]>(['[SYSTEM] Initialization sequence started...', '[SYSTEM] Awaiting command parameters.']);

  // Simulate some logs when running
  useEffect(() => {
    if (agentStatus === 'running') {
      const interval = setInterval(() => {
        setLogs(prev => [...prev, `[PROCESS] Executing sequence 0x${Math.floor(Math.random() * 1000).toString(16).toUpperCase()}...`]);
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [agentStatus]);

  return (
    <div className="h-screen w-full flex flex-col relative z-0">
      {/* Background Elements */}
      <div className="cyber-grid" />
      <div className="scanline" />
      
      {/* Header */}
      <header className="h-16 border-b border-[#1a1e2b] bg-[#0a0b10]/90 backdrop-blur flex items-center justify-between px-6 z-10 shrink-0">
        <div className="flex items-center gap-3">
          <div className="relative flex h-8 w-8 items-center justify-center">
            <Cpu className="text-[#00E5FF] absolute z-10" size={20} />
            <motion.div 
              animate={{ rotate: 360 }} 
              transition={{ repeat: Infinity, duration: 8, ease: "linear" }}
              className="absolute inset-0 rounded-full border border-[#00E5FF]/30 border-t-[#00E5FF]"
            />
          </div>
          <h1 className="font-display text-xl font-bold tracking-[0.2em] text-white">WEB UI <span className="text-[#00E5FF]">AGENT</span></h1>
        </div>
        
        <div className="flex items-center gap-6 font-mono text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[#94A3B8]">STATUS:</span>
            <span className={agentStatus === 'running' ? 'text-[#00FFA3] animate-pulse' : agentStatus === 'paused' ? 'text-[#FF3366]' : 'text-[#00E5FF]'}>
              {agentStatus.toUpperCase()}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#94A3B8]">UPLINK:</span>
            <span className="text-[#00FFA3]">SECURE</span>
          </div>
        </div>
      </header>

      {/* Main Layout */}
      <main className="flex-1 p-4 grid grid-cols-12 grid-rows-6 gap-4 overflow-hidden z-10">
        
        {/* Left Column: Sandbox & Live View */}
        <div className="col-span-8 row-span-6 flex flex-col gap-4">
          
          {/* Sandbox / Metrics */}
          <HudPanel title="AGENT SANDBOX" icon={<Activity size={16} />} className="h-48 shrink-0">
            <div className="grid grid-cols-3 gap-4 h-full">
              <div className="border border-[#1a1e2b] bg-black/40 p-3 flex flex-col justify-between">
                <span className="text-[10px] text-[#94A3B8] uppercase">Current Task</span>
                <span className="font-mono text-sm text-[#00E5FF] truncate">Search web for design inspiration</span>
              </div>
              <div className="border border-[#1a1e2b] bg-black/40 p-3 flex flex-col justify-between">
                <span className="text-[10px] text-[#94A3B8] uppercase">Step Progress</span>
                <div className="flex items-end gap-2">
                  <span className="font-display text-2xl text-[#00FFA3]">04</span>
                  <span className="text-xs text-[#94A3B8] pb-1">/ 10</span>
                </div>
                <div className="h-1 w-full bg-[#1a1e2b] mt-2">
                  <div className="h-full bg-[#00FFA3]" style={{ width: '40%' }} />
                </div>
              </div>
              <div className="border border-[#1a1e2b] bg-black/40 p-3 flex flex-col justify-between">
                <span className="text-[10px] text-[#94A3B8] uppercase">Last Action</span>
                <span className="font-mono text-sm text-[#B52BFF]">Click Element [id="submit"]</span>
              </div>
            </div>
          </HudPanel>

          {/* Live View */}
          <HudPanel title="LIVE FEED" icon={<MonitorPlay size={16} />} className="flex-1">
            <div className="absolute inset-4 border border-[#1a1e2b] bg-[#050507] flex items-center justify-center overflow-hidden group">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,229,255,0.05),transparent)]" />
              <div className="text-center">
                <MonitorPlay className="mx-auto mb-4 text-[#1a1e2b] group-hover:text-[#00E5FF]/50 transition-colors" size={48} />
                <p className="font-mono text-xs text-[#94A3B8]">AWAITING VIDEO STREAM...</p>
              </div>
              {/* Fake crosshairs */}
              <div className="absolute top-4 left-4 w-4 h-4 border-t border-left border-[#00E5FF]/30" />
              <div className="absolute top-4 right-4 w-4 h-4 border-t border-right border-[#00E5FF]/30" />
              <div className="absolute bottom-4 left-4 w-4 h-4 border-bottom border-left border-[#00E5FF]/30" />
              <div className="absolute bottom-4 right-4 w-4 h-4 border-bottom border-right border-[#00E5FF]/30" />
            </div>
          </HudPanel>
        </div>

        {/* Right Column: Controls & Terminal */}
        <div className="col-span-4 row-span-6 flex flex-col gap-4">
          
          {/* Controls */}
          <HudPanel title="COMMAND CENTER" icon={<Settings size={16} />} className="shrink-0">
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] text-[#94A3B8] uppercase mb-1">Target Objective</label>
                <textarea 
                  className="w-full bg-black/40 border border-[#1a1e2b] p-2 text-sm font-mono text-[#E2E8F0] focus:border-[#00E5FF] focus:outline-none resize-none transition-colors"
                  rows={3}
                  placeholder="Enter objective..."
                  defaultValue="Analyze the layout and propose a futuristic redesign."
                />
              </div>
              
              <div className="grid grid-cols-3 gap-2">
                <button 
                  onClick={() => setAgentStatus('running')}
                  className="flex flex-col items-center justify-center py-2 border border-[#00FFA3]/30 bg-[#00FFA3]/10 text-[#00FFA3] hover:bg-[#00FFA3]/20 transition-colors"
                >
                  <Play size={16} className="mb-1" />
                  <span className="text-[10px] uppercase font-bold">Start</span>
                </button>
                <button 
                  onClick={() => setAgentStatus('paused')}
                  className="flex flex-col items-center justify-center py-2 border border-[#FF3366]/30 bg-[#FF3366]/10 text-[#FF3366] hover:bg-[#FF3366]/20 transition-colors"
                >
                  <Pause size={16} className="mb-1" />
                  <span className="text-[10px] uppercase font-bold">Pause</span>
                </button>
                <button 
                  onClick={() => setAgentStatus('idle')}
                  className="flex flex-col items-center justify-center py-2 border border-[#94A3B8]/30 bg-[#94A3B8]/10 text-[#94A3B8] hover:bg-[#94A3B8]/20 transition-colors"
                >
                  <Square size={16} className="mb-1" />
                  <span className="text-[10px] uppercase font-bold">Stop</span>
                </button>
              </div>
            </div>
          </HudPanel>

          {/* Files / Assets */}
          <HudPanel title="FILE SYSTEM" icon={<FileCode2 size={16} />} className="h-48 shrink-0">
            <ul className="space-y-2 font-mono text-xs">
              <li className="flex items-center gap-2 text-[#E2E8F0] cursor-pointer hover:text-[#00E5FF]">
                <HardDrive size={14} className="text-[#94A3B8]" />
                <span>session_data.json</span>
              </li>
              <li className="flex items-center gap-2 text-[#E2E8F0] cursor-pointer hover:text-[#00E5FF]">
                <FileCode2 size={14} className="text-[#94A3B8]" />
                <span>agent_logs_2026.log</span>
              </li>
              <li className="flex items-center gap-2 text-[#E2E8F0] cursor-pointer hover:text-[#00E5FF]">
                <FileCode2 size={14} className="text-[#94A3B8]" />
                <span>action_history.csv</span>
              </li>
            </ul>
          </HudPanel>

          {/* Terminal */}
          <HudPanel title="TERMINAL OUTPUT" icon={<Terminal size={16} />} className="flex-1">
            <div className="font-mono text-[11px] leading-relaxed space-y-1">
              {logs.map((log, i) => (
                <div key={i} className={`${log.includes('SYSTEM') ? 'text-[#00E5FF]' : log.includes('ERROR') ? 'text-[#FF3366]' : 'text-[#00FFA3]'}`}>
                  {log}
                </div>
              ))}
              {agentStatus === 'running' && (
                <div className="flex items-center">
                  <span className="text-[#00FFA3] mr-2">&gt;</span>
                  <motion.div 
                    animate={{ opacity: [1, 0] }} 
                    transition={{ repeat: Infinity, duration: 0.8 }}
                    className="w-2 h-3 bg-[#00FFA3]"
                  />
                </div>
              )}
            </div>
          </HudPanel>

        </div>
      </main>
    </div>
  );
}

export default App;