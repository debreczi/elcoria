import numpy as np
from typing import Dict, Any, AsyncIterator
import asyncio
import logging
from .base import BaseASR
from ..schemas import ASRResult

logger = logging.getLogger(__name__)


class FasterWhisperASR(BaseASR):
    """Faster Whisper implementation using CTranslate2."""

    def __init__(self):
        self.model = None
        self.device = "cpu"
        self.compute_type = "int8"
        self.language = "hu"
        self.beam_size = 5

    def load(self, config: Dict[str, Any]) -> None:
        try:
            from faster_whisper import WhisperModel

            model_path = config.get("model_path", "openai/whisper-large-v3")
            self.device = config.get("device", "cpu")
            self.compute_type = config.get("compute_type", "int8_float16")
            self.language = config.get("language", "hu")
            self.beam_size = config.get("beam_size", 5)

            self.model = WhisperModel(
                model_path,
                device=self.device,
                compute_type=self.compute_type,
                local_files_only=True,
            )
            logger.info(f"FasterWhisperASR loaded: {model_path} on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load FasterWhisperASR: {e}")
            raise

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> ASRResult:
        """Transcribe audio using faster-whisper."""
        loop = asyncio.get_event_loop()

        try:
            segments, info = await loop.run_in_executor(
                None, self._do_transcribe, audio, sample_rate
            )

            # Combine segments into single result
            text = " ".join([segment.text for segment in segments])
            confidence = np.mean([segment.confidence for segment in segments]) if segments else 0.0

            return ASRResult(
                text=text,
                language=info.language,
                confidence=float(confidence),
                is_final=True,
                start_ms=0,
                end_ms=int(len(audio) / sample_rate * 1000),
            )
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ASRResult(
                text="",
                language=self.language,
                confidence=0.0,
                is_final=True,
                start_ms=0,
                end_ms=0,
            )

    async def transcribe_stream(
        self, audio_generator: AsyncIterator[np.ndarray], sample_rate: int
    ) -> AsyncIterator[ASRResult]:
        """Stream transcription results."""
        buffer = np.array([], dtype=np.float32)
        chunk_duration_ms = 1000  # Transcribe every 1 second

        async for chunk in audio_generator:
            buffer = np.concatenate([buffer, chunk])

            # Check if we have enough for a chunk
            chunk_samples = int(sample_rate * chunk_duration_ms / 1000)
            if len(buffer) >= chunk_samples:
                # Transcribe current buffer
                result = await self.transcribe(buffer, sample_rate)
                if result.text:
                    result_with_timing = ASRResult(
                        text=result.text,
                        language=result.language,
                        confidence=result.confidence,
                        is_final=False,
                        start_ms=0,
                        end_ms=int(len(buffer) / sample_rate * 1000),
                    )
                    yield result_with_timing

                # Keep last 500ms for overlap
                overlap_samples = int(sample_rate * 500 / 1000)
                buffer = buffer[-overlap_samples:] if len(buffer) > overlap_samples else buffer

        # Final transcription
        if len(buffer) > 0:
            result = await self.transcribe(buffer, sample_rate)
            if result.text:
                result.is_final = True
                yield result

    def _do_transcribe(self, audio: np.ndarray, sample_rate: int):
        """Synchronous transcription (runs in executor)."""
        if self.model is None:
            return [], None

        # Resample if necessary
        if sample_rate != 16000:
            import librosa
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)
            sample_rate = 16000

        segments, info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=False,
            word_timestamps=True,
        )

        return list(segments), info

    async def shutdown(self) -> None:
        if self.model is not None:
            del self.model
            self.model = None


class HuggingFaceWhisperASR(BaseASR):
    """HuggingFace Transformers Whisper implementation."""

    def __init__(self):
        self.pipeline = None
        self.device = "cpu"
        self.language = "hu"

    def load(self, config: Dict[str, Any]) -> None:
        try:
            import torch
            from transformers import (
                AutoModelForSpeechSeq2Seq,
                AutoProcessor,
                pipeline,
            )

            model_path = config.get("model_path", "openai/whisper-small")
            self.device = config.get("device", "cpu")
            self.language = config.get("language", "hu")

            torch_dtype = torch.float16 if self.device == "cuda" else torch.float32

            model = AutoModelForSpeechSeq2Seq.from_pretrained(
                model_path, local_files_only=True, torch_dtype=torch_dtype
            )
            processor = AutoProcessor.from_pretrained(
                model_path, local_files_only=True
            )

            # Note: NO chunk_length_s — that triggers long-form padding-to-30s,
            # which made every short streaming call slow + hallucinate on silence.
            self.pipeline = pipeline(
                "automatic-speech-recognition",
                model=model,
                tokenizer=processor.tokenizer,
                feature_extractor=processor.feature_extractor,
                torch_dtype=torch_dtype,
                device=0 if self.device == "cuda" else -1,
            )
            logger.info(
                f"HuggingFaceWhisperASR loaded: {model_path} on {self.device} (dtype={torch_dtype})"
            )
        except Exception as e:
            logger.error(f"Failed to load HuggingFaceWhisperASR: {e}")
            raise

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> ASRResult:
        """Transcribe audio using HuggingFace Whisper."""
        loop = asyncio.get_event_loop()

        try:
            result = await loop.run_in_executor(
                None, self._do_transcribe, audio, sample_rate
            )

            return ASRResult(
                text=result.get("text", ""),
                language=self.language,
                confidence=result.get("confidence", 0.0),
                is_final=True,
                start_ms=0,
                end_ms=int(len(audio) / sample_rate * 1000),
            )
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ASRResult(
                text="",
                language=self.language,
                confidence=0.0,
                is_final=True,
                start_ms=0,
                end_ms=0,
            )

    async def transcribe_stream(
        self, audio_generator: AsyncIterator[np.ndarray], sample_rate: int
    ) -> AsyncIterator[ASRResult]:
        """Stream transcription results."""
        buffer = np.array([], dtype=np.float32)

        async for chunk in audio_generator:
            buffer = np.concatenate([buffer, chunk])

            # Transcribe every ~2 seconds
            if len(buffer) >= sample_rate * 2:
                result = await self.transcribe(buffer, sample_rate)
                if result.text:
                    yield result
                    buffer = np.array([], dtype=np.float32)

        # Final transcription
        if len(buffer) > 0:
            result = await self.transcribe(buffer, sample_rate)
            if result.text:
                result.is_final = True
                yield result

    def _do_transcribe(self, audio: np.ndarray, sample_rate: int):
        """Synchronous transcription (runs in executor)."""
        if self.pipeline is None:
            return {}

        if sample_rate != 16000:
            import librosa
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)

        # Normalize quiet audio so Whisper sees consistent loudness.
        # Target RMS ~0.1 (~-20 dBFS), but cap gain at 12x so we don't blow up pure noise.
        rms = float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0
        if rms > 1e-4:
            target_rms = 0.1
            gain = min(target_rms / rms, 12.0)
            audio = (audio * gain).astype(np.float32)
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            if peak > 0.99:
                audio = (audio * (0.99 / peak)).astype(np.float32)

        import time
        t0 = time.time()
        result = self.pipeline(
            audio,
            generate_kwargs={
                "language": self.language,
                "task": "transcribe",
                "max_new_tokens": 96,
                "no_repeat_ngram_size": 3,
            },
        )
        logger.info(
            f"whisper transcribe: audio={len(audio)/16000:.1f}s took={time.time()-t0:.2f}s text={result.get('text','')!r}"
        )
        return result

    async def shutdown(self) -> None:
        if self.pipeline is not None:
            del self.pipeline
            self.pipeline = None
