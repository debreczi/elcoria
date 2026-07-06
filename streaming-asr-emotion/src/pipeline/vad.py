import numpy as np
from typing import Dict, Any, List
from collections import deque
import logging
from .base import BaseVAD
from ..schemas import VADResult

logger = logging.getLogger(__name__)


class EnergyVAD(BaseVAD):
    """Energy-based Voice Activity Detection (CPU-friendly fallback)."""

    def __init__(self):
        self.threshold_db = -40
        self.min_silence_ms = 600
        self.frame_ms = 30
        self.sample_rate = 16000

        # State machine
        self.is_speech = False
        self.silence_buffer = deque(maxlen=int(self.min_silence_ms / self.frame_ms))

    def load(self, config: Dict[str, Any]) -> None:
        self.threshold_db = config.get("threshold_db", -40)
        self.min_silence_ms = config.get("min_silence_ms", 600)
        self.frame_ms = config.get("frame_ms", 30)
        self.silence_buffer = deque(maxlen=int(self.min_silence_ms / self.frame_ms))
        logger.info(f"EnergyVAD loaded: threshold={self.threshold_db}dB, min_silence={self.min_silence_ms}ms")

    async def process(self, audio_chunk: np.ndarray, sample_rate: int) -> List[VADResult]:
        """Detect speech using RMS energy."""
        self.sample_rate = sample_rate
        results = []

        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio_chunk**2))
        db = 20 * np.log10(rms + 1e-10)

        # Detect speech
        is_speech_now = db > self.threshold_db

        # Track silence
        if not is_speech_now:
            self.silence_buffer.append(True)
        else:
            self.silence_buffer.clear()

        # State transitions
        if is_speech_now and not self.is_speech:
            self.is_speech = True
            results.append(VADResult(event="speech_start", confidence=0.9, frame_ms=self.frame_ms))
        elif not is_speech_now and self.is_speech and len(self.silence_buffer) == self.silence_buffer.maxlen:
            self.is_speech = False
            results.append(VADResult(event="speech_end", confidence=0.9, frame_ms=self.frame_ms))
        elif not is_speech_now:
            results.append(VADResult(event="silence", confidence=0.5, frame_ms=self.frame_ms))

        return results

    async def shutdown(self) -> None:
        pass


class SileroVAD(BaseVAD):
    """Silero VAD - Neural network-based voice activity detection."""

    def __init__(self):
        self.model = None
        self.get_speech_timestamps = None
        self.threshold = 0.5
        self.min_silence_duration_ms = 500
        self.speech_pad_ms = 100
        self.frame_ms = 30
        self.sample_rate = 16000
        self.device = "cpu"
        self.is_speech = False
        self.speech_buffer = []

    def load(self, config: Dict[str, Any]) -> None:
        try:
            import torch

            self.device = config.get("device", "cpu")
            self.threshold = config.get("threshold", 0.5)
            self.min_silence_duration_ms = config.get("min_silence_duration_ms", 500)
            self.speech_pad_ms = config.get("speech_pad_ms", 100)
            self.frame_ms = config.get("frame_ms", 30)

            # Load Silero VAD
            torch.hub.set_dir(config.get("model_path", "./models/silero-vad"))
            self.model = torch.hub.load("snakers4/silero-vad", "silero_vad", source="local")
            self.model.to(self.device)
            self.model.eval()

            logger.info(f"SileroVAD loaded on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load SileroVAD: {e}")
            raise

    async def process(self, audio_chunk: np.ndarray, sample_rate: int) -> List[VADResult]:
        """Detect speech using Silero VAD."""
        self.sample_rate = sample_rate
        results = []

        if self.model is None:
            return results

        try:
            import torch

            # Convert to tensor and process
            audio_tensor = torch.tensor(audio_chunk, dtype=torch.float32).to(self.device)
            confidence = self.model(audio_tensor, sample_rate).item()

            is_speech_now = confidence > self.threshold

            # State transitions
            if is_speech_now and not self.is_speech:
                self.is_speech = True
                results.append(VADResult(event="speech_start", confidence=float(confidence), frame_ms=self.frame_ms))
            elif not is_speech_now and self.is_speech:
                self.is_speech = False
                results.append(VADResult(event="speech_end", confidence=float(confidence), frame_ms=self.frame_ms))

            return results
        except Exception as e:
            logger.error(f"SileroVAD processing error: {e}")
            return []

    async def shutdown(self) -> None:
        if self.model is not None:
            try:
                import torch
                self.model.cpu()
                del self.model
            except:
                pass
