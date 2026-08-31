import { useMissionControlStore } from '../store/missionControlStore';

export function PerformanceMonitor() {
  const metrics = useMissionControlStore((s) => s.metrics);

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
  const gpuTimeStatus = getMetricStatus(metrics.gpuTime, { warning: 12, critical: 16 });
  const drawCallsStatus = getMetricStatus(metrics.drawCalls, { warning: 2000, critical: 4000 });
  const textureMemoryStatus = getMetricStatus(metrics.textureMemory / (1024 ** 3), { warning: 8, critical: 12 });
  const latencyStatus = getMetricStatus(metrics.latency.total, { warning: 300, critical: 500 });

  const networkMs =
    metrics.latency.total - metrics.latency.stt - metrics.latency.llm - metrics.latency.tool - metrics.latency.tts;
  // Scale bars by the largest component so the breakdown reads clearly.
  const latencyDenom = Math.max(
    metrics.latency.stt, metrics.latency.llm, metrics.latency.tool, metrics.latency.tts, networkMs, 1,
  );
  const latencyRows: { label: string; value: number }[] = [
    { label: 'STT (Whisper)', value: metrics.latency.stt },
    { label: 'LLM (Nemotron)', value: metrics.latency.llm },
    { label: 'Tool Execution', value: metrics.latency.tool },
    { label: 'TTS (Kokoro)', value: metrics.latency.tts },
    { label: 'Network', value: networkMs },
  ];

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
          {latencyRows.map((row) => (
            <div key={row.label} className="latency-item">
              <span className="latency-label">{row.label}</span>
              <div className="latency-bar">
                <div
                  className="latency-bar-fill"
                  style={{ width: `${Math.min(100, (row.value / latencyDenom) * 100)}%` }}
                />
              </div>
              <span className="latency-value">{row.value} ms</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}