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
  fps: number;
  frameTime: number;
  gpuTime: number;
  cpuTime: number;
  drawCalls: number;
  triangles: number;
  textureMemory: number;
  latency: {
    stt: number;
    llm: number;
    tool: number;
    tts: number;
    total: number;
  };
}

export type AgentState = 'idle' | 'listening' | 'thinking' | 'acting' | 'speaking' | 'error';

/** Same-origin when served by forge observe (proxies /v1 and /agent). */
const API_BASE: string = (import.meta as { env?: { VITE_HEPHAESTUS_API?: string } }).env?.VITE_HEPHAESTUS_API ?? '';

async function postCommand(body: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/v1/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function pollAgentJob(jobId: string): Promise<Record<string, unknown>> {
  const deadline = Date.now() + 30 * 60 * 1000;
  while (Date.now() < deadline) {
    const res = await fetch(`${API_BASE}/agent/job/${encodeURIComponent(jobId)}`);
    const data = await res.json();
    if (data.status === 'done' && data.result) return data.result as Record<string, unknown>;
    if (data.status === 'error') throw new Error(String(data.error || 'Agent job failed'));
    await new Promise((r) => setTimeout(r, 350));
  }
  throw new Error('Agent job timed out');
}

interface MissionControlState {
  isConnected: boolean;
  frameUrl: string | null;
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
  chatMessages: ChatMessage[];
  lastGrade: GradeSummary | null;
  preflightReady: boolean;
  plannerAvailable: boolean;
  sendAgentChat: (message: string, opts?: { reset?: boolean; mode?: string }) => Promise<void>;
  loadAgentHealth: () => Promise<void>;
  loadSession: () => Promise<void>;

  thoughtLog: ThoughtEntry[];
  addThought: (entry: Omit<ThoughtEntry, 'id' | 'timestamp'>) => void;
  clearThoughts: () => void;

  actors: ActorInfo[];
  selectedActor: string | null;
  setActors: (actors: ActorInfo[]) => void;
  selectActor: (path: string | null) => void;
  playLocomotion: (mode: 'idle' | 'walk' | 'run') => Promise<void>;
  frameActor: () => Promise<void>;
  destroyActor: () => Promise<void>;

  assets: AssetInfo[];
  setAssets: (assets: AssetInfo[]) => void;

  metrics: PerformanceMetrics | null;
  updateMetrics: (metrics: Partial<PerformanceMetrics>) => void;

  isRecording: boolean;
  setIsRecording: (recording: boolean) => void;
  audioLevel: number;
  setAudioLevel: (level: number) => void;
}

let healthTimer: number | undefined;

export const useMissionControlStore = create<MissionControlState>((set, get) => ({
  isConnected: false,
  frameUrl: null,

  connect: () => {
    const tick = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/health`);
        const json = await res.json();
        const online = !!json.ok;
        set({ isConnected: online });
        if (online) {
          await get().refreshActors();
        }
      } catch {
        set({ isConnected: false });
      }
    };
    tick();
    get().loadAgentHealth();
    get().loadSession();
    healthTimer = window.setInterval(tick, 4000);
  },

  disconnect: () => {
    if (healthTimer) window.clearInterval(healthTimer);
    set({ isConnected: false });
  },

  sendCommand: async (body) => {
    const result = await postCommand(body);
    get().addThought({
      type: result.success ? 'tool_result' : 'error',
      content: `${body.command}: ${result.success ? 'ok' : String(result.error || 'failed')}`,
      metadata: result,
    });
    return result;
  },

  searchAssets: async (query, assetClass = '') => {
    const q = query.trim();
    if (!q) {
      set({ assets: [] });
      return;
    }
    const params: Record<string, unknown> = { query: q, limit: 24 };
    if (assetClass) params.class = assetClass;
    const result = await get().sendCommand({ command: 'asset.search', params });
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
    });
  },

  spawnAsset: async (assetPath) => {
    const res = await fetch(`${API_BASE}/agent/spawn`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_path: assetPath, with_light: true }),
    });
    const data = await res.json();
    if (data.ok) {
      await get().refreshActors();
      await get().captureFrame();
    }
    return !!data.ok;
  },

  refreshActors: async () => {
    const result = await get().sendCommand({ command: 'world.list_actors', params: {} });
    let paths: string[] = (result.actor_paths as string[]) ?? [];
    try {
      const inner = JSON.parse(String(result.result_json || '{}'));
      if (Array.isArray(inner.actors)) paths = inner.actors;
    } catch {
      /* ignore */
    }
    set({
      actors: paths.map((path) => ({
        path,
        name: path.split('.').pop() || path,
        class: /SkeletalMeshActor|Character|SimAgent/.test(path) ? 'SkeletalMeshActor' : 'Actor',
        location: [0, 0, 0],
        rotation: [0, 0, 0],
        scale: [1, 1, 1],
        isSelected: false,
        components: [],
      })),
    });
  },

  captureFrame: async () => {
    const result = await get().sendCommand({ command: 'vision.capture_frame', params: {} });
    if (result.success) {
      set({ frameUrl: `${API_BASE}/v1/frame?t=${Date.now()}` });
    }
  },

  agentState: 'idle',
  setAgentState: (state) => set({ agentState: state }),
  agentBusy: false,
  chatMessages: [],
  lastGrade: null,
  preflightReady: false,
  plannerAvailable: false,

  loadAgentHealth: async () => {
    try {
      const res = await fetch(`${API_BASE}/agent/health`);
      const data = await res.json();
      set({
        preflightReady: !!data.ready_for_goals,
        plannerAvailable: !!data.llm_available,
      });
    } catch {
      set({ preflightReady: false, plannerAvailable: false });
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
    set({ agentBusy: true, agentState: 'thinking' });
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
      if (data.thoughts) {
        for (const t of data.thoughts) {
          get().addThought({
            type: (t.kind as ThoughtEntry['type']) || 'reflection',
            content: t.content || '',
            metadata: t.metadata,
          });
        }
      }
      set({ agentState: data.ok ? 'idle' : 'error' });
      await get().refreshActors();
      await get().captureFrame();
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
