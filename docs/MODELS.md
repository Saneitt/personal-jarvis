# Model choice for this PC

Checked on 17 October 2026. The installed default is **Qwen3.5 4B, Q4_K_M**, served by the project's private Ollama instance under the name jarvis-local:4b. This is my recommendation for this build after checking actual tool use on this laptop, rather than choosing from parameter counts alone.

## Hardware checked

- Intel Core i7-10750H, six cores / twelve threads
- 16 GB system RAM
- NVIDIA GeForce RTX 3050 Laptop GPU, 4 GB VRAM
- Windows 11 Home; NVIDIA driver 595.97

The 4 GB GPU is the constraint. A larger model can spill into system RAM, but that usually adds latency that is particularly noticeable in conversation. Keep the laptop connected to power and leave graphics memory available when using Jarvis.

## Installed configuration

| Component | Choice | Reason |
| --- | --- | --- |
| Brain | Qwen3.5 4B / jarvis-local:4b, Q4_K_M, approximately 3.3 GB source download | Modern tool-capable open model; passed live PC status and file operations |
| Context | 4096 tokens | Limits memory overhead on the 4 GB GPU |
| Reasoning mode | Disabled for voice requests | Avoids long internal reasoning before a spoken response |
| Recognition | faster-whisper base.en, CPU int8 | Leaves scarce GPU memory available for the brain |
| Voice | Kokoro 82M, full-precision ONNX on CPU, bm_george | Natural British male voice; tested faster than the int8 export on this CPU |
| Alternative voice | Piper, en_GB-alan-medium | Much lighter speech generation |
| Wake phrase | openWakeWord Hey Jarvis | Local detection without an API key |

Qwen3.5 and Kokoro have Apache 2.0 model licenses. The wake model has a separate noncommercial license; see THIRD_PARTY.md.

The local profile reuses the original language weights and official qwen3.5 renderer/parser, without loading the unused vision projector. It does not duplicate the language weights on disk. The original qwen3.5:4b package is retained as an alternative. This app does not send images to the model. The profile increased GPU offload from 15/33 to 25/33 layers in the measured configuration.

The first model load can take considerably longer than an ordinary reply. The launcher preloads the brain, and the app displays a loading note. Ollama keeps it resident for fifteen minutes after use; an idle model may need to reload. The model may offload only some layers to the GPU depending on available memory.

## Measurements and rejected candidates

Machine-readable records are kept locally in data/benchmark-*.json, data/speech-verification.json and data/e2e-verification.json.

Short Kokoro sentences tested at roughly 1.5–1.7 seconds to synthesize and roughly 0.7–0.8 seconds to transcribe with Whisper. The int8 Kokoro export was much slower on this setup (15–23 seconds in the initial comparison), so it is not used. Piper produced the same short test sentences in approximately 0.1–0.3 seconds.

Qwen3 4B was also downloaded and tested. Although it generated tokens quickly, its installed Ollama template/runtime combination returned reasoning as normal content despite think=false. Explicit non-thinking prompts and a local template profile did not resolve it reliably. It was rejected and its experimental downloads removed. Raw results are retained for diagnosis. This is an observation about this tested configuration, not a claim that Qwen3 cannot work with other runtimes.

The text-only profile improved the short warm tool-selection benchmark from roughly 2.75 seconds / 14 tokens per second to 1.92 seconds / 21.6 tokens per second. These are model-generation measurements, not total voice latency; the full request also includes transcription, tool execution and speech.

Short tests are not a general intelligence benchmark. The model can still misunderstand requests, miss tool arguments, or answer poorly. This laptop can support useful local assistance; it does not offer the capability or conversational latency of a large hosted voice model.

## Upgrading later

The brain is replaceable without rewriting tools, voice, memory or the interface. Start Jarvis, use the download script, then choose the model in Settings:

~~~powershell
.\.venv\Scripts\python.exe scripts\pull_model.py qwen3.5:9b
~~~

A larger Qwen3.5 model is an upgrade candidate, not a recommendation to download it onto this 4 GB laptop now. Choose the model and quantization after inspecting the new PC's GPU memory. Model weights, context cache, computation buffers, speech and other apps all need headroom. Test tool calls and end-to-end voice latency before making it the default.

Use a local Ollama model with tool support and a compatible non-thinking mode. The native API adapter is in jarvis/brain.py; models with different API requirements need a small adapter change. Settings selects installed models; explicit preferences and reminders are in SQLite rather than model weights.

## Primary sources

- [Qwen3.5 4B on Ollama](https://ollama.com/library/qwen3.5:4b)
- [Qwen3.5 4B model card](https://huggingface.co/Qwen/Qwen3.5-4B)
- [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling)
- [Ollama Windows support](https://docs.ollama.com/windows)
- [Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M)
- [Kokoro ONNX](https://github.com/thewh1teagle/kokoro-onnx)


## Setup catalog

The guided setup reads config/models.json and offers Qwen3.5 0.8B, 2B, 4B, 9B, 27B and 35B MoE, plus a custom Ollama name. Hardware suggestions are estimates; only the 4B profile has been tested on the development PC. The selector uses RAM and NVIDIA VRAM to suggest a starting tier and downloads only the selected model. The language-only profile builder now accepts each Qwen3.5 source/tag.

All context presets remain at 4096 tokens to keep the first installation predictable. Increase context in config.local.json only after measuring memory use on the target PC. Model quality, tool reliability and latency need validation on every new profile.
