import base64
import asyncio
import importlib.util
import json
import sys
import types
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mission_control_server  # noqa: E402
import studio_voice  # noqa: E402


class _FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self.status = status
        self._payload = payload
        self.headers = headers or {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


def _write_ref(project_root: Path, voice_id: str = "hephaestus_default") -> Path:
    ref_dir = project_root / "ProjectMemory" / "voice_library" / "references" / voice_id
    ref_dir.mkdir(parents=True)
    ref = ref_dir / "ref_0.wav"
    ref.write_bytes(b"ref-audio")
    return ref


def test_detect_engine_prefers_healthy_local_8082(monkeypatch):
    def fake_urlopen(req, timeout=None):
        assert req.full_url == "http://127.0.0.1:8082/health"
        assert timeout <= 2
        return _FakeResponse({"status": "healthy", "engines": ["fish-speech", "xtts"]})

    monkeypatch.delenv("HEPHAESTUS_TTS_BASE_URL", raising=False)
    monkeypatch.delenv("HEPHAESTUS_TTS_8082_URL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    engine = studio_voice.detect_engine()

    assert engine["engine"] == "local_tts_8082"
    assert engine["base_url"] == "http://127.0.0.1:8082"
    assert engine["fallback"] != "browser"


def test_voice_status_clone_ready_requires_local_engine_and_reference_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(
        studio_voice,
        "detect_engine",
        lambda: {
            "engine": "local_tts_8082",
            "base_url": "http://127.0.0.1:8082",
            "fallback": "local",
            "detail": "healthy",
        },
    )
    _write_ref(tmp_path)

    status = studio_voice.voice_status(project_root=tmp_path)

    assert status["ok"] is True
    assert status["engine"] == "local_tts_8082"
    assert status["enrolled"] is True
    assert status["clone_ready"] is True
    assert status["fallback"] != "browser"


def test_synthesize_talkback_posts_to_local_tts_and_decodes_audio(monkeypatch, tmp_path):
    _write_ref(tmp_path)
    expected_audio = b"fake-wav"
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append((req, timeout))
        body = json.loads(req.data.decode("utf-8"))
        assert req.full_url == "http://127.0.0.1:8082/synthesize"
        assert body == {
            "text": "Welcome back.",
            "voice_id": "hephaestus_default",
            "engine": "fish-speech",
        }
        return _FakeResponse({"audio_b64": base64.b64encode(expected_audio).decode("ascii"), "sample_rate": 24000})

    monkeypatch.setattr(
        studio_voice,
        "detect_engine",
        lambda: {
            "engine": "local_tts_8082",
            "base_url": "http://127.0.0.1:8082",
            "fallback": "local",
        },
    )
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = studio_voice.synthesize_talkback(
        "Welcome back.",
        project_root=tmp_path,
        voice_id="hephaestus_default",
        engine="fish-speech",
    )

    assert result["ok"] is True
    assert result["engine"] == "local_tts_8082"
    assert result["voice_id"] == "hephaestus_default"
    assert result["audio_b64"] == base64.b64encode(expected_audio).decode("ascii")
    assert result["sample_rate"] == 24000
    assert calls


def test_synthesize_talkback_does_not_count_browser_fallback_as_success(monkeypatch, tmp_path):
    monkeypatch.setattr(
        studio_voice,
        "detect_engine",
        lambda: {"engine": None, "base_url": "", "fallback": "browser", "detail": "no tts engine"},
    )

    result = studio_voice.synthesize_talkback("Hello", project_root=tmp_path)

    assert result["ok"] is False
    assert result["fallback"] == "browser"
    assert "engine" in result["error"]


def test_enroll_voice_reference_saves_refs_without_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(
        studio_voice,
        "detect_engine",
        lambda: {"engine": None, "base_url": "", "fallback": "browser", "detail": "no tts engine"},
    )

    result = studio_voice.enroll_voice_reference(
        base64.b64encode(b"reference-audio").decode("ascii"),
        project_root=tmp_path,
        voice_id="hephaestus_default",
        filename="sample.wav",
    )

    assert result["ok"] is True
    assert result["enrolled"] is True
    assert result["clone_ready"] is False
    assert result["engine"] is None
    saved = tmp_path / "ProjectMemory" / "voice_library" / "references" / "hephaestus_default" / "sample.wav"
    assert saved.read_bytes() == b"reference-audio"


def test_enroll_voice_reference_rejects_oversized_or_non_audio_refs(monkeypatch, tmp_path):
    monkeypatch.setenv("HEPHAESTUS_VOICE_REF_MAX_BYTES", "4")

    oversized = studio_voice.enroll_voice_reference(
        base64.b64encode(b"12345").decode("ascii"),
        project_root=tmp_path,
        filename="sample.wav",
    )
    non_audio = studio_voice.enroll_voice_reference(
        base64.b64encode(b"1234").decode("ascii"),
        project_root=tmp_path,
        filename="sample.txt",
    )

    assert oversized["ok"] is False
    assert "too large" in oversized["error"]
    assert non_audio["ok"] is False
    assert "audio" in non_audio["error"]
    assert not (tmp_path / "ProjectMemory" / "voice_library" / "references").exists()


def test_env_base_url_remains_a_fallback_after_local_8082(monkeypatch):
    responses = []

    def fake_urlopen(req, timeout=None):
        responses.append(req.full_url)
        if req.full_url == "http://127.0.0.1:8082/health":
            raise OSError("local down")
        if req.full_url == "http://tts.example/health":
            return _FakeResponse({"ok": True, "engine": "remote-clone"})
        raise AssertionError(req.full_url)

    monkeypatch.setenv("HEPHAESTUS_TTS_BASE_URL", "http://tts.example")
    monkeypatch.delenv("HEPHAESTUS_TTS_8082_URL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    engine = studio_voice.detect_engine()

    assert responses == ["http://127.0.0.1:8082/health", "http://tts.example/health"]
    assert engine["engine"] == "remote_tts"
    assert engine["base_url"] == "http://tts.example"


def test_mission_control_voice_status_and_talkback_routes(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(
        studio_voice,
        "voice_status",
        lambda project_root=None, voice_id="hephaestus_default": {
            "ok": True,
            "engine": "local_tts_8082",
            "clone_ready": True,
            "enrolled": True,
        },
    )
    monkeypatch.setattr(
        studio_voice,
        "synthesize_talkback",
        lambda text, project_root=None, voice_id="hephaestus_default", engine=None: {
            "ok": True,
            "engine": "local_tts_8082",
            "audio_b64": base64.b64encode(b"audio").decode("ascii"),
            "sample_rate": 24000,
            "voice_id": voice_id,
        },
    )

    handler_cls = mission_control_server.make_handler(dist, "http://127.0.0.1:8765", project_root=tmp_path)
    server = mission_control_server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    try:
        port = server.server_address[1]
        thread = mission_control_server.threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        with mission_control_server.urllib.request.urlopen(
            f"http://127.0.0.1:{port}/agent/voice/status",
            timeout=5,
        ) as resp:
            status = json.loads(resp.read().decode("utf-8"))
        assert status["engine"] == "local_tts_8082"
        assert status["clone_ready"] is True

        req = mission_control_server.urllib.request.Request(
            f"http://127.0.0.1:{port}/agent/talkback",
            data=json.dumps({"text": "Hello", "voice_id": "speaker"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with mission_control_server.urllib.request.urlopen(req, timeout=5) as resp:
            talkback = json.loads(resp.read().decode("utf-8"))
        assert talkback["ok"] is True
        assert talkback["engine"] == "local_tts_8082"
        assert talkback["voice_id"] == "speaker"

        enroll_req = mission_control_server.urllib.request.Request(
            f"http://127.0.0.1:{port}/agent/voice/enroll",
            data=json.dumps({
                "audio_b64": base64.b64encode(b"ref").decode("ascii"),
                "voice_id": "speaker",
                "filename": "speaker.wav",
            }).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        monkeypatch.setattr(
            studio_voice,
            "enroll_voice_reference",
            lambda audio_b64, project_root=None, voice_id="hephaestus_default", filename=None: {
                "ok": True,
                "engine": "local_tts_8082",
                "clone_ready": True,
                "enrolled": True,
                "voice_id": voice_id,
                "filename": filename,
            },
        )
        with mission_control_server.urllib.request.urlopen(enroll_req, timeout=5) as resp:
            enrolled = json.loads(resp.read().decode("utf-8"))
        assert enrolled["ok"] is True
        assert enrolled["voice_id"] == "speaker"

        bad_req = mission_control_server.urllib.request.Request(
            f"http://127.0.0.1:{port}/agent/talkback",
            data=b"[]",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            mission_control_server.urllib.request.urlopen(bad_req, timeout=5)
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error"] == "invalid_json_object"
        else:
            raise AssertionError("non-object JSON should return 400")
    finally:
        server.shutdown()
        server.server_close()


def _load_voice_cloning_template(monkeypatch):
    class FakeArray:
        def __init__(self, samples):
            self.samples = samples

        def tobytes(self):
            return b"\0" * self.samples * 2

    fake_np = types.SimpleNamespace(
        ndarray=object,
        int16="int16",
        zeros=lambda samples, dtype=None: FakeArray(samples),
        load=lambda path: None,
        save=lambda path, value: None,
    )
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        device=lambda name: name,
    )
    monkeypatch.setitem(sys.modules, "numpy", fake_np)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "torchaudio", types.SimpleNamespace())

    module_name = "voice_cloning_template_under_test"
    path = ROOT / "templates" / "tts_server" / "voice_cloning.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_template_synthesize_builds_voice_profile_from_reference_files(monkeypatch, tmp_path):
    module = _load_voice_cloning_template(monkeypatch)
    library_dir = tmp_path / "ProjectMemory" / "voice_library"
    ref_dir = library_dir / "references" / "hephaestus_default"
    ref_dir.mkdir(parents=True)
    (ref_dir / "ref_0.wav").write_bytes(b"ref")

    class RecordingEngine(module.TTSEngine):
        name = "fish-speech"
        supports_cloning = True
        supports_streaming = True
        supports_emotions = False
        sample_rate = 24000

        async def initialize(self):
            self._initialized = True
            return True

        async def synthesize(self, request, voice_profile):
            assert voice_profile.voice_id == "hephaestus_default"
            assert voice_profile.reference_audio_paths == [str(ref_dir / "ref_0.wav")]
            return module.TTSResult(
                audio_data=b"audio",
                sample_rate=24000,
                duration=0.1,
                voice_id=request.voice_id,
                engine=self.name,
            )

        async def synthesize_stream(self, request, voice_profile):
            yield b"audio"

        async def clone_voice(self, reference_audio_paths, voice_id):
            return module.VoiceProfile(
                voice_id=voice_id,
                name="from refs",
                reference_audio_paths=reference_audio_paths,
            )

        def get_supported_languages(self):
            return ["en"]

    manager = module.TTSManager({
        "voice_library_dir": str(library_dir),
        "default_voice": "hephaestus_default",
    })
    manager.register_engine(RecordingEngine({}))

    result = asyncio.run(manager.synthesize(module.TTSRequest(
        text="Welcome back.",
        voice_id="hephaestus_default",
        engine="fish-speech",
    )))

    assert result.audio_data == b"audio"
    assert manager.voice_library.get_voice("hephaestus_default") is not None
