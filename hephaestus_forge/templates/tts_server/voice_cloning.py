# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""
Multi-Engine TTS with Voice Cloning Support.
Supports Fish-Speech (primary), XTTS v2, OpenVoice v2, and RVC v2.
"""

import asyncio
import base64
import hashlib
import json
import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Any

import numpy as np
import torch
import torchaudio


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class VoiceProfile:
    """Voice profile with cloning metadata."""
    voice_id: str
    name: str
    language: str = "en"
    gender: Optional[str] = None
    description: str = ""
    # Engine-specific data
    fish_speech_embedding: Optional[np.ndarray] = None
    xtts_embedding: Optional[np.ndarray] = None
    openvoice_embedding: Optional[np.ndarray] = None
    rvc_model_path: Optional[str] = None
    # Reference audio
    reference_audio_paths: List[str] = field(default_factory=list)
    # Metadata
    created_at: float = 0.0
    updated_at: float = 0.0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "voice_id": self.voice_id,
            "name": self.name,
            "language": self.language,
            "gender": self.gender,
            "description": self.description,
            "reference_audio_paths": self.reference_audio_paths,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceProfile":
        profile = cls(
            voice_id=data["voice_id"],
            name=data["name"],
            language=data.get("language", "en"),
            gender=data.get("gender"),
            description=data.get("description", ""),
            reference_audio_paths=data.get("reference_audio_paths", []),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            tags=data.get("tags", []),
        )
        # Engine embeddings loaded separately
        return profile


@dataclass
class TTSRequest:
    """TTS synthesis request."""
    text: str
    voice_id: str
    language: str = "en"
    speed: float = 1.0
    pitch: float = 1.0
    energy: float = 1.0
    emotion: Optional[str] = None
    streaming: bool = True
    sample_rate: int = 24000


@dataclass
class TTSResult:
    """TTS synthesis result."""
    audio_data: bytes
    sample_rate: int
    duration: float
    voice_id: str
    engine: str


# ─── Base Engine Interface ────────────────────────────────────────────────────

class TTSEngine(ABC):
    """Abstract base class for TTS engines."""
    
    name: str = "base"
    supports_cloning: bool = True
    supports_streaming: bool = True
    supports_emotions: bool = False
    sample_rate: int = 24000
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._initialized = False
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the engine."""
        pass
    
    @abstractmethod
    async def synthesize(self, request: TTSRequest, voice_profile: VoiceProfile) -> TTSResult:
        """Synthesize speech."""
        pass
    
    @abstractmethod
    async def synthesize_stream(
        self, 
        request: TTSRequest, 
        voice_profile: VoiceProfile
    ) -> AsyncGenerator[bytes, None]:
        """Stream synthesis chunks."""
        pass
    
    @abstractmethod
    async def clone_voice(
        self, 
        reference_audio_paths: List[str], 
        voice_id: str
    ) -> VoiceProfile:
        """Create voice profile from reference audio."""
        pass
    
    @abstractmethod
    def get_supported_languages(self) -> List[str]:
        """Get supported languages."""
        pass
    
    def is_initialized(self) -> bool:
        return self._initialized


# ─── Fish-Speech Engine ───────────────────────────────────────────────────────

class FishSpeechEngine(TTSEngine):
    """Fish-Speech 1.5 - Primary engine with native voice cloning & streaming."""
    
    name = "fish-speech"
    supports_cloning = True
    supports_streaming = True
    supports_emotions = True
    sample_rate = 24000
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_path = config.get("model_path", "models/fish-speech-1.5-q4_k_m.gguf")
        self.compile = config.get("compile", True)
        self.vqgan_path = config.get("vqgan_path", "models/fish-speech-vqgan.pt")
    
    async def initialize(self) -> bool:
        try:
            # Import fish-speech modules
            # In practice: from fish_speech.models.text2semantic import Text2Semantic
            # For now, stub
            print(f"[{self.name}] Initializing Fish-Speech...")
            self._initialized = True
            return True
        except Exception as e:
            print(f"[{self.name}] Initialization failed: {e}")
            return False
    
    async def synthesize(self, request: TTSRequest, voice_profile: VoiceProfile) -> TTSResult:
        # Stub implementation
        # Real implementation would use fish-speech Text2Semantic + VQGAN
        silence = np.zeros(int(24000 * len(request.text) * 0.08), dtype=np.int16)
        return TTSResult(
            audio_data=silence.tobytes(),
            sample_rate=self.sample_rate,
            duration=len(silence) / self.sample_rate,
            voice_id=request.voice_id,
            engine=self.name,
        )
    
    async def synthesize_stream(
        self, 
        request: TTSRequest, 
        voice_profile: VoiceProfile
    ) -> AsyncGenerator[bytes, None]:
        # Streaming synthesis
        # Real implementation yields chunks from fish-speech
        chunk_size = 4800  # 100ms at 24kHz
        total_chunks = max(1, len(request.text) // 10)
        
        for i in range(total_chunks):
            chunk = np.zeros(chunk_size, dtype=np.int16)
            yield chunk.tobytes()
            await asyncio.sleep(0.05)  # Simulate streaming
    
    async def clone_voice(
        self, 
        reference_audio_paths: List[str], 
        voice_id: str
    ) -> VoiceProfile:
        # Fish-Speech computes speaker embedding from reference audio
        print(f"[{self.name}] Cloning voice {voice_id} from {len(reference_audio_paths)} references")
        
        # In real implementation:
        # embedding = self.model.encode_speaker(reference_audio_paths)
        
        profile = VoiceProfile(
            voice_id=voice_id,
            name=f"Cloned Voice {voice_id[:8]}",
            language="en",
            reference_audio_paths=reference_audio_paths,
            # fish_speech_embedding=embedding,
        )
        return profile
    
    def get_supported_languages(self) -> List[str]:
        return ["en", "zh", "ja", "ko", "fr", "de", "es"]


# ─── XTTS v2 Engine ───────────────────────────────────────────────────────────

class XTTSEngine(TTSEngine):
    """Coqui XTTS v2 - Multilingual voice cloning."""
    
    name = "xtts"
    supports_cloning = True
    supports_streaming = True
    supports_emotions = False
    sample_rate = 22050  # XTTS native rate
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_path = config.get("model_path", "models/xtts_v2.onnx")
    
    async def initialize(self) -> bool:
        try:
            # import onnxruntime
            # self.session = onnxruntime.InferenceSession(self.model_path)
            print(f"[{self.name}] Initializing XTTS v2...")
            self._initialized = True
            return True
        except Exception as e:
            print(f"[{self.name}] Initialization failed: {e}")
            return False
    
    async def synthesize(self, request: TTSRequest, voice_profile: VoiceProfile) -> TTSResult:
        # Stub
        silence = np.zeros(int(self.sample_rate * len(request.text) * 0.08), dtype=np.int16)
        return TTSResult(
            audio_data=silence.tobytes(),
            sample_rate=self.sample_rate,
            duration=len(silence) / self.sample_rate,
            voice_id=request.voice_id,
            engine=self.name,
        )
    
    async def synthesize_stream(
        self, 
        request: TTSRequest, 
        voice_profile: VoiceProfile
    ) -> AsyncGenerator[bytes, None]:
        chunk_size = 4410  # 100ms at 22.05kHz
        total_chunks = max(1, len(request.text) // 10)
        
        for i in range(total_chunks):
            chunk = np.zeros(chunk_size, dtype=np.int16)
            yield chunk.tobytes()
            await asyncio.sleep(0.05)
    
    async def clone_voice(
        self, 
        reference_audio_paths: List[str], 
        voice_id: str
    ) -> VoiceProfile:
        print(f"[{self.name}] Cloning voice {voice_id} from {len(reference_audio_paths)} references")
        
        profile = VoiceProfile(
            voice_id=voice_id,
            name=f"XTTS Voice {voice_id[:8]}",
            language="en",
            reference_audio_paths=reference_audio_paths,
            # xtts_embedding=embedding,
        )
        return profile
    
    def get_supported_languages(self) -> List[str]:
        return [
            "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl",
            "cs", "ar", "zh", "ja", "ko", "hu", "hi", "id", "vi"
        ]


# ─── OpenVoice v2 Engine ──────────────────────────────────────────────────────

class OpenVoiceEngine(TTSEngine):
    """OpenVoice v2 - Fast tone color cloning."""
    
    name = "openvoice"
    supports_cloning = True
    supports_streaming = False  # OpenVoice typically batch
    supports_emotions = False
    sample_rate = 24000
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_path = config.get("model_path", "models/openvoice_v2.onnx")
        self.tone_converter_path = config.get("tone_converter_path", "models/tone_converter.pt")
    
    async def initialize(self) -> bool:
        try:
            print(f"[{self.name}] Initializing OpenVoice v2...")
            self._initialized = True
            return True
        except Exception as e:
            print(f"[{self.name}] Initialization failed: {e}")
            return False
    
    async def synthesize(self, request: TTSRequest, voice_profile: VoiceProfile) -> TTSResult:
        silence = np.zeros(int(self.sample_rate * len(request.text) * 0.08), dtype=np.int16)
        return TTSResult(
            audio_data=silence.tobytes(),
            sample_rate=self.sample_rate,
            duration=len(silence) / self.sample_rate,
            voice_id=request.voice_id,
            engine=self.name,
        )
    
    async def synthesize_stream(
        self, 
        request: TTSRequest, 
        voice_profile: VoiceProfile
    ) -> AsyncGenerator[bytes, None]:
        # OpenVoice doesn't natively stream, but we can chunk
        result = await self.synthesize(request, voice_profile)
        chunk_size = 4800
        for i in range(0, len(result.audio_data), chunk_size):
            yield result.audio_data[i:i+chunk_size]
            await asyncio.sleep(0.01)
    
    async def clone_voice(
        self, 
        reference_audio_paths: List[str], 
        voice_id: str
    ) -> VoiceProfile:
        print(f"[{self.name}] Cloning voice {voice_id} from {len(reference_audio_paths)} references")
        
        profile = VoiceProfile(
            voice_id=voice_id,
            name=f"OpenVoice {voice_id[:8]}",
            language="en",
            reference_audio_paths=reference_audio_paths,
            # openvoice_embedding=embedding,
        )
        return profile
    
    def get_supported_languages(self) -> List[str]:
        return ["en", "zh", "ja", "ko", "fr", "de", "es"]


# ─── RVC v2 Engine ────────────────────────────────────────────────────────────

class RVCEngine(TTSEngine):
    """RVC v2 - Retrieval-based Voice Conversion (highest fidelity)."""
    
    name = "rvc"
    supports_cloning = True  # Requires training
    supports_streaming = False
    supports_emotions = False
    sample_rate = 40000  # RVC typically 40kHz
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.models_dir = config.get("models_dir", "models/rvc")
    
    async def initialize(self) -> bool:
        try:
            print(f"[{self.name}] Initializing RVC v2...")
            self._initialized = True
            return True
        except Exception as e:
            print(f"[{self.name}] Initialization failed: {e}")
            return False
    
    async def synthesize(self, request: TTSRequest, voice_profile: VoiceProfile) -> TTSResult:
        # RVC requires a trained model (.pth) and index file
        if not voice_profile.rvc_model_path:
            raise ValueError(f"RVC model not found for voice {request.voice_id}")
        
        # Real implementation would:
        # 1. Generate base TTS (e.g., from Fish-Speech)
        # 2. Convert using RVC model
        
        silence = np.zeros(int(self.sample_rate * len(request.text) * 0.08), dtype=np.int16)
        return TTSResult(
            audio_data=silence.tobytes(),
            sample_rate=self.sample_rate,
            duration=len(silence) / self.sample_rate,
            voice_id=request.voice_id,
            engine=self.name,
        )
    
    async def synthesize_stream(
        self, 
        request: TTSRequest, 
        voice_profile: VoiceProfile
    ) -> AsyncGenerator[bytes, None]:
        result = await self.synthesize(request, voice_profile)
        chunk_size = 8000
        for i in range(0, len(result.audio_data), chunk_size):
            yield result.audio_data[i:i+chunk_size]
            await asyncio.sleep(0.01)
    
    async def clone_voice(
        self, 
        reference_audio_paths: List[str], 
        voice_id: str
    ) -> VoiceProfile:
        # RVC requires training a model - not instant cloning
        # This would trigger a training job
        print(f"[{self.name}] RVC training required for {voice_id}")
        
        profile = VoiceProfile(
            voice_id=voice_id,
            name=f"RVC Voice {voice_id[:8]}",
            language="en",
            reference_audio_paths=reference_audio_paths,
            rvc_model_path=f"{self.models_dir}/{voice_id}.pth",
        )
        return profile
    
    def get_supported_languages(self) -> List[str]:
        return ["en", "ja", "zh", "ko"]  # Depends on trained models


# ─── Voice Library Manager ────────────────────────────────────────────────────

class VoiceLibrary:
    """Manages voice profiles and embeddings."""
    
    def __init__(self, library_dir: str):
        self.library_dir = Path(library_dir)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.profiles: Dict[str, VoiceProfile] = {}
        self.embeddings_dir = self.library_dir / "embeddings"
        self.embeddings_dir.mkdir(exist_ok=True)
        self.references_dir = self.library_dir / "references"
        self.references_dir.mkdir(exist_ok=True)
        self.rvc_models_dir = self.library_dir / "rv_models"
        self.rvc_models_dir.mkdir(exist_ok=True)
        
        self._load_library()
    
    def _load_library(self):
        """Load all voice profiles from disk."""
        index_file = self.library_dir / "voices_index.json"
        if index_file.exists():
            with open(index_file) as f:
                data = json.load(f)
                for voice_data in data.get("voices", []):
                    profile = VoiceProfile.from_dict(voice_data)
                    self._load_embeddings(profile)
                    self.profiles[profile.voice_id] = profile
    
    def _load_embeddings(self, profile: VoiceProfile):
        """Load engine-specific embeddings."""
        # Fish-Speech embedding
        fs_path = self.embeddings_dir / f"{profile.voice_id}_fish.npy"
        if fs_path.exists():
            profile.fish_speech_embedding = np.load(fs_path)
        
        # XTTS embedding
        xtts_path = self.embeddings_dir / f"{profile.voice_id}_xtts.npy"
        if xtts_path.exists():
            profile.xtts_embedding = np.load(xtts_path)
        
        # OpenVoice embedding
        ov_path = self.embeddings_dir / f"{profile.voice_id}_openvoice.npy"
        if ov_path.exists():
            profile.openvoice_embedding = np.load(ov_path)
    
    def _save_library(self):
        """Save voice index to disk."""
        index_file = self.library_dir / "voices_index.json"
        data = {
            "voices": [p.to_dict() for p in self.profiles.values()]
        }
        with open(index_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _save_embeddings(self, profile: VoiceProfile):
        """Save engine-specific embeddings."""
        if profile.fish_speech_embedding is not None:
            np.save(self.embeddings_dir / f"{profile.voice_id}_fish.npy", profile.fish_speech_embedding)
        if profile.xtts_embedding is not None:
            np.save(self.embeddings_dir / f"{profile.voice_id}_xtts.npy", profile.xtts_embedding)
        if profile.openvoice_embedding is not None:
            np.save(self.embeddings_dir / f"{profile.voice_id}_openvoice.npy", profile.openvoice_embedding)
    
    def add_voice(self, profile: VoiceProfile) -> VoiceProfile:
        """Add or update voice profile."""
        self.profiles[profile.voice_id] = profile
        self._save_embeddings(profile)
        self._save_library()
        return profile
    
    def get_voice(self, voice_id: str) -> Optional[VoiceProfile]:
        return self.profiles.get(voice_id)
    
    def list_voices(self) -> List[VoiceProfile]:
        return list(self.profiles.values())
    
    def delete_voice(self, voice_id: str) -> bool:
        if voice_id in self.profiles:
            del self.profiles[voice_id]
            # Clean up embedding files
            for suffix in ["_fish.npy", "_xtts.npy", "_openvoice.npy"]:
                path = self.embeddings_dir / f"{voice_id}{suffix}"
                if path.exists():
                    path.unlink()
            self._save_library()
            return True
        return False
    
    def import_reference_audio(self, voice_id: str, audio_paths: List[str]) -> List[str]:
        """Copy reference audio to library."""
        imported = []
        voice_ref_dir = self.references_dir / voice_id
        voice_ref_dir.mkdir(exist_ok=True)
        
        for i, src_path in enumerate(audio_paths):
            src = Path(src_path)
            dst = voice_ref_dir / f"ref_{i}{src.suffix}"
            import shutil
            shutil.copy2(src, dst)
            imported.append(str(dst))
        
        return imported


# ─── TTS Manager (Multi-Engine) ───────────────────────────────────────────────

class TTSManager:
    """Multi-engine TTS manager with fallback and voice cloning."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.engines: Dict[str, TTSEngine] = {}
        self.primary_engine_name = config.get("primary", "fish-speech")
        self.fallback_engine_name = config.get("fallback", "xtts")
        self.voice_library = VoiceLibrary(config.get("voice_library_dir", "ProjectMemory/voice_library"))
        self.default_voice_id = config.get("default_voice", "hephaestus_default")
        self._initialized = False
    
    def register_engine(self, engine: TTSEngine):
        self.engines[engine.name] = engine
    
    async def initialize(self) -> bool:
        """Initialize all engines."""
        results = []
        for name, engine in self.engines.items():
            try:
                result = await engine.initialize()
                results.append((name, result))
                print(f"[{name}] {'OK' if result else 'FAILED'}")
            except Exception as e:
                print(f"[{name}] Error: {e}")
                results.append((name, False))
        
        # Check primary engine
        primary_ok = any(name == self.primary_engine_name and ok for name, ok in results)
        if not primary_ok:
            print(f"Warning: Primary engine {self.primary_engine_name} failed, using fallback")
        
        self._initialized = True
        return any(ok for _, ok in results)
    
    def get_engine(self, name: str = None) -> Optional[TTSEngine]:
        name = name or self.primary_engine_name
        return self.engines.get(name)
    
    async def synthesize(
        self, 
        request: TTSRequest, 
        engine_name: str = None
    ) -> TTSResult:
        """Synthesize with fallback."""
        engine = self.get_engine(engine_name)
        if not engine:
            raise ValueError(f"Engine not found: {engine_name or self.primary_engine_name}")
        
        voice_profile = self.voice_library.get_voice(request.voice_id)
        if not voice_profile:
            # Try default voice
            voice_profile = self.voice_library.get_voice(self.default_voice_id)
        if not voice_profile:
            raise ValueError(f"Voice not found: {request.voice_id}")
        
        try:
            return await engine.synthesize(request, voice_profile)
        except Exception as e:
            # Try fallback
            if engine_name != self.fallback_engine_name:
                print(f"[{engine.name}] Failed: {e}, trying fallback...")
                return await self.synthesize(request, self.fallback_engine_name)
            raise
    
    async def synthesize_stream(
        self, 
        request: TTSRequest, 
        engine_name: str = None
    ) -> AsyncGenerator[bytes, None]:
        """Stream synthesis with fallback."""
        engine = self.get_engine(engine_name)
        if not engine:
            raise ValueError(f"Engine not found: {engine_name or self.primary_engine_name}")
        
        voice_profile = self.voice_library.get_voice(request.voice_id)
        if not voice_profile:
            voice_profile = self.voice_library.get_voice(self.default_voice_id)
        if not voice_profile:
            raise ValueError(f"Voice not found: {request.voice_id}")
        
        try:
            async for chunk in engine.synthesize_stream(request, voice_profile):
                yield chunk
        except Exception as e:
            if engine_name != self.fallback_engine_name:
                print(f"[{engine.name}] Stream failed: {e}, trying fallback...")
                fallback_engine = self.get_engine(self.fallback_engine_name)
                if fallback_engine:
                    async for chunk in fallback_engine.synthesize_stream(request, voice_profile):
                        yield chunk
                    return
            raise
    
    async def create_voice(
        self, 
        name: str, 
        reference_audio_paths: List[str],
        engine_name: str = None,
        language: str = "en",
        description: str = ""
    ) -> VoiceProfile:
        """Create new voice profile from reference audio."""
        engine = self.get_engine(engine_name)
        if not engine:
            engine = self.get_engine(self.primary_engine_name)
        
        if not engine.supports_cloning:
            raise ValueError(f"Engine {engine.name} doesn't support voice cloning")
        
        voice_id = str(uuid.uuid4())[:12]
        
        # Import reference audio to library
        imported_paths = self.voice_library.import_reference_audio(voice_id, reference_audio_paths)
        
        # Clone voice with engine
        profile = await engine.clone_voice(imported_paths, voice_id)
        profile.name = name
        profile.language = language
        profile.description = description
        
        # Save to library
        self.voice_library.add_voice(profile)
        
        return profile
    
    def list_voices(self) -> List[VoiceProfile]:
        return self.voice_library.list_voices()
    
    def get_voice(self, voice_id: str) -> Optional[VoiceProfile]:
        return self.voice_library.get_voice(voice_id)
    
    def delete_voice(self, voice_id: str) -> bool:
        return self.voice_library.delete_voice(voice_id)
    
    def get_available_engines(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": e.name,
                "supports_cloning": e.supports_cloning,
                "supports_streaming": e.supports_streaming,
                "supports_emotions": e.supports_emotions,
                "sample_rate": e.sample_rate,
                "languages": e.get_supported_languages(),
                "initialized": e.is_initialized(),
            }
            for e in self.engines.values()
        ]


# ─── Factory ──────────────────────────────────────────────────────────────────

async def create_tts_manager(config: Dict[str, Any]) -> TTSManager:
    """Create and initialize TTS manager with all engines."""
    manager = TTSManager(config)
    
    # Register engines
    tts_config = config.get("models", {})
    
    manager.register_engine(FishSpeechEngine(tts_config.get("fish_speech", {})))
    manager.register_engine(XTTSEngine(tts_config.get("xtts", {})))
    manager.register_engine(OpenVoiceEngine(tts_config.get("openvoice", {})))
    manager.register_engine(RVCEngine(tts_config.get("rvc", {})))
    
    await manager.initialize()
    return manager


# ─── FastAPI Server ───────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
    import uvicorn

    app = FastAPI(title="Hephaestus TTS Server", version="1.0.0")
    _tts_manager: Optional[TTSManager] = None

    class SynthesizeRequest(BaseModel):
        text: str
        voice_id: str = "hephaestus_default"
        engine: Optional[str] = None

    @app.on_event("startup")
    async def _startup():
        global _tts_manager
        config = {
            "models": {
                "fish_speech": {"model_path": os.getenv("FISH_SPEECH_MODEL", "models/fish-speech-1.5-q4_k_m.gguf")},
                "xtts": {"model_path": os.getenv("XTTS_MODEL", "models/xtts_v2.onnx")},
            },
        }
        _tts_manager = await create_tts_manager(config)

    @app.get("/health")
    async def health():
        return {"status": "healthy", "engines": _tts_manager.get_available_engines() if _tts_manager else []}

    @app.post("/synthesize")
    async def synthesize(req: SynthesizeRequest):
        if _tts_manager is None:
            raise HTTPException(status_code=503, detail="TTS not initialized")
        request = TTSRequest(text=req.text, voice_id=req.voice_id, engine=req.engine)
        result = await _tts_manager.synthesize(request)
        return {"audio_b64": base64.b64encode(result.audio).decode(), "sample_rate": result.sample_rate}

    if __name__ == "__main__":
        host = os.getenv("TTS_HOST", "127.0.0.1")
        port = int(os.getenv("TTS_PORT", "8082"))
        uvicorn.run(app, host=host, port=port)
except ImportError:
    app = None  # FastAPI optional until deploy installs deps