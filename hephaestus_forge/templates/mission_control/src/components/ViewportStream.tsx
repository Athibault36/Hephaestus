import { useEffect, useRef, useState } from 'react';
import { useMissionControlStore } from '../store/missionControlStore';

export function ViewportStream() {
  const { isConnected, latestFrame } = useMissionControlStore();
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [stats, setStats] = useState({ fps: 0, bitrate: 0, latency: 0 });
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!isConnected) {
      setStreamUrl(null);
      return;
    }

    // In production, this would connect to WebRTC stream
    // For now, we'll simulate with a placeholder
    const setupStream = async () => {
      try {
        // Would connect to WebRTC peer connection here
        // const stream = await connectToWebRTC();
        // videoRef.current!.srcObject = stream;
      } catch (e) {
        console.error('Failed to setup viewport stream:', e);
      }
    };

    setupStream();

    // Stats polling
    const interval = setInterval(() => {
      setStats({
        fps: Math.floor(Math.random() * 10) + 25,
        bitrate: Math.floor(Math.random() * 2000) + 6000,
        latency: Math.floor(Math.random() * 50) + 20,
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [isConnected]);

  return (
    <div className="viewport-container">
      {streamUrl && videoRef.current ? (
        <video
          ref={videoRef}
          className="viewport-stream"
          autoPlay
          playsInline
          muted
          style={{ width: '100%', height: '100%' }}
        />
      ) : latestFrame ? (
        <img
          className="viewport-stream"
          src={latestFrame}
          alt="Latest captured UE viewport frame"
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
      ) : (
        <canvas
          ref={canvasRef}
          className="viewport-stream"
          style={{ width: '100%', height: '100%' }}
        />
      )}

      <div className="viewport-overlay">
        {/* Debug overlay would be rendered here */}
      </div>

      <div className="viewport-stats">
        <span>FPS: {stats.fps}</span>
        <span>Bitrate: {stats.bitrate} kbps</span>
        <span>Latency: {stats.latency}ms</span>
      </div>

      {!isConnected && (
        <div className="viewport-placeholder">
          <div className="placeholder-content">
            <span className="placeholder-icon">📷</span>
            <p>Waiting for UE connection...</p>
            <p className="placeholder-hint">Run <code>hephaestus_forge deploy</code> to start</p>
          </div>
        </div>
      )}
    </div>
  );
}