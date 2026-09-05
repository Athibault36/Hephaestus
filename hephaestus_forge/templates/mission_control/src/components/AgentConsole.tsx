import { useEffect, useRef, useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';

export function AgentConsole() {
  const {
    isConnected,
    agentBusy,
    chatMessages,
    lastGrade,
    sendAgentChat,
    loadAgentHealth,
    preflightReady,
    plannerAvailable,
    assetMatches,
    exportSession,
  } = useMissionControlStore();
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<'auto' | 'cinematic' | 'gameplay'>('auto');
  const [dccShape, setDccShape] = useState('cube');
  const [dccColor, setDccColor] = useState('');
  const [dccSpin, setDccSpin] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadAgentHealth();
    const t = window.setInterval(loadAgentHealth, 30000);
    return () => window.clearInterval(t);
  }, [loadAgentHealth]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [chatMessages]);

  const onSend = async (reset = false) => {
    const message = input.trim();
    if (!message || agentBusy) return;
    setInput('');
    await sendAgentChat(message, { reset, mode });
  };

  const onAuthorIntoPie = async () => {
    if (agentBusy) return;
    let msg = `make a ${dccColor ? `${dccColor} ` : ''}${dccShape} and put it in the scene and frame it`;
    if (dccSpin) msg += ' and spin it slowly';
    setInput(msg);
    await sendAgentChat(msg, { mode });
  };

  return (
    <div className="agent-console">
      <div className="agent-status-row">
        <span className={`pill ${preflightReady ? 'ok' : 'bad'}`}>
          {preflightReady ? 'PIE ready' : 'PIE offline'}
        </span>
        <span className={`pill ${plannerAvailable ? 'ok' : ''}`}>
          {plannerAvailable ? 'Nemotron Ultra ready' : 'Heuristic mode'}
        </span>
        {agentBusy && <span className="pill busy">Agent working…</span>}
      </div>

      <div className="agent-chat-log" ref={logRef}>
        {chatMessages.length === 0 ? (
          <p className="agent-chat-empty">
            Try: make a red cube, frame it, and spin it slowly — or use Author into PIE below
          </p>
        ) : (
          chatMessages.map((m, i) => (
            <div key={`${m.role}-${i}`} className={`agent-chat-line ${m.role}`}>
              <strong>{m.role === 'user' ? 'You' : 'Hephaestus'}:</strong> {m.content}
            </div>
          ))
        )}
      </div>

      {lastGrade && (
        <p className="agent-grade" title={lastGrade.summary}>
          Grade: {lastGrade.met ? 'met' : 'in progress'} — {lastGrade.summary}
        </p>
      )}

      {assetMatches.length > 0 && (
        <div className="asset-chips">
          {assetMatches.slice(0, 8).map((path) => (
            <button key={path} type="button" className="asset-chip" title={path} onClick={() => setInput(`Spawn ${path} in front of the camera`)}>
              {path.split('.').pop() || path}
            </button>
          ))}
        </div>
      )}

      <div className="dcc-author-row">
        <span className="dcc-author-label">DCC author</span>
        <select
          value={dccShape}
          onChange={(e) => setDccShape(e.target.value)}
          disabled={!isConnected || agentBusy}
          aria-label="Shape"
        >
          <option value="cube">cube</option>
          <option value="sphere">sphere</option>
          <option value="cylinder">cylinder</option>
          <option value="cone">cone</option>
          <option value="plane">plane</option>
        </select>
        <select
          value={dccColor}
          onChange={(e) => setDccColor(e.target.value)}
          disabled={!isConnected || agentBusy}
          aria-label="Color"
        >
          <option value="">default</option>
          <option value="red">red</option>
          <option value="blue">blue</option>
          <option value="green">green</option>
          <option value="gold">gold</option>
        </select>
        <label className="dcc-spin-label">
          <input
            type="checkbox"
            checked={dccSpin}
            onChange={(e) => setDccSpin(e.target.checked)}
            disabled={!isConnected || agentBusy}
          />
          spin
        </label>
        <button
          type="button"
          className="primary"
          disabled={!isConnected || agentBusy}
          onClick={() => void onAuthorIntoPie()}
        >
          Author into PIE
        </button>
      </div>

      <div className="agent-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isConnected ? 'Goal for the agent…' : 'Connect PIE first'}
          disabled={!isConnected || agentBusy}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSend(false);
            }
          }}
        />
        <div className="agent-input-actions">
          <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
            <option value="auto">Auto</option>
            <option value="cinematic">Cinematic</option>
            <option value="gameplay">Gameplay</option>
          </select>
          <button type="button" className="primary" disabled={!isConnected || agentBusy} onClick={() => onSend(false)}>
            Send
          </button>
          <button type="button" disabled={agentBusy} onClick={() => onSend(true)}>
            New
          </button>
          <button type="button" disabled={agentBusy} onClick={() => exportSession()}>
            Export
          </button>
        </div>
      </div>
    </div>
  );
}
