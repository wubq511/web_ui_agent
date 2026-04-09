import React from 'react';

interface HudPanelProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  headerActions?: React.ReactNode;
}

const HudPanel: React.FC<HudPanelProps> = ({ title, icon, children, className = '', bodyClassName = 'p-4', headerActions }) => (
  <div className={`hud-panel flex flex-col ${className}`}>
    <div className="hud-corner-tl" />
    <div className="hud-corner-br" />
    <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 border-b border-[#1a1e2b] bg-black/40 shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-[#00E5FF]">{icon}</span>
        <h2 className="font-display font-semibold text-sm tracking-widest text-[#E2E8F0] uppercase">{title}</h2>
      </div>
      {headerActions && (
        <div className="flex items-center gap-2">
          {headerActions}
        </div>
      )}
    </div>
    <div className={`flex-1 overflow-auto relative ${bodyClassName}`}>
      {children}
    </div>
  </div>
);

export default HudPanel;
