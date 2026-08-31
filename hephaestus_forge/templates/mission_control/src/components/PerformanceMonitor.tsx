import React from 'react';
import { useMissionControlStore } from '../store/missionControlStore';
import { PerformanceMetrics } from '../store/missionControlStore';

export function PerformanceMonitor() {
  const { metrics } = useMissionControlStore();

  const getMetricStatus = (value: number, thresholds: { warning: number; critical: number }, lowerIsBetter = true) => {
    if (lowerIsBetter) {
      if (value >= thresholds.critical) return 'critical';
      if (value >= thresholds.warning) return 'warning';
      return 'good';
    } else {
      if (value <= thresholds.critical) return 'critical';
      if (value <= thresholds.warning) return 'warning';
      return 'good';
    }
  };

  const renderMetricCard = (
    title: string,
    value: string | number,
    status: string,
    subtitle?: string
  ) => (
    <div className="perf-card">
      <div className="perf-card-title">{title}</div>
      <div className={`perf-value ${status}`}>{value}</div>
      {subtitle && <div className="perf-subtitle">{subtitle}</div>}
    </div>
  );

  if (!metrics) {
    return (
      <div className="perf-grid">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="perf-card">
            <div className="perf-card-title">Loading...</div>
            <div className="perf-value">--</div>
          </div>
        ))}
      </div>
    );
  }

  const fpsStatus = getMetricStatus(metrics.fps, { warning: 45, critical: 30 }, false);
  const frameTimeStatus = getMetricStatus(metrics.frameTime, { warning: 16.67, critical: 33.33 });
  const gpuTimeStatus = getMetricStatus(metrics.gpuTime, { warning: 12, critical: 16 });
  const cpuTimeStatus = getMetricStatus(metrics.cpuTime, { warning: 10, critical: 16 });
  const drawCallsStatus = getMetricStatus(metrics.drawCalls, { warning: 2000, critical: 4000 });
  const trianglesStatus = getMetricStatus(metrics.triangles, { warning: 5_000_000, critical: 10_000_000 });
  const textureMemoryStatus = getMetricStatus(metrics.textureMemory / (1024 ** 3), { warning: 8, critical: 12 });
  const latencyStatus = getMetricStatus(metrics.latency.total, { warning: 300, critical: 500 });

  return (
    <div className="perf-grid">
      {renderMetricCard(
        'FPS',
        metrics.fps,
        fpsStatus,
        `${metrics.frameTime.toFixed(1)} ms/frame`
      )}
      {renderMetricCard(
        'GPU Time',
        `${metrics.gpuTime.toFixed(1)} ms`,
        gpuTimeStatus,
        `CPU: ${metrics.cpuTime.toFixed(1)} ms`
      )}
      {renderMetricCard(
        'Draw Calls',
        metrics.drawCalls.toLocaleString(),
        drawCallsStatus,
        `${(metrics.triangles / 1_000_000).toFixed(1)}M tris`
      )}
      {renderMetricCard(
        'Texture Mem',
        `${(metrics.textureMemory / (1024 ** 3)).toFixed(1)} GB`,
        textureMemoryStatus,
        'Budget: 8 GB'
      )}
      {renderMetricCard(
        'Total Latency',
        `${metrics.latency.total} ms`,
        latencyStatus,
        'Target: <300ms'
      )}

      <div className="perf-card" style={{ gridColumn: '1 / -1' }}>
        <div className="perf-card-title">Latency Breakdown</div>
        <div className="latency-breakdown">
          <div className="latency-item">
            <span className="latency-label">STT (Whisper)</span>
            <span className="latency-value">{metrics.latency.stt} ms</span>
          </div>
          <div className="latency-item">
            <span className="latency-label">LLM (Nemotron)</span>
            <span className="latency-value">{metrics.latency.llm} ms</span>
          </div>
          <div className="latency-item">
            <span className="latency-label">Tool Execution</span>
            <span className="latency-value">{metrics.latency.tool} ms</span>
          </div>
          <div className="latency-item">
            <span className="latency-label">TTS (Kokoro)</span>
            <span className="latency-value">{metrics.latency.tts} ms</span>
          </div>
          <div className="latency-item">
            <span className="latency-label">Network</span>
            <span className="latency-value">{metrics.latency.total - metrics.latency.stt - metrics.latency.llm - metrics.latency.tool - metrics.latency.tts} ms</span>
          </div>
        </div>
      </div>
    </div>
  );
}