import { useRef, useEffect } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import { ThoughtEntry } from '../store/missionControlStore';

export function ChainOfThought() {
  const thoughtLog = useMissionControlStore((s) => s.thoughtLog);
  const clearThoughts = useMissionControlStore((s) => s.clearThoughts);
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
    const hms = date.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const ms = date.getMilliseconds().toString().padStart(3, '0');
    return `${hms}.${ms}`;
  };

  return (
    <div className="thought-log" role="log" aria-live="polite">
      {thoughtLog.length === 0 ? (
        <div className="thought-empty">
          <span className="empty-icon">🧠</span>
          <p>No thoughts yet...</p>
          <p className="empty-hint">Agent thoughts will appear here</p>
        </div>
      ) : (
        thoughtLog.map((entry) => (
          <div key={entry.id} className={`thought-entry ${entry.type}`}>
            <span className="thought-time">{formatTime(entry.timestamp)}</span>
            <span className={`thought-type ${entry.type}`}>{getTypeIcon(entry.type)} {entry.type.toUpperCase()}</span>
            <div className="thought-content">
              {entry.content}
              {entry.metadata && (
                <details className="thought-metadata">
                  <summary>Metadata</summary>
                  <pre>{JSON.stringify(entry.metadata, null, 2)}</pre>
                </details>
              )}
            </div>
          </div>
        ))
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