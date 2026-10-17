import asyncio, io, json, re, sys, time, wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import httpx
from websockets.asyncio.client import connect
from jarvis.config import Settings,offline_environment
offline_environment()
from jarvis.speech import SpeechEngines
import numpy as np
from scipy.signal import resample_poly
from math import gcd

async def main():
    async with httpx.AsyncClient(trust_env=False) as client:
        html=(await client.get("http://127.0.0.1:8765/")).text
        token=re.search(r'name="jarvis-token" content="([^"]+)"',html).group(1)
    records=[]
    async with connect("ws://127.0.0.1:8765/ws",subprotocols=["jarvis",token],
                       origin="http://127.0.0.1:8765",max_size=4_000_000) as ws:
        print(await ws.recv(),flush=True)
        async def collect():
            packets=[]
            while True:
                event=json.loads(await asyncio.wait_for(ws.recv(),120))
                packets.append(event)
                if event["type"] in {"heard","error","metrics","approval","action","done"}:
                    print(json.dumps({k:v for k,v in event.items() if k!="wav"}),flush=True)
                if event["type"]=="done":
                    return packets
        for request in ["What time is it and how much free memory do I have? Reply briefly.",
                        "Use the files tool to create C:\\PersonalJarvis\\data\\smoke-note.txt containing the exact text [Jarvis is online] without brackets or punctuation."]:
            await ws.send(json.dumps({"type":"text","text":request}))
            events=await collect()
            if any(e["type"]=="approval" for e in events):
                # Only approve the explicitly requested test-file overwrite.
                pending=next(e for e in events if e["type"]=="approval")
                assert "smoke-note.txt" in pending["detail"]
                await ws.send(json.dumps({"type":"approval","id":pending["id"],"approved":True}))
                events+=await collect()
            assert not any(e["type"]=="error" for e in events),events
            assert any(e["type"]=="audio" for e in events)
            records.append({"request":request,"events":[e for e in events if e["type"] in {"action","metrics","done"}]})
        assert Path("data/smoke-note.txt").read_text().strip()=="Jarvis is online"
        speech=SpeechEngines(Settings.load());await asyncio.to_thread(speech.load)
        wav=await asyncio.to_thread(speech.synthesize,"How much free memory do I have?")
        with wave.open(io.BytesIO(wav)) as f:
            rate=f.getframerate();samples=np.frombuffer(f.readframes(f.getnframes()),dtype="<i2")
        divisor=gcd(rate,16000)
        pcm=resample_poly(samples.astype(np.float32),16000//divisor,rate//divisor).astype("<i2").tobytes()+bytes(32000)
        await ws.send(json.dumps({"type":"arm"}))
        while True:
            event=json.loads(await ws.recv())
            if event.get("phase")=="standby":break
        # Exercise the actual wake detector before the microphone request.
        wake_wav=await asyncio.to_thread(speech.synthesize,"Hey Jarvis.")
        with wave.open(io.BytesIO(wake_wav)) as f:
            wake_rate=f.getframerate()
            wake_samples=np.frombuffer(f.readframes(f.getnframes()),dtype="<i2")
        divisor=gcd(wake_rate,16000)
        wake_pcm=bytes(16000)+resample_poly(wake_samples.astype(np.float32),16000//divisor,wake_rate//divisor).astype("<i2").tobytes()+bytes(32000)
        for i in range(0,len(wake_pcm),2560):
            await ws.send(wake_pcm[i:i+2560]);await asyncio.sleep(.08)
        while True:
            event=json.loads(await asyncio.wait_for(ws.recv(),15))
            if event["type"]=="wake":
                print("Wake word detected from synthetic microphone audio",flush=True)
                break
        collector=asyncio.create_task(collect())
        for i in range(0,len(pcm),2560):
            await ws.send(pcm[i:i+2560]);await asyncio.sleep(.08)
        events=await collector
        assert any(e["type"]=="heard" and "memory" in e["text"].lower() for e in events)
        assert any(e["type"]=="audio" for e in events)
        records.append({"request":"Synthetic microphone audio through VAD -> STT -> model -> tools -> TTS",
                        "events":[e for e in events if e["type"] in {"heard","transcription_metrics","action","metrics","done"}]})
        await ws.send(json.dumps({"type":"text","text":"Remind me to take a short break in five seconds."}))
        events=await collect()
        assert any(e["type"]=="action" and e["name"]=="reminders" and "created" in e["result"] for e in events)
        while True:
            event=json.loads(await asyncio.wait_for(ws.recv(),30))
            if event["type"]=="reminder":
                records.append({"request":"Create and deliver a local reminder","reminder":event})
                break
        # Consume its speech before starting the cancellation check.
        while True:
            event=json.loads(await asyncio.wait_for(ws.recv(),30))
            if event["type"]=="audio":break
        await ws.send(json.dumps({"type":"text","text":"Explain the history of computing in detail."}))
        while True:
            event=json.loads(await asyncio.wait_for(ws.recv(),10))
            if event.get("phase")=="thinking":
                active_turn=event["turn"]
                break
        await asyncio.sleep(.4)
        started=time.perf_counter()
        await ws.send(json.dumps({"type":"interrupt"}))
        while True:
            event=json.loads(await asyncio.wait_for(ws.recv(),10))
            if event["type"]=="interrupted" and event["turn"]>active_turn:
                records.append({"request":"Interrupt an active response","ack_seconds":round(time.perf_counter()-started,3)})
                break
        await ws.send(json.dumps({"type":"disarm"}))
    Path("data/e2e-verification.json").write_text(json.dumps(records,indent=2),encoding="utf-8")
    print("End-to-end checks passed",flush=True)
asyncio.run(main())
