import { create } from 'zustand';

export interface ThoughtEntry {
  id: string;
  timestamp: number;
  type: 'observation' | 'plan' | 'action' | 'reflection' | 'tool_call' | 'tool_result' | 'error';
  content: string;
  metadata?: Record<string, any>;
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

const API_BASE = (import.meta as any).env?.VITE_HEPHAESTUS_API ?? 'http://127.0.0.1:8765';

async function postCommand(body: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/v1/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json();
}

interface MissionControlState {
  isConnected: boolean;
  frameUrl: string | null;
  connect: () => void;
  disconnect: () => void;
  refreshActors: () => Promise<void>;
  captureFrame: () => Promise<void>;
  sendCommand: (body: Record<string, unknown>) => Promise<any>;

  agentState: AgentState;
  setAgentState: (state: AgentState) => void;

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
        set({ isConnected: !!json.ok });
      } catch {
        set({ isConnected: false });
      }
    };
    tick();
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
      content: `${body.command}: ${result.success ? 'ok' : result.error}`,
      metadata: result,
    });
    return result;
  },

  refreshActors: async () => {
    const result = await get().sendCommand({ command: 'world.list_actors', params: {} });
    let paths: string[] = result.actor_paths ?? [];
    try {
      const inner = JSON.parse(result.result_json || '{}');
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

  thoughtLog: [],
  addThought: (entry) => set((state) => ({
    thoughtLog: [
      ...state.thoughtLog,
      { ...entry, id: crypto.randomUUID(), timestamp: Date.now() }
    ].slice(-500)
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
      const inner = JSON.parse(detail.result_json || '{}');
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
    metrics: state.metrics ? { ...state.metrics, ...metrics } : metrics as PerformanceMetrics
  })),

  isRecording: false,
  setIsRecording: (recording) => set({ isRecording: recording }),
  audioLevel: 0,
  setAudioLevel: (level) => set({ audioLevel: level }),
}));
