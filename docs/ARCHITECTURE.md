# Architecture

## Conversation path

Native WebView2 microphone -> echo cancellation/noise suppression -> AudioWorklet PCM at 16 kHz -> authenticated local WebSocket -> openWakeWord when asleep -> WebRTC VAD when awake -> faster-whisper -> Ollama streaming chat/tool loop -> local tool results -> speech chunk queue -> Kokoro/Piper WAV -> scheduled Web Audio playback.

The microphone is independent of model generation and playback. This allows voice activity to interrupt a running response. Each response has an incrementing turn ID. Interrupted/cancelled TTS work cannot send stale audio into a new turn. The client separately invalidates queued and decoding audio.

Short streamed sentences are grouped until a complete boundary with roughly 16 words, or a bounded clause/word boundary for long sentences. Final short replies flush immediately when text generation completes. Kokoro preserves its complete waveform with trim=False. The browser decodes ahead, schedules consecutive clips on the audio clock and keeps output active until the final scheduled buffer ends. The model completing its response does not stop audio already playing.

Settings voice previews use a validated settings snapshot and a fixed script, bypassing the brain and conversation history. They do not change saved settings. Microphone input is ignored until sample playback finishes; manual stop and Escape still work.

Speaker mode checks captured words against recently spoken text before accepting a voice interruption. Headphone mode uses sustained voice activity directly. Follow-up listening remains open for the configured period after playback, without repeating the wake phrase. This is a heuristic; overlapping speech and recognition errors can still affect it.

The browser requests microphone access only when Enable voice or the central core is clicked. The explicit off control stops MediaStream tracks. A disconnected socket releases capture and does not silently reactivate it.

## Components

- jarvis/config.py: validated settings, project-relative paths, offline flags
- jarvis/server.py: loopback FastAPI server, origin/token checks, status/settings/memory APIs, reminders
- jarvis/session.py: per-window voice state, cancellation, audio processing and speech queue
- jarvis/speech.py: speech engines, wake detector, buffered utterance segmentation
- jarvis/brain.py: personality, bounded conversation history, streaming model requests, approvals and tool loop
- jarvis/tools.py: explicit JSON tool schemas, input validation, Windows operations
- jarvis/storage.py: SQLite persistence, calendar records and alert delivery state
- jarvis/calendar.py: timezone-aware event validation shared by voice and API
- desktop/Jarvis.cs: native WinForms/WebView2 host, app identity, icon, single window, Windows Job Object ownership
- web/: preserved visual language of the original prototype, replaced production controller
- scripts/: setup, launch/stop, model downloads, benchmarks, verification

A single voice window owns the assistant at a time to prevent duplicate microphones and commands. Close the existing Jarvis window before opening another client.

## Windows lifecycle

The native window starts the private services inside a Windows Job Object with kill-on-close ownership. Closing or terminating the host releases its model runners and backend even after an abnormal exit. Normal close disposes the microphone/browser and requests service shutdown first. User apps explicitly launched by the computer tool can break away so they remain open independently.

A per-user Start menu shortcut points to the compiled native executable and custom multi-size icon. There is no tray process, scheduled wakeup, login startup or always-on monitor. launch.ps1 -NoWindow deliberately retains a manual service mode for development.

The calendar uses timezone-aware ISO inputs, UTC timestamps in SQLite and local display dates. Month queries include overlapping multiday events. Create/update/delete are shared by UI and model tools. Alerts persist their delivered state; edits reschedule them. A closed PC/app cannot issue alerts, and ended calendar events are not replayed on restart.

## Model portability

Ollama is accessed through its native local chat API. The model name and context size are settings. No tool logic or memories are embedded into a particular model's weights. The tested default supports tool calls and think=false. The local jarvis-local:4b profile keeps Qwen3.5 language weights and its native renderer/parser, omitting its unused vision projector to improve GPU utilization. Other models must be checked for compatible tool and thinking behavior.

Larger context windows require more memory. The shipped context is 4096 tokens for this 4 GB GPU. History is retained as complete user/assistant/tool turns and trimmed to a bounded recent window, while explicit saved preferences are included in the system prompt.

## Execution semantics

The system prompt distinguishes real tool results from conversational claims. A maximum of five model/tool rounds prevents an unbounded action loop. Tool schemas and application-side validation reject unknown functions, wrong types and extra arguments.

A pending action contains its exact tool arguments, an opaque ID and a two-minute expiry. The application consumes this pending action before execution. Duplicate approval requests cannot replay it. A new unrelated request cancels the prior pending action.

Overwrites back up the prior file. Moves refuse destination collisions. Deletes use the Recycle Bin. The tool executor records successes, failures and interruptions. Generic PowerShell commands run in a child process with a 30-second limit; timeout or cancellation terminates the process tree.

This is a local personal agent, not a sandbox for untrusted model code. If trusted PowerShell is enabled, model-generated scripts inherit the user's account privileges. Loopback authentication only protects the application entry points.

## Known limitations and next work

- Text-only reasoning is used even if the model supports vision; no screenshot-driven desktop control yet.
- English base.en recognition is configured. Multilingual recognition needs another downloaded Whisper model and a matching language setting.
- VAD is acoustic endpointing, not a speech-to-speech model with semantic turn detection.
- Browser echo cancellation helps but cannot guarantee perfect speakerphone interruption.
- Wake-word recognition needs a live microphone check with the user's voice.
- No tray daemon, Windows login autostart, proactive screen observer, external calendar/mail integration, or scheduled unattended workflows. A local calendar is provided.
- File contents and retrieved text are treated as data in the prompt, but prompt instructions alone cannot guarantee that a small model will never follow hostile text.
