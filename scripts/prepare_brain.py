"""Reuse Qwen3.5's language weights without loading its unused vision projector."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from jarvis.config import MODELS, Settings
SOURCE = "qwen3.5:4b"
TARGET = "jarvis-local:4b"

def prepare(source=SOURCE, target=TARGET):
    if not source.startswith("qwen3.5:") or "/" in source or "\\\\" in source:
        raise ValueError("Use a local Qwen3.5 source model")
    tag = source.split(":", 1)[1]
    manifest = json.loads((MODELS / "ollama/manifests/registry.ollama.ai/library/qwen3.5" / tag).read_text("utf-8"))
    layers = [x for x in manifest["layers"] if x["mediaType"] == "application/vnd.ollama.image.model"]
    if len(layers) != 1:
        raise RuntimeError("Qwen3.5 package changed; inspect its language weights before creating the local profile.")
    with httpx.Client(timeout=120, trust_env=False) as client:
        response = client.post(Settings().ollama_url + "/api/show", json={"model": source})
        response.raise_for_status()
        metadata = response.json()
        response = client.post(Settings().ollama_url + "/api/create", json={
            "model": target, "files": {"model.gguf": layers[0]["digest"]},
            "template": "{{ .Prompt }}", "renderer": "qwen3.5", "parser": "qwen3.5",
            "license": metadata.get("license", ""),
            "parameters": {"presence_penalty": 1.5, "temperature": 0.65, "top_k": 20, "top_p": 0.95},
            "stream": False})
        response.raise_for_status()
        if response.json().get("status") != "success":
            raise RuntimeError(response.text)
    print("Ready: " + target + " (" + source + " language weights)", flush=True)

if __name__ == "__main__":
    prepare(*(sys.argv[1:3] or [SOURCE, TARGET]))
