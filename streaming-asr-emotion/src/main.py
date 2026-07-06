import os
import asyncio
import logging
import uuid
import json
from pathlib import Path
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import load_config, get_config_manager
from .orchestrator import PipelineOrchestrator
from .pipeline.asr import FasterWhisperASR, HuggingFaceWhisperASR
from .pipeline.emotion import Wav2VecEmotionSER, TextSentimentEmotion, AcousticBiomarkersEmotion
from .pipeline.fusion import OllamaFusion, TemplateFusion

# Set offline mode
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

# Work around system-wide cuDNN conflicting with torch's bundled cuDNN on Windows.
try:
    import torch as _torch
    if _torch.cuda.is_available():
        _torch.backends.cudnn.enabled = False
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# UI directory served at `/`. Aligned with elcoria-ui/INSTRUCTIONS.md §4 (v1 contract).
FRONTEND_DIR_NAME = "frontend-v2"
DEFAULT_CONFIG = "lightweight-cpu"

# Global state
active_sessions = {}

# Cache of loaded ASR/Emotion/Fusion stacks keyed by config name. VAD is per-session.
_shared_stacks: dict = {}

_ASR_IMPLS = {"FasterWhisperASR": FasterWhisperASR, "HuggingFaceWhisperASR": HuggingFaceWhisperASR}
_EMO_IMPLS = {
    "Wav2VecEmotionSER": Wav2VecEmotionSER,
    "TextSentimentEmotion": TextSentimentEmotion,
    "AcousticBiomarkersEmotion": AcousticBiomarkersEmotion,
}
_FUSION_IMPLS = {"OllamaFusion": OllamaFusion, "TemplateFusion": TemplateFusion}


def _build_shared_stack(config) -> dict:
    """Load ASR + Emotion + Fusion once for a given config (these are model-heavy and stateless)."""
    asr_cls = _ASR_IMPLS[config.asr.implementation]
    emo_cls = _EMO_IMPLS[config.emotion.implementation]
    fus_cls = _FUSION_IMPLS[config.fusion.implementation]
    asr = asr_cls(); asr.load(config.asr.params)
    emo = emo_cls(); emo.load(config.emotion.params)
    fus = fus_cls(); fus.load(config.fusion.params)
    return {"asr": asr, "emotion": emo, "fusion": fus}


def _resolve_config_name(requested: str | None) -> str:
    """Map a UI-supplied config name to a server-side config that actually loaded."""
    if requested and requested in _shared_stacks:
        return requested
    # The UI default is "lightweight-cpu" but the server may only have "lightweight" / "turbo".
    aliases = {
        "lightweight-cpu": ["lightweight", "turbo"],
        "lightweight": ["lightweight-cpu", "turbo"],
    }
    for candidate in aliases.get(requested or "", []):
        if candidate in _shared_stacks:
            return candidate
    # Fallback: first loaded stack.
    if _shared_stacks:
        return next(iter(_shared_stacks.keys()))
    raise RuntimeError("No preloaded config stacks available")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting Elcoria Healthcare PoC")

    # Check Ollama availability
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get("http://localhost:11434/api/tags")
            logger.info("Ollama is available")
    except Exception as e:
        logger.warning(f"Ollama not available (this is OK for TemplateFusion fallback): {e}")

    # Pre-load model stacks for every available config so the first WS session is fast.
    try:
        manager = get_config_manager()
        for name in manager.list_configs():
            try:
                logger.info(f"Preloading stack for config: {name}")
                cfg = manager.load_config(name)
                _shared_stacks[name] = _build_shared_stack(cfg)
                logger.info(f"Preloaded stack for config: {name}")
            except Exception as e:
                logger.error(f"Failed to preload {name}: {e}")
    except Exception as e:
        logger.error(f"Could not enumerate configs for preload: {e}")

    yield

    # Cleanup
    logger.info("Shutting down, closing all sessions...")
    for session in active_sessions.values():
        await session["orchestrator"].shutdown()
    active_sessions.clear()
    for stack in _shared_stacks.values():
        for k in ("asr", "emotion", "fusion"):
            try:
                await stack[k].shutdown()
            except Exception:
                pass
    _shared_stacks.clear()


app = FastAPI(
    title="Elcoria Healthcare PoC",
    description="Real-time healthcare conversation analysis (v1 contract)",
    version="0.2.0",
    lifespan=lifespan,
)


# ─── API routes ───────────────────────────────────────────────────────────────


@app.get("/configs")
async def list_configs():
    """Configs whose model stacks preloaded successfully at startup."""
    try:
        manager = get_config_manager()
        names = manager.list_configs(available_only=False)
        ready = [n for n in names if n in _shared_stacks]
        return {"configs": ready}
    except Exception as e:
        logger.error(f"Error listing configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/v1/stream")
async def v1_stream(websocket: WebSocket):
    """v1 WebSocket contract per elcoria-ui/INSTRUCTIONS.md §4.

    Query params:  session_id=<uuid>&config=<name>
    Client → server:
      - binary frames: raw Float32 LE PCM, 16 kHz mono, ~250 ms each
      - JSON  {"type":"session.end"}   optional graceful end
    Server → client (all JSON):
      session.start, transcript.partial, transcript.final, intent.update, error
    """
    qp = websocket.query_params
    session_id = qp.get("session_id") or str(uuid.uuid4())
    requested_config = qp.get("config") or DEFAULT_CONFIG

    await websocket.accept()
    logger.info(f"v1/stream connected: session={session_id} requested_config={requested_config}")

    orchestrator = None
    chunk_counter = [0]
    chunk_samples_total = [0]

    try:
        try:
            config_name = _resolve_config_name(requested_config)
        except Exception as e:
            await websocket.send_json({
                "type": "error",
                "code": "CONFIG_UNAVAILABLE",
                "message": f"No usable config (requested {requested_config!r}): {e}",
            })
            await websocket.close()
            return

        if config_name != requested_config:
            logger.info(f"Config alias: requested={requested_config!r} → using {config_name!r}")

        try:
            config = load_config(config_name)
        except Exception as e:
            await websocket.send_json({
                "type": "error",
                "code": "CONFIG_LOAD_FAILED",
                "message": str(e),
            })
            await websocket.close()
            return

        async def send_message(msg):
            try:
                await websocket.send_json(msg)
                mtype = msg.get("type", "?")
                if mtype in ("transcript.partial", "transcript.final"):
                    uid = msg.get("uid")
                    if mtype == "transcript.partial":
                        logger.info(f"WS sent {mtype} uid={uid} text={msg.get('text', '')!r}")
                    else:
                        txt = msg.get("transcript", {}).get("text", "")
                        logger.info(f"WS sent {mtype} uid={uid} text={txt!r}")
            except Exception as e:
                logger.error(f"Error sending message: {e}")

        orchestrator = PipelineOrchestrator(
            config=config,
            session_id=session_id,
            send_message=send_message,
            shared=_shared_stacks.get(config_name),
        )

        active_sessions[session_id] = {
            "orchestrator": orchestrator,
            "config": config,
        }
        logger.info(f"Session {session_id} ready with {config_name}")

        # The v1 contract: tell the client the session is live.
        await websocket.send_json({
            "type": "session.start",
            "session_id": session_id,
            "ts_ms": 0,
        })

        # Main receive loop
        while True:
            data = await websocket.receive()

            if "bytes" in data:
                try:
                    audio_np = _decode_pcm_f32(data["bytes"])
                    if audio_np is not None and audio_np.size > 0:
                        chunk_counter[0] += 1
                        chunk_samples_total[0] += int(audio_np.size)
                        if chunk_counter[0] == 1 or chunk_counter[0] % 20 == 0:
                            rms = float(np.sqrt(np.mean(audio_np ** 2))) if audio_np.size else 0.0
                            logger.info(
                                f"audio chunks={chunk_counter[0]} samples_total={chunk_samples_total[0]} "
                                f"this_chunk_samples={audio_np.size} rms={rms:.5f}"
                            )
                        await orchestrator.process_chunk(audio_np, 16000)
                except Exception as e:
                    logger.error(f"Error processing audio: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "code": "AUDIO_PROCESSING_ERROR",
                        "message": str(e),
                    })
            elif "text" in data:
                try:
                    ctrl = json.loads(data["text"])
                    if ctrl.get("type") == "session.end":
                        logger.info(f"Session {session_id} ending (client requested)")
                        break
                except Exception as e:
                    logger.warning(f"Could not parse text frame: {e}")

    except Exception as e:
        logger.error(f"v1/stream error: {e}")
    finally:
        if orchestrator:
            await orchestrator.shutdown()
        if session_id in active_sessions:
            del active_sessions[session_id]
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"v1/stream disconnected: {session_id}")


@app.post("/upload/{session_id}")
async def upload_file(session_id: str, file: UploadFile = File(...)):
    """Upload an audio file; replay it through the orchestrator for an open session."""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        contents = await file.read()

        audio_np = await _decode_audio_file(contents, file.filename or "audio")
        if audio_np is None:
            raise ValueError("Could not decode audio file")

        orchestrator = active_sessions[session_id]["orchestrator"]
        config = active_sessions[session_id]["config"]

        # Stream the file through the orchestrator at the configured cadence.
        chunk_size = int(16000 * config.streaming.chunk_ms / 1000)
        delay_per_chunk = config.streaming.chunk_ms / 1000.0

        for i in range(0, len(audio_np), chunk_size):
            chunk = audio_np[i: i + chunk_size]
            await orchestrator.process_chunk(chunk, 16000)
            await asyncio.sleep(delay_per_chunk)

        return {"status": "ok", "duration_ms": int(len(audio_np) / 16000 * 1000)}
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ─── Audio decoding helpers ───────────────────────────────────────────────────


def _decode_pcm_f32(audio_bytes: bytes) -> np.ndarray | None:
    """Decode raw Float32 LE PCM at 16 kHz mono (matches frontend-v2/mic-capture.js output)."""
    if not audio_bytes:
        return None
    try:
        return np.frombuffer(audio_bytes, dtype=np.float32).copy()
    except Exception as e:
        logger.error(f"PCM decode error: {e}")
        return None


async def _decode_audio_file(audio_bytes: bytes, filename: str) -> np.ndarray | None:
    """Decode an uploaded audio file (WAV / FLAC / OGG / MP3 / ...)."""
    try:
        import soundfile as sf
        import io

        try:
            audio_np, sr = sf.read(io.BytesIO(audio_bytes))
            if sr != 16000:
                import librosa
                audio_np = librosa.resample(audio_np, orig_sr=sr, target_sr=16000)
            return audio_np.astype(np.float32)
        except Exception:
            pass

        import av
        container = av.open(io.BytesIO(audio_bytes))
        stream = container.streams.audio[0]
        audio_frames = []
        for frame in container.decode(stream):
            audio_frames.append(frame.to_ndarray())
        if audio_frames:
            audio_np = np.concatenate(audio_frames, axis=-1)
            if audio_np.ndim > 1:
                audio_np = np.mean(audio_np, axis=0)
            if stream.sample_rate != 16000:
                import librosa
                audio_np = librosa.resample(audio_np, orig_sr=stream.sample_rate, target_sr=16000)
            return audio_np.astype(np.float32)
        return None
    except Exception as e:
        logger.error(f"Audio file decoding error: {e}")
        return None


# ─── Static frontend (registered LAST so it doesn't shadow the API routes) ────

_frontend_dir = Path(__file__).parent.parent / FRONTEND_DIR_NAME
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
    logger.info(f"Serving UI from {_frontend_dir}")
else:
    logger.warning(f"Frontend directory not found: {_frontend_dir}")


if __name__ == "__main__":
    import uvicorn

    config_dir = Path(__file__).parent.parent / "configs"
    get_config_manager(str(config_dir))

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
