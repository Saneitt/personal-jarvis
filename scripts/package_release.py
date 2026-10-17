"""Build a clean Windows download without personal data or model weights."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent.parent
DIRECTORIES=("jarvis","web","scripts","desktop","config","docs","tests",".github")
FILES=("README.md","LICENSE","VERSION","requirements.txt","requirements.lock.txt",
       "Setup Jarvis.cmd","Launch Jarvis.cmd","Stop Jarvis.cmd",".gitignore")
def package(destination=None,desktop=False):
    version=(ROOT/"VERSION").read_text("utf-8").strip()
    destination=Path(destination) if destination else ROOT/"dist"/f"PersonalJarvis-{version}-Windows.zip"
    destination.parent.mkdir(exist_ok=True,parents=True)
    selected=[ROOT/name for name in FILES]
    for folder in DIRECTORIES:
        selected += [p for p in (ROOT/folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix not in {".pyc",".log"}]
    if desktop:
        selected += [ROOT/".runtime"/"desktop"/name for name in
                     ("Jarvis.exe","Microsoft.Web.WebView2.Core.dll",
                      "Microsoft.Web.WebView2.WinForms.dll","WebView2Loader.dll",
                      "WebView2-LICENSE.txt","WebView2-NOTICE.txt")]
    hashes={}
    with zipfile.ZipFile(destination,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(set(selected)):
            name=path.relative_to(ROOT).as_posix()
            if not path.exists():raise FileNotFoundError(path)
            data=path.read_bytes();hashes[name]=hashlib.sha256(data).hexdigest()
            archive.writestr("PersonalJarvis/"+name,data)
        archive.writestr("PersonalJarvis/PACKAGE.json",json.dumps({
            "version":version,"platform":"Windows x64","files":hashes,
            "models_included":False,"personal_data_included":False},indent=2))
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(digest+"  "+destination.name+"\n",encoding="utf-8")
    print(json.dumps({"package":str(destination),"files":len(hashes),"bytes":destination.stat().st_size,"sha256":digest}))
    return destination
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output");parser.add_argument("--with-desktop",action="store_true")
    args=parser.parse_args();package(args.output,args.with_desktop)
