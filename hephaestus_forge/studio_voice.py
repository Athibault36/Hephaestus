"""Mission Control voice enrollment and talkback helpers."""

from __future__ import annotations

import base64
import binascii
import importlib.util
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional


DEFAULT_LOCAL_TTS_URL = "http://127.0.0.1:8082"
DEFAULT_VOICE_ID = "hephaestus_default"
REFERENCE_ROOT = Path("ProjectMemory") / "voice_library" / "references"
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_ALLOWED_REFERENCE_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}
_DEFAULT_MAX_REFERENCE_BYTES = 25 * 1024 * 1024


def _project_root(project_root: Optional[Path]) -> Path:
    return Path(project_root) if project_root else Path.cwd()


def _safe_voice_id(voice_id: str) -> str:
    safe = _SAFE_FILENAME_RE.sub("_", Path(voice_id or DEFAULT_VOICE_ID).name).strip("._")
    return safe or DEFAULT_VOICE_ID


def _references_dir(project_root: Optional[Path], voice_id: str = DEFAULT_VOICE_ID) -> Path:
    return _project_root(project_root) / REFERENCE_ROOT / _safe_voice_id(voice_id)


def _reference_files(project_root: Optional[Path], voice_id: str = DEFAULT_VOICE_ID) -> list[Path]:
    ref_dir = _references_dir(project_root, voice_id)
    if not ref_dir.exists():
        return []
    return sorted(p for p in ref_dir.iterdir() if p.is_file())


def _healthy(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status", "")).strip().lower()
    return bool(payload.get("ok")) or status in {"ok", "healthy", "ready"}


def _read_json(resp) -> dict[str, Any]:
    raw = resp.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _probe_http_engine(base_url: str, engine_name: str) -> dict[str, Any]:
    health_url = base_url.rstrip("/") + "/health"
    req = urllib.request.Request(health_url, method="GET")
    with urllib.request.urlopen(req, timeout=1.5) as resp:
        payload = _read_json(resp)
    if not _healthy(payload):
        return {
            "ok": False,
            "engine": None,
            "base_url": base_url.rstrip("/"),
            "fallback": "browser",
            "detail": f"{engine_name} health not ready",
            "health": payload,
        }
    return {
        "ok": True,
        "engine": engine_name,
        "base_url": base_url.rstrip("/"),
        "fallback": "none",
        "detail": "healthy",
        "health": payload,
    }


def _probe_coqui() -> dict[str, Any]:
    if importlib.util.find_spec("TTS") is None:
        return {
            "ok": False,
            "engine": None,
            "base_url": "",
            "fallback": "browser",
            "detail": "no local TTS service or Coqui TTS import",
        }
    return {
        "ok": True,
        "engine": "coqui",
        "base_url": "",
        "fallback": "none",
        "detail": "Coqui TTS import available",
    }


def detect_engine() -> dict[str, Any]:
    """Detect the best available talkback engine.

    Prefer the live local clone/TTS service, then an explicit HTTP override,
    then an importable Coqui TTS package. Browser speech synthesis is reported
    only as a fallback and is never a successful engine.
    """

    local_url = os.getenv("HEPHAESTUS_TTS_8082_URL", DEFAULT_LOCAL_TTS_URL).strip() or DEFAULT_LOCAL_TTS_URL
    errors: list[str] = []
    try:
        local = _probe_http_engine(local_url, "local_tts_8082")
        if local.get("ok"):
            return local
        errors.append(f"{local_url}/health: {local.get('detail', 'not ready')}")
    except Exception as exc:
        errors.append(f"{local_url}/health: {exc}")

    env_url = os.getenv("HEPHAESTUS_TTS_BASE_URL", "").strip()
    if env_url and env_url.rstrip("/") != local_url.rstrip("/"):
        try:
            remote = _probe_http_engine(env_url, "remote_tts")
            if remote.get("ok"):
                return remote
            errors.append(f"{env_url.rstrip('/')}/health: {remote.get('detail', 'not ready')}")
        except Exception as exc:
            errors.append(f"{env_url.rstrip('/')}/health: {exc}")

    coqui = _probe_coqui()
    if coqui.get("ok"):
        if errors:
            coqui["detail"] = f"{coqui['detail']}; HTTP probes failed: {'; '.join(errors)}"
        return coqui

    detail = coqui["detail"]
    if errors:
        detail = f"{detail}; {'; '.join(errors)}"
    return {
        "ok": False,
        "engine": None,
        "base_url": "",
        "fallback": "browser",
        "detail": detail,
    }


def voice_status(
    project_root: Optional[Path] = None,
    voice_id: str = DEFAULT_VOICE_ID,
) -> dict[str, Any]:
    voice_id = _safe_voice_id(voice_id)
    engine = detect_engine()
    refs = _reference_files(project_root, voice_id)
    engine_name = engine.get("engine")
    http_clone_engine = engine_name in {"local_tts_8082", "remote_tts"}
    engine_ok = bool(engine.get("ok", bool(engine_name)))
    clone_ready = bool(engine_ok and http_clone_engine and refs)
    return {
        "ok": True,
        "voice_id": voice_id,
        "engine": engine_name,
        "engine_ok": engine_ok,
        "base_url": engine.get("base_url", ""),
        "fallback": engine.get("fallback", "browser"),
        "enrolled": bool(refs),
        "reference_count": len(refs),
        "clone_ready": clone_ready,
        "detail": engine.get("detail", ""),
    }


def _decode_audio_b64(audio_b64: str) -> bytes:
    try:
        return base64.b64decode(audio_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid audio_b64 from TTS server") from exc


def _synthesize_http(
    base_url: str,
    text: str,
    voice_id: str,
    engine: Optional[str] = None,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    payload: dict[str, Any] = {"text": text, "voice_id": voice_id}
    if engine:
        payload["engine"] = engine
    req = urllib.request.Request(
        base_url + "/synthesize",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        return _read_speech_response(req)
    except urllib.error.HTTPError as exc:
        if exc.code not in {404, 405, 501}:
            raise

    shim_payload = {
        "model": engine or "tts-1",
        "input": text,
        "voice": voice_id,
        "response_format": "wav",
    }
    shim_req = urllib.request.Request(
        base_url + "/v1/audio/speech",
        data=json.dumps(shim_payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return _read_speech_response(shim_req)


def _read_speech_response(req: urllib.request.Request) -> dict[str, Any]:
    with urllib.request.urlopen(req, timeout=60) as resp:
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read()

    if content_type.startswith("audio/"):
        audio = raw
        return {
            "audio_b64": base64.b64encode(audio).decode("ascii"),
            "sample_rate": None,
            "audio_bytes": len(audio),
        }

    data = json.loads(raw.decode("utf-8") or "{}")
    audio_b64 = str(data.get("audio_b64") or "")
    if not audio_b64:
        raise ValueError("TTS server response missing audio_b64")
    audio = _decode_audio_b64(audio_b64)
    return {
        "audio_b64": base64.b64encode(audio).decode("ascii"),
        "sample_rate": data.get("sample_rate"),
        "audio_bytes": len(audio),
    }


def _synthesize_coqui(text: str, voice_id: str) -> dict[str, Any]:
    from TTS.api import TTS  # type: ignore

    model_name = os.getenv("HEPHAESTUS_COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC")
    tts = TTS(model_name=model_name, progress_bar=False)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        tts.tts_to_file(text=text, file_path=str(tmp_path))
        audio = tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
    return {
        "audio_b64": base64.b64encode(audio).decode("ascii"),
        "sample_rate": None,
        "audio_bytes": len(audio),
        "voice_id": voice_id,
    }


def synthesize_talkback(
    text: str,
    project_root: Optional[Path] = None,
    voice_id: str = DEFAULT_VOICE_ID,
    engine: Optional[str] = None,
) -> dict[str, Any]:
    voice_id = _safe_voice_id(voice_id)
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "text required", "fallback": "browser"}

    detected = detect_engine()
    engine_name = detected.get("engine")
    engine_ok = bool(detected.get("ok", bool(engine_name)))
    if not engine_ok or not engine_name:
        return {
            "ok": False,
            "engine": engine_name,
            "fallback": detected.get("fallback", "browser"),
            "error": f"no real TTS engine available: {detected.get('detail', '')}",
            "voice_id": voice_id,
        }

    try:
        if engine_name in {"local_tts_8082", "remote_tts"}:
            audio = _synthesize_http(str(detected.get("base_url") or ""), text, voice_id, engine)
        elif engine_name == "coqui":
            audio = _synthesize_coqui(text, voice_id)
        else:
            raise ValueError(f"unsupported TTS engine: {engine_name}")
    except Exception as exc:
        return {
            "ok": False,
            "engine": engine_name,
            "fallback": "browser",
            "error": str(exc),
            "voice_id": voice_id,
        }

    return {
        "ok": True,
        "engine": engine_name,
        "fallback": detected.get("fallback", "none"),
        "voice_id": voice_id,
        **audio,
    }


def _safe_filename(filename: Optional[str], ref_dir: Path) -> str:
    if filename:
        name = _SAFE_FILENAME_RE.sub("_", Path(filename).name).strip("._")
        if name:
            return name
    return f"ref_{len(list(ref_dir.glob('ref_*'))) + 1}.webm"


def _max_reference_bytes() -> int:
    raw = os.getenv("HEPHAESTUS_VOICE_REF_MAX_BYTES", "").strip()
    if not raw:
        return _DEFAULT_MAX_REFERENCE_BYTES
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_MAX_REFERENCE_BYTES


def _looks_like_reference_audio(audio: bytes, filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    if suffix == ".wav":
        return len(audio) >= 12 and audio.startswith(b"RIFF") and audio[8:12] == b"WAVE"
    if suffix == ".webm":
        return audio.startswith(b"\x1a\x45\xdf\xa3")
    if suffix == ".ogg":
        return audio.startswith(b"OggS")
    if suffix == ".flac":
        return audio.startswith(b"fLaC")
    if suffix == ".mp3":
        return audio.startswith(b"ID3") or (len(audio) >= 2 and audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0)
    if suffix == ".m4a":
        return len(audio) >= 12 and audio[4:8] == b"ftyp"
    if suffix == ".aac":
        return len(audio) >= 2 and audio[0] == 0xFF and (audio[1] & 0xF6) in {0xF0, 0xF2}
    return False


def enroll_voice_reference(
    audio_b64: str,
    project_root: Optional[Path] = None,
    voice_id: str = DEFAULT_VOICE_ID,
    filename: Optional[str] = None,
) -> dict[str, Any]:
    voice_id = _safe_voice_id(voice_id)
    if not audio_b64:
        return {"ok": False, "error": "audio_b64 required", "voice_id": voice_id}
    try:
        audio = base64.b64decode(audio_b64, validate=True)
    except (binascii.Error, ValueError):
        return {"ok": False, "error": "invalid audio_b64", "voice_id": voice_id}
    if not audio:
        return {"ok": False, "error": "audio_b64 decoded to empty audio", "voice_id": voice_id}
    if len(audio) > _max_reference_bytes():
        return {"ok": False, "error": "voice reference audio is too large", "voice_id": voice_id}

    ref_dir = _references_dir(project_root, voice_id)
    name = _safe_filename(filename, ref_dir)
    if Path(name).suffix.lower() not in _ALLOWED_REFERENCE_EXTENSIONS:
        return {"ok": False, "error": "voice reference must use an audio filename", "voice_id": voice_id}
    if not _looks_like_reference_audio(audio, name):
        return {"ok": False, "error": "voice reference does not look like supported audio", "voice_id": voice_id}

    ref_dir.mkdir(parents=True, exist_ok=True)
    dest = ref_dir / name
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        index = 2
        while dest.exists():
            dest = ref_dir / f"{stem}_{index}{suffix}"
            index += 1
    dest.write_bytes(audio)

    status = voice_status(project_root=project_root, voice_id=voice_id)
    return {
        "ok": True,
        "voice_id": voice_id,
        "saved_ref": str(dest),
        "filename": dest.name,
        "enrolled": status["enrolled"],
        "clone_ready": status["clone_ready"],
        "engine": status["engine"],
        "fallback": status["fallback"],
        "reference_count": status["reference_count"],
    }
