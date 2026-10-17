# Build checkpoint — 17 October 2026

Working project: C:/PersonalJarvis. The OneDrive prototype folder is not required to launch it. The preserved original prototype is reference/Personal_Jarvis_Source.zip.

Installed and running: portable Ollama 0.40.5, self-contained Python 3.12.15, pinned Python packages, Qwen3.5 4B with a text-only jarvis-local:4b profile, Whisper base.en, Kokoro British voices, Piper Alan, and the Hey Jarvis wake detector. No Codex runtime is needed by the application.

After the battery shutdown, the SQLite integrity check returned ok, model/voice downloads were verified, the interpreter was repaired, and the complete setup ran successfully. Both service ports were confirmed closed after Stop Jarvis, then restarted through the launcher.

## Verification completed

- 25 core tests passed (including the voice playback update): tool input validation, real file operations and backups, persistent memory/reminders, approval expiry and replay prevention, voice segmentation, spoken decimals, turn cancellation, API access controls and redirected Windows folders.
- Real model read live PC status and wrote data/smoke-note.txt.
- Synthetic Hey Jarvis audio activated the actual wake detector.
- Synthetic microphone PCM passed through VAD, Whisper, model tool calls and Kokoro speech.
- A model-created reminder was delivered with local audio.
- An active model response was interrupted and acknowledged.
- Harmless PowerShell calculation returned the expected result; cancellation killed its process tree.
- Edge UI test passed with no page errors or mobile overflow; synthetic microphone capture started/stopped, a model response played through Web Audio, and Escape stopped playback.
- Local speech models loaded with no errors. Full-precision Kokoro is selected after measuring the int8 export as slower on this CPU.

Evidence: data/e2e-verification.json, data/speech-verification.json, data/benchmark-jarvis-local-4b.json and data/desktop.png / settings.png / mobile.png.

## Use

Open Launch Jarvis.cmd. Click Enable voice and allow the microphone. Say Hey Jarvis, pause for the chime, then speak. Follow-up listening stays active for 40 seconds. Stop Jarvis.cmd releases both local services.

The user reported that speech cut off during conversation on laptop/external speakers. A standalone George WAV played smoothly for them, so replacing the TTS model is not currently justified. Live conversation with the updated playback still needs their listening check. Automated microphone verification uses generated audio.

This working first version provides files, apps, system/media controls, PowerShell, explicit memory and reminders. It does not yet provide screen-driven GUI automation, connected calendar/email, a tray background microphone service, login autostart or semantic speech-to-speech turn taking. See README.md and ARCHITECTURE.md for exact behavior and limits.


## Voice playback update

- Keep short sentences together and preserve all text, including decimals, abbreviations and final fragments.
- Kokoro retains its complete generated waveform instead of trimming silence at the boundaries.
- Decode upcoming WAVs ahead and schedule them on the Web Audio clock. A done event cannot stop the final clip early.
- Settings now has Test voice: previews unsaved voice/speed choices, bypasses the brain and pauses microphone input for the duration of the sample.
- Natural follow-ups and spoken interruptions do not require another wake phrase. Speaker interruption checks compare recognized words with recent output before cancelling.
- 4 audio scheduler tests passed in addition to the 25 Python tests.
- Actual Edge playback check passed: complete preview and multi-clip model reply, no premature stops and no measurable scheduling gap (rounded to 0.000 seconds) between buffered reply clips. Preview restored listening and kept the saved George voice unchanged.
- Standard UI smoke check passed: no page errors or mobile overflow, microphone start/stop, actual model speech and Escape interruption.
- The user confirmed the untrimmed standalone George comparison sample plays smoothly. This distinguishes a working voice source from the reported conversation playback problem; it does not prove every live conversation is fixed.

Evidence: data/voice-comparison/results.json and WAVs, data/ui-voice-verification.json, data/settings-voice-test.png, data/voice-regression.json. Diagnostics are local and ignored by Git.


## Windows and calendar release 0.2.0

- Native C# / WebView2 window with a custom multi-size icon, app metadata, single-window activation and Start menu shortcut.
- Kernel-owned service lifecycle: normal close and forced host termination both left zero Jarvis services, model runners, WebView2 profile processes and service/debug listeners.
- Local month calendar, daily agenda, notes, all-day events, editable reminders, configurable advance alerts and model-accessible CRUD tools.
- Actual Qwen3.5 4B created, moved and deleted a calendar event. No-alert configuration survived rescheduling.
- Native UI event creation/edit/delete, reminder edit, custom 15-minute alert preservation, real voice playback and mobile overflow checks passed.
- 38 Python tests and 4 JavaScript scheduler tests passed.
- Full recommended setup completed: self-contained Python, pinned dependencies, cached model verification, language-only profile, offline speech, native build, runtime detection and Start registration. Setup stopped all its services on completion.
- Guided hardware suggestions and model choices from 0.8B to 35B MoE; only the 4B profile is validated on this laptop.
- Clean ZIP builder excludes personal data, settings, installed model weights and runtime caches; includes hashes and SDK redistribution notices.
- Public portfolio card and case study now describe the working application. The one-page product design resume was updated, exported with Microsoft Word and visually checked with Poppler.

Additional evidence: data/shutdown-verification.json, data/calendar-ui-verification.json, data/voice-calendar-verification.json and data/calendar-final-ui.json. Public screenshots use a temporary sample calendar entry, removed after capture.
