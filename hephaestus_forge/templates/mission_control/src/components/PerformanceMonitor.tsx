import { useMissionControlStore } from '../store/missionControlStore';
import { PanelState } from './PanelState';

export function PerformanceMonitor() {
  const { metrics, isConnected, isConnecting, connectionError } = useMissionControlStore();

  const getMetricStatus = (value: number | null, thresholds: { warning: number; critical: number }, lowerIsBetter = true) => {
    if (value === null) return 'unknown';
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

  const formatNumber = (value: number | null, fallback = 'Waiting') => (
    value === null ? fallback : value.toLocaleString()
  );

  const formatMs = (value: number | null, fallback = 'Not reported') => (
    value === null ? fallback : `${value.toFixed(1)} ms`
  );

  const formatLatency = (value: number | null, fallback = 'Optional') => (
    value === null ? fallback : `${value} ms`
  );

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

  if (!isConnected && !isConnecting) {
    return (
      <PanelState
        tone="offline"
        icon="📊"
        title="Performance offline"
        message={connectionError || 'Start forge observe and PIE to populate bridge health metrics.'}
      />
    );
  }

  if (!metrics) {
    return (
      <PanelState
        tone={isConnecting ? 'loading' : 'empty'}
        icon="📊"
        title={isConnecting ? 'Checking bridge health' : 'Waiting for metrics'}
        message={
          isConnecting
            ? 'Mission Control is probing the bridge before reporting performance.'
            : 'Metrics will populate after the first successful bridge health check.'
        }
      />
    );
  }

  const fpsStatus = getMetricStatus(metrics.fps, { warning: 45, critical: 30 }, false);
  const gpuTimeStatus = getMetricStatus(metrics.gpuTime, { warning: 12, critical: 16 });
  const actorStatus = metrics.drawCalls === null ? 'unknown' : 'good';
  const textureGb = metrics.textureMemory === null ? null : metrics.textureMemory / (1024 ** 3);
  const textureMemoryStatus = getMetricStatus(textureGb, { warning: 8, critical: 12 });
  const latencyStatus = getMetricStatus(metrics.latency.total, { warning: 300, critical: 500 });
  const runtimeLatencyKnown = [metrics.latency.stt, metrics.latency.llm, metrics.latency.tool, metrics.latency.tts, metrics.latency.total]
    .every((value) => typeof value === 'number');
  const networkLatency = runtimeLatencyKnown
    ? (metrics.latency.total as number) - (metrics.latency.stt as number) - (metrics.latency.llm as number) - (metrics.latency.tool as number) - (metrics.latency.tts as number)
    : null;

  return (
    <div className="perf-grid">
      {renderMetricCard(
        'FPS',
        formatNumber(metrics.fps),
        fpsStatus,
        metrics.frameTime === null ? 'Frame timing not reported by bridge' : `${metrics.frameTime.toFixed(1)} ms bridge heartbeat`
      )}
      {renderMetricCard(
        'GPU Time',
        formatMs(metrics.gpuTime),
        gpuTimeStatus,
        `CPU: ${formatMs(metrics.cpuTime)}`
      )}
      {renderMetricCard(
        'World Actors',
        formatNumber(metrics.drawCalls),
        actorStatus,
        'Latest outliner count'
      )}
      {renderMetricCard(
        'Texture Mem',
        textureGb === null ? 'Not reported' : `${textureGb.toFixed(1)} GB`,
        textureMemoryStatus,
        'GPU telemetry pending bridge support'
      )}
      {renderMetricCard(
        'Bridge RTT',
        formatLatency(metrics.latency.tool, 'Waiting'),
        latencyStatus,
        'Health endpoint round-trip'
      )}

      <div className="perf-card" style={{ gridColumn: '1 / -1' }}>
        <div className="perf-card-title">Latency Breakdown</div>
        <div className="latency-breakdown">
          <div className="latency-item">
            <span className="latency-label">STT (optional)</span>
            <span className="latency-value">{formatLatency(metrics.latency.stt)}</span>
          </div>
          <div className="latency-item">
            <span className="latency-label">LLM (Nemotron)</span>
            <span className="latency-value">{formatLatency(metrics.latency.llm, 'Not reported')}</span>
          </div>
          <div className="latency-item">
            <span className="latency-label">Tool Execution</span>
            <span className="latency-value">{formatLatency(metrics.latency.tool, 'Waiting')}</span>
          </div>
          <div className="latency-item">
            <span className="latency-label">TTS (optional)</span>
            <span className="latency-value">{formatLatency(metrics.latency.tts)}</span>
          </div>
          <div className="latency-item">
            <span className="latency-label">Network</span>
            <span className="latency-value">{formatLatency(networkLatency, 'Not reported')}</span>
          </div>
        </div>
      </div>
    </div>
  );
}