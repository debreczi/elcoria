# Elcoria Healthcare Conversation Analysis PoC

Real-time audio transcription, emotion analysis, and AI-generated clarification questions for doctor-patient conversations. Fully local, offline-capable, with swappable model stacks.

## Features

✅ **Real-time Transcription** — Hungarian speech-to-text with grammar correction  
✅ **Patient Mood Analysis** — Emotion detection from audio or text  
✅ **AI-Powered Questions** — Automatic clarification questions for doctors  
✅ **Offline-First** — No internet required after initial model download  
✅ **Modular Architecture** — Swap ASR, emotion, and LLM models via YAML config  
✅ **Two-Panel UI** — Live transcript + animated mood + streaming questions  
✅ **Multiple Input Sources** — Microphone (browser) or pre-recorded audio files  

## Prerequisites

- Python 3.10+
- 8+ GB RAM (16 GB recommended for GPU stack)
- NVIDIA GPU (optional, for `gpu.yaml` config)
- Ollama (for question generation with `OllamaFusion`)

### Optional: Ollama Setup

For AI-powered questions, install [Ollama](https://ollama.ai) and pull a model:

```bash
ollama pull qwen2.5:7b
# or
ollama pull llama3:8b
```

Keep Ollama running: `ollama serve`

## Quick Start

### 1. Setup

```bash
cd streaming-asr-emotion

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Download Models (Internet Required, One-Time)

```bash
python scripts/download_models.py
```

This downloads:
- Whisper (ASR) models
- wav2vec2 (emotion) models
- Silero VAD model

After completion, you can work offline.

### 3. Run the PoC

```bash
# Optional: Start Ollama in another terminal
ollama serve

# Start the server
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Open browser: **http://localhost:8000**

### 4. Test

1. **Select config**: `lightweight` (CPU) or `gpu` (requires NVIDIA GPU)
2. **Click "Start Recording"** and speak in Hungarian
3. Watch transcript appear in Panel 1, mood update in real-time, and questions stream in Panel 2

Or **upload an audio file** (WAV, MP3, OGG supported).

## Configuration

### `configs/lightweight.yaml`
- **VAD**: EnergyVAD (fast, CPU)
- **ASR**: HuggingFace Whisper small (CPU-friendly)
- **Emotion**: Text-based sentiment (no audio processing)
- **Questions**: Template-based (instant, no LLM)
- **Use case**: Development, testing, low-resource machines

### `configs/gpu.yaml`
- **VAD**: Silero VAD (GPU-accelerated)
- **ASR**: faster-whisper large-v3-hu (GPU, CTranslate2)
- **Emotion**: wav2vec2 XLS-R (GPU-based audio emotion)
- **Questions**: Ollama with qwen2.5:7b or llama3:8b
- **Use case**: Production, best accuracy, requires GPU

### Custom Config

Create `configs/my_config.yaml`:

```yaml
name: my_config
description: "Custom stack"
models_dir: "./models"

vad:
  implementation: EnergyVAD
  params:
    threshold_db: -40

asr:
  implementation: HuggingFaceWhisperASR
  params:
    model_path: "./models/whisper-small-hu"
    device: cpu
    language: hu

emotion:
  implementation: TextSentimentEmotion
  params:
    model_path: "./models/xlm-roberta-sentiment"
    device: cpu

fusion:
  implementation: TemplateFusion
  params:
    system_prompt_file: "./prompts/doctor_questions_hu.txt"

streaming:
  chunk_ms: 100
  vad_buffer_ms: 3000
  emotion_interval_ms: 2000
```

## Architecture

### Backend (FastAPI + WebSocket)

```
┌─────────────────────────────────────────┐
│         Browser (Web Audio API)         │
│   ├─ Microphone capture (MediaRecorder) │
│   └─ Audio file upload                  │
└──────────────┬──────────────────────────┘
               │ WebSocket binary frames (PCM)
               ▼
┌─────────────────────────────────────────┐
│      FastAPI WebSocket Handler          │
│  (src/main.py)                          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   PipelineOrchestrator                  │
│  (async coordination of 4 stages)       │
│                                         │
│  ┌─ VAD (EnergyVAD / SileroVAD)         │
│  ├─ ASR (FasterWhisper / HFWhisper)     │
│  ├─ Emotion (Wav2Vec / TextSent)        │
│  └─ Fusion (Ollama / Template)          │
└─────────────────────────────────────────┘
```

### Data Flow

```
Audio Chunk (16kHz, mono, float32)
    ↓
VAD → [speech_start | silence | speech_end]
    ↓ (on speech_start)
Accumulate buffer → every 500ms:
    ├─ ASR → partial transcript (async)
    └─ Emotion → mood scores (async)
    ↓ (on speech_end)
Final ASR + Emotion → send final_transcript message
    ↓
Fusion (OllamaFusion / TemplateFusion)
    ├─ Stream question_chunk messages
    └─ Send question_final message
```

### WebSocket Messages

**Client → Server (control)**
```json
{"type": "control", "event": "start_session", "config_name": "lightweight"}
```

**Server → Client (streaming results)**
```json
{"type": "partial_transcript", "text": "Nem érz...", "is_final": false}
{"type": "final_transcript", "text": "Nem érzem jól magam.", "utterance_id": "utt-001"}
{"type": "emotion_update", "label": "anxious", "scores": {...}}
{"type": "question_chunk", "delta": "Mióta", "utterance_id": "utt-001"}
{"type": "question_final", "utterance_id": "utt-001"}
```

## Project Structure

```
streaming-asr-emotion/
├── src/
│   ├── main.py              # FastAPI app, WebSocket handler
│   ├── config.py            # YAML config loader
│   ├── schemas.py           # Pydantic models
│   ├── orchestrator.py      # Pipeline orchestration
│   └── pipeline/
│       ├── base.py          # Abstract base classes
│       ├── vad.py           # Voice Activity Detection
│       ├── asr.py           # Speech Recognition
│       ├── emotion.py       # Emotion/Sentiment Analysis
│       └── fusion.py        # Question Generation
├── frontend/
│   └── index.html           # Single-page UI (two-panel layout)
├── configs/
│   ├── lightweight.yaml     # CPU-friendly stack
│   └── gpu.yaml             # GPU-accelerated stack
├── prompts/
│   └── doctor_questions_hu.txt  # System prompt for question generation
├── scripts/
│   └── download_models.py   # One-time model downloader
├── models/                  # Model cache (downloaded on demand)
├── requirements.txt
├── .env
└── README.md (this file)
```

## Implemented Stages

### VAD (Voice Activity Detection)
- **EnergyVAD**: RMS-based, instant, CPU-only
- **SileroVAD**: Neural network, pre-trained on 40+ languages, GPU

### ASR (Speech Recognition)
- **FasterWhisperASR**: CTranslate2-based Whisper, supports int8 quantization
- **HuggingFaceWhisperASR**: Transformer-based, broader model selection

### Emotion
- **Wav2VecEmotionSER**: Audio-based emotion recognition (8 classes: angry, anxious, sad, neutral, happy, fearful, disgusted, surprised)
- **TextSentimentEmotion**: Multilingual sentiment analysis (positive/negative/neutral → happy/sad/neutral)

### Fusion (Questions)
- **OllamaFusion**: Streams questions from local Ollama LLM with HTTP streaming
- **TemplateFusion**: Rule-based fallback, no LLM required, instant

## Limitations & Notes

⚠️ **Emotion Accuracy**: wav2vec2 XLS-R was fine-tuned on English. Performance on Hungarian is ~60-70%. Label outputs as "indicative."

⚠️ **Ollama Required for GPU Config**: If using `gpu.yaml`, Ollama must be running and the model must be pulled beforehand. Falls back to TemplateFusion if Ollama unavailable.

⚠️ **Offline Mode**: After `python scripts/download_models.py`, set `TRANSFORMERS_OFFLINE=1` to prevent accidental external API calls.

⚠️ **Browser Audio**: MediaRecorder produces WebM/Opus. Backend decodes via PyAV. Ensure PyAV installed (`pip install av`).

## Troubleshooting

### WebSocket Connection Error
- Ensure server is running: `uvicorn src.main:app`
- Check firewall (port 8000)
- Browser console should show WebSocket connected message

### "Model not found" Error
- Run `python scripts/download_models.py`
- Ensure models are in `./models/` directory
- Check config `model_path` values

### Ollama Connection Error
- Start Ollama: `ollama serve`
- Check http://localhost:11434 is accessible
- If unavailable, system falls back to TemplateFusion

### Microphone Permission Denied
- Allow microphone access when browser prompts
- Check OS microphone permissions
- Try Firefox or Chrome (Safari has additional restrictions)

### Audio File Upload Fails
- Ensure file is WAV, MP3, OGG, FLAC, etc.
- Check file size (>50MB may be slow)
- Try re-encoding to 16-bit 16kHz mono WAV

## Performance

### Lightweight Config (CPU)
- **Latency**: ~5-10s per utterance
- **CPU usage**: 2-4 cores fully loaded
- **Memory**: ~2-3 GB

### GPU Config
- **Latency**: <2s per utterance (target from spec)
- **GPU**: A10 24GB or RTX 3090/4090
- **Memory**: ~9-10 GB VRAM

## Future Enhancements

- [ ] Speaker diarization (who is speaking: doctor or patient)
- [ ] Clinical entity extraction (symptoms, medications, conditions)
- [ ] Multi-language support (EN, FR, DE, ES)
- [ ] Fine-tuned emotion model for Hungarian
- [ ] NIS2 compliance (audit logging, PII masking)
- [ ] Kubernetes deployment manifests
- [ ] Docker image

## Development

### Running Tests

```bash
pytest -v
```

### Adding a New Model

1. Create implementation class inheriting from `Base*` in `src/pipeline/*.py`
2. Add `model_path` or `model_name` to config params
3. Reference in YAML config

Example (new ASR):
```python
# src/pipeline/asr.py
class MyNewASRModel(BaseASR):
    def load(self, config):
        ...
    async def transcribe(self, audio, sample_rate):
        ...
```

Update `src/orchestrator.py` implementations dict:
```python
implementations = {
    "MyNewASRModel": MyNewASRModel,
    ...
}
```

Reference in config:
```yaml
asr:
  implementation: MyNewASRModel
  params:
    model_path: "./models/my_model"
```

## License

Proprietary — SMP Solutions Zrt

## Support

For issues, questions, or feature requests, contact the Elcoria team.
