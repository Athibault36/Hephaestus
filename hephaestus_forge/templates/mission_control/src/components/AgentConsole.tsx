import { useEffect, useRef, useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import { PanelState } from './PanelState';

function isStructuredPayload(content: string) {
  const trimmed = content.trim();
  if (!trimmed || !/^[{[]/.test(trimmed)) return false;
  try {
    JSON.parse(trimmed);
    return true;
  } catch {
    return false;
  }
}

function displayChatContent(role: 'user' | 'assistant', content: string) {
  if (role === 'assistant' && isStructuredPayload(content)) {
    return 'Structured response received. Use Export for the full session details.';
  }
  return content;
}

export function AgentConsole() {
  const {
    isConnected,
    agentBusy,
    agentError,
    chatMessages,
    lastGrade,
    sendAgentChat,
    loadAgentHealth,
    preflightReady,
    preflightHint,
    plannerAvailable,
    agentHealthLoading,
    agentHealthError,
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

  const canRunAgent = isConnected && preflightReady && !agentBusy;
  const preflightMessage = preflightHint || 'Run forge sync-plugin, rebuild HephaestusBridge, then start PIE.';
  const chatEmptyTone = !isConnected ? 'offline' : !preflightReady ? 'degraded' : 'empty';

  const onSend = async (reset = false) => {
    const message = input.trim();
    if (!message || !canRunAgent) return;
    setInput('');
    await sendAgentChat(message, { reset, mode });
  };

  const onAuthorIntoPie = async () => {
    if (!canRunAgent) return;
    let msg = `make a ${dccColor ? `${dccColor} ` : ''}${dccShape} and put it in the scene and frame it`;
    if (dccSpin) msg += ' and spin it slowly';
    setInput(msg);
    await sendAgentChat(msg, { mode });
  };

  return (
    <div className="agent-console">
      <div className="agent-status-row">
        <span className={`pill ${preflightReady ? 'ok' : agentHealthLoading ? '' : 'bad'}`}>
          {agentHealthLoading ? 'Checking preflight' : preflightReady ? 'PIE ready' : 'Preflight blocked'}
        </span>
        <span className={`pill ${plannerAvailable ? 'ok' : 'warn'}`}>
          {agentHealthLoading ? 'Planner checking' : plannerAvailable ? 'Nemotron Ultra ready' : 'Planner unavailable'}
        </span>
        {agentBusy && <span className="pill busy">Agent working…</span>}
      </div>

      {agentHealthError && (
        <div className="agent-callout error" role="alert">
          <strong>Director preflight unavailable.</strong> {agentHealthError}
        </div>
      )}

      {isConnected && !preflightReady && !agentHealthLoading && !agentHealthError && (
        <div className="agent-callout degraded" role="status">
          <strong>Confirm before authoring into PIE.</strong> {preflightMessage}
        </div>
      )}

      {agentError && (
        <div className="agent-callout error" role="alert">
          <strong>Agent request failed.</strong> {agentError}
        </div>
      )}

      <div className="agent-chat-log" ref={logRef}>
        {chatMessages.length === 0 ? (
          <PanelState
            tone={chatEmptyTone}
            icon="🤖"
            title={!isConnected ? 'Director offline' : !preflightReady ? 'PIE preflight required' : 'Ready for a shot goal'}
            message={
              !isConnected
                ? 'Start forge observe and PIE to connect the director to a live UE world.'
                : !preflightReady
                  ? preflightMessage
                  : 'Try: make a red cube, frame it, and spin it slowly — or use Author into PIE below.'
            }
          />
        ) : (
          chatMessages.map((m, i) => (
            <div key={`${m.role}-${i}`} className={`agent-chat-line ${m.role}`}>
              <strong>{m.role === 'user' ? 'You' : 'Hephaestus'}:</strong> {displayChatContent(m.role, m.content)}
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
          disabled={!canRunAgent}
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
          disabled={!canRunAgent}
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
            disabled={!canRunAgent}
          />
          spin
        </label>
        <button
          type="button"
          className="primary"
          disabled={!canRunAgent}
          onClick={() => void onAuthorIntoPie()}
        >
          Author into PIE
        </button>
      </div>

      <div className="agent-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={!isConnected ? 'Connect PIE first' : !preflightReady ? 'PIE preflight must pass before sending a goal' : 'Goal for the agent…'}
          disabled={!canRunAgent}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSend(false);
            }
          }}
        />
        <div className="agent-input-actions">
          <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} disabled={agentBusy}>
            <option value="auto">Auto</option>
            <option value="cinematic">Cinematic</option>
            <option value="gameplay">Gameplay</option>
          </select>
          <button type="button" className="primary" disabled={!canRunAgent} onClick={() => onSend(false)}>
            Send
          </button>
          <button type="button" disabled={!canRunAgent} onClick={() => onSend(true)}>
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
