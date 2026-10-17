"""Generate microphone-free comparison clips and measure their speech content."""
import io
import json
import sys
import time
import wave
from math import gcd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from scipy.signal import resample_poly
from jarvis.config import Settings, offline_environment
from jarvis.speech import SpeechEngines
offline_environment()
engines = SpeechEngines(Settings.load())
engines.load()
if engines.errors:
    raise RuntimeError(engines.errors)
folder = Path("data/voice-comparison")
folder.mkdir(exist_ok=True)
phrases = [
    "Certainly, Captain.",
    "Your computer is running smoothly, and everything is ready.",
    "I can open your files, check the system, or help you get something done."
]
text = " ".join(phrases)
reports = []
for name, voice, split, trim in [
    ("george-sentence-clips", "bm_george", True, True),
    ("george-connected", "bm_george", False, True),
    ("george-untrimmed", "bm_george", False, False),
    ("fable-connected", "bm_fable", False, False),
    ("alan-piper", None, False, False),
]:
    started = time.perf_counter()
    if voice:
        parts = [engines.kokoro.create(part, voice=voice, speed=engines.settings.speech_speed,
                                      lang="en-gb", trim=trim)[0]
                 for part in (phrases if split else [text])]
        samples = np.concatenate(parts)
        rate = 24000
    else:
        engines.settings.tts_engine = "piper"
        with wave.open(io.BytesIO(engines.synthesize(text))) as f:
            rate = f.getframerate()
            samples = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(np.float32)/32768
    seconds = time.perf_counter() - started
    path = folder / (name + ".wav")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes((np.clip(samples,-1,1)*32767).astype("<i2").tobytes())
    divisor = gcd(rate,16000)
    pcm = resample_poly(samples,16000//divisor,rate//divisor)
    heard = engines.transcribe((np.clip(pcm,-1,1)*32767).astype("<i2").tobytes())
    report = dict(name=name, generation_seconds=round(seconds,3),
                  audio_seconds=round(len(samples)/rate,3), heard=heard,
                  peak=round(float(np.max(np.abs(samples))),4),
                  clipped_samples=int(np.count_nonzero(np.abs(samples)>=1)),
                  start_peak=round(float(np.max(np.abs(samples[:240]))),6),
                  end_peak=round(float(np.max(np.abs(samples[-240:]))),6))
    reports.append(report)
    print(json.dumps(report), flush=True)
(folder / "results.json").write_text(json.dumps(dict(input=text,clips=reports), indent=2),encoding="utf-8")
