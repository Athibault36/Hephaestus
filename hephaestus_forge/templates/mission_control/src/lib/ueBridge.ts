/**
 * Minimal UE bridge client for Mission Control viewport polling.
 * Mirrors hephaestus_forge/runtime/ue_client.py over fetch().
 */

const UE_BRIDGE_BASE =
  import.meta.env.VITE_UE_BRIDGE_URL?.replace(/\/$/, '') || '/ue-bridge';
const BRIDGE_TOKEN = import.meta.env.VITE_UE_BRIDGE_TOKEN || '';
const AUTH_HEADER = 'X-Hephaestus-Token';

function bridgeHeaders(json = false): HeadersInit {
  const headers: Record<string, string> = {};
  if (json) headers['Content-Type'] = 'application/json';
  if (BRIDGE_TOKEN) headers[AUTH_HEADER] = BRIDGE_TOKEN;
  return headers;
}

export async function checkBridgeHealth(): Promise<boolean> {
  try {
    const resp = await fetch(`${UE_BRIDGE_BASE}/health`, { headers: bridgeHeaders() });
    if (!resp.ok) return false;
    const data = await resp.json();
    const status = String(data.status || '').toLowerCase();
    return status === 'ok' || status === 'healthy' || status === 'ready' || !!data.healthy;
  } catch {
    return false;
  }
}

/** Capture a viewport frame and return a PNG object URL for <img src>. */
export async function captureFrameObjectUrl(): Promise<string | null> {
  const captureResp = await fetch(`${UE_BRIDGE_BASE}/command`, {
    method: 'POST',
    headers: bridgeHeaders(true),
    body: JSON.stringify({
      command: 'vision.capture_frame',
      params: { action: 'capture_frame' },
    }),
  });
  if (!captureResp.ok) return null;

  const capture = await captureResp.json();
  if (!capture.success) return null;

  let result: Record<string, unknown> = {};
  try {
    result = JSON.parse(capture.result_json || '{}');
  } catch {
    return null;
  }

  const frameId = result.frame_id;
  if (frameId == null) return null;

  const frameResp = await fetch(`${UE_BRIDGE_BASE}/frame/${frameId}`, {
    headers: bridgeHeaders(),
  });
  if (!frameResp.ok) return null;

  const blob = await frameResp.blob();
  return URL.createObjectURL(blob);
}

export function getFramePollIntervalMs(): number {
  const raw = import.meta.env.VITE_FRAME_POLL_MS;
  const parsed = raw ? parseInt(raw, 10) : 2000;
  return Number.isFinite(parsed) && parsed >= 500 ? parsed : 2000;
}

export function getUeBridgeBase(): string {
  return UE_BRIDGE_BASE;
}
