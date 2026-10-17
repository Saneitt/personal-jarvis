import asyncio
import json
import time
from pathlib import Path
import numpy as np
import pytest
from jarvis.config import Settings
from jarvis.storage import Store
from jarvis.tools import ToolRunner, validate_call, local_path
from jarvis.brain import Conversation
from jarvis.speech import UtteranceGate

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.sqlite3")

def test_offline_model_and_host_validation():
    for url in ["https://api.example.com", "http://192.168.1.2:11434", "http://localhost@evil.example"]:
        with pytest.raises(ValueError):
            Settings(ollama_url=url)
    with pytest.raises(ValueError):
        Settings(model="qwen3.5:cloud")
    assert Settings(ollama_url="http://127.0.0.1:11435").model

def test_arguments_reject_bad_types_and_unknown_tools():
    for name,args in [("delete_everything",{}),("files",{"action":"read"}),
                      ("computer",{"action":"open","target":["calc"]}),
                      ("computer",{"action":"status","script":"oops"}),
                      ("reminders",{"action":"cancel","id":True})]:
        with pytest.raises(ValueError):
            validate_call(name,args)

@pytest.mark.asyncio
async def test_real_file_creation_read_search_and_overwrite_backup(store,tmp_path):
    tools=ToolRunner(store,Settings())
    path=tmp_path/"note.txt"
    result=await tools.execute("files",{"action":"write","path":str(path),"text":"First version"})
    assert path.read_text()=="First version" and "error" not in result
    assert tools.confirmation("files",{"action":"write","path":str(path),"text":"Second"})
    result=await tools.execute("files",{"action":"write","path":str(path),"text":"Second"})
    assert Path(result["backup"]).read_text()=="First version"
    assert tools.files("read",str(path))["text"]=="Second"
    assert str(path) in tools.files("search",str(tmp_path),pattern="note")["matches"]

def test_move_never_silently_overwrites(store,tmp_path):
    a,b=tmp_path/"a.txt",tmp_path/"b.txt"
    a.write_text("a");b.write_text("b")
    tools=ToolRunner(store,Settings())
    with pytest.raises(ValueError):
        tools.files("move",str(a),destination=str(b))
    assert a.read_text()=="a" and b.read_text()=="b"

def test_memory_and_reminders_persist(store):
    item=store.remember("I prefer concise replies")
    assert Store(store.path).memories()[0]["id"]==item
    tools=ToolRunner(store,Settings())
    result=tools.reminders("create",text="Stretch",seconds=60)
    assert len(Store(store.path).reminders())==1
    assert tools.reminders("cancel",id=result["created"])["cancelled"]
    assert store.reminders()==[]
    with pytest.raises(ValueError):
        tools.reminders("create",text="Impossible",due_at="2000-01-01T00:00:00+00:00")

@pytest.mark.asyncio
async def test_approval_not_executed_until_confirmed_and_not_replayed(store):
    events,speech=[],[]
    async def emit(kind,payload):events.append((kind,payload))
    async def say(text,**kwargs):speech.append(text)
    c=Conversation(Settings(),store,emit,say)
    class Brain:
        async def stream(self,messages,on_token):
            if messages[-1]["role"]=="tool":
                await on_token("Completed, sir.")
                return {"role":"assistant","content":"Completed, sir."},{}
            return {"role":"assistant","content":"","tool_calls":[{"function":{"name":"powershell","arguments":{"script":"'hello'","reason":"Print hello"}}}]},{}
    c.brain=Brain()
    executed=[]
    async def execute(name,args):
        executed.append((name,args));return {"stdout":"hello"}
    c.tools.execute=execute
    await c.respond("Print hello using PowerShell")
    assert not executed and c.pending
    approval_id=c.pending["id"]
    await c.approval(True,approval_id)
    await c.approval(True,approval_id)
    assert len(executed)==1

@pytest.mark.asyncio
async def test_cancelled_and_expired_approval_does_not_execute(store):
    async def noop(*args,**kwargs):pass
    c=Conversation(Settings(),store,noop,noop)
    called=[]
    async def execute(*args):called.append(args)
    c.tools.execute=execute
    base={"id":"one","created":time.monotonic(),"name":"powershell","args":{"script":"'hi'"},"turn":[]}
    c.pending=base.copy()
    await c.approval(False,"one")
    c.pending={**base,"created":time.monotonic()-121}
    await c.approval(True,"one")
    assert not called and not c.pending

def test_utterance_gate_keeps_preroll_and_ends_on_silence():
    gate=UtteranceGate(Settings(silence_ms=400),classifier=lambda b,sr:True)
    voice=(np.ones(320,dtype="<i2")*3000).tobytes()
    events=[]
    for _ in range(30):events+=gate.feed(voice)
    for _ in range(22):events+=gate.feed(bytes(640))
    assert [x[0] for x in events]==["start","utterance"]
    assert len(events[1][1])>=30*640

def test_noise_spike_does_not_start_a_turn():
    gate=UtteranceGate(Settings(),classifier=lambda b,sr:True)
    spike=(np.ones(320,dtype="<i2")*3000).tobytes()
    assert not gate.feed(spike)
    assert not gate.feed(bytes(640*45))

def test_api_rejects_unauthenticated_and_cross_origin_requests(monkeypatch,store):
    from fastapi.testclient import TestClient
    import jarvis.server as server
    monkeypatch.setattr(server,"store",store)
    client=TestClient(server.app)
    assert client.get("/api/memory").status_code==401
    assert client.get("/api/memory",headers={"X-Jarvis-Token":server.TOKEN,"Origin":"https://evil.example"}).status_code==403
    assert client.get("/api/memory",headers={"X-Jarvis-Token":server.TOKEN}).status_code==200
    assert client.get("/",headers={"Host":"evil.example"}).status_code==400
    with pytest.raises(Exception):
        with client.websocket_connect("/ws",subprotocols=["jarvis","bad-token"]):
            pass


def test_redirected_windows_folder_alias(monkeypatch, tmp_path):
    import jarvis.tools as module
    monkeypatch.setattr(module, "known_folder", lambda name: tmp_path / name)
    assert local_path("documents") == (tmp_path / "documents").resolve()

@pytest.mark.asyncio
async def test_spoken_decimal_is_not_split_into_two_sentences(store):
    spoken = []
    async def emit(*args, **kwargs): pass
    async def say(text, **kwargs): spoken.append(text)
    conversation = Conversation(Settings(), store, emit, say)
    class Brain:
        async def stream(self, messages, token):
            for chunk in ["You have 4", ".", "5 GB available", ".", " Plenty of room", "."]:
                await token(chunk)
            return {"role": "assistant", "content": "You have 4.5 GB available. Plenty of room."}, {}
    conversation.brain = Brain()
    await conversation.respond("How much memory is free?")
    assert spoken == ["You have 4.5 GB available. Plenty of room."]

@pytest.mark.asyncio
async def test_interruption_cancels_turn_and_stale_audio(store):
    from jarvis.session import VoiceSession
    from types import SimpleNamespace
    events = []
    class Socket:
        async def send_json(self, event): events.append(event)
    session = VoiceSession(Socket(), Settings(), store, SimpleNamespace())
    cancelled = asyncio.Event()
    async def slow_turn():
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()
    session.task = asyncio.create_task(slow_turn())
    await asyncio.sleep(0)
    await session.interrupt()
    assert cancelled.is_set() and session.task is None
    assert session.turn_id == 1 and events[-1]["type"] == "interrupted"

def test_headphone_interruption_rejects_brief_speech_burst():
    gate = UtteranceGate(Settings(audio_output="headphones"), classifier=lambda b, sr: True)
    voice = (np.ones(320, dtype="<i2") * 3000).tobytes()
    assert not gate.feed(voice * 8, speaking=True)
    assert not gate.feed(bytes(640 * 30), speaking=True)
    events = gate.feed(voice * 20, speaking=True)
    assert [event[0] for event in events] == ["start"]

@pytest.mark.asyncio
async def test_speaker_echo_never_uses_vad_to_cancel_reply(store):
    from jarvis.session import VoiceSession
    from types import SimpleNamespace
    events = []
    class Socket:
        async def send_json(self, event): events.append(event)
    session = VoiceSession(Socket(), Settings(audio_output="speakers"), store,
                           SimpleNamespace(transcribe=lambda pcm: "I can help with your files"))
    session.output_texts.append("I can help with your files.")
    session.armed = True
    session.awake_until = time.monotonic() + 40
    session.gate = UtteranceGate(session.settings, classifier=lambda b, sr: True)
    await session.handle({"type": "playback", "playing": True, "turn": 0})
    echo = (np.ones(1280, dtype="<i2") * 6000).tobytes()
    for _ in range(25):
        await session.process_audio(echo)
    if session.barge_probe: await session.barge_probe
    assert session.speaking and session.turn_id == 0
    assert not any(e["type"] == "interrupted" for e in events)
    await session.handle({"type": "playback", "playing": False, "turn": 0})
    for _ in range(12):
        await session.process_audio(bytes(2560))
    assert session.turn_id == 0
    await session.cancel_probe()

@pytest.mark.asyncio
async def test_speaker_user_can_interrupt_without_wake_phrase(store):
    from jarvis.session import VoiceSession
    from types import SimpleNamespace
    events = []
    class Socket:
        async def send_json(self, event): events.append(event)
    session = VoiceSession(Socket(), Settings(audio_output="speakers"), store,
                           SimpleNamespace(transcribe=lambda pcm: "Actually open my downloads"))
    session.output_texts.append("Your computer is running smoothly, Captain.")
    session.armed = session.speaking = True
    session.echo_candidate = True
    session.gate.frames = [bytes(640)] * 60
    await session.verify_speaker_speech(bytes(640*60), 0)
    assert not session.speaking and session.turn_id == 1
    assert len(session.gate.frames) == 60  # Keep the start of the user's utterance.
    assert any(e["type"] == "interrupted" and e["reason"] == "confirmed_speech" for e in events)

def test_echo_matching_covers_partial_and_imperfect_transcriptions():
    from jarvis.speech import echo_similarity
    spoken = ["Your computer is running smoothly, Captain.", "You have plenty of memory available."]
    assert echo_similarity("computer is running smoothly", spoken) == 1
    assert echo_similarity("you have plenty memory available", spoken) >= .62
    assert echo_similarity("Actually open my downloads", spoken) < .45

@pytest.mark.asyncio
async def test_speaker_followup_stays_awake_without_wake_phrase(store):
    from jarvis.session import VoiceSession
    from types import SimpleNamespace
    class Socket:
        async def send_json(self, event): pass
    session = VoiceSession(Socket(), Settings(audio_output="speakers"), store,
                           SimpleNamespace(transcribe=lambda pcm: "Please open my downloads"))
    session.armed = session.speaking = True
    session.awake_until = time.monotonic() + 40
    session.output_texts.append("Your computer is running smoothly, Captain.")
    await session.handle({"type": "playback", "playing": False, "turn": 0})
    assert session.awake_until > time.monotonic()
    heard = []
    async def begin(**kwargs): heard.append(kwargs)
    session.begin = begin
    await session.verify_speaker_speech(bytes(32000), 0, final=True)
    assert heard == [{"text": "Please open my downloads"}]

@pytest.mark.asyncio
async def test_stale_playback_end_cannot_disable_echo_protection(store):
    from jarvis.session import VoiceSession
    from types import SimpleNamespace
    class Socket:
        async def send_json(self, event): pass
    session = VoiceSession(Socket(), Settings(), store, SimpleNamespace())
    session.turn_id = 3
    session.speaking = True
    await session.handle({"type": "playback", "playing": False, "turn": 2})
    assert session.speaking

@pytest.mark.asyncio
async def test_headphones_still_allow_natural_speech_interruption(store):
    from jarvis.session import VoiceSession
    from types import SimpleNamespace
    events = []
    class Socket:
        async def send_json(self, event): events.append(event)
    settings = Settings(audio_output="headphones")
    session = VoiceSession(Socket(), settings, store, SimpleNamespace())
    session.armed = session.speaking = True
    session.gate = UtteranceGate(settings, classifier=lambda b, sr: True)
    await session.process_audio((np.ones(320*20, dtype="<i2") * 3000).tobytes())
    assert session.turn_id == 1 and not session.speaking
    assert any(e["type"] == "interrupted" and e["reason"] == "microphone_speech" for e in events)


def test_speech_groups_short_sentences_and_preserves_all_streamed_text():
    from jarvis.brain import SpeechBuffer
    text = ("Certainly, sir. Dr. Smith has 4.5 GB available on this computer, "
            "which should be enough for your next task. Shall I open your files?")
    buffer, chunks = SpeechBuffer(), []
    for char in text:
        chunks += buffer.feed(char)
    chunks.append(buffer.finish())
    assert chunks[0].startswith("Certainly, sir. Dr. Smith has 4.5 GB")
    assert chunks[0].endswith("task.")
    assert " ".join(chunks) == text


def test_speech_streams_long_sentences_without_losing_the_tail():
    from jarvis.brain import SpeechBuffer
    text = " ".join(["A deliberately long sentence without punctuation"] * 30) + ". All done."
    buffer, chunks = SpeechBuffer(), []
    for index in range(0, len(text), 7):
        chunks += buffer.feed(text[index:index + 7])
    assert chunks  # Audio is available before the response completes.
    chunks.append(buffer.finish())
    assert all(len(chunk) <= 320 for chunk in chunks)
    assert " ".join(chunks) == text
    assert buffer.finish() == ""


def test_kokoro_preserves_full_waveform_and_selected_preview_voice():
    import io
    import wave
    from types import SimpleNamespace
    from jarvis.speech import SpeechEngines
    settings = Settings(kokoro_voice="bm_george")
    engines = SpeechEngines(settings)
    calls = []
    samples = np.array([0, .0001, .4, -.3, .0001, 0], dtype=np.float32)
    def create(text, **options):
        calls.append(options)
        return samples, 24000
    engines.kokoro = SimpleNamespace(create=create)
    options = Settings(kokoro_voice="bm_fable", speech_speed=.95)
    wav = engines.synthesize("All done.", options=options)
    with wave.open(io.BytesIO(wav)) as f:
        assert f.getnframes() == len(samples)
        assert f.getframerate() == 24000
        assert f.readframes(f.getnframes()) == (samples*32767).astype("<i2").tobytes()
    assert calls[0]["trim"] is False
    assert calls[0]["voice"] == "bm_fable"
    assert calls[0]["speed"] == .95
    assert settings.kokoro_voice == "bm_george"


@pytest.mark.asyncio
async def test_voice_preview_skips_microphone_and_brain_then_resumes(store):
    import io
    import wave
    from types import SimpleNamespace
    from jarvis.session import VoiceSession
    events, generated = [], []
    class Socket:
        async def send_json(self, event): events.append(event)
    def synthesize(text, *, options):
        generated.append(options.kokoro_voice)
        output = io.BytesIO()
        with wave.open(output, "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000)
            f.writeframes(bytes(2400))
        return output.getvalue()
    session = VoiceSession(Socket(), Settings(), store, SimpleNamespace(synthesize=synthesize))
    session.armed = True
    async def forbidden(*args): raise AssertionError("Preview must not use the brain or microphone")
    session.conversation.respond = forbidden
    session.gate.feed = forbidden
    await session.handle({"type":"preview_voice", "settings":{"kokoro_voice":"bm_fable"}})
    await session.process_audio(bytes(2560))
    await session.task
    assert session.previewing and generated == ["bm_fable"]
    assert session.settings.kokoro_voice == "bm_george"
    assert session.conversation.turns == []
    assert any(e["type"] == "audio" and e["final"] for e in events)
    await session.handle({"type":"playback", "turn":session.turn_id, "playing":True})
    await session.handle({"type":"playback", "turn":session.turn_id, "playing":False})
    assert not session.previewing and session.armed


@pytest.mark.asyncio
async def test_preview_rejects_invalid_voice_before_interrupting(store):
    from types import SimpleNamespace
    from jarvis.session import VoiceSession
    class Socket:
        async def send_json(self, event): pass
    session = VoiceSession(Socket(), Settings(), store, SimpleNamespace())
    for values in [{"kokoro_voice":"not-installed"}, {"speech_speed":99}, {"model":"different-model"}]:
        with pytest.raises(ValueError):
            await session.preview_voice({"settings":values})
    assert session.turn_id == 0 and not session.previewing
