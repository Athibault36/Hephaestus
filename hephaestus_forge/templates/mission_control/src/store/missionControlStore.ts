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

export type CreativeBriefSlotName = 'cast' | 'style' | 'shot';
export type CreativeBriefSlotState = 'empty' | 'pending' | 'constrained' | 'error';

export interface CreativeBriefSlot {
  state: CreativeBriefSlotState;
  value: string;
  source: '' | 'manual' | 'reference_image' | 'vision_caption';
}

export interface CreativeBriefReferenceImage {
  name: string;
  type: string;
  size: number | null;
  source: string;
  previewUrl: string;
  url: string;
}

export interface CreativeBriefState {
  status: 'empty' | 'loading' | 'awaiting_vision_caption' | 'caption_received' | 'manual_constraints_applied' | 'error';
  message: string;
  error: string;
  referenceImage: CreativeBriefReferenceImage | null;
  slots: Record<CreativeBriefSlotName, CreativeBriefSlot>;
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

const BRIEF_SLOT_NAMES: CreativeBriefSlotName[] = ['cast', 'style', 'shot'];

function createEmptyBriefSlots(): Record<CreativeBriefSlotName, CreativeBriefSlot> {
  return {
    cast: { state: 'empty', value: '', source: '' },
    style: { state: 'empty', value: '', source: '' },
    shot: { state: 'empty', value: '', source: '' },
  };
}

function createEmptyBrief(): CreativeBriefState {
  return {
    status: 'empty',
    message: 'Attach a sketch or reference image to constrain the brief.',
    error: '',
    referenceImage: null,
    slots: createEmptyBriefSlots(),
  };
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Could not read image file'));
    reader.readAsDataURL(file);
  });
}

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
  preflightHint: string;
  bridgeCapabilitiesOk: boolean;
  forgeVersion: string;
  operatorMilestone: string;
  assetMatches: string[];
  connectThoughtStream: () => void;
  exportSession: () => Promise<void>;
  sendAgentChat: (message: string, opts?: { reset?: boolean; mode?: string }) => Promise<void>;
  loadAgentHealth: () => Promise<void>;
  loadSession: () => Promise<void>;

  creativeBrief: CreativeBriefState;
  attachCreativeBriefReferenceImage: (file: File) => Promise<void>;
  updateCreativeBriefSlot: (slot: CreativeBriefSlotName, value: string) => void;
  resetCreativeBrief: () => void;

  thoughtLog: ThoughtEntry[];
  addThought: (entry: Omit<ThoughtEntry, 'id' | 'timestamp'>) => void;
  clearThoughts: () => void;

  actors: ActorInfo[];
  selectedActor: string | null;
  setActors: (actors: ActorInfo[]) => void;
  selectActor: (path: string | null) => void;
  playLocomotion: (mode: 'idle' | 'walk' | 'run') => Promise<void>;
  playMontage: () => Promise<void>;
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
let thoughtSource: EventSource | null = null;

export const useMissionControlStore = create<MissionControlState>((set, get) => ({
  isConnected: false,
  frameUrl: null,

  connect: () => {
    const tick = async () => {
      try {
        const t0 = performance.now();
        const res = await fetch(`${API_BASE}/v1/health`);
        const pingMs = Math.round(performance.now() - t0);
        const json = await res.json();
        const online = !!json.ok;
        set({ isConnected: online });
        if (online) {
          await get().refreshActors();
        }
        const actorCount = get().actors.length;
        get().updateMetrics({
          fps: online ? 60 : 0,
          frameTime: pingMs,
          gpuTime: 0,
          cpuTime: 0,
          drawCalls: actorCount,
          triangles: 0,
          textureMemory: 0,
          latency: { stt: 0, llm: 0, tool: pingMs, tts: 0, total: pingMs },
        });
      } catch {
        set({ isConnected: false });
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
    const result = await get().sendCommand({
      command: 'world.list_actors',
      params: { include_details: true, detail_limit: 40 },
    });
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
  preflightHint: '',
  bridgeCapabilitiesOk: true,
  forgeVersion: '',
  operatorMilestone: '',

  creativeBrief: createEmptyBrief(),
  attachCreativeBriefReferenceImage: async (file) => {
    set((state) => ({
      creativeBrief: {
        ...state.creativeBrief,
        status: 'loading',
        message: `Reading ${file.name}...`,
        error: '',
      },
    }));
    try {
      const dataUrl = await readFileAsDataUrl(file);
      const res = await fetch(`${API_BASE}/agent/brief/reference-image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_name: file.name,
          image_type: file.type,
          image_url: dataUrl,
        }),
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) {
        throw new Error(String(data.message || data.error || 'Could not attach reference image'));
      }

      const nextSlots = createEmptyBriefSlots();
      const serverSlots = (data.slots || {}) as Record<string, Partial<CreativeBriefSlot>>;
      for (const name of BRIEF_SLOT_NAMES) {
        const slot = serverSlots[name] || {};
        nextSlots[name] = {
          state: (slot.state as CreativeBriefSlotState) || 'pending',
          value: String(slot.value || ''),
          source: (slot.source as CreativeBriefSlot['source']) || 'reference_image',
        };
      }
      const attachment = (data.attachment || {}) as Record<string, unknown>;
      set({
        creativeBrief: {
          status: data.status || 'awaiting_vision_caption',
          message: String(data.message || 'Reference image attached.'),
          error: '',
          referenceImage: {
            name: String(attachment.name || file.name),
            type: String(attachment.type || file.type || 'image'),
            size: typeof attachment.size === 'number' ? attachment.size : file.size || null,
            source: String(attachment.source || 'upload'),
            previewUrl: dataUrl,
            url: String(attachment.url || ''),
          },
          slots: nextSlots,
        },
      });
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      set((state) => ({
        creativeBrief: {
          ...state.creativeBrief,
          status: 'error',
          message: 'Reference image was not attached.',
          error: message,
        },
      }));
    }
  },
  updateCreativeBriefSlot: (slot, value) => set((state) => {
    const nextSlots = {
      ...state.creativeBrief.slots,
      [slot]: {
        state: value.trim() ? 'constrained' : (state.creativeBrief.referenceImage ? 'pending' : 'empty'),
        value,
        source: value.trim() ? 'manual' : (state.creativeBrief.referenceImage ? 'reference_image' : ''),
      },
    } as Record<CreativeBriefSlotName, CreativeBriefSlot>;
    const hasManualConstraints = BRIEF_SLOT_NAMES.some((name) => nextSlots[name].value.trim());
    return {
      creativeBrief: {
        ...state.creativeBrief,
        status: hasManualConstraints
          ? 'manual_constraints_applied'
          : (state.creativeBrief.referenceImage ? 'awaiting_vision_caption' : 'empty'),
        message: hasManualConstraints
          ? 'Manual Creative Brief constraints are applied.'
          : (state.creativeBrief.referenceImage
              ? 'Reference image attached; awaiting vision caption ingress. Add manual constraints meanwhile.'
              : 'Attach a sketch or reference image to constrain the brief.'),
        slots: nextSlots,
      },
    };
  }),
  resetCreativeBrief: () => set({ creativeBrief: createEmptyBrief() }),

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
              content: String(t.content),
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
    try {
      const res = await fetch(`${API_BASE}/agent/health`);
      const data = await res.json();
      const checks = Array.isArray(data.checks) ? data.checks : [];
      const bridgeTemplate = checks.find((c: { name?: string }) => c.name === 'bridge_template');
      set({
        preflightReady: !!data.ready_for_goals,
        plannerAvailable: !!data.llm_available,
        preflightHint: String(bridgeTemplate?.detail || data.bridge_capabilities || ''),
        bridgeCapabilitiesOk: data.bridge_capabilities_ok !== false,
        forgeVersion: String(data.forge_version || ''),
        operatorMilestone: String(data.operator_milestone || 'v1.0'),
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
