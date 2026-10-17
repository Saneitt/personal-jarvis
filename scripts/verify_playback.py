"""Real local TTS -> microphone feedback regression, without controlling the desktop."""
import asyncio, io, json, time, wave, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from scipy.signal import resample_poly
from math import gcd
from jarvis.config import Settings, DATA, offline_environment
from jarvis.speech import SpeechEngines, UtteranceGate
from jarvis.session import VoiceSession
from jarvis.storage import Store
offline_environment()

def pcm16(wav, gain=1):
    with wave.open(io.BytesIO(wav)) as file:
        rate=file.getframerate()
        samples=np.frombuffer(file.readframes(file.getnframes()),dtype="<i2").astype(np.float32)
    factor=gcd(rate,16000)
    return np.clip(resample_poly(samples,16000//factor,rate//factor)*gain,-32768,32767).astype("<i2").tobytes()

async def main():
    settings=Settings.load()
    settings.audio_output="speakers"
    engines=SpeechEngines(settings)
    await asyncio.to_thread(engines.load)
    assert not engines.errors,engines.errors
    reply="Your computer is running smoothly, Captain. You have plenty of memory available."
    wav=await asyncio.to_thread(engines.synthesize,reply)
    (DATA/"playback-regression.wav").write_bytes(wav)
    echo=pcm16(wav,.6)+bytes(32000)
    baseline=UtteranceGate(settings)
    baseline_events=[]
    for i in range(0,len(echo),2560): baseline_events += baseline.feed(echo[i:i+2560],speaking=True)
    assert any(e[0]=="start" for e in baseline_events), "Fixture must trigger the old VAD-only cutoff"
    events=[]
    class Socket:
        async def send_json(self, event): events.append(event)
    session=VoiceSession(Socket(),settings,Store(DATA/"voice-regression.sqlite3"),engines)
    session.armed=True
    session.awake_until=time.monotonic()+120
    session.output_texts.append(reply)
    await session.handle({"type":"playback","playing":True,"turn":0})
    async def feed(pcm):
        for i in range(0,len(pcm),2560):
            await session.process_audio(pcm[i:i+2560])
            await asyncio.sleep(.08)
    await feed(echo)
    if session.barge_probe: await session.barge_probe
    assert not any(e["type"]=="interrupted" for e in events),events
    print("Speaker feedback rejected without cutting playback",flush=True)
    requests=[]
    async def begin(text=None,pcm=None,**kwargs):
        requests.append(text or await asyncio.to_thread(engines.transcribe,pcm))
    session.begin=begin
    user="Actually tell me a short joke instead."
    user_wav=await asyncio.to_thread(engines.synthesize,user)
    await feed(pcm16(user_wav)+bytes(32000))
    if session.barge_probe: await session.barge_probe
    assert any(e["type"]=="interrupted" and e.get("reason")=="confirmed_speech" for e in events),events
    assert requests and "joke" in requests[-1].lower(),requests
    assert requests[-1].lower().startswith("actually"),requests
    result={"baseline_vad_would_interrupt":True,"echo_did_not_interrupt":True,
            "natural_interruption_without_wake_word":True,"heard":requests[-1]}
    (DATA/"voice-regression.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    await session.cancel_probe()
    print(json.dumps(result),flush=True)
asyncio.run(main())
