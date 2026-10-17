import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jarvis.brain import OllamaBrain, PERSONALITY
from jarvis.config import Settings

async def main():
    model = sys.argv[1] if len(sys.argv) > 1 else Settings.load().model
    brain = OllamaBrain(Settings(model=model))
    records = []
    for question in ["Introduce yourself in one short sentence.", "How much free RAM does my computer have?"]:
        tokens=[]
        async def token(t): tokens.append(t)
        messages=[{"role":"system","content":PERSONALITY.format(owner="Captain",time="2026-10-17",home=Path.home(),memories="[]")},
                  {"role":"user","content":question}]
        message, stats=await brain.stream(messages,token)
        records.append({"question":question,"message":message,"stats":stats})
        print(json.dumps(records[-1],ensure_ascii=False),flush=True)
    Path("data/benchmark-"+model.replace(":","-")+".json").write_text(json.dumps(records,indent=2),encoding="utf-8")
asyncio.run(main())
