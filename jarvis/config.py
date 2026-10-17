from __future__ import annotations
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Literal
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MODELS = ROOT / "models"

class Settings(BaseModel):
    model: str = "jarvis-local:4b"
    ollama_url: str = "http://127.0.0.1:11435"
    owner_name: str = "Captain"
    context_length: int = Field(default=4096, ge=2048, le=65536)
    max_reply_tokens: int = Field(default=256, ge=64, le=2048)
    temperature: float = Field(default=0.65, ge=0, le=1.5)
    stt_model: str = "base.en"
    speech_language: str = "en"
    voice: str = "en_GB-alan-medium"
    tts_engine: Literal["kokoro", "piper"] = "kokoro"
    kokoro_voice: Literal["bm_george", "bm_lewis", "bm_daniel", "bm_fable"] = "bm_george"
    speech_speed: float = Field(default=1.05, ge=0.7, le=1.5)
    wake_threshold: float = Field(default=0.5, ge=0.1, le=0.95)
    silence_ms: int = Field(default=700, ge=300, le=2000)
    follow_up_seconds: int = Field(default=40, ge=5, le=300)
    noise_floor: float = Field(default=0.008, ge=0.001, le=0.15)
    audio_output: Literal["speakers", "headphones"] = "speakers"
    barge_in: bool = True
    confirm_shell: bool = True

    @field_validator("model", "voice", "stt_model")
    @classmethod
    def local_model(cls, value):
        if not value or len(value) > 120 or any(c in value for c in "/\\\r\n"):
            raise ValueError("Use a local model name, not a path or URL")
        if "cloud" in value.lower():
            raise ValueError("Cloud models are disabled")
        return value

    @field_validator("ollama_url")
    @classmethod
    def loopback_only(cls, value):
        parsed = urlparse(value)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("The model server must be on this PC")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Use only the local server address and port")
        return value.rstrip("/")

    @classmethod
    def load(cls):
        path = ROOT / "config.local.json"
        return cls.model_validate_json(path.read_text("utf-8")) if path.exists() else cls()

    def save(self):
        tmp = ROOT / "config.local.json.tmp"
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(ROOT / "config.local.json")

def offline_environment():
    DATA.mkdir(exist_ok=True)
    os.environ.setdefault("HF_HOME", str(MODELS / "huggingface"))
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
