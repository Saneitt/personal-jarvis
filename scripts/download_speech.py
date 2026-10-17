"""One-time network setup. The running assistant never downloads models."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jarvis.config import MODELS
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"
import requests
from huggingface_hub import snapshot_download

def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        print(f"Already downloaded: {path.name}", flush=True)
        return
    print(f"Downloading {path.name}", flush=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with requests.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with tmp.open("wb") as file:
            for chunk in response.iter_content(1024 * 1024):
                file.write(chunk)
    tmp.replace(path)

voice = "en_GB-alan-medium"
base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/"
for suffix in [".onnx", ".onnx.json"]:
    download(base + voice + suffix, MODELS / "piper" / (voice + suffix))
download(base + "MODEL_CARD", MODELS / "piper" / "MODEL_CARD")
for name in ["hey_jarvis_v0.1", "embedding_model", "melspectrogram"]:
    download(f"https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/{name}.onnx",
             MODELS / "wake" / f"{name}.onnx")
print("Downloading faster-whisper base.en", flush=True)
snapshot_download("Systran/faster-whisper-base.en", local_dir=MODELS / "whisper" / "base.en",
                  allow_patterns=["*.bin", "*.json", "*.txt"])
print("Speech models are ready for offline use.", flush=True)
