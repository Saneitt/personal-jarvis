"""Download an Ollama model with readable progress; safe to re-run to resume."""
import json,sys,time
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from jarvis.config import Settings
model=sys.argv[1] if len(sys.argv)>1 else "qwen3.5:4b"
settings=Settings(model=model)
last={}
with httpx.Client(timeout=httpx.Timeout(600,connect=10),trust_env=False) as client:
    with client.stream("POST",settings.ollama_url+"/api/pull",json={"model":model,"stream":True}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:continue
            packet=json.loads(line)
            if packet.get("error"):raise RuntimeError(packet["error"])
            digest=packet.get("digest","")
            progress=int(packet.get("completed",0)/max(packet.get("total",1),1)*100)//10*10
            status=packet.get("status","")
            if last.get(digest)!=(status,progress):
                print(status+(f" {progress}%" if packet.get("total") else ""),flush=True)
                last[digest]=(status,progress)
print("Ready: "+model)
