import { useRef, useEffect } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import { ThoughtEntry } from '../store/missionControlStore';
import { PanelState } from './PanelState';

function labelForMetadataKey(key: string) {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function summarizeValue(value: unknown) {
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : 'not available';
  if (typeof value === 'string') return value.length > 120 ? `${value.slice(0, 117)}...` : value;
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? '' : 's'}`;
  if (value && typeof value === 'object') return 'structured details available';
  return 'not available';
}

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

function displayThoughtContent(content: string, hasMetadata: boolean) {
  if (isStructuredPayload(content)) {
    return hasMetadata
      ? 'Structured bridge event received; readable details are summarized here.'
      : 'Structured bridge event received.';
  }
  return content;
}

function summarizeResultJson(resultJson: unknown) {
  if (typeof resultJson !== 'string' || !resultJson.trim()) return null;
  try {
    const parsed = JSON.parse(resultJson) as Record<string, unknown>;
    if (Array.isArray(parsed.actors)) return `Actors returned: ${parsed.actors.length}`;
    if (Array.isArray(parsed.actor_details)) return `Actor details returned: ${parsed.actor_details.length}`;
    if (Array.isArray(parsed.assets)) return `Assets returned: ${parsed.assets.length}`;
    if (parsed.location && typeof parsed.location === 'object') return 'Actor location returned';
    return 'Bridge returned structured details';
  } catch {
    return 'Bridge returned text details';
  }
}

function metadataRows(metadata: Record<string, unknown>) {
  const rows: Array<{ label: string; value: string }> = [];
  const resultSummary = summarizeResultJson(metadata.result_json);
  if (resultSummary) rows.push({ label: 'Result', value: resultSummary });

  for (const [key, value] of Object.entries(metadata)) {
    if (key === 'result_json' || key === 'stack' || key === 'traceback') continue;
    rows.push({ label: labelForMetadataKey(key), value: summarizeValue(value) });
  }

  return rows.slice(0, 6);
}

export function ChainOfThought() {
  const { thoughtLog, clearThoughts } = useMissionControlStore();
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [thoughtLog]);

  const getTypeIcon = (type: ThoughtEntry['type']) => {
    switch (type) {
      case 'observation': return '👁️';
      case 'plan': return '📋';
      case 'action': return '⚡';
      case 'reflection': return '🤔';
      case 'tool_call': return '🔧';
      case 'tool_result': return '✅';
      case 'error': return '❌';
    }
  };

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const pad = (n: number, w = 2) => String(n).padStart(w, '0');
    return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(), 3)}`;
  };

  return (
    <div className="thought-log" role="log" aria-live="polite">
      {thoughtLog.length === 0 ? (
        <PanelState
          tone="empty"
          icon="🧠"
          title="No director notes yet"
          message="When the agent observes, plans, or runs tools, readable notes will appear here."
        />
      ) : (
        thoughtLog.map((entry) => {
          const rows = entry.metadata ? metadataRows(entry.metadata) : [];
          return (
            <div key={entry.id} className={`thought-entry ${entry.type}`}>
              <span className="thought-time">{formatTime(entry.timestamp)}</span>
              <span className={`thought-type ${entry.type}`}>{getTypeIcon(entry.type)} {entry.type.toUpperCase()}</span>
              <div className="thought-content">
                {displayThoughtContent(entry.content, rows.length > 0)}
                {rows.length > 0 && (
                  <details className="thought-metadata">
                    <summary>Readable details</summary>
                    <dl className="metadata-summary-list">
                      {rows.map((row) => (
                        <div key={`${entry.id}-${row.label}`} className="metadata-summary-row">
                          <dt>{row.label}</dt>
                          <dd>{row.value}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                )}
              </div>
            </div>
          );
        })
      )}
      <div ref={logEndRef} />
      
      {thoughtLog.length > 0 && (
        <button 
          className="clear-thoughts-btn"
          onClick={clearThoughts}
          title="Clear thought log"
        >
          Clear
        </button>
      )}
    </div>
  );
}