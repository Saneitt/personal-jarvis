"""Download the pinned CPU voice model, with resume and hash verification."""
import hashlib
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
ASSETS = {
    "kokoro-v1.0.onnx": "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}
for name, expected in ASSETS.items():
    target = ROOT / "models" / "kokoro" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and hashlib.file_digest(target.open("rb"), "sha256").hexdigest() == expected:
        continue
    temp = target.with_suffix(target.suffix + ".part")
    print("Downloading " + name, flush=True)
    subprocess.run(["curl.exe", "-fL", "--connect-timeout", "30", "--speed-time", "30",
                    "--speed-limit", "1024", "--retry", "4", "--retry-all-errors",
                    "-C", "-", "--output", str(temp), BASE + name], check=True)
    with temp.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError(f"Checksum mismatch: {temp}. Remove this partial download and rerun setup.")
    temp.replace(target)
print("Kokoro voice ready", flush=True)
