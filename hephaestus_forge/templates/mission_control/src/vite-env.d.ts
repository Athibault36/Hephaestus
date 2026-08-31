/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BRIDGE_URL?: string;
  readonly VITE_UE_BRIDGE_URL?: string;
  readonly VITE_UE_BRIDGE_TOKEN?: string;
  readonly VITE_FRAME_POLL_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
