"""Publish the tested download from GitHub Actions using its scoped token."""
import os
from pathlib import Path
import subprocess

def publish():
    root=Path(__file__).resolve().parent.parent
    version=(root/"VERSION").read_text("utf-8").strip()
    tag="v"+version
    target=os.environ.get("GITHUB_SHA")
    if not target:
        raise RuntimeError("Run this publisher in GitHub Actions; use package_release.py for local ZIPs.")
    check=subprocess.run(["gh","release","view",tag],capture_output=True,text=True,encoding="utf-8")
    if check.returncode:
        if "release not found" not in check.stderr.lower():
            raise RuntimeError(check.stderr.strip())
        subprocess.run(["gh","release","create",tag,"--target",target,"--title","Personal Jarvis "+version,
            "--notes","Local Windows voice assistant. Extract the Windows ZIP and run Setup Jarvis.cmd to choose and download a local model. Model weights and personal data are not included."],check=True)
    files=sorted((root/"dist").glob("*.zip"))+sorted((root/"dist").glob("*.sha256"))
    if len(files)<2:
        raise RuntimeError("The Windows package and checksum were not built.")
    subprocess.run(["gh","release","upload",tag,*map(str,files),"--clobber"],check=True)

if __name__=="__main__":
    publish()
