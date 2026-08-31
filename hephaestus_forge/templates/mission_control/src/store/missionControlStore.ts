import { create } from 'zustand';
import { io, Socket } from 'socket.io-client';

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

interface MissionControlState {
  // Connection
  socket: Socket | null;
  isConnected: boolean;
  connect: () => void;
  disconnect: () => void;

  // Agent state
  agentState: AgentState;
  setAgentState: (state: AgentState) => void;

  // Chain of Thought
  thoughtLog: ThoughtEntry[];
  addThought: (entry: Omit<ThoughtEntry, 'id' | 'timestamp'>) => void;
  clearThoughts: () => void;

  // World Outliner
  actors: ActorInfo[];
  selectedActor: string | null;
  setActors: (actors: ActorInfo[]) => void;
  selectActor: (path: string | null) => void;

  // Asset Browser
  assets: AssetInfo[];
  setAssets: (assets: AssetInfo[]) => void;

  // Performance
  metrics: PerformanceMetrics | null;
  updateMetrics: (metrics: Partial<PerformanceMetrics>) => void;

  // Voice (always-on, speaker-verified — no push-to-talk)
  isRecording: boolean;
  setIsRecording: (recording: boolean) => void;
  audioLevel: number;
  setAudioLevel: (level: number) => void;
  voiceActive: boolean;                       // continuous listening enabled
  setVoiceActive: (active: boolean) => void;
  speakerRecognized: boolean | null;          // true=you, false=other speaker, null=idle
  setSpeakerRecognized: (recognized: boolean | null) => void;

  // Viewport frame (PNG data URL pushed by the agent bridge)
  latestFrame: string | null;
  setLatestFrame: (dataUrl: string | null) => void;
}

export const useMissionControlStore = create<MissionControlState>((set, get) => ({
  // Connection
  socket: null,
  isConnected: false,
  connect: () => {
    const socket = io('http://127.0.0.1:8081', {
      transports: ['polling', 'websocket'],
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
    });

    socket.on('connect', () => {
      set({ isConnected: true });
      console.log('[MissionControl] Connected to UE');
    });

    socket.on('disconnect', () => {
      set({ isConnected: false });
      console.log('[MissionControl] Disconnected from UE');
    });

    socket.on('thought', (entry: ThoughtEntry) => {
      get().addThought(entry);
    });

    socket.on('actors', (actors: ActorInfo[]) => {
      set({ actors });
    });

    socket.on('assets', (assets: AssetInfo[]) => {
      set({ assets });
    });

    socket.on('metrics', (metrics: PerformanceMetrics) => {
      set({ metrics });
    });

    socket.on('agentState', (state: AgentState) => {
      set({ agentState: state });
    });

    socket.on('audioLevel', (level: number) => {
      set({ audioLevel: level });
    });

    socket.on('frame', (frame: { dataUrl: string }) => {
      if (frame && frame.dataUrl) set({ latestFrame: frame.dataUrl });
    });

    socket.on('voiceActive', (active: boolean) => {
      set({ voiceActive: !!active });
    });

    socket.on('speaker', (info: { recognized: boolean }) => {
      set({ speakerRecognized: info ? info.recognized : null });
    });

    set({ socket });
  },

  disconnect: () => {
    const { socket } = get();
    if (socket) {
      socket.disconnect();
      set({ socket: null, isConnected: false });
    }
  },

  // Agent state
  agentState: 'idle',
  setAgentState: (state) => set({ agentState: state }),

  // Chain of Thought
  thoughtLog: [],
  addThought: (entry) => set((state) => ({
    thoughtLog: [
      ...state.thoughtLog,
      { ...entry, id: crypto.randomUUID(), timestamp: Date.now() }
    ].slice(-500) // Keep last 500 entries
  })),
  clearThoughts: () => set({ thoughtLog: [] }),

  // World Outliner
  actors: [],
  selectedActor: null,
  setActors: (actors) => set({ actors }),
  selectActor: (path) => set({ selectedActor: path }),

  // Asset Browser
  assets: [],
  setAssets: (assets) => set({ assets }),

  // Performance
  metrics: null,
  updateMetrics: (metrics) => set((state) => ({
    metrics: state.metrics ? { ...state.metrics, ...metrics } : metrics as PerformanceMetrics
  })),

  // Voice
  isRecording: false,
  setIsRecording: (recording) => set({ isRecording: recording }),
  audioLevel: 0,
  setAudioLevel: (level) => set({ audioLevel: level }),
  voiceActive: true,
  setVoiceActive: (active) => set({ voiceActive: active }),
  speakerRecognized: null,
  setSpeakerRecognized: (recognized) => set({ speakerRecognized: recognized }),

  // Viewport frame
  latestFrame: null,
  setLatestFrame: (dataUrl) => set({ latestFrame: dataUrl }),
}));