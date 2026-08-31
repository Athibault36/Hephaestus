import React, { useState, useEffect } from 'react';
import { ViewportStream } from './components/ViewportStream';
import { ChainOfThought } from './components/ChainOfThought';
import { WorldOutliner } from './components/WorldOutliner';
import { AssetBrowser } from './components/AssetBrowser';
import { VoiceConsole } from './components/VoiceConsole';
import { PerformanceMonitor } from './components/PerformanceMonitor';
import { useMissionControlStore } from './store/missionControlStore';
import './MissionControl.css';

export function MissionControl() {
  const [activePanels, setActivePanels] = useState<Record<string, boolean>>({
    viewport: true,
    chainOfThought: true,
    worldOutliner: true,
    assetBrowser: false,
    voiceConsole: true,
    performance: true,
  });

  const { connect, disconnect, isConnected } = useMissionControlStore();

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return (
    <div className="mission-control">
      <header className="header">
        <div className="header-left">
          <h1>HEPHAESTUS Mission Control</h1>
          <ConnectionStatus isConnected={isConnected} />
        </div>
        <div className="header-center">
          <AgentStatus />
        </div>
        <div className="header-right">
          <PanelToggles activePanels={activePanels} setActivePanels={setActivePanels} />
        </div>
      </header>

      <main className="main-grid">
        {activePanels.viewport && (
          <section className="panel viewport-panel" data-panel="viewport">
            <PanelHeader title="Viewport Stream" icon="📷" />
            <ViewportStream />
          </section>
        )}

        {activePanels.chainOfThought && (
          <section className="panel chain-of-thought-panel" data-panel="chainOfThought">
            <PanelHeader title="Chain of Thought" icon="🧠" />
            <ChainOfThought />
          </section>
        )}

        {activePanels.worldOutliner && (
          <section className="panel world-outliner-panel" data-panel="worldOutliner">
            <PanelHeader title="World Outliner" icon="🌍" />
            <WorldOutliner />
          </section>
        )}

        {activePanels.assetBrowser && (
          <section className="panel asset-browser-panel" data-panel="assetBrowser">
            <PanelHeader title="Asset Browser" icon="📦" />
            <AssetBrowser />
          </section>
        )}

        {activePanels.voiceConsole && (
          <section className="panel voice-console-panel" data-panel="voiceConsole">
            <PanelHeader title="Voice Console" icon="🎤" />
            <VoiceConsole />
          </section>
        )}

        {activePanels.performance && (
          <section className="panel performance-panel" data-panel="performance">
            <PanelHeader title="Performance" icon="📊" />
            <PerformanceMonitor />
          </section>
        )}
      </main>
    </div>
  );
}

function ConnectionStatus({ isConnected }: { isConnected: boolean }) {
  return (
    <span className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
      <span className="dot" />
      {isConnected ? 'Connected' : 'Disconnected'}
    </span>
  );
}

function AgentStatus() {
  const { agentState } = useMissionControlStore();
  return (
    <div className="agent-status">
      <span className={`status-indicator ${agentState}`} />
      <span className="status-text">{agentState.toUpperCase()}</span>
      <span className="status-label">AGENT</span>
    </div>
  );
}

function PanelToggles({
  activePanels,
  setActivePanels,
}: {
  activePanels: Record<string, boolean>;
  setActivePanels: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
}) {
  const panels = [
    { key: 'viewport', label: 'Viewport', icon: '📷' },
    { key: 'chainOfThought', label: 'Thought', icon: '🧠' },
    { key: 'worldOutliner', label: 'Outliner', icon: '🌍' },
    { key: 'assetBrowser', label: 'Assets', icon: '📦' },
    { key: 'voiceConsole', label: 'Voice', icon: '🎤' },
    { key: 'performance', label: 'Perf', icon: '📊' },
  ];

  return (
    <div className="panel-toggles">
      {panels.map(({ key, label, icon }) => (
        <button
          key={key}
          className={`panel-toggle ${activePanels[key] ? 'active' : ''}`}
          onClick={() => setActivePanels(prev => ({ ...prev, [key]: !prev[key] }))}
          title={label}
        >
          {icon}
        </button>
      ))}
    </div>
  );
}

function PanelHeader({ title, icon, children }: { title: string; icon: string; children?: React.ReactNode }) {
  return (
    <div className="panel-header">
      <span className="panel-icon">{icon}</span>
      <h2 className="panel-title">{title}</h2>
      <div className="panel-actions">{children}</div>
    </div>
  );
}