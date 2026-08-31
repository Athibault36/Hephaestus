import { useMissionControlStore, PerformanceMetrics } from '../store/missionControlStore';

function isMeasured(metrics: PerformanceMetrics, key: keyof NonNullable<PerformanceMetrics['measured']>): boolean {
  return metrics.measured?.[key] === true;
}

function fmtNum(value: number | null | undefined, digits = 1, suffix = ''): string {
  if (value == null) return '--';
  return `${value.toFixed(digits)}${suffix}`;
}

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

  const fpsValue = metrics.fps ?? null;
  const gpuTimeValue = metrics.gpuTime ?? null;
  const toolCalls = metrics.toolCallCount ?? metrics.drawCalls ?? null;
  const textureMemGb = metrics.textureMemory != null ? metrics.textureMemory / (1024 ** 3) : null;
  const totalLatency = metrics.latency.total ?? null;

  const fpsStatus = fpsValue != null
    ? getMetricStatus(fpsValue, { warning: 45, critical: 30 }, false)
    : 'neutral';
  const gpuTimeStatus = gpuTimeValue != null
    ? getMetricStatus(gpuTimeValue, { warning: 12, critical: 16 })
    : 'neutral';
  const toolCallStatus = toolCalls != null
    ? getMetricStatus(toolCalls, { warning: 2000, critical: 4000 })
    : 'neutral';
  const textureMemoryStatus = textureMemGb != null
    ? getMetricStatus(textureMemGb, { warning: 8, critical: 12 })
    : 'neutral';
  const latencyStatus = totalLatency != null
    ? getMetricStatus(totalLatency, { warning: 300, critical: 500 })
    : 'neutral';

  const stt = metrics.latency.stt ?? 0;
  const llm = metrics.latency.llm ?? 0;
  const tool = metrics.latency.tool ?? 0;
  const tts = metrics.latency.tts ?? 0;
  const total = metrics.latency.total ?? 0;
  const networkMs = total - stt - llm - tool - tts;

  const latencyDenom = Math.max(stt, llm, tool, tts, networkMs, 1);
  const latencyRows: { label: string; value: number | null; measured: boolean }[] = [
    { label: 'STT (Whisper)', value: metrics.latency.stt, measured: metrics.latency.stt != null },
    { label: 'LLM (Nemotron)', value: metrics.latency.llm, measured: isMeasured(metrics, 'llmLatency') },
    { label: 'Tool Execution', value: metrics.latency.tool, measured: isMeasured(metrics, 'toolLatency') },
    { label: 'TTS (Kokoro)', value: metrics.latency.tts, measured: metrics.latency.tts != null },
    { label: 'Network', value: metrics.latency.total != null ? networkMs : null, measured: false },
  ];

  return (
    <div className="perf-grid">
      {renderMetricCard(
        'FPS',
        fpsValue != null ? fpsValue : 'N/A',
        fpsStatus,
        fpsValue != null ? `${fmtNum(metrics.frameTime)} ms/frame` : 'Not measured (UE GPU required)'
      )}
      {renderMetricCard(
        'GPU Time',
        gpuTimeValue != null ? `${fmtNum(gpuTimeValue)} ms` : 'N/A',
        gpuTimeStatus,
        gpuTimeValue != null ? `CPU: ${fmtNum(metrics.cpuTime)} ms` : 'Not measured'
      )}
      {renderMetricCard(
        toolCalls != null && metrics.toolCallCount != null ? 'Tool Calls' : 'Draw Calls',
        toolCalls != null ? toolCalls.toLocaleString() : 'N/A',
        toolCallStatus,
        metrics.triangles != null
          ? `${(metrics.triangles / 1_000_000).toFixed(1)}M tris`
          : metrics.toolCallCount != null
            ? 'Agent-measured'
            : 'Not measured'
      )}
      {renderMetricCard(
        'Texture Mem',
        textureMemGb != null ? `${textureMemGb.toFixed(1)} GB` : 'N/A',
        textureMemoryStatus,
        textureMemGb != null ? 'Budget: 8 GB' : 'Not measured'
      )}
      {renderMetricCard(
        'Total Latency',
        totalLatency != null ? `${totalLatency} ms` : 'N/A',
        latencyStatus,
        totalLatency != null ? 'Target: <300ms' : 'Awaiting agent activity'
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
                  style={{
                    width: row.value != null
                      ? `${Math.min(100, (row.value / latencyDenom) * 100)}%`
                      : '0%',
                  }}
                />
              </div>
              <span className="latency-value">
                {row.value != null ? `${row.value} ms` : '--'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
