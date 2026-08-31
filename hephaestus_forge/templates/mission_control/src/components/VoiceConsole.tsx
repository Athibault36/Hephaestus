import { useEffect, useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';

/**
 * Always-on, speaker-verified voice console (no push-to-talk).
 *
 * Hephaestus listens continuously and only acts on the enrolled operator's
 * voice. This panel reflects the live listening state and whether the current
 * speaker is recognized; the actual capture + verification runs server-side in
 * the voice pipeline and is pushed here via the bridge.
 */
export function VoiceConsole() {
  const isConnected = useMissionControlStore((s) => s.isConnected);
  const agentState = useMissionControlStore((s) => s.agentState);
  const voiceActive = useMissionControlStore((s) => s.voiceActive);
  const setVoiceActive = useMissionControlStore((s) => s.setVoiceActive);
  const speakerRecognized = useMissionControlStore((s) => s.speakerRecognized);
  const audioLevel = useMissionControlStore((s) => s.audioLevel);
  const [level, setLevel] = useState(0);

  const listening = isConnected && voiceActive && agentState !== 'speaking';

  // Animate the waveform while listening (falls back to store audioLevel when present).
  useEffect(() => {
    if (!listening) {
      setLevel(0);
      return;
    }
    const interval = setInterval(() => {
      setLevel(audioLevel > 0 ? audioLevel : Math.random() * 0.6 + 0.2);
    }, 80);
    return () => clearInterval(interval);
  }, [listening, audioLevel]);

  const bars = Array.from({ length: 40 }, (_, i) => {
    const height = listening ? Math.max(4, level * 100 * (0.4 + Math.abs(Math.sin(i * 0.5)) * 0.6)) : 4;
    return <div key={i} className="voice-bar" style={{ height: `${height}px` }} />;
  });

  const recognition =
    speakerRecognized === true
      ? { cls: 'recognized', icon: '✓', text: 'Recognized — you' }
      : speakerRecognized === false
      ? { cls: 'unrecognized', icon: '✗', text: 'Unrecognized speaker — ignoring' }
      : { cls: 'idle', icon: '•', text: listening ? 'Listening for your voice…' : 'Standby' };

  return (
    <div className="voice-console">
      <div className="voice-visualizer">
        <div className={`voice-waveform ${listening ? 'live' : ''}`} role="img" aria-label="Live audio waveform">
          {bars}
        </div>
        <div className={`voice-status ${listening ? 'live' : ''}`}>
          {listening ? (
            <>
              <span className="listening-dot" /> Always listening
            </>
          ) : isConnected ? (
            'Microphone muted'
          ) : (
            'Connect to UE first'
          )}
        </div>
      </div>

      <div className={`voice-recognition ${recognition.cls}`}>
        <span className="recognition-icon">{recognition.icon}</span>
        <span className="recognition-text">{recognition.text}</span>
      </div>

      <div className="voice-controls">
        <button
          className={`voice-btn ${voiceActive ? 'listening' : 'muted'}`}
          onClick={() => setVoiceActive(!voiceActive)}
          disabled={!isConnected}
          aria-label={voiceActive ? 'Mute microphone' : 'Resume listening'}
          title={voiceActive ? 'Mute (stop listening)' : 'Resume listening'}
        >
          {voiceActive ? '🎙️' : '🔇'}
        </button>
        <div className="voice-input-level">
          <div className="voice-input-level-fill" style={{ width: `${level * 100}%` }} />
        </div>
      </div>

      <div className="voice-history">
        <h4>Recent Commands</h4>
        <div className="command-history">
          {/* Recognized operator utterances appear here */}
        </div>
      </div>
    </div>
  );
}
