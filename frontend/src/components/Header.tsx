
import React from 'react';
import { Cpu } from 'lucide-react';
import { useControl } from '../store/controlStore';

const Header: React.FC = () => {
  const { state } = useControl();

  const getStatusStyle = () => {
    switch (state.status) {
      case 'running':
      case 'error':
        return {
          text: 'text-[#00FFA3]',
          label: 'RUNNING',
          animate: true,
        };
      case 'paused':
        return {
          text: 'text-[#FF3366]',
          label: 'PAUSED',
          animate: false,
        };
      case 'stopped':
        return {
          text: 'text-[#FF3366]',
          label: 'STOPPED',
          animate: false,
        };
      case 'completed':
        return {
          text: 'text-[#00E5FF]',
          label: 'COMPLETED',
          animate: false,
        };
      default:
        return {
          text: 'text-[#00E5FF]',
          label: 'IDLE',
          animate: false,
        };
    }
  };

  const statusStyle = getStatusStyle();

  return (
    <header className="min-h-[4rem] py-2 border-b border-[#1a1e2b] bg-[#0a0b10]/90 backdrop-blur flex flex-wrap items-center justify-between gap-4 px-4 md:px-6 z-10 shrink-0">
      <div className="flex items-center gap-3">
        <div className="relative flex h-8 w-8 items-center justify-center">
          <Cpu className="text-[#00E5FF] absolute z-10" size={20} />
          <div 
            className="absolute inset-0 rounded-full border border-[#00E5FF]/30 border-t-[#00E5FF] animate-[spin_8s_linear_infinite]"
          />
        </div>
        <h1 className="font-display text-lg md:text-xl font-bold tracking-[0.2em] text-white">
          WEB UI <span className="text-[#00E5FF]">AGENT</span>
        </h1>
      </div>
      
      <div className="flex items-center gap-3 md:gap-6 font-mono text-[10px] md:text-xs">
        <div className="flex items-center gap-2">
          <span className="text-[#94A3B8]">STATUS:</span>
          <span className={`${statusStyle.text} ${statusStyle.animate ? 'animate-pulse' : ''}`}>
            {statusStyle.label}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[#94A3B8]">UPLINK:</span>
          <span className="text-[#00FFA3]">SECURE</span>
        </div>
      </div>
    </header>
  );
};

export default Header;
