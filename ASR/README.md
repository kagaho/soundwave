# Speech and voice experiments

These Python clients demonstrate microphone transcription, LLM requests, and speech synthesis. They expect separate running ASR, inference, and TTS services; they are not a packaged application.

| File | Purpose |
| --- | --- |
| `mic-transcribe.py`, `riva-mic.py` | Microphone/ASR experiments |
| `elita-chat.py` | Text/voice interaction experiment |
| `soundwave-agent-ver1_4.py` | Combined voice-agent prototype |
| `chat.sh` | Local launcher; inspect expected interpreter and paths |
| `RIVA-TTS.md` | Historical Riva notes |

Review imports and install dependencies in an isolated environment. Adapt hardcoded endpoint constants, audio devices, model names, and service ports before use. NVIDIA client libraries and audio support depend on the host. No live GPU or microphone test is implied by release validation. Redundant older prototypes and sample audio have been omitted from the public snapshots.
