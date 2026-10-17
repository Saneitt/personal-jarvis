from __future__ import annotations
import asyncio
import base64
import contextlib
import logging
import io
import wave
from collections import deque
import re
import time
from .config import Settings
from .brain import Conversation
from .speech import UtteranceGate, WakeDetector, echo_similarity

log = logging.getLogger("jarvis")

class VoiceSession:
    def __init__(self, websocket, settings, store, engines):
        self.ws, self.settings, self.store, self.engines = websocket, settings, store, engines
        self.gate = UtteranceGate(settings)
        self.wake = None
        self.armed = self.speaking = False
        self.previewing = False
        self.playback_guard_until = 0
        self.output_texts = deque(maxlen=12)
        self.echo_candidate = False
        self.barge_probe = None
        self.last_probe_frames = 0
        self.awake_until = 0
        self.turn_id = 0
        self.task = None
        self.audio_queue = asyncio.Queue(maxsize=40)
        self.speech_queue = None
        self.send_lock = asyncio.Lock()
        self.conversation = Conversation(settings, store, self.emit, self.say)
        self.wake_buffer = bytearray()
        self.idle_notified = False

    async def emit(self, kind, payload=None):
        async with self.send_lock:
            await self.ws.send_json({"type": kind, "turn": self.turn_id, **(payload or {})})

    async def phase(self, phase, label):
        await self.emit("phase", {"phase": phase, "label": label})

    async def say(self, text, caption=True):
        if caption:
            await self.emit("caption", {"text": text})
        if self.speech_queue:
            await self.speech_queue.put(text)

    async def speaker(self, queue, turn):
        while True:
            text = await queue.get()
            if text is None:
                return
            try:
                started = time.perf_counter()
                wav = await asyncio.to_thread(self.engines.synthesize, text)
                if turn == self.turn_id:
                    with wave.open(io.BytesIO(wav)) as audio:
                        duration = audio.getnframes() / audio.getframerate()
                    await self.emit("speech_metrics", {"generation_seconds": round(time.perf_counter() - started, 3),
                                                      "audio_seconds": round(duration, 3)})
                    self.output_texts.append(text)
                    await self.emit("audio", {"wav": base64.b64encode(wav).decode(), "text": text})
            except Exception as exc:
                await self.emit("error", {"message": f"Voice output: {exc}"})

    async def cancel_probe(self):
        probe = self.barge_probe
        if probe and probe is not asyncio.current_task() and not probe.done():
            probe.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await probe
        if probe is not asyncio.current_task():
            self.barge_probe = None

    async def interrupt(self, reason="manual"):
        await self.cancel_probe()
        if reason not in {"confirmed_speech", "microphone_speech"}:
            self.gate.reset()
        self.echo_candidate = False
        self.previewing = False
        self.turn_id += 1
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        self.task = None
        self.speaking = False
        self.playback_guard_until = 0
        await self.emit("interrupted", {"reason": reason})

    async def begin(self, text=None, pcm=None, approval=None):
        await self.interrupt(reason="new_turn")
        self.awake_until = time.monotonic() + self.settings.follow_up_seconds
        self.idle_notified = False
        self.task = asyncio.create_task(self.run_turn(text, pcm, approval))

    async def run_turn(self, text, pcm, approval):
        queue = asyncio.Queue()
        self.speech_queue = queue
        speaker = asyncio.create_task(self.speaker(queue, self.turn_id))
        start = time.perf_counter()
        try:
            if pcm:
                await self.phase("transcribing", "Listening to what you said")
                text = await asyncio.to_thread(self.engines.transcribe, pcm)
                await self.emit("transcription_metrics", {"seconds": round(time.perf_counter() - start, 2)})
            if approval is not None:
                await self.conversation.approval(approval["approved"], approval.get("id"))
            elif text and text.strip():
                await self.emit("heard", {"text": text})
                normal = re.sub(r"[^\w\s]", "", text.lower()).strip()
                if normal in {"stop", "stop talking", "quiet", "be quiet"}:
                    pass
                elif normal in {"go to sleep", "stand by", "standby", "thats all", "sleep"}:
                    self.awake_until = 0
                    self.conversation.pending = None
                    await self.emit("approval_cleared", {})
                    await self.say("Standing by, sir.")
                else:
                    await self.conversation.respond(text.strip())
            else:
                await self.phase("listening", "I didn't catch that, sir")
            await queue.put(None)
            await speaker
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Conversation failed")
            await self.emit("error", {"message": str(exc)[:500]})
        finally:
            speaker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await speaker
            if self.speech_queue is queue:
                self.speech_queue = None
        if self.awake_until:
            self.awake_until = time.monotonic() + self.settings.follow_up_seconds
        await self.emit("done", {"seconds": round(time.perf_counter() - start, 2),
                                 "awake": self.awake_until > time.monotonic()})

    async def arm(self):
        if self.wake is None:
            await self.phase("loading", "Preparing the wake word")
            try:
                self.wake = await asyncio.to_thread(WakeDetector)
            except Exception as exc:
                await self.emit("error", {"message": f"Wake word unavailable: {exc}. Tap the core to talk."})
        self.armed = True
        self.gate.reset()
        self.awake_until = 0
        await self.phase("standby", "Say “Hey Jarvis”")

    async def detect_wake(self, data):
        if not self.wake:
            return False
        self.wake_buffer.extend(data)
        while len(self.wake_buffer) >= 2560:
            chunk = bytes(self.wake_buffer[:2560])
            del self.wake_buffer[:2560]
            score = await asyncio.to_thread(self.wake.score, chunk)
            if score >= self.settings.wake_threshold:
                self.wake.reset()
                self.wake_buffer.clear()
                return True
        return False

    async def wake_listening(self, interrupt=False):
        if interrupt:
            await self.interrupt(reason="wake_word")
        self.gate.reset()
        self.awake_until = time.monotonic() + self.settings.follow_up_seconds
        self.idle_notified = False
        await self.emit("wake", {})
        await self.phase("listening", "Yes, Captain?")

    async def audio_loop(self):
        while True:
            await self.process_audio(await self.audio_queue.get())

    async def verify_speaker_speech(self, pcm, turn, final=False):
        # A microphone speech detector alone cannot distinguish speaker echo.
        # Keep playback intact while checking words against the audio we just sent.
        try:
            text = await asyncio.to_thread(self.engines.transcribe, pcm)
        except Exception:
            log.debug("Speaker interruption check failed", exc_info=True)
            return
        if turn != self.turn_id or not text:
            return
        similarity = echo_similarity(text, self.output_texts)
        if similarity >= 0.62:
            return
        words = re.findall(r"[a-z0-9]+", text.lower())
        explicit_stop = " ".join(words) in {"stop", "wait", "hold on", "stop talking", "be quiet", "quiet", "hang on", "no"}
        # Early fragments are less reliable than a completed utterance.
        if not final and not explicit_stop and (len(words) < 3 or similarity >= 0.45):
            return
        self.echo_candidate = False
        if final:
            await self.begin(text=text)
        else:
            await self.interrupt(reason="confirmed_speech")
            self.awake_until = time.monotonic() + self.settings.follow_up_seconds
            await self.phase("listening", "Listening, Captain")

    async def process_audio(self, data):
        if not self.armed or self.previewing:
            return
        protected = self.speaking or time.monotonic() < self.playback_guard_until
        if protected and not self.settings.barge_in:
            self.gate.reset()
            self.echo_candidate = False
            return
        busy = self.task and not self.task.done()
        awake = time.monotonic() < self.awake_until or busy or self.speaking or self.echo_candidate
        if not awake:
            if not self.idle_notified:
                await self.phase("standby", "Say “Hey Jarvis”")
                self.idle_notified = True
            if await self.detect_wake(data):
                await self.wake_listening()
            return
        for event, value in self.gate.feed(data, self.speaking or self.echo_candidate):
            if event == "start":
                if protected and self.settings.audio_output == "speakers":
                    self.echo_candidate = True
                    self.last_probe_frames = 0
                else:
                    await self.interrupt(reason="microphone_speech")
                    await self.phase("listening", "Listening, Captain")
            elif event == "utterance":
                candidate = self.echo_candidate
                self.echo_candidate = False
                await self.cancel_probe()
                if candidate:
                    await self.verify_speaker_speech(value, self.turn_id, final=True)
                else:
                    await self.begin(pcm=value)
            elif event == "noise":
                self.echo_candidate = False
                if not protected:
                    await self.phase("listening", "Listening, Captain")
        # Check about one second of sustained speech before cancelling playback.
        # Full utterance capture continues, preserving the start of the user's request.
        if (self.echo_candidate and self.gate.recording
                and len(self.gate.frames) - self.last_probe_frames >= 50
                and (self.barge_probe is None or self.barge_probe.done())):
            self.last_probe_frames = len(self.gate.frames)
            pcm = b"".join(self.gate.frames[-200:])
            self.barge_probe = asyncio.create_task(self.verify_speaker_speech(pcm, self.turn_id))

    async def preview_voice(self, packet):
        values = packet.get("settings", {})
        allowed = {"tts_engine", "kokoro_voice", "speech_speed"}
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError("Unsupported voice preview settings")
        options = Settings.model_validate({**self.settings.model_dump(), **values})
        await self.interrupt(reason="voice_preview")
        self.previewing = True
        self.task = asyncio.create_task(self.run_preview(options, self.turn_id))

    async def run_preview(self, options, turn):
        text = ("At your service, Captain. Everything is ready for our next conversation. "
                "I can help with your files, check the computer, or offer a suitably dry observation.")
        sent = False
        try:
            await self.phase("thinking", "Preparing the voice sample")
            await self.emit("caption", {"text": text})
            wav = await asyncio.to_thread(self.engines.synthesize, text, options=options)
            if turn != self.turn_id:
                return
            self.output_texts.append(text)
            await self.emit("audio", {"wav": base64.b64encode(wav).decode(),
                                      "text": text, "final": True})
            sent = True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.emit("error", {"message": f"Voice sample: {exc}"})
        finally:
            if turn == self.turn_id:
                if not sent:
                    self.previewing = False
                await self.emit("done", {"awake": self.awake_until > time.monotonic()})

    async def handle(self, packet):
        kind = packet.get("type")
        if kind == "arm":
            await self.arm()
        elif kind == "disarm":
            self.armed = False
            self.awake_until = 0
            self.gate.reset()
            self.wake_buffer.clear()
            while not self.audio_queue.empty():
                self.audio_queue.get_nowait()
            await self.interrupt()
            self.conversation.pending = None
            await self.emit("approval_cleared", {})
            await self.phase("idle", "Microphone off")
        elif kind == "listen":
            await self.interrupt()
            self.gate.reset()
            self.awake_until = time.monotonic() + self.settings.follow_up_seconds
            await self.phase("listening", "Listening, Captain")
        elif kind == "interrupt":
            await self.interrupt()
            await self.phase("listening" if self.armed else "idle", "At your service, sir")
        elif kind == "preview_voice":
            await self.preview_voice(packet)
        elif kind == "text":
            text = packet.get("text", "")
            if isinstance(text, str) and text.strip() and len(text) <= 6000:
                await self.begin(text=text)
        elif kind == "approval":
            if isinstance(packet.get("approved"), bool):
                await self.begin(approval=packet)
        elif kind == "playback":
            if packet.get("turn", self.turn_id) != self.turn_id:
                return
            was_speaking = self.speaking
            self.speaking = bool(packet.get("playing"))
            if self.speaking != was_speaking:
                if not self.gate.recording:
                    self.gate.reset()
                self.wake_buffer.clear()
                if self.wake:
                    self.wake.reset()
            if not self.speaking and self.previewing:
                self.previewing = False
                self.gate.reset()
            if was_speaking and not self.speaking:
                self.playback_guard_until = time.monotonic() + (0.3 if self.settings.audio_output == "speakers" else 0.05)
            if not self.speaking and self.awake_until:
                self.awake_until = time.monotonic() + self.settings.follow_up_seconds
        elif kind == "new_conversation":
            await self.interrupt()
            self.conversation.turns.clear()
            self.conversation.pending = None
            await self.emit("approval_cleared", {})
            await self.emit("caption", {"text": ""})
            await self.phase("listening" if self.armed else "idle", "A fresh start, Captain")
