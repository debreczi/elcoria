# Streaming ASR + Emotion + Intent Analysis — Build Spec

**Context:** Hungarian healthcare PoC. Real-time transcription with mood detection (Sonde Health–style vocal biomarkers) and intent classification. On-prem, K8s-deployable, NIS2-aware.

**Target environment:** Single GPU (A10 24 GB or equivalent), Python 3.11+, FastAPI, asyncio, WebSocket streaming.

---

## 1. Problem statement

Build a streaming pipeline that ingests live audio (microphone, SIP, WebSocket) and emits, in real time:

- Transcript (Hungarian, with English fallback)
- Speaker emotion / mood (angry, anxious, desperate, happy, neutral, etc.)
- Vocal biomarkers (prosodic features — pitch, jitter, shimmer, energy)
- Classified intent (routine / concerned / urgent / crisis) for healthcare triage

End-to-end target latency: **under 2 seconds** from speech-end to full structured output.

---

## 2. Honest constraint up front

There is **no single open-source model on Hugging Face today that does excellent Hungarian ASR and native emotion classification in one pass.**

- Sonde Health–style vocal biomarker analysis is proprietary (Sonde, Behavox, Cogito, audEERING).
- Open-source emotion models are overwhelmingly English-trained (RAVDESS, IEMOCAP, CREMA-D, MELD).
- Emotion classifiers often transfer cross-lingually because they lean on **acoustic prosody** (pitch, energy, jitter/shimmer) rather than lexical content — but this needs validation on Hungarian voices and likely fine-tuning for production.

Therefore the architecture is a **multi-stage pipeline**, not a single model.

---

## 3. Architecture

```
Mic / SIP audio (16 kHz PCM)
    │
    ▼
┌─────────────┐
│ Silero VAD  │  Stage 0: chunks audio into utterances (~20 ms frames)
└──────┬──────┘
       │ utterance buffer (0.5–3 s)
       │
       ├──────────────┬──────────────┐
       ▼              ▼              ▼
  ┌─────────┐   ┌──────────┐   ┌──────────┐
  │ Whisper │   │ wav2vec2 │   │ openSMILE│
  │ HU-v3   │   │ emotion  │   │ eGeMAPS  │
  │ (ASR)   │   │ (SER)    │   │ (biomark)│
  └────┬────┘   └─────┬────┘   └─────┬────┘
       │              │              │
       └──────────────┼──────────────┘
                      ▼
              ┌───────────────┐
              │ Fusion / LLM  │  intent classification
              │ (Qwen/Claude) │
              └───────┬───────┘
                      ▼
              {transcript, emotion, biomarkers, intent}
                      ▼
                  WebSocket → UI
```

Three audio models run **in parallel** on the same chunk via `asyncio.gather()` with separate CUDA streams. Total latency ≈ slowest model, not the sum.

---

## 4. Model selection

### Stage 0 — Voice Activity Detection
- **`snakers4/silero-vad`** — tiny, CPU-fast, 30 ms frames, robust to noise. De facto standard for streaming.

### Stage 1 — ASR (Hungarian)

Hungarian Whisper leaderboard (sarpba/whisper-teszt-eredmenyek on Hugging Face):

| Model | WER (CV17) | Notes |
|---|---|---|
| `benmajor27/whisper-large-v3-hu_full` | 9.42 | Best WER, primary choice |
| `sarpba/whisper-hu-large-v3-turbo-finetuned` | 12.67 | Faster, turbo arch |
| `Trendency/whisper-large-v3-hu` | ~11.26 | Beats MS Teams transcription |
| `jonatasgrosman/wav2vec2-large-xlsr-53-hungarian` | — | wav2vec2 baseline, also useful as feature extractor |
| `nvidia/parakeet-tdt-0.6b-v3` | — | Lists Hungarian among 25 languages, ~19s for 1h on M4 Pro |

**Recommended:** `benmajor27/whisper-large-v3-hu_full` via **faster-whisper** (CTranslate2) with `int8_float16` quantization for streaming.

### Stage 2 — Speech Emotion Recognition (SER)

| Model | Labels | Notes |
|---|---|---|
| `ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition` | 8 (angry, calm, disgust, fearful, happy, neutral, sad, surprised) | XLS-R-53 backbone is multilingual — best transfer to Hungarian |
| `firdhokk/speech-emotion-recognition-with-openai-whisper-large-v3` | 7 | Whisper backbone, shares VRAM with Stage 1 |
| `Dpngtm/wav2vec2-emotion-recognition` | 7 | ~80% val accuracy, lightweight |
| `speechbrain/emotion-recognition-wav2vec2-IEMOCAP` | 4 (angry, happy, sad, neutral) | SpeechBrain ecosystem |

**Recommended:** `ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition`. The XLS-R-53 backbone was pretrained on 53 languages including Hungarian phonemes; only the SER head was English-fine-tuned. Validate on Hungarian samples, fine-tune the head if needed.

### Stage 3 — Vocal Biomarkers (Sonde-like layer)

No Hugging Face equivalent. Build with:
- **openSMILE** with **eGeMAPS** feature set — clinically validated, 88 features per window
- **parselmouth** (Praat in Python) — pitch contours, jitter, shimmer, HNR
- Extract per 1.5–3 s window → feed as feature vector to fusion stage

This is the layer worth investing in for the medical angle. eGeMAPS is the de facto standard for clinical speech research.

### Stage 4 — Fusion & Intent

Two options:

- **Option A — Lightweight (recommended for PoC):** Send `{transcript, emotion_label, emotion_confidence, biomarker_summary}` to an LLM with a prompt: *"Classify intent for Hungarian healthcare triage: routine / concerned / urgent / crisis. Justify."*  Use Claude Sonnet via API, or self-host Qwen2.5-Omni-7B int4 (~6 GB VRAM).
- **Option B — Custom classifier:** Train a small MLP on labeled call data. More work, lower latency, no external API. Phase 2.

---

## 5. VRAM budget (single A10 24 GB)

| Component | VRAM |
|---|---|
| faster-whisper large-v3-hu (int8_float16) | ~2.0 GB |
| wav2vec2 XLS-R emotion (fp16) | ~1.3 GB |
| openSMILE | 0 (CPU) |
| Silero VAD | ~0.1 GB |
| Qwen2.5-Omni-7B int4 (optional, on-prem fusion) | ~6.0 GB |
| **Total with on-prem LLM** | **~9.5 GB** |
| **Total with external LLM API** | **~3.5 GB** |

Comfortable headroom for batching and CUDA workspace.

---

## 6. Latency budget

| Stage | Target |
|---|---|
| VAD detection of speech-end | ~100 ms |
| Partial transcript (first token) | ~300–500 ms |
| Final transcript after pause | ~400–700 ms |
| Emotion classification (parallel with ASR) | ~300–500 ms |
| Biomarker extraction (parallel) | ~150 ms (CPU) |
| Fusion → intent (LLM call) | ~300–800 ms |
| **End-to-end (speech-end → intent emitted)** | **~1.0–1.8 s** |

---

## 7. Streaming behavior

- **VAD** runs continuously on 30 ms frames; emits utterance boundaries.
- **faster-whisper** runs in streaming mode (use `whisper_streaming` or `WhisperLive` wrapper) — partial transcripts every ~300 ms.
- **SER + biomarkers** run on 1.5–3 s sliding windows with 50% overlap. This produces a smooth mood curve rather than per-utterance jumps — important for detecting **escalation** (calm → anxious → desperate), which is the healthcare-relevant signal.
- **Fusion** triggers on utterance-end (VAD silence > 500 ms) with the full utterance transcript + averaged emotion vector + biomarker summary for that window.

---

## 8. Tech stack

| Layer | Choice |
|---|---|
| API framework | FastAPI + uvicorn |
| Streaming protocol | WebSocket (binary frames in, JSON out) |
| Audio I/O | `soundfile`, `sounddevice`, or WebRTC via `aiortc` |
| ML runtime | PyTorch 2.x + CUDA 12 |
| ASR runtime | `faster-whisper` (CTranslate2 backend) |
| Emotion runtime | `transformers` + `torch.compile` |
| Biomarkers | `opensmile-python`, `praat-parselmouth` |
| VAD | `silero-vad` |
| Concurrency | `asyncio`, CUDA streams via `torch.cuda.Stream()` |
| Containerization | Docker, multi-stage build (CUDA base) |
| Orchestration | Kubernetes (existing SMP cluster) |
| Secrets | Infisical (existing setup) |
| Observability | OpenTelemetry → Grafana/Loki |

---

## 9. Orchestration framework options

Three viable approaches, increasing in abstraction:

1. **Bare FastAPI + asyncio.** Maximum control, minimum dependencies. Recommended for the PoC.
2. **FunASR** (SenseVoice's parent framework) — supports VAD + ASR + SER + punctuation as a chained pipeline natively. Good if SenseVoice ends up being the chosen ASR.
3. **Pipecat** or **LiveKit Agents** — real-time voice-agent frameworks built around exactly this fan-out pattern. K8s-friendly, but adds a heavy dependency.

For phase 1, go bare FastAPI to fully understand the flow. Move to Pipecat in phase 2 if you need multi-agent / barge-in / TTS-back-to-user features.

---

## 10. Project structure

```
streaming-asr-emotion/
├── README.md
├── pyproject.toml
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── ingress.yaml
├── src/
│   ├── main.py                  # FastAPI app, WebSocket endpoint
│   ├── pipeline/
│   │   ├── vad.py               # Silero VAD wrapper
│   │   ├── asr.py               # faster-whisper streaming
│   │   ├── emotion.py           # wav2vec2 SER
│   │   ├── biomarkers.py        # openSMILE + parselmouth
│   │   └── fusion.py            # LLM intent classification
│   ├── orchestrator.py          # asyncio.gather fan-out
│   ├── schemas.py               # Pydantic models for output
│   └── config.py                # Infisical-backed settings
├── tests/
│   ├── fixtures/                # Hungarian audio samples
│   ├── test_asr.py
│   ├── test_emotion.py
│   └── test_e2e.py
└── notebooks/
    └── validate_hungarian_ser.ipynb
```

---

## 11. Output schema

```json
{
  "session_id": "uuid",
  "timestamp_ms": 1234567890,
  "type": "partial | final | intent",
  "transcript": {
    "text": "Nem érzem jól magam, kérem segítsen.",
    "language": "hu",
    "confidence": 0.94
  },
  "emotion": {
    "label": "anxious",
    "scores": {
      "angry": 0.05, "anxious": 0.71, "sad": 0.12,
      "neutral": 0.08, "happy": 0.01, "fearful": 0.03
    },
    "window_ms": [1200, 4200]
  },
  "biomarkers": {
    "pitch_mean_hz": 178.4,
    "pitch_std_hz": 42.1,
    "jitter_local": 0.024,
    "shimmer_local": 0.087,
    "hnr_db": 12.3,
    "energy_rms": 0.18
  },
  "intent": {
    "label": "concerned",
    "urgency": 3,
    "reasoning": "Patient reports feeling unwell with anxious vocal markers.",
    "escalate": false
  }
}
```

---

## 12. Build phases

**Phase 1 — Spike (1–2 weeks)**
- Bare FastAPI + WebSocket echo
- Integrate Silero VAD + faster-whisper, prove streaming transcript on Hungarian audio
- Measure baseline latency

**Phase 2 — Add emotion (1 week)**
- Wire in ehcalabres wav2vec2 SER
- Run in parallel CUDA stream, validate latency stays under budget
- Test on 20–50 Hungarian samples spanning emotions; document accuracy gap vs. English

**Phase 3 — Add biomarkers (3–5 days)**
- openSMILE + parselmouth feature extraction
- Sliding window with overlap
- Output to schema

**Phase 4 — Fusion & intent (1 week)**
- LLM-based fusion (Claude API or Qwen2.5-Omni)
- Define healthcare intent taxonomy with clinical input
- Evaluate against labeled scenarios

**Phase 5 — Production hardening (2 weeks)**
- Dockerize, K8s manifests, Infisical wiring
- Auth (mTLS or JWT)
- Audit logging (NIS2 requirement)
- Load test: target 10 concurrent sessions on one A10
- Observability dashboards

**Phase 6 — Hungarian SER fine-tuning (research track, parallel)**
- Collect labeled Hungarian emotional speech
- Fine-tune SER head on XLS-R-53 backbone
- Compare against zero-shot baseline from Phase 2

---

## 13. NIS2 / data privacy notes

- All processing on-prem in SMP K8s cluster; no audio leaves the boundary.
- If using Claude API for fusion: send **text + emotion label only**, never raw audio or PII transcripts. Mask PII (names, IDs, addresses) before LLM call.
- Audit log every inference: session_id, timestamp, input duration, output labels — not the audio itself.
- Secrets (model paths, LLM API keys) via Infisical.
- Consider on-prem Qwen2.5-Omni for fusion to eliminate external API dependency entirely.

---

## 14. Open questions for the clinical / BA team

1. What intent taxonomy fits the actual triage workflow? (routine / concerned / urgent / crisis is a placeholder)
2. What's the escalation trigger — single utterance over threshold, or sustained emotional trajectory?
3. Do we need speaker diarization (multi-party calls)? SenseVoice added this in May 2026; faster-whisper supports it via pyannote.
4. Is real-time required, or is near-real-time batch (per call segment) acceptable? Affects architecture significantly.
5. What's the labeled Hungarian emotional data situation for fine-tuning?

---

## 15. First commands for Claude Code

```bash
# Bootstrap
mkdir streaming-asr-emotion && cd streaming-asr-emotion
uv init  # or poetry init
uv add fastapi uvicorn websockets faster-whisper transformers torch torchaudio \
       silero-vad opensmili-python praat-parselmouth pydantic httpx

# Pull models locally (one-time)
huggingface-cli download benmajor27/whisper-large-v3-hu_full
huggingface-cli download ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition
huggingface-cli download snakers4/silero-vad

# Skeleton
mkdir -p src/pipeline tests/fixtures k8s docker
touch src/main.py src/orchestrator.py src/schemas.py src/config.py
touch src/pipeline/{vad,asr,emotion,biomarkers,fusion}.py
```

Start with `src/pipeline/asr.py` + `src/main.py` minimal WebSocket loop. Validate the streaming partial transcripts on a Hungarian audio file before adding any other stage.