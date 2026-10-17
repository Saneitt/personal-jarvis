import io
import json
import sys
import time
import wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from jarvis.config import Settings,offline_environment
offline_environment()
from jarvis.speech import SpeechEngines,WakeDetector
import numpy as np
from scipy.signal import resample_poly

engines=SpeechEngines(Settings.load())
engines.load()
if engines.errors:raise RuntimeError(engines.errors)
with wave.open("data/silence.wav","wb") as silent:
    silent.setnchannels(1);silent.setsampwidth(2);silent.setframerate(16000);silent.writeframes(bytes(64000))
results=[]
for text in ["How much memory is available on my computer?", "Remind me to stretch in twenty minutes."]:
    t=time.perf_counter()
    wav=engines.synthesize(text)
    tts_seconds=time.perf_counter()-t
    with wave.open(io.BytesIO(wav)) as f:
        sample_rate=f.getframerate()
        audio=np.frombuffer(f.readframes(f.getnframes()),dtype="<i2")
    from math import gcd
    divisor=gcd(sample_rate,16000)
    pcm=resample_poly(audio.astype(np.float32),16000//divisor,sample_rate//divisor).astype("<i2").tobytes()
    t=time.perf_counter()
    transcription=engines.transcribe(pcm)
    result={"input":text,"heard":transcription,"tts_seconds":round(tts_seconds,2),"stt_seconds":round(time.perf_counter()-t,2)}
    print(json.dumps(result),flush=True);results.append(result)
wake=WakeDetector()
assert wake.score(bytes(2560))<0.5
Path("data/speech-verification.json").write_text(json.dumps(results,indent=2))
