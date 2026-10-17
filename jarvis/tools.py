from __future__ import annotations
import asyncio
import base64
import ctypes
import fnmatch
import os
import platform
import shutil
import subprocess
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
import psutil
from send2trash import send2trash
from .config import DATA
from .calendar import CalendarEvent, timestamp

def spec(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(required),
                           "additionalProperties": False}}}

S = {"type": "string"}
I = {"type": "integer"}
SCHEMAS = [
    spec("computer", "Read live PC information, launch an app or open a file/folder/website, control volume/media, or read clipboard. Launch common apps by name; use full paths for other apps.",
         {"action": {"type": "string", "enum": ["status", "open", "volume_up", "volume_down", "mute", "play_pause", "next_track", "previous_track", "clipboard_read"]},
          "target": S}, ["action"]),
    spec("files", "Access local files on any drive. List directory, search filenames recursively, read text, write text, mkdir, move, or recycle. Search before opening uncertain paths. Overwrites, moves and deletes need confirmation.",
         {"action": {"type": "string", "enum": ["list", "search", "read", "write", "mkdir", "move", "recycle"]},
          "path": S, "pattern": S, "text": S, "destination": S}, ["action", "path"]),
    spec("powershell", "Run a Windows PowerShell script for operations not covered by other tools. User confirmation precedes execution. Runs under the current account with a 30 second limit.",
         {"script": S, "reason": S}, ["script", "reason"]),
    spec("memory", "Save a preference only when asked to remember it. List or forget saved preferences.",
         {"action": {"type": "string", "enum": ["list", "remember", "forget"]}, "text": S, "id": I}, ["action"]),
    spec("reminders", "Create, list, update or cancel local reminders. Read existing IDs before updates. Use seconds for timers, or ISO 8601 due_at with timezone for scheduled reminders. Fires while Jarvis runs; overdue reminders fire on restart.",
         {"action": {"type": "string", "enum": ["list", "create", "update", "cancel"]},
          "text": S, "seconds": I, "due_at": S, "id": I}, ["action"]),
    spec("calendar", "Manage the local calendar. List or show dates, create, update or delete events. Use ISO 8601 dates WITH timezone. Read existing events before updating or deleting; never guess IDs. For a day use its midnight to next midnight. Event reminders sound while Jarvis is open.",
         {"action": {"type": "string", "enum": ["list", "show", "create", "update", "delete"]},
          "id": I, "title": S, "start_at": S, "end_at": S, "notes": S,
          "all_day": {"type": "boolean"}, "remind_minutes": {"type": "integer", "minimum": -1, "maximum": 10080,
          "description": "Minutes before the event for an alert. -1 means NO ALERT (default); 0 means at start. Set a nonnegative value only when the user wants an alert."}}, ["action"]),
]
SCHEMA_MAP = {s["function"]["name"]: s["function"]["parameters"] for s in SCHEMAS}
APPS = {"notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe",
        "explorer": "explorer.exe", "file explorer": "explorer.exe",
        "task manager": "taskmgr.exe", "paint": "mspaint.exe",
        "settings": "ms-settings:", "browser": "https://www.google.com",
        "edge": "microsoft-edge:", "terminal": "wt.exe"}

def validate_call(name, args):
    if name not in SCHEMA_MAP or not isinstance(args, dict):
        raise ValueError("Unknown tool or malformed arguments")
    schema = SCHEMA_MAP[name]
    if set(args) - set(schema["properties"]):
        raise ValueError("Unexpected tool arguments")
    if not set(schema["required"]).issubset(args):
        raise ValueError("Missing required tool arguments")
    action_required = {
        ("files", "write"): ["text"], ("files", "move"): ["destination"],
        ("computer", "open"): ["target"], ("memory", "remember"): ["text"],
        ("memory", "forget"): ["id"], ("reminders", "cancel"): ["id"],
        ("calendar", "create"): ["title", "start_at", "end_at"],
        ("reminders", "update"): ["id"], ("calendar", "update"): ["id"], ("calendar", "delete"): ["id"]}
    for key in action_required.get((name, args.get("action")), []):
        if key not in args:
            raise ValueError(f"Missing {key} for this action")
    for key, value in args.items():
        rule = schema["properties"][key]
        if rule["type"] == "string" and not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        if rule["type"] == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"{key} must be an integer")
        if rule["type"] == "boolean" and not isinstance(value, bool):
            raise ValueError(f"{key} must be true or false")
        if isinstance(value, str) and (len(value) > 24000 or "\0" in value):
            raise ValueError("Tool input is too long or contains a null character")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"Invalid {key}")

def known_folder(name):
    fallback = Path.home() / {"desktop": "Desktop", "downloads": "Downloads", "documents": "Documents"}[name]
    if os.name == "nt":
        try:
            import winreg
            keyname = {"desktop": "Desktop", "documents": "Personal",
                       "downloads": "{374DE290-123F-4565-9164-39C4925E467B}"}[name]
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                value, _ = winreg.QueryValueEx(key, keyname)
                return Path(os.path.expandvars(value))
        except OSError:
            pass
    return fallback

def local_path(raw):
    if not raw.strip() or raw.startswith(("\\\\", "//")):
        raise ValueError("Use a local path, not an empty or network path")
    aliases = {"home": Path.home(), **{name: known_folder(name) for name in ("desktop", "downloads", "documents")}}
    path = aliases.get(raw.lower())
    if path is None:
        path = Path(os.path.expandvars(raw)).expanduser()
    if not path.is_absolute():
        path = Path.home() / path
    path = path.resolve()
    if os.name == "nt" and (str(path).startswith("\\\\") or ":" in str(path)[2:]):
        raise ValueError("Network paths and alternate streams are not supported")
    return path

class ToolRunner:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def confirmation(self, name, args):
        validate_call(name, args)
        if name == "powershell" and self.settings.confirm_shell:
            return {"title": args["reason"], "detail": args["script"], "kind": "PowerShell command"}
        if name == "files":
            path = local_path(args["path"])
            if args["action"] in {"move", "recycle"} or (args["action"] == "write" and path.exists()):
                return {"title": f'{args["action"].capitalize()} {path.name}',
                        "detail": str(path) + (" → " + args.get("destination", "") if args["action"] == "move" else ""),
                        "kind": "File change"}
        if name == "computer" and args["action"] == "open":
            target = args.get("target", "")
            if target.lower() not in APPS and Path(target).suffix.lower() in {".exe", ".ps1", ".bat", ".cmd", ".vbs", ".msi", ".lnk", ".url", ".hta"}:
                return {"title": "Launch this program", "detail": target, "kind": "Program"}
        return None

    async def execute(self, name, args):
        validate_call(name, args)
        try:
            if name == "powershell":
                result = await self.run_powershell(args["script"])
            else:
                result = await asyncio.to_thread(getattr(self, name), **args)
        except asyncio.CancelledError:
            self.store.log(name, args, {"interrupted": True, "note": "Completed changes are not reversed."})
            raise
        except Exception as exc:
            result = {"error": str(exc)}
        self.store.log(name, args, result)
        return result

    def computer(self, action, target=""):
        if action == "status":
            mem = psutil.virtual_memory()
            disk = shutil.disk_usage(Path.home().anchor)
            battery = psutil.sensors_battery()
            gpu = None
            try:
                gpu = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader"],
                    timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).decode().strip()
            except (OSError, subprocess.SubprocessError):
                pass
            return {"time": datetime.now().astimezone().isoformat(), "os": platform.platform(),
                    "cpu_percent": psutil.cpu_percent(interval=0.15),
                    "ram_total_gb": round(mem.total / 2**30, 1),
                    "ram_available_gb": round(mem.available / 2**30, 1),
                    "disk_free_gb": round(disk.free / 2**30, 1), "gpu": gpu,
                    "battery_percent": battery.percent if battery else None,
                    "plugged_in": battery.power_plugged if battery else None,
                    "home": str(Path.home())}
        if action == "open":
            if not target.strip():
                raise ValueError("Specify an app, URL or existing path")
            mapped = APPS.get(target.lower(), target)
            parsed = urlparse(mapped)
            if parsed.scheme in {"http", "https"}:
                webbrowser.open(mapped)
            elif target.lower() in APPS:
                if mapped.endswith(":"):
                    os.startfile(mapped)
                else:
                    subprocess.Popen([mapped], creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                        | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)))
            else:
                path = local_path(mapped)
                if not path.exists():
                    raise FileNotFoundError("Path not found. Search first or use the full app path.")
                os.startfile(str(path))
            return {"opened": target}
        keys = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD, "play_pause": 0xB3,
                "next_track": 0xB0, "previous_track": 0xB1}
        if action in keys:
            ctypes.windll.user32.keybd_event(keys[action], 0, 0, 0)
            ctypes.windll.user32.keybd_event(keys[action], 0, 2, 0)
            return {"performed": action}
        if action == "clipboard_read":
            encoded = base64.b64encode("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); Get-Clipboard -Raw".encode("utf-16-le")).decode()
            value = subprocess.check_output(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                            timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"clipboard": value.decode("utf-8", errors="replace")[:8000]}
        raise ValueError("Unsupported computer action")

    def files(self, action, path, pattern="*", text="", destination=""):
        p = local_path(path)
        if action == "list":
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            return {"path": str(p), "entries": [{"name": x.name, "directory": x.is_dir()} for x in entries[:80]],
                    "truncated": len(entries) > 80}
        if action == "search":
            if not p.is_dir():
                raise ValueError("Search path must be an existing directory")
            found, visited, partial = [], 0, False
            start = time.monotonic()
            needle = pattern if any(c in pattern for c in "*?[") else f"*{pattern}*"
            for folder, dirs, filenames in os.walk(p, followlinks=False):
                dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", ".venv", "AppData", "$RECYCLE.BIN"}
                           and not Path(folder, d).is_symlink() and not Path(folder, d).is_junction()]
                for filename in dirs + filenames:
                    visited += 1
                    if fnmatch.fnmatch(filename.lower(), needle.lower()):
                        found.append(str(Path(folder, filename)))
                        if len(found) >= 40:
                            break
                if len(found) >= 40 or time.monotonic() - start > 8 or visited > 80000:
                    partial = True
                    break
            return {"matches": found, "partial": partial}
        if action == "read":
            with p.open("rb") as f:
                content = f.read(16001)
            if b"\0" in content:
                raise ValueError("Binary file. Use an appropriate application or PowerShell to inspect it.")
            return {"path": str(p), "text": content[:16000].decode("utf-8-sig", errors="replace"),
                    "truncated": len(content) > 16000}
        if action == "mkdir":
            p.mkdir(parents=True, exist_ok=True)
            return {"created": str(p)}
        if action == "write":
            backup = None
            if p.exists():
                backup_dir = DATA / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup = backup_dir / f"{time.time_ns()}-{p.name}"
                shutil.copy2(p, backup)
            p.write_text(text, encoding="utf-8")
            return {"written": str(p), "backup": str(backup) if backup else None}
        if action == "move":
            dest = local_path(destination)
            if dest.exists():
                raise ValueError("Destination already exists; choose a new name")
            if p == Path(p.anchor) or p == Path.home() or p in dest.parents:
                raise ValueError("Cannot move a drive, home directory, or directory into itself")
            shutil.move(str(p), str(dest))
            return {"moved": str(p), "to": str(dest)}
        if action == "recycle":
            if p == Path(p.anchor) or p == Path.home() or p in Path.home().parents:
                raise ValueError("Cannot recycle a drive or home directory")
            send2trash(str(p))
            return {"recycled": str(p), "restore": "Windows Recycle Bin"}
        raise ValueError("Unsupported file action")

    def memory(self, action, text="", id=0):
        if action == "list":
            return {"preferences": self.store.memories()}
        if action == "remember":
            if not text.strip():
                raise ValueError("Specify the preference to remember")
            return {"saved": self.store.remember(text)}
        return {"forgotten": self.store.forget(id)}

    def reminders(self, action, text="", seconds=0, due_at="", id=0):
        if action == "list":
            return {"reminders": self.store.reminders()}
        if action == "cancel":
            return {"cancelled": self.store.finish_reminder(id)}
        existing=self.store.reminder(id) if action=="update" else None
        if action=="update" and not existing:
            raise ValueError("Reminder not found")
        if existing and not text:
            text=existing["text"]
        if not text.strip():
            raise ValueError("Specify what to remind you about")
        if seconds > 0:
            due = time.time() + seconds
        elif due_at:
            parsed = datetime.fromisoformat(due_at)
            if parsed.tzinfo is None:
                raise ValueError("Include the timezone in due_at")
            due = parsed.timestamp()
        elif existing:
            due=existing["due"]
        else:
            raise ValueError("Specify positive seconds or ISO due_at")
        if due <= time.time():
            raise ValueError("The reminder time must be in the future")
        if existing:
            self.store.update_reminder(id,text,due)
            return {"updated": id, "text": text, "due_at": datetime.fromtimestamp(due).astimezone().isoformat()}
        return {"created": self.store.add_reminder(text, due),
                "due_at": datetime.fromtimestamp(due).astimezone().isoformat(), "text": text}

    async def run_powershell(self, script):
        prelude = "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); $ErrorActionPreference='Stop'; "
        encoded = base64.b64encode((prelude + script).encode("utf-16-le")).decode()
        process = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(Path.home()), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
            return {"exit_code": process.returncode, "stdout": stdout.decode("utf-8", errors="replace")[:12000],
                    "stderr": stderr.decode("utf-8", errors="replace")[:4000]}
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill", "/PID", str(process.pid), "/T", "/F",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                await killer.wait()
                await process.wait()
            raise


    def calendar(self, action, id=None, title=None, start_at=None, end_at=None,
                 notes=None, all_day=None, remind_minutes=None):
        now = datetime.now().astimezone()
        if action in {"show", "list"}:
            start = timestamp(start_at) if start_at else now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            end = timestamp(end_at) if end_at else start + 7*86400
            if end <= start or end - start > 366*86400:
                raise ValueError("Choose a calendar range of up to one year")
            return {"events": self.store.events(start, end),
                    "focus_date": datetime.fromtimestamp(start).date().isoformat()}
        if action == "delete":
            return {"deleted": self.store.delete_event(id)}
        base = {}
        if action == "update":
            existing = self.store.event(id)
            if not existing:
                raise ValueError("Calendar event not found; list events first")
            base = {key: existing[key] for key in CalendarEvent.model_fields}
        changes = dict(title=title, start_at=start_at, end_at=end_at, notes=notes,
                       all_day=all_day, remind_minutes=remind_minutes)
        event = CalendarEvent.model_validate({**base, **{k:v for k,v in changes.items() if v is not None}})
        saved = self.store.save_event(event, id if action == "update" else None)
        return {"event": saved, "focus_date": datetime.fromtimestamp(saved["starts_at"]).date().isoformat()}
