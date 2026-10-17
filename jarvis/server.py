from __future__ import annotations
import asyncio
import base64
import contextlib
import json
import secrets
import time
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError
from .config import ROOT, DATA, Settings, offline_environment
from .storage import Store
from .calendar import CalendarEvent, timestamp
from .speech import SpeechEngines
from .session import VoiceSession

offline_environment()
settings = Settings.load()
store = Store(DATA / "jarvis.sqlite3")
engines = SpeechEngines(settings)
VERSION = (ROOT / "VERSION").read_text("utf-8").strip()
TOKEN = secrets.token_urlsafe(32)
ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}
sessions = set()
loading = True
warming = False
warm_task = None

async def load_speech():
    global loading
    await asyncio.to_thread(engines.load)
    loading = False

async def warm_model():
    global warming
    warming = True
    try:
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            for attempt in range(15):
                try:
                    await client.get(settings.ollama_url + "/api/version", timeout=2)
                    break
                except httpx.HTTPError:
                    await asyncio.sleep(1)
            response = await client.post(settings.ollama_url + "/api/chat", json={
                "model": settings.model, "messages": [{"role": "user", "content": "Ready?"}],
                "think": False, "stream": False, "keep_alive": "15m",
                "options": {"num_ctx": settings.context_length, "num_predict": 1}})
            response.raise_for_status()
    except (httpx.HTTPError, ValueError):
        pass  # The status panel reports missing/offline models; a later request can retry.
    finally:
        warming = False

def start_warmup():
    global warm_task
    if warm_task and not warm_task.done():
        warm_task.cancel()
    warm_task = asyncio.create_task(warm_model())
    return warm_task

async def reminder_loop():
    while True:
        await asyncio.sleep(1)
        due = store.reminders() + [
            {"id": e["id"], "text": "Calendar: " + e["title"], "due": time.time(),
             "calendar_event": True} for e in store.due_events(time.time())]
        for reminder in due:
            available = [s for s in sessions if not (s.task and not s.task.done()) and not s.speaking and not s.gate.recording and not s.previewing]
            if reminder["due"] > time.time() or not available:
                continue
            text = "A reminder, sir. " + reminder["text"]
            for session in available:
                try:
                    turn = session.turn_id
                    await session.emit("reminder", reminder)
                    await session.emit("caption", {"text": text})
                    if engines.tts:
                        wav = await asyncio.to_thread(engines.synthesize, text)
                        if turn != session.turn_id or session.gate.recording:
                            continue
                        session.output_texts.append(text)
                        await session.emit("audio", {"wav": base64.b64encode(wav).decode(), "text": text, "final": True})
                    if reminder.get("calendar_event"):
                        store.notify_event(reminder["id"])
                    else:
                        store.finish_reminder(reminder["id"])
                except (RuntimeError, WebSocketDisconnect):
                    pass

@asynccontextmanager
async def lifespan(app):
    tasks = [asyncio.create_task(load_speech()), asyncio.create_task(reminder_loop())]
    start_warmup()
    yield
    if warm_task:
        tasks.append(warm_task)
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

@app.middleware("http")
async def local_access(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in ORIGINS:
        return JSONResponse({"detail": "This is a local application"}, status_code=403)
    if request.url.path.startswith("/api/") and not secrets.compare_digest(
            request.headers.get("x-jarvis-token", ""), TOKEN):
        return JSONResponse({"detail": "Open Jarvis from its local launcher"}, status_code=401)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store" if request.url.path == "/" or request.url.path.startswith("/api/") else "no-cache"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self' ws://127.0.0.1:8765 ws://localhost:8765; media-src 'self' blob: data:; "
        "frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
    return response

@app.get("/")
async def index():
    html = (ROOT / "web" / "index.html").read_text("utf-8").replace("__TOKEN__", TOKEN).replace("__VERSION__", VERSION)
    return HTMLResponse(html)

@app.get("/health")
async def health():
    return {"application": "Personal Jarvis", "version": VERSION, "loading": loading}

async def model_status():
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(settings.ollama_url + "/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
            return {"connected": True, "available": settings.model in models, "models": models}
    except (httpx.HTTPError, ValueError) as exc:
        return {"connected": False, "available": False, "models": [], "error": str(exc)}

@app.get("/api/status")
async def status():
    model = await model_status()
    return {"loading": loading, "warming": warming, "model": model, "settings": settings.model_dump(),
            "speech": {"stt": engines.stt is not None, "tts": engines.tts is not None,
                       "errors": engines.errors},
            "reminders": store.reminders(), "memory_count": len(store.memories()),
            "actions": store.actions()[:8]}

@app.get("/api/memory")
async def memories():
    return store.memories()

@app.post("/api/memory")
async def remember(request: Request):
    payload = await request.json()
    text = payload.get("text", "")
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        raise HTTPException(422, "Enter a preference up to 500 characters")
    return {"id": store.remember(text.strip())}

@app.delete("/api/memory/{item_id}")
async def forget(item_id: int):
    return {"forgotten": store.forget(item_id)}

@app.get("/api/activity")
async def activity():
    return store.actions()

@app.delete("/api/reminders/{item_id}")
async def cancel_reminder(item_id: int):
    return {"cancelled": store.finish_reminder(item_id)}

@app.get("/api/calendar")
async def calendar_list(start: str, end: str):
    try:
        first, last = timestamp(start), timestamp(end)
        if last <= first or last-first > 367*86400:
            raise ValueError("Choose a range of up to one year")
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"events": store.events(first, last),
            "reminders": [r for r in store.reminders() if first <= r["due"] < last]}

@app.post("/api/calendar")
async def calendar_create(event: CalendarEvent):
    return store.save_event(event)

@app.put("/api/calendar/{item_id}")
async def calendar_update(item_id: int, event: CalendarEvent):
    try:
        return store.save_event(event, item_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

@app.delete("/api/calendar/{item_id}")
async def calendar_delete(item_id: int):
    if not store.delete_event(item_id):
        raise HTTPException(404, "Calendar event not found")
    return {"deleted": True}

@app.post("/api/reminders")
async def reminder_create(request: Request):
    payload = await request.json()
    try:
        from .tools import ToolRunner
        return ToolRunner(store, settings).reminders("create", text=payload["text"], due_at=payload["due_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc

@app.put("/api/reminders/{item_id}")
async def reminder_update(item_id: int, request: Request):
    payload = await request.json()
    try:
        from .tools import ToolRunner
        return ToolRunner(store, settings).reminders("update", id=item_id,
            text=payload["text"], due_at=payload["due_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc

@app.put("/api/settings")
async def update_settings(request: Request):
    payload = await request.json()
    allowed = {"model", "owner_name", "temperature", "context_length", "max_reply_tokens",
               "speech_speed", "wake_threshold", "silence_ms", "follow_up_seconds",
               "noise_floor", "barge_in", "confirm_shell", "tts_engine", "kokoro_voice", "audio_output"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise HTTPException(422, "Unsupported settings")
    if any(s.task and not s.task.done() for s in sessions):
        raise HTTPException(409, "Let the current response finish before changing settings")
    try:
        updated = Settings.model_validate({**settings.model_dump(), **payload})
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    if len(updated.owner_name) > 60:
        raise HTTPException(422, "Name is too long")
    if updated.tts_engine == "kokoro" and engines.kokoro is None:
        raise HTTPException(422, "Kokoro is not installed. Run Setup Jarvis.")
    if updated.tts_engine == "piper" and engines.piper is None:
        raise HTTPException(422, "Piper is not installed. Run Setup Jarvis.")
    model_changed = updated.model != settings.model or updated.context_length != settings.context_length
    for key, value in updated.model_dump().items():
        setattr(settings, key, value)
    settings.save()
    if model_changed:
        start_warmup()
    return settings.model_dump()

@app.websocket("/ws")
async def voice(websocket: WebSocket):
    offered = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    if websocket.headers.get("origin") not in ORIGINS | {None} or len(offered) != 2 or not secrets.compare_digest(offered[1], TOKEN):
        await websocket.close(code=4403)
        return
    if sessions:
        await websocket.accept(subprotocol="jarvis")
        await websocket.send_json({"type": "error", "message": "Jarvis is open in another window. Close it before connecting here."})
        await websocket.close(code=4409)
        return
    await websocket.accept(subprotocol="jarvis")
    session = VoiceSession(websocket, settings, store, engines)
    sessions.add(session)
    audio_task = asyncio.create_task(session.audio_loop())
    await session.emit("connected", {"model": settings.model})
    try:
        while True:
            packet = await websocket.receive()
            if packet["type"] == "websocket.disconnect":
                break
            if packet.get("bytes") is not None:
                data = packet["bytes"]
                if len(data) > 32000 or len(data) % 2:
                    continue
                if session.audio_queue.full():
                    session.audio_queue.get_nowait()
                await session.audio_queue.put(data)
            elif packet.get("text"):
                if len(packet["text"]) > 16000:
                    continue
                try:
                    data = json.loads(packet["text"])
                    if isinstance(data, dict):
                        await session.handle(data)
                except (ValueError, TypeError):
                    await session.emit("error", {"message": "Invalid command"})
    except WebSocketDisconnect:
        pass
    finally:
        sessions.discard(session)
        if session.task:
            session.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.task
        audio_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await audio_task
        await session.cancel_probe()

app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
