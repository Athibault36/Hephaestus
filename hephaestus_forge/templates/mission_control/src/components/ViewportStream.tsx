import { useEffect, useRef, useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import {
  captureFrameObjectUrl,
  checkBridgeHealth,
  getFramePollIntervalMs,
  getUeBridgeBase,
} from '../lib/ueBridge';

export function ViewportStream() {
  const isConnected = useMissionControlStore((s) => s.isConnected);
  const latestFrame = useMissionControlStore((s) => s.latestFrame);
  const setLatestFrame = useMissionControlStore((s) => s.setLatestFrame);
  const metrics = useMissionControlStore((s) => s.metrics);

  const [bridgeOnline, setBridgeOnline] = useState(false);
  const [pollError, setPollError] = useState<string | null>(null);
  const [pollFps, setPollFps] = useState(0);
  const objectUrlRef = useRef<string | null>(null);
  const lastPollRef = useRef<number>(0);

  // Poll UE bridge GET /frame (via capture_frame -> /frame/:id) when Socket.IO
  // has not pushed a frame yet, or as a fallback live feed.
  useEffect(() => {
    let cancelled = false;
    const pollMs = getFramePollIntervalMs();

    const poll = async () => {
      const healthy = await checkBridgeHealth();
      if (cancelled) return;
      setBridgeOnline(healthy);
      if (!healthy) {
        setPollError('UE bridge unreachable');
        return;
      }

      try {
        const objectUrl = await captureFrameObjectUrl();
        if (cancelled || !objectUrl) return;

        if (objectUrlRef.current) {
          URL.revokeObjectURL(objectUrlRef.current);
        }
        objectUrlRef.current = objectUrl;
        setLatestFrame(objectUrl);
        setPollError(null);

        const now = performance.now();
        if (lastPollRef.current > 0) {
          const interval = now - lastPollRef.current;
          setPollFps(Math.round(1000 / interval));
        }
        lastPollRef.current = now;
      } catch (err) {
        if (!cancelled) {
          setPollError(err instanceof Error ? err.message : 'frame poll failed');
        }
      }
    };

    poll();
    const interval = setInterval(poll, pollMs);
    return () => {
      cancelled = true;
      clearInterval(interval);
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [setLatestFrame]);

  const stats = {
    fps: metrics?.fps || pollFps || 0,
    bitrate: 0,
    latency: metrics?.latency?.tool || 0,
  };

  const showPlaceholder = !isConnected && !bridgeOnline && !latestFrame;

  return (
    <div className="viewport-container">
      {latestFrame ? (
        <img
          key={latestFrame}
          className="viewport-stream viewport-frame"
          src={latestFrame}
          alt="Latest captured UE viewport frame"
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
      ) : (
        <canvas className="viewport-stream" style={{ width: '100%', height: '100%' }} />
      )}

      <div className="viewport-overlay" />

      <div className="viewport-stats">
        <span>FPS: {stats.fps || '—'}</span>
        <span>Tool latency: {stats.latency ? `${stats.latency}ms` : '—'}</span>
        <span>Bridge: {getUeBridgeBase()}</span>
      </div>

      {pollError && bridgeOnline === false && (
        <div className="viewport-placeholder viewport-poll-hint">
          <p className="placeholder-hint">{pollError}</p>
        </div>
      )}

      {showPlaceholder && (
        <div className="viewport-placeholder">
          <div className="placeholder-content">
            <span className="placeholder-icon">📷</span>
            <p>Waiting for UE connection...</p>
            <p className="placeholder-hint">
              Run <code>hephaestus_forge deploy</code> or start the UE bridge at{' '}
              <code>{getUeBridgeBase()}</code>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
