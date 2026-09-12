import { useEffect } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import { PanelState } from './PanelState';

export function ViewportStream() {
  const { isConnected, frameUrl, frameLoading, frameError, captureFrame } = useMissionControlStore();

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
      ) : frameLoading ? (
        <PanelState
          tone="loading"
          icon="📷"
          title="Capturing viewport"
          message="Mission Control is asking the UE bridge for the latest PIE frame."
        />
      ) : frameError && isConnected ? (
        <PanelState tone="error" icon="⚠️" title="Viewport unavailable" message={frameError} />
      ) : (
        <div className="viewport-placeholder">
          <PanelState
            tone={isConnected ? 'empty' : 'offline'}
            icon="📷"
            title={isConnected ? 'No frame captured yet' : 'Waiting for PIE'}
            message={
              isConnected
                ? 'The bridge is connected; a viewport frame will appear after capture succeeds.'
                : 'Start Play in UE with HephaestusBridge, then run Mission Control through forge observe.'
            }
          />
        </div>
      )}
    </div>
  );
}
