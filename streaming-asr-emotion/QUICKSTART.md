# Quick Start Guide

Get Elcoria running in 5 minutes.

## 1. Install Dependencies

```bash
cd streaming-asr-emotion
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

## 2. Download Models (Internet Required, ~5-15 min)

```bash
python scripts/download_models.py
```

This downloads ~4-5 GB of models. After this, you can work offline.

## 3. Start Ollama (Optional, for Questions)

Open a new terminal:
```bash
# Install Ollama first from https://ollama.ai
ollama pull qwen2.5:7b
ollama serve
```

## 4. Run the PoC

```bash
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Server output should show:
```
INFO:     Application startup complete
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## 5. Open Browser

Go to: **http://localhost:8000**

## 6. Test It

1. **Select Config**: `lightweight` (CPU) or `gpu` (requires NVIDIA GPU)
2. **Click "Start Recording"**
3. **Speak in Hungarian**, e.g.:
   - "Nem érzem jól magam, fejfájásom van"
   - "Már hárompedig érzek így"
4. Watch:
   - **Left panel**: Transcript appears in real-time + patient mood
   - **Right panel**: Clarification questions stream in

Or **upload an audio file** (WAV, MP3).

## 7. Try Both Configs

- **lightweight**: CPU-friendly, instant feedback, rule-based questions
- **gpu**: Requires NVIDIA GPU, faster ASR, AI-powered questions via Ollama

## What's Happening

```
Your Voice
  ↓
MediaRecorder (browser) → WebSocket
  ↓
FastAPI backend
  ├─ Voice Activity Detection (VAD)
  ├─ Speech Recognition (ASR)
  └─ Emotion Analysis
  ├─ Question Generation (Ollama)
  ↓
WebSocket Messages
  ↓
Browser UI
  ├─ Partial transcript (gray) → Final transcript (black)
  ├─ Animated mood bars
  └─ Streaming questions
```

## Troubleshooting

### Port 8000 already in use
```bash
python -m uvicorn src.main:app --port 8001
# Then visit http://localhost:8001
```

### Microphone not working
- Allow microphone permission when browser prompts
- Try Chrome/Firefox (Safari may have restrictions)
- Check OS microphone settings

### Ollama not found
- Models still work! System falls back to template-based questions
- If you want AI questions, install Ollama and run `ollama serve`

### Models not downloaded
```bash
python scripts/download_models.py
# Wait for "✓ Model download complete!"
```

## Next Steps

- Read [README.md](README.md) for architecture details
- Try custom configs in `configs/`
- Upload test audio files (WAV, MP3)
- Check logs: `uvicorn` output shows pipeline execution

## Support

For issues:
1. Check README.md troubleshooting section
2. Verify models downloaded: `ls models/` should show subdirs
3. Ensure Python 3.10+: `python --version`
