# Third-party components

The runtime downloads these components rather than redistributing their model files in the source repository. Retain the original licenses if packaging binaries/models for others.

| Component | Role | Source / license |
| --- | --- | --- |
| WebView2 SDK 1.0.4258.31 | Native Windows window | https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.4258.31 — Microsoft license and notice copied beside the distributed SDK assemblies |
| Ollama | Local model host | https://github.com/ollama/ollama — MIT |
| Qwen3 4B / Qwen3.5 4B | Assistant brain | https://ollama.com/library/qwen3:4b ; https://huggingface.co/Qwen/Qwen3.5-4B — Apache 2.0 model licenses |
| faster-whisper | Speech recognition runtime | https://github.com/SYSTRAN/faster-whisper — MIT |
| Whisper base.en | Speech recognition weights | https://huggingface.co/Systran/faster-whisper-base.en — original OpenAI Whisper MIT |
| Kokoro 82M | Neural voice model | https://huggingface.co/hexgrad/Kokoro-82M — Apache 2.0 |
| kokoro-onnx | Local voice runtime | https://github.com/thewh1teagle/kokoro-onnx — MIT |
| Piper | Alternative local voice runtime | https://github.com/OHF-Voice/piper1-gpl — GPL-3.0 |
| Alan medium voice | British alternative voice | https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/alan/medium — consult the downloaded MODEL_CARD and linked source dataset license |
| openWakeWord | Wake detector code | https://github.com/dscripka/openWakeWord — Apache 2.0 code |
| Hey Jarvis pretrained wake model | Wake phrase | Same project — pretrained models are CC BY-NC-SA 4.0; personal noncommercial use. Review this before commercial distribution. |
| eSpeak NG / phonemizer | Text pronunciation | https://github.com/espeak-ng/espeak-ng ; https://github.com/bootphon/phonemizer — GPL components |
| ONNX Runtime | CPU neural inference | https://github.com/microsoft/onnxruntime — MIT |
| uv / Python build standalone | Isolated Python setup | https://github.com/astral-sh/uv ; https://github.com/astral-sh/python-build-standalone |

Model registry details were checked on 17 October 2026. The compact models' benchmarks do not imply equal capability to larger cloud assistants. Hardware suitability is checked with on-device benchmarks.
