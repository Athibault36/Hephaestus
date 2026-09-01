import { useEffect } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';

export function ViewportStream() {
  const { isConnected, frameUrl, captureFrame } = useMissionControlStore();

  useEffect(() => {
    if (!isConnected) return;
    captureFrame();
    const interval = window.setInterval(captureFrame, 4000);
    return () => window.clearInterval(interval);
  }, [isConnected, captureFrame]);

  return (
    <div className="viewport-container">
      {frameUrl ? (
        <img src={frameUrl} alt="UE viewport" className="viewport-stream" />
      ) : (
        <div className="viewport-placeholder">
          <div className="placeholder-content">
            <span className="placeholder-icon">📷</span>
            <p>{isConnected ? 'Capturing viewport…' : 'Waiting for PIE…'}</p>
            <p className="placeholder-hint">Start Play in UE with HephaestusBridge</p>
          </div>
        </div>
      )}
    </div>
  );
}
