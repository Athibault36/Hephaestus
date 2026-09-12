import { create } from 'zustand';

export interface ThoughtEntry {
  id: string;
  timestamp: number;
  type: 'observation' | 'plan' | 'action' | 'reflection' | 'tool_call' | 'tool_result' | 'error';
  content: string;
  metadata?: Record<string, unknown>;
}

export interface ActorInfo {
  path: string;
  name: string;
  class: string;
  location: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
  isSelected: boolean;
  components: string[];
}

export interface AssetInfo {
  path: string;
  name: string;
  type: string;
  size: number;
  modified: number;
  tags: string[];
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface GradeSummary {
  met: boolean;
  score: number;
  summary: string;
  missing: string[];
}

export interface PerformanceMetrics {
  fps: number | null;
  frameTime: number | null;
  gpuTime: number | null;
  cpuTime: number | null;
  drawCalls: number | null;
  triangles: number | null;
  textureMemory: number | null;
  latency: {
    stt: number | null;
    llm: number | null;
    tool: number | null;
    tts: number | null;
    total: number | null;
  };
}

export type AgentState = 'idle' | 'listening' | 'thinking' | 'acting' | 'speaking' | 'error';

/** Same-origin when served by forge observe (proxies /v1 and /agent). */
const API_BASE: string = (import.meta as { env?: { VITE_HEPHAESTUS_API?: string } }).env?.VITE_HEPHAESTUS_API ?? '';

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof SyntaxError) return fallback;
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === 'string' && error.trim()) return error;
  return fallback;
}

function getReadableDetail(value: unknown, fallback: string) {
  if (value instanceof SyntaxError) return fallback;
  if (value instanceof Error && value.message) return value.message;
  if (typeof value === 'string' && value.trim()) return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const key of ['message', 'detail', 'error', 'reason', 'summary']) {
      const candidate = record[key];
      if (typeof candidate === 'string' && candidate.trim()) return candidate;
    }
  }
  return fallback;
}

async function postCommand(body: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/v1/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const error = (data as { error?: unknown }).error;
    throw new Error(getReadableDetail(error, `Bridge command failed (${res.status})`));
  }
  return data as Record<string, unknown>;
}

async function pollAgentJob(jobId: string): Promise<Record<string, unknown>> {
  const deadline = Date.now() + 30 * 60 * 1000;
  while (Date.now() < deadline) {
    const res = await fetch(`${API_BASE}/agent/job/${encodeURIComponent(jobId)}`);
    const data = await res.json();
    if (data.status === 'done' && data.result) return data.result as Record<string, unknown>;
    if (data.status === 'error') throw new Error(getReadableDetail(data.error, 'Agent job failed'));
    await new Promise((r) => setTimeout(r, 350));
  }
  throw new Error('Agent job timed out');
}

interface MissionControlState {
  isConnected: boolean;
  isConnecting: boolean;
  connectionError: string;
  frameUrl: string | null;
  frameLoading: boolean;
  frameError: string;
  connect: () => void;
  disconnect: () => void;
  refreshActors: () => Promise<void>;
  captureFrame: () => Promise<void>;
  sendCommand: (body: Record<string, unknown>) => Promise<Record<string, unknown>>;
  searchAssets: (query: string, assetClass?: string) => Promise<void>;
  spawnAsset: (assetPath: string) => Promise<boolean>;

  agentState: AgentState;
  setAgentState: (state: AgentState) => void;
  agentBusy: boolean;
  agentError: string;
  chatMessages: ChatMessage[];
  lastGrade: GradeSummary | null;
  preflightReady: boolean;
  plannerAvailable: boolean;
  preflightHint: string;
  bridgeCapabilitiesOk: boolean;
  agentHealthLoading: boolean;
  agentHealthError: string;
  forgeVersion: string;
  operatorMilestone: string;
  assetMatches: string[];
  connectThoughtStream: () => void;
  exportSession: () => Promise<void>;
  sendAgentChat: (message: string, opts?: { reset?: boolean; mode?: string }) => Promise<void>;
  loadAgentHealth: () => Promise<void>;
  loadSession: () => Promise<void>;

  thoughtLog: ThoughtEntry[];
  addThought: (entry: Omit<ThoughtEntry, 'id' | 'timestamp'>) => void;
  clearThoughts: () => void;

  actors: ActorInfo[];
  actorsLoading: boolean;
  actorsError: string;
  selectedActor: string | null;
  setActors: (actors: ActorInfo[]) => void;
  selectActor: (path: string | null) => void;
  playLocomotion: (mode: 'idle' | 'walk' | 'run') => Promise<void>;
  playMontage: () => Promise<void>;
  frameActor: () => Promise<void>;
  destroyActor: () => Promise<void>;

  assets: AssetInfo[];
  assetsLoading: boolean;
  assetsError: string;
  assetSearchAttempted: boolean;
  setAssets: (assets: AssetInfo[]) => void;

  metrics: PerformanceMetrics | null;
  updateMetrics: (metrics: Partial<PerformanceMetrics>) => void;

  isRecording: boolean;
  setIsRecording: (recording: boolean) => void;
  audioLevel: number;
  setAudioLevel: (level: number) => void;
}

let healthTimer: number | undefined;
let thoughtSource: EventSource | null = null;

export const useMissionControlStore = create<MissionControlState>((set, get) => ({
  isConnected: false,
  isConnecting: false,
  connectionError: '',
  frameUrl: null,
  frameLoading: false,
  frameError: '',

  connect: () => {
    const tick = async () => {
      if (!get().isConnected) set({ isConnecting: true });
      try {
        const t0 = performance.now();
        const res = await fetch(`${API_BASE}/v1/health`);
        const pingMs = Math.round(performance.now() - t0);
        const json = await res.json();
        const online = !!json.ok;
        set({
          isConnected: online,
          isConnecting: false,
          connectionError: online ? '' : 'UE bridge health responded but is not ready yet.',
        });
        if (!online) {
          set({ metrics: null });
          return;
        }
        await get().refreshActors();
        const actorCount = get().actors.length;
        get().updateMetrics({
          fps: null,
          frameTime: pingMs,
          gpuTime: null,
          cpuTime: null,
          drawCalls: actorCount,
          triangles: null,
          textureMemory: null,
          latency: { stt: null, llm: null, tool: pingMs, tts: null, total: pingMs },
        });
      } catch (error) {
        set({
          isConnected: false,
          isConnecting: false,
          frameUrl: null,
          metrics: null,
          connectionError: getErrorMessage(error, 'Mission Control cannot reach forge observe or the UE bridge yet.'),
        });
      }
    };
    tick();
    get().loadAgentHealth();
    get().loadSession();
    get().connectThoughtStream();
    healthTimer = window.setInterval(tick, 4000);
  },

  disconnect: () => {
    if (healthTimer) window.clearInterval(healthTimer);
    set({ isConnected: false, isConnecting: false, frameUrl: null, metrics: null });
  },

  sendCommand: async (body) => {
    try {
      const result = await postCommand(body);
      get().addThought({
        type: result.success ? 'tool_result' : 'error',
        content: `${body.command}: ${result.success ? 'ok' : getReadableDetail(result.error, 'failed')}`,
        metadata: result,
      });
      return result;
    } catch (error) {
      const message = getErrorMessage(error, 'Command failed before the bridge returned a result.');
      get().addThought({
        type: 'error',
        content: `${String(body.command || 'Command')}: ${message}`,
      });
      throw error;
    }
  },

  searchAssets: async (query, assetClass = '') => {
    const q = query.trim();
    if (!q) {
      set({ assets: [], assetsError: '', assetSearchAttempted: false });
      return;
    }
    set({ assetsLoading: true, assetsError: '', assetSearchAttempted: true });
    try {
      const params: Record<string, unknown> = { query: q, limit: 24 };
      if (assetClass) params.class = assetClass;
      const result = await get().sendCommand({ command: 'asset.search', params });
      if (result.success === false) {
        throw new Error(getReadableDetail(result.error, 'Asset search failed in the UE bridge.'));
      }
      let paths: string[] = [];
      try {
        const inner = JSON.parse(String(result.result_json || '{}'));
        if (Array.isArray(inner.assets)) paths = inner.assets;
      } catch {
        /* ignore */
      }
      set({
        assets: paths.map((path) => ({
          path,
          name: path.split('.').pop() || path,
          type: path.includes('SkeletalMesh') ? 'SkeletalMesh' : path.includes('Anim') ? 'AnimSequence' : 'Asset',
          size: 0,
          modified: 0,
          tags: [],
        })),
        assetsLoading: false,
      });
    } catch (error) {
      set({
        assets: [],
        assetsLoading: false,
        assetsError: getErrorMessage(error, 'Asset search is unavailable while the bridge is offline.'),
      });
    }
  },

  spawnAsset: async (assetPath) => {
    try {
      const res = await fetch(`${API_BASE}/agent/spawn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_path: assetPath, with_light: true }),
      });
      const data = await res.json();
      if (data.ok) {
        await get().refreshActors();
        await get().captureFrame();
      } else {
        set({ assetsError: getReadableDetail(data.error, 'The selected asset could not be spawned in PIE.') });
      }
      return !!data.ok;
    } catch (error) {
      set({ assetsError: getErrorMessage(error, 'The selected asset could not be spawned in PIE.') });
      return false;
    }
  },

  refreshActors: async () => {
    set({ actorsLoading: true, actorsError: '' });
    try {
      const result = await get().sendCommand({
        command: 'world.list_actors',
        params: { include_details: true, detail_limit: 40 },
      });
      if (result.success === false) {
        throw new Error(getReadableDetail(result.error, 'World actors could not be loaded from the bridge.'));
      }
      let paths: string[] = (result.actor_paths as string[]) ?? [];
      const detailsByPath = new Map<string, Record<string, unknown>>();
      try {
        const inner = JSON.parse(String(result.result_json || '{}'));
        if (Array.isArray(inner.actors)) paths = inner.actors;
        if (Array.isArray(inner.actor_details)) {
          for (const row of inner.actor_details) {
            const path = String((row as { path?: string }).path || '');
            if (path) detailsByPath.set(path, row as Record<string, unknown>);
          }
        }
      } catch {
        /* ignore */
      }
      set({
        actors: paths.map((path) => {
          const detail = detailsByPath.get(path);
          const loc = (detail?.location as { x?: number; y?: number; z?: number }) || {};
          const rot = (detail?.rotation as { pitch?: number; yaw?: number; roll?: number }) || {};
          const scl = (detail?.scale as { x?: number; y?: number; z?: number }) || {};
          return {
            path,
            name: path.split('.').pop() || path,
            class: String(detail?.class || (/SkeletalMeshActor|Character|SimAgent/.test(path) ? 'SkeletalMeshActor' : 'Actor')),
            location: [loc.x ?? 0, loc.y ?? 0, loc.z ?? 0],
            rotation: [rot.pitch ?? 0, rot.yaw ?? 0, rot.roll ?? 0],
            scale: [scl.x ?? 1, scl.y ?? 1, scl.z ?? 1],
            isSelected: false,
            components: [],
          };
        }),
        actorsLoading: false,
      });
    } catch (error) {
      set({
        actors: [],
        actorsLoading: false,
        actorsError: getErrorMessage(error, 'World actors could not be loaded from the bridge.'),
      });
    }
  },

  captureFrame: async () => {
    set({ frameLoading: true, frameError: '' });
    try {
      const result = await get().sendCommand({ command: 'vision.capture_frame', params: {} });
      if (result.success) {
        set({ frameUrl: `${API_BASE}/v1/frame?t=${Date.now()}`, frameLoading: false });
      } else {
        set({ frameLoading: false, frameError: getReadableDetail(result.error, 'Viewport capture is not available yet.') });
      }
    } catch (error) {
      set({
        frameLoading: false,
        frameError: getErrorMessage(error, 'Viewport capture is not available while PIE is offline.'),
      });
    }
  },

  agentState: 'idle',
  setAgentState: (state) => set({ agentState: state }),
  agentBusy: false,
  agentError: '',
  chatMessages: [],
  lastGrade: null,
  preflightReady: false,
  plannerAvailable: false,
  preflightHint: '',
  bridgeCapabilitiesOk: true,
  agentHealthLoading: false,
  agentHealthError: '',
  forgeVersion: '',
  operatorMilestone: '',

  assetMatches: [],
  connectThoughtStream: () => {
    const connect = () => {
      if (thoughtSource) {
        thoughtSource.close();
        thoughtSource = null;
      }
      thoughtSource = new EventSource(`${API_BASE}/agent/thoughts/stream`);
      thoughtSource.onmessage = (ev) => {
        try {
          const t = JSON.parse(ev.data);
          if (t.content) {
            get().addThought({
              type: t.kind === 'error' ? 'error' : 'reflection',
              content: getReadableDetail(t.content, 'Structured thought event received.'),
              metadata: t.metadata,
            });
          }
        } catch {
          /* ignore */
        }
      };
      thoughtSource.onerror = () => {
        if (thoughtSource) {
          thoughtSource.close();
          thoughtSource = null;
        }
        window.setTimeout(connect, 5000);
      };
    };
    connect();
  },

  exportSession: async () => {
    const res = await fetch(`${API_BASE}/agent/export`);
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `hephaestus-session-${data.session?.id || 'export'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  },

  loadAgentHealth: async () => {
    set({ agentHealthLoading: true, agentHealthError: '' });
    try {
      const res = await fetch(`${API_BASE}/agent/health`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(getReadableDetail(data.error, `Director preflight failed (${res.status}).`));
      }
      const checks = Array.isArray(data.checks) ? data.checks : [];
      const bridgeTemplate = checks.find((c: { name?: string }) => c.name === 'bridge_template');
      const bridgeHint = getReadableDetail(
        bridgeTemplate?.detail || data.bridge_capabilities,
        'Bridge capability details are available in preflight checks.',
      );
      set({
        preflightReady: !!data.ready_for_goals,
        plannerAvailable: !!data.llm_available,
        preflightHint: bridgeHint,
        bridgeCapabilitiesOk: data.bridge_capabilities_ok !== false,
        agentHealthLoading: false,
        forgeVersion: String(data.forge_version || ''),
        operatorMilestone: String(data.operator_milestone || 'v1.0'),
      });
    } catch (error) {
      set({
        preflightReady: false,
        plannerAvailable: false,
        bridgeCapabilitiesOk: false,
        agentHealthLoading: false,
        agentHealthError: getErrorMessage(error, 'Director preflight is unavailable until forge observe is running.'),
      });
    }
  },

  loadSession: async () => {
    try {
      const res = await fetch(`${API_BASE}/agent/session`);
      const data = await res.json();
      const messages = data.session?.messages;
      if (Array.isArray(messages)) {
        set({
          chatMessages: messages.map((m: { role: string; content: string }) => ({
            role: m.role === 'user' ? 'user' : 'assistant',
            content: m.content || '',
          })),
        });
      }
      if (data.session?.last_grade) {
        set({ lastGrade: data.session.last_grade });
      }
    } catch {
      /* ignore */
    }
  },

  sendAgentChat: async (message, opts = {}) => {
    set({ agentBusy: true, agentState: 'thinking', agentError: '' });
    try {
      const res = await fetch(`${API_BASE}/agent/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          reset: !!opts.reset,
          mode: opts.mode || 'auto',
          max_steps: 20,
        }),
      });
      let data = await res.json();
      if (!res.ok) {
        throw new Error(getReadableDetail(data.error || data.llm_error, `Agent request failed (${res.status}).`));
      }
      if (res.status === 202 && data.job_id) {
        data = await pollAgentJob(String(data.job_id));
      }
      if (data.session?.messages) {
        set({
          chatMessages: data.session.messages.map((m: { role: string; content: string }) => ({
            role: m.role === 'user' ? 'user' : 'assistant',
            content: m.content || '',
          })),
        });
      }
      if (data.grade) set({ lastGrade: data.grade });
      if (data.asset_matches) set({ assetMatches: data.asset_matches });
      if (data.thoughts) {
        for (const t of data.thoughts) {
          get().addThought({
            type: (t.kind as ThoughtEntry['type']) || 'reflection',
            content: t.content || '',
            metadata: t.metadata,
          });
        }
      }
      if (!data.ok) {
        const message = getReadableDetail(data.llm_error || data.error, 'The director could not complete that goal.');
        set({ agentError: message });
        get().addThought({ type: 'error', content: `Agent request failed: ${message}` });
      }
      set({ agentState: data.ok ? 'idle' : 'error' });
      await get().refreshActors();
      await get().captureFrame();
    } catch (error) {
      const message = getErrorMessage(error, 'The director request failed before Mission Control received a reply.');
      set((state) => ({
        agentState: 'error',
        agentError: message,
        chatMessages: [
          ...state.chatMessages,
          { role: 'assistant', content: `I could not complete that goal: ${message}` },
        ],
      }));
      get().addThought({ type: 'error', content: `Agent request failed: ${message}` });
    } finally {
      set({ agentBusy: false });
    }
  },

  thoughtLog: [],
  addThought: (entry) => set((state) => ({
    thoughtLog: [
      ...state.thoughtLog,
      { ...entry, id: crypto.randomUUID(), timestamp: Date.now() },
    ].slice(-500),
  })),
  clearThoughts: () => set({ thoughtLog: [] }),

  actors: [],
  actorsLoading: false,
  actorsError: '',
  selectedActor: null,
  setActors: (actors) => set({ actors }),
  selectActor: (path) => set({ selectedActor: path }),

  playLocomotion: async (mode) => {
    const path = get().selectedActor;
    if (!path) return;
    await get().sendCommand({
      command: 'animation.play_locomotion',
      params: { actor_path: path, mode, loop: true },
    });
    await get().refreshActors();
  },

  playMontage: async () => {
    const path = get().selectedActor;
    if (!path) return;
    await get().searchAssets('idle', 'AnimMontage');
    const montage = get().assets.find((a) => a.type.includes('Anim'))?.path;
    if (!montage) {
      get().addThought({ type: 'error', content: 'No montage found — search assets first' });
      return;
    }
    await get().sendCommand({
      command: 'animation.play_montage',
      params: { actor_path: path, montage_path: montage, loop: true },
    });
    await get().refreshActors();
  },

  frameActor: async () => {
    const path = get().selectedActor;
    if (!path) return;
    const detail = await get().sendCommand({ command: 'world.get_actor', params: { actor_path: path } });
    let loc = { x: 0, y: 0, z: 200 };
    try {
      const inner = JSON.parse(String(detail.result_json || '{}'));
      if (inner.location) loc = inner.location;
    } catch {
      /* ignore */
    }
    await get().sendCommand({
      command: 'sequence.create_shot',
      params: {
        location: { x: loc.x - 280, y: loc.y + 120, z: loc.z + 90 },
        rotation: { pitch: -12, yaw: 25, roll: 0 },
        duration: 2.5,
      },
    });
  },

  destroyActor: async () => {
    const path = get().selectedActor;
    if (!path) return;
    await get().sendCommand({ command: 'world.destroy_actor', params: { actor_path: path } });
    set({ selectedActor: null });
    await get().refreshActors();
  },

  assets: [],
  assetsLoading: false,
  assetsError: '',
  assetSearchAttempted: false,
  setAssets: (assets) => set({ assets }),

  metrics: null,
  updateMetrics: (metrics) => set((state) => ({
    metrics: state.metrics ? { ...state.metrics, ...metrics } : metrics as PerformanceMetrics,
  })),

  isRecording: false,
  setIsRecording: (recording) => set({ isRecording: recording }),
  audioLevel: 0,
  setAudioLevel: (level) => set({ audioLevel: level }),
}));
