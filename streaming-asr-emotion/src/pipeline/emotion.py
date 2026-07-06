import numpy as np
from typing import Dict, Any
from collections import deque
import asyncio
import logging
from .base import BaseEmotion
from ..schemas import EmotionResult

logger = logging.getLogger(__name__)

EMOTION_LABELS = ["angry", "anxious", "sad", "neutral", "happy", "fearful", "disgusted", "surprised"]


class Wav2VecEmotionSER(BaseEmotion):
    """Audio-based emotion recognition using wav2vec2 XLS-R."""

    def __init__(self):
        self.model = None
        self.processor = None
        self.device = "cpu"
        self.window_ms = 2000
        self.overlap_ms = 1000
        self.audio_buffer = deque(maxlen=int(16000 * 30))  # 30 seconds buffer
        self.last_emotion = None

    def load(self, config: Dict[str, Any]) -> None:
        try:
            from transformers import (
                AutoModelForAudioClassification,
                AutoFeatureExtractor,
            )

            model_path = config.get("model_path", "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition")
            self.device = config.get("device", "cpu")
            self.window_ms = config.get("window_ms", 2000)
            self.overlap_ms = config.get("overlap_ms", 1000)

            self.processor = AutoFeatureExtractor.from_pretrained(
                model_path, local_files_only=True
            )
            self.model = AutoModelForAudioClassification.from_pretrained(
                model_path, local_files_only=True
            )
            self.model.to(self.device)
            self.model.eval()

            logger.info(f"Wav2VecEmotionSER loaded on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load Wav2VecEmotionSER: {e}")
            raise

    async def classify(self, audio: np.ndarray, sample_rate: int) -> EmotionResult:
        """Classify emotion from audio."""
        loop = asyncio.get_event_loop()

        try:
            emotion_dict = await loop.run_in_executor(
                None, self._do_classify, audio, sample_rate
            )

            top_emotion = max(emotion_dict.items(), key=lambda x: x[1])
            return EmotionResult(
                label=top_emotion[0],
                scores=emotion_dict,
                window_ms=(0, int(len(audio) / sample_rate * 1000)),
            )
        except Exception as e:
            logger.error(f"Emotion classification error: {e}")
            return EmotionResult(
                label="neutral",
                scores={label: 0.0 for label in EMOTION_LABELS},
                window_ms=(0, 0),
            )

    async def classify_text(self, text: str) -> EmotionResult:
        """Classify emotion from text (fallback)."""
        # For now, return neutral - this can be implemented later
        return EmotionResult(
            label="neutral",
            scores={label: 0.0 for label in EMOTION_LABELS},
            window_ms=(0, 0),
        )

    def _do_classify(self, audio: np.ndarray, sample_rate: int):
        """Synchronous emotion classification (runs in executor)."""
        if self.model is None:
            return {label: 0.0 for label in EMOTION_LABELS}

        try:
            import torch

            if sample_rate != 16000:
                import librosa
                audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)

            inputs = self.processor(audio, sampling_rate=16000, return_tensors="pt").to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probabilities = torch.nn.functional.softmax(logits, dim=-1)

            id2label = self.model.config.id2label
            scores = {
                id2label[i].lower(): float(probabilities[0][i].cpu().numpy())
                for i in range(probabilities.shape[-1])
            }
            # Low-confidence guard: if the top class is barely above uniform, collapse to neutral.
            # 8-class uniform = 0.125; "barely confident" = under 0.20.
            top = max(scores.values()) if scores else 0.0
            if top < 0.20:
                logger.info(f"Low-confidence emotion (top={top:.2f}) — reporting neutral")
                scores = {k: 0.0 for k in scores}
                scores["neutral"] = 1.0
            return scores
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return {label: 0.0 for label in EMOTION_LABELS}

    async def shutdown(self) -> None:
        if self.model is not None:
            del self.model
            del self.processor
            self.model = None
            self.processor = None


class AcousticBiomarkersEmotion(BaseEmotion):
    """Language-independent mood from voice prosody (pitch, energy, jitter, shimmer).

    Inspired by Sonde Health / eGeMAPS feature sets. Uses parselmouth (Praat).
    Maps prosodic features to UI emotion labels via simple rules — no ML model,
    so quality is consistent regardless of speaker language.
    """

    def __init__(self):
        self.sample_rate = 16000
        # Personal speaker baseline learned across the session.
        self._pitch_baseline: float = 0.0
        self._intensity_baseline: float = 0.0
        self._n_observations: int = 0

    def load(self, config: Dict[str, Any]) -> None:
        try:
            import parselmouth  # noqa: F401
        except ImportError as e:
            logger.error(f"parselmouth not installed: {e}")
            raise
        logger.info("AcousticBiomarkersEmotion loaded (parselmouth)")

    async def classify(self, audio: np.ndarray, sample_rate: int) -> EmotionResult:
        loop = asyncio.get_event_loop()
        try:
            features = await loop.run_in_executor(None, self._extract_features, audio, sample_rate)
            scores = self._features_to_scores(features)
            label = max(scores.items(), key=lambda x: x[1])[0]
            return EmotionResult(
                label=label,
                scores=scores,
                window_ms=(0, int(len(audio) / sample_rate * 1000)),
            )
        except Exception as e:
            logger.error(f"Acoustic emotion error: {e}")
            return EmotionResult(label="neutral", scores={l: 0.0 for l in EMOTION_LABELS} | {"neutral": 1.0}, window_ms=(0, 0))

    async def classify_text(self, text: str) -> EmotionResult:
        return EmotionResult(label="neutral", scores={l: 0.0 for l in EMOTION_LABELS} | {"neutral": 1.0}, window_ms=(0, 0))

    def _extract_features(self, audio: np.ndarray, sample_rate: int) -> Dict[str, float]:
        import parselmouth
        from parselmouth.praat import call

        # Need at least 0.5s of audio for reliable pitch tracking.
        if audio.size < int(sample_rate * 0.5):
            return {}

        snd = parselmouth.Sound(audio.astype(np.float64), sampling_frequency=sample_rate)

        pitch = snd.to_pitch(time_step=0.01, pitch_floor=75.0, pitch_ceiling=500.0)
        f0 = pitch.selected_array["frequency"]
        f0 = f0[f0 > 0]  # drop unvoiced frames
        pitch_mean = float(np.mean(f0)) if f0.size else 0.0
        pitch_std = float(np.std(f0)) if f0.size else 0.0

        intensity = snd.to_intensity(minimum_pitch=75.0)
        i_values = intensity.values[0]
        intensity_mean = float(np.mean(i_values)) if i_values.size else 0.0

        # Jitter and shimmer require a PointProcess
        point_process = call(snd, "To PointProcess (periodic, cc)", 75, 500)
        try:
            jitter_local = float(call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3))
        except Exception:
            jitter_local = 0.0
        try:
            shimmer_local = float(call(
                [snd, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6
            ))
        except Exception:
            shimmer_local = 0.0

        # Speech-rate proxy: fraction of voiced frames
        voiced_ratio = float(f0.size / max(1, pitch.selected_array["frequency"].size))

        return {
            "pitch_mean": pitch_mean,
            "pitch_std": pitch_std,
            "intensity_mean": intensity_mean,
            "jitter": jitter_local if not np.isnan(jitter_local) else 0.0,
            "shimmer": shimmer_local if not np.isnan(shimmer_local) else 0.0,
            "voiced_ratio": voiced_ratio,
        }

    def _features_to_scores(self, f: Dict[str, float]) -> Dict[str, float]:
        if not f or f.get("pitch_mean", 0.0) <= 0:
            return {l: 0.0 for l in EMOTION_LABELS} | {"neutral": 1.0}

        # Update rolling baselines for this speaker.
        self._n_observations += 1
        alpha = 1.0 / min(self._n_observations, 10)  # warm-up over first ~10 obs
        if self._pitch_baseline == 0.0:
            self._pitch_baseline = f["pitch_mean"]
            self._intensity_baseline = f["intensity_mean"]
        else:
            self._pitch_baseline = (1 - alpha) * self._pitch_baseline + alpha * f["pitch_mean"]
            self._intensity_baseline = (1 - alpha) * self._intensity_baseline + alpha * f["intensity_mean"]

        # Arousal ≈ pitch + intensity + pitch variance, normalized to baseline.
        pitch_rel = (f["pitch_mean"] - self._pitch_baseline) / max(20.0, self._pitch_baseline * 0.15)
        intensity_rel = (f["intensity_mean"] - self._intensity_baseline) / 5.0
        animation = f["pitch_std"] / max(15.0, self._pitch_baseline * 0.12)  # ~1.0 = animated
        arousal = pitch_rel + intensity_rel + (animation - 1.0)

        # Stress markers from voice quality.
        stressed_voice = (f["jitter"] > 0.02) or (f["shimmer"] > 0.10)

        scores = {l: 0.0 for l in EMOTION_LABELS}
        if arousal > 0.6 and stressed_voice:
            scores["anxious"] = 0.6
            scores["fearful"] = 0.25
            scores["angry"] = 0.15
        elif arousal > 0.6:
            scores["happy"] = 0.5
            scores["surprised"] = 0.3
            scores["neutral"] = 0.2
        elif arousal < -0.4:
            scores["sad"] = 0.55
            scores["neutral"] = 0.3
            scores["anxious"] = 0.15
        elif stressed_voice:
            scores["anxious"] = 0.55
            scores["neutral"] = 0.35
            scores["fearful"] = 0.10
        else:
            scores["neutral"] = 0.8
            scores["happy"] = 0.1
            scores["sad"] = 0.1
        return scores

    async def shutdown(self) -> None:
        pass


class TextSentimentEmotion(BaseEmotion):
    """Text-based sentiment analysis (CPU-friendly fallback)."""

    def __init__(self):
        self.pipeline = None
        self.device = "cpu"

    def load(self, config: Dict[str, Any]) -> None:
        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
                pipeline,
            )

            model_path = config.get("model_path", "nlptown/bert-base-multilingual-uncased-sentiment")
            self.device = config.get("device", "cpu")

            model = AutoModelForSequenceClassification.from_pretrained(
                model_path, local_files_only=True
            )
            tokenizer = AutoTokenizer.from_pretrained(
                model_path, local_files_only=True
            )

            self.pipeline = pipeline(
                "text-classification",
                model=model,
                tokenizer=tokenizer,
                device=0 if self.device == "cuda" else -1,
            )
            logger.info(f"TextSentimentEmotion loaded on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load TextSentimentEmotion: {e}")
            raise

    async def classify(self, audio: np.ndarray, sample_rate: int) -> EmotionResult:
        """Not implemented for audio - use classify_text instead."""
        return EmotionResult(
            label="neutral",
            scores={label: 0.0 for label in EMOTION_LABELS},
            window_ms=(0, 0),
        )

    async def classify_text(self, text: str) -> EmotionResult:
        """Classify emotion from text."""
        loop = asyncio.get_event_loop()

        try:
            result = await loop.run_in_executor(None, self._do_classify_text, text)

            # Map sentiment to emotion
            sentiment_to_emotion = {
                "positive": "happy",
                "neutral": "neutral",
                "negative": "sad",
            }

            label = sentiment_to_emotion.get(result["label"].lower(), "neutral")
            confidence = result.get("score", 0.0)

            emotion_dict = {
                "happy": confidence if label == "happy" else 0.0,
                "neutral": confidence if label == "neutral" else 0.0,
                "sad": confidence if label == "sad" else 0.0,
                "angry": 0.1 * confidence if label == "sad" else 0.0,
                "anxious": 0.0,
                "fearful": 0.0,
                "disgusted": 0.0,
                "surprised": 0.0,
            }

            return EmotionResult(
                label=label,
                scores=emotion_dict,
                window_ms=(0, 0),
            )
        except Exception as e:
            logger.error(f"Text classification error: {e}")
            return EmotionResult(
                label="neutral",
                scores={label: 0.0 for label in EMOTION_LABELS},
                window_ms=(0, 0),
            )

    def _do_classify_text(self, text: str):
        """Synchronous text classification (runs in executor)."""
        if self.pipeline is None:
            return {}

        result = self.pipeline(text)[0]
        return result

    async def shutdown(self) -> None:
        if self.pipeline is not None:
            del self.pipeline
            self.pipeline = None
