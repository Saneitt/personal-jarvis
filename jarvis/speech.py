from __future__ import annotations
import io
import re
import threading
import wave
from difflib import SequenceMatcher
from collections import deque
import numpy as np
import webrtcvad
from .config import MODELS

class SpeechEngines:
    def __init__(self, settings):
        self.settings = settings
        self.stt = self.piper = self.kokoro = None
        self.stt_lock, self.tts_lock = threading.Lock(), threading.Lock()
        self.errors = {}

    @property
    def tts(self):
        return self.kokoro if self.settings.tts_engine == 'kokoro' else self.piper

    def load(self):
        try:
            from faster_whisper import WhisperModel
            self.stt = WhisperModel(str(MODELS / "whisper" / self.settings.stt_model),
                                    device="cpu", compute_type="int8", cpu_threads=4,
                                    local_files_only=True)
        except Exception as exc:
            self.errors["stt"] = str(exc)
        try:
            from piper import PiperVoice
            self.piper = PiperVoice.load(str(MODELS / "piper" / (self.settings.voice + ".onnx")))
        except Exception as exc:
            self.errors["piper"] = str(exc)
        try:
            from kokoro_onnx import Kokoro
            import onnxruntime as ort
            options = ort.SessionOptions()
            options.intra_op_num_threads = 3
            options.inter_op_num_threads = 1
            options.add_session_config_entry("session.intra_op.allow_spinning", "0")
            options.add_session_config_entry("session.inter_op.allow_spinning", "0")
            session = ort.InferenceSession(str(MODELS / "kokoro" / "kokoro-v1.0.onnx"),
                                           sess_options=options, providers=["CPUExecutionProvider"])
            self.kokoro = Kokoro.from_session(session, str(MODELS / "kokoro" / "voices-v1.0.bin"))
        except Exception as exc:
            self.errors["kokoro"] = str(exc)

    def transcribe(self, pcm):
        if not self.stt:
            raise RuntimeError("Speech recognition is unavailable. Run Setup Jarvis first.")
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        with self.stt_lock:
            segments, _ = self.stt.transcribe(audio, language=self.settings.speech_language,
                beam_size=1, best_of=1, condition_on_previous_text=False,
                vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
                no_speech_threshold=0.6)
            text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.65).strip()
        return re.sub(r"^(?:hey\s+)?jarvis[,.\s]*", "", text, flags=re.I).strip()

    def synthesize(self, text, *, options=None):
        selected = options or self.settings
        engine = self.kokoro if selected.tts_engine == "kokoro" else self.piper
        if not engine:
            raise RuntimeError("The local voice is unavailable. Run Setup Jarvis first.")
        from piper import SynthesisConfig
        clean = re.sub(r"[*#]", "", text).replace(chr(96), "")
        output = io.BytesIO()
        with self.tts_lock, wave.open(output, "wb") as wav:
            if selected.tts_engine == "kokoro":
                # Preserve the model's own onset, breath and final release.
                samples, rate = engine.create(clean, voice=selected.kokoro_voice,
                    speed=selected.speech_speed, lang="en-gb", trim=False)
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(rate)
                wav.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
            else:
                engine.synthesize_wav(clean, wav, syn_config=SynthesisConfig(
                    length_scale=1.0 / selected.speech_speed))
        return output.getvalue()

class WakeDetector:
    def __init__(self):
        from openwakeword.model import Model
        self.model = Model(
            wakeword_models=[str(MODELS / "wake" / "hey_jarvis_v0.1.onnx")],
            inference_framework="onnx",
            melspec_model_path=str(MODELS / "wake" / "melspectrogram.onnx"),
            embedding_model_path=str(MODELS / "wake" / "embedding_model.onnx"))

    def score(self, pcm):
        result = self.model.predict(np.frombuffer(pcm, dtype="<i2"))
        return max(float(value) for value in result.values())

    def reset(self):
        self.model.reset()

class UtteranceGate:
    """20 ms frames; retain pre-roll, reject short noises, end on silence."""
    def __init__(self, settings, classifier=None):
        self.settings = settings
        self.vad = classifier or webrtcvad.Vad(2).is_speech
        self.reset()

    def reset(self):
        self.pending = bytearray()
        self.pre = deque(maxlen=25)
        self.frames = []
        self.votes = deque(maxlen=25)
        self.silent = self.voiced = 0
        self.recording = False

    def feed(self, data, speaking=False):
        self.pending.extend(data)
        events = []
        while len(self.pending) >= 640:
            frame = bytes(self.pending[:640])
            del self.pending[:640]
            samples = np.frombuffer(frame, dtype="<i2").astype(np.float32) / 32768
            rms = float(np.sqrt(np.mean(samples * samples)))
            voiced = rms >= self.settings.noise_floor and self.vad(frame, 16000)
            if not self.recording:
                self.pre.append(frame)
                self.votes.append(voiced)
                threshold = 18 if speaking else 5
                recent_votes = list(self.votes)[-(25 if speaking else 10):]
                if len(recent_votes) >= threshold and sum(recent_votes) >= threshold:
                    self.recording = True
                    self.frames = list(self.pre)
                    self.voiced = sum(self.votes)
                    self.silent = 0
                    events.append(("start", None))
            else:
                self.frames.append(frame)
                self.voiced += int(voiced)
                self.silent = 0 if voiced else self.silent + 1
                if self.silent * 20 >= self.settings.silence_ms or len(self.frames) >= 1500:
                    if self.voiced >= 12:
                        events.append(("utterance", b"".join(self.frames)))
                    else:
                        events.append(("noise", None))
                    self.frames, self.recording = [], False
                    self.votes.clear()
                    self.pre.clear()
                    self.silent = self.voiced = 0
        return events


def echo_similarity(text, spoken_texts):
    """Compare captured words to recent output, including partial sentences."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    if not words:
        return 1.0
    reference = re.findall(r"[a-z0-9]+", " ".join(spoken_texts).lower())
    if not reference:
        return 0.0
    width = len(words)
    best = 0.0
    for size in range(max(1, width - 2), width + 3):
        for start in range(max(1, len(reference) - size + 1)):
            window = reference[start:start + size]
            best = max(best, SequenceMatcher(None, words, window, autojunk=False).ratio())
            if best == 1:
                return best
    return best
