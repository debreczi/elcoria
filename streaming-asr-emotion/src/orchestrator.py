import asyncio
import logging
import time
import numpy as np
from typing import Callable, Optional, List, Dict
from .config import PipelineConfig
from .pipeline.vad import EnergyVAD, SileroVAD
from .pipeline.asr import FasterWhisperASR, HuggingFaceWhisperASR
from .pipeline.emotion import Wav2VecEmotionSER, TextSentimentEmotion, AcousticBiomarkersEmotion
from .pipeline.fusion import OllamaFusion, TemplateFusion
from .schemas import EmotionResult

logger = logging.getLogger(__name__)


# ─── v1 wire-shape helpers ────────────────────────────────────────────────────

DEFAULT_BIOMARKERS: Dict[str, float] = {
    "pitch_mean": 0.0,
    "pitch_std": 0.0,
    "jitter": 0.0,
    "shimmer": 0.0,
    "hnr": 0.0,
    "energy": 0.0,
}


def _compute_biomarkers(audio: np.ndarray, sample_rate: int) -> Dict[str, float]:
    """Prosodic biomarkers from utterance audio. Uses parselmouth; degrades gracefully."""
    bm = dict(DEFAULT_BIOMARKERS)
    if audio is None or audio.size == 0:
        return bm
    bm["energy"] = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if audio.size < int(sample_rate * 0.3):
        return bm
    try:
        import parselmouth
        from parselmouth.praat import call
    except ImportError:
        return bm
    try:
        snd = parselmouth.Sound(audio.astype(np.float64), sampling_frequency=sample_rate)
        pitch = snd.to_pitch(time_step=0.01, pitch_floor=75.0, pitch_ceiling=500.0)
        f0 = pitch.selected_array["frequency"]
        f0_voiced = f0[f0 > 0]
        if f0_voiced.size:
            bm["pitch_mean"] = float(np.mean(f0_voiced))
            bm["pitch_std"] = float(np.std(f0_voiced))
        try:
            pp = call(snd, "To PointProcess (periodic, cc)", 75, 500)
            jit = float(call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3))
            bm["jitter"] = 0.0 if np.isnan(jit) else jit
            shim = float(call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6))
            bm["shimmer"] = 0.0 if np.isnan(shim) else shim
        except Exception:
            pass
        try:
            harm = snd.to_harmonicity()
            hv = harm.values[0]
            hv = hv[~np.isnan(hv) & (hv > -200)]
            if hv.size:
                bm["hnr"] = float(np.mean(hv))
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Biomarker compute failed (partial result): {e}")
    return bm


def _split_questions(text: str) -> List[Dict]:
    """Parse the fusion's free-text into a structured question list."""
    raw_lines = (text or "").split("\n")
    cleaned: List[str] = []
    for ln in raw_lines:
        s = ln.strip()
        # Strip leading list markers / numbering
        while s and s[0] in "-•*0123456789. \t)":
            s = s[1:]
        s = s.strip(" \t")
        if s and ("?" in s or len(s) > 8):
            cleaned.append(s)
    out: List[Dict] = []
    for i, ln in enumerate(cleaned[:6]):
        priority = "high" if i == 0 else ("med" if i < 3 else "low")
        out.append({"p": priority, "hu": ln, "en": "", "tags": []})
    return out


_CRISIS_KW = ("nem kapok levegőt", "ájulok", "ájulás", "stroke", "infarktus", "haldoklom",
              "összeesem", "öngyilkos")
_URGENT_KW = ("fáj", "mellkas", "szédülök", "hányinger", "vérzés", "rosszul vagyok")
_LEVELS = {1: "Routine", 2: "Concerned", 3: "Urgent", 4: "Crisis"}


def _synthesize_prediction(transcript: str, emotion: Optional[EmotionResult]) -> Dict:
    """Heuristic intent prediction. Replace with a real classifier when one exists."""
    label = emotion.label if emotion else "neutral"
    top = max(emotion.scores.values()) if emotion and emotion.scores else 0.0
    t_lower = (transcript or "").lower()
    if any(k in t_lower for k in _CRISIS_KW):
        level, name = 4, "Possible critical event"
    elif any(k in t_lower for k in _URGENT_KW) or label in ("anxious", "fearful", "angry"):
        level, name = 3, "Possible acute discomfort"
    elif label == "sad":
        level, name = 2, "Concerned — affective signal"
    else:
        level, name = 1, "Routine assessment"
    return {
        "name": name,
        "icd": "",
        "level": level,
        "level_label": _LEVELS[level],
        "confidence": round(float(top) if top else 0.3, 2),
        "reasoning": f"Top emotion: {label} ({(top or 0):.0%}). Transcript: {(transcript or '')[:120]}",
        "differential": [],
    }


# ─── Orchestrator ─────────────────────────────────────────────────────────────


class PipelineOrchestrator:
    """Coordinates VAD/ASR/Emotion/Fusion and emits v1 wire-shape messages.

    Wire contract (see streaming-asr-emotion/elcoria-ui/INSTRUCTIONS.md §4):
      transcript.partial  — { type, uid, ts_ms, text }
      transcript.final    — { type, uid, ts_ms, transcript, emotion, biomarkers }
      intent.update       — { type, ts_ms, prediction, questions }
      error               — { type, code, message }

    `session.start` is emitted by the WebSocket endpoint, not here.
    """

    def __init__(
        self,
        config: PipelineConfig,
        session_id: str,
        send_message: Callable,
        shared=None,
    ):
        self.config = config
        self.session_id = session_id
        self.send_message = send_message
        self._owns_models = shared is None

        # VAD has per-session state (silence buffer, is_speech flag) — build per session.
        self.vad = self._load_stage("vad", config.vad)
        # ASR / Emotion / Fusion models are stateless across sessions — reuse if cached.
        if shared is not None:
            self.asr = shared["asr"]
            self.emotion = shared["emotion"]
            self.fusion = shared["fusion"]
            logger.info("Orchestrator using shared ASR/Emotion/Fusion (no model reload)")
        else:
            self.asr = self._load_stage("asr", config.asr)
            self.emotion = self._load_stage("emotion", config.emotion)
            self.fusion = self._load_stage("fusion", config.fusion)

        self.is_speech = False
        self.utterance_buffer = np.array([], dtype=np.float32)
        self.session_context: List[str] = []
        self.last_emotion: Optional[EmotionResult] = None
        self.sample_rate = 16000
        self._asr_in_flight = False
        self._emotion_in_flight = False
        self._stream_interval_samples = int(16000 * 1.5)  # 1.5s minimum between partials
        self._last_stream_offset = 0
        self._utterance_task: Optional[asyncio.Task] = None

        # v1 utterance ID — bumped per speech_start, attached to partials and the matching final.
        self._utterance_seq = 0
        self._current_uid: Optional[str] = None
        self._session_started_ms = int(time.time() * 1000)

    def _load_stage(self, stage_name: str, stage_config):
        impl_name = stage_config.implementation
        implementations = {
            "EnergyVAD": EnergyVAD,
            "SileroVAD": SileroVAD,
            "FasterWhisperASR": FasterWhisperASR,
            "HuggingFaceWhisperASR": HuggingFaceWhisperASR,
            "Wav2VecEmotionSER": Wav2VecEmotionSER,
            "TextSentimentEmotion": TextSentimentEmotion,
            "AcousticBiomarkersEmotion": AcousticBiomarkersEmotion,
            "OllamaFusion": OllamaFusion,
            "TemplateFusion": TemplateFusion,
        }
        if impl_name not in implementations:
            raise ValueError(f"Unknown implementation: {impl_name}")
        instance = implementations[impl_name]()
        instance.load(stage_config.params)
        logger.info(f"Loaded {stage_name}: {impl_name}")
        return instance

    def _ts_ms(self) -> int:
        return int(time.time() * 1000) - self._session_started_ms

    async def process_chunk(self, audio_chunk: np.ndarray, sample_rate: int) -> None:
        self.sample_rate = sample_rate

        vad_results = await self.vad.process(audio_chunk, sample_rate)

        for vad_result in vad_results:
            if vad_result.event == "speech_start":
                self.is_speech = True
                self.utterance_buffer = np.array([], dtype=np.float32)
                if self._utterance_task and not self._utterance_task.done():
                    logger.info("New speech_start — cancelling pending utterance task")
                    self._utterance_task.cancel()
                    self._utterance_task = None
                self._utterance_seq += 1
                self._current_uid = f"u{self._utterance_seq:03d}"
                logger.info(f"VAD speech_start uid={self._current_uid} (conf={vad_result.confidence:.2f})")

            elif vad_result.event == "speech_end":
                self.is_speech = False
                buf_ms = int(len(self.utterance_buffer) / max(1, sample_rate) * 1000)
                logger.info(f"VAD speech_end uid={self._current_uid} — buffered {buf_ms}ms")
                if len(self.utterance_buffer) > 0 and self._current_uid:
                    snapshot = self.utterance_buffer.copy()
                    uid_for_final = self._current_uid
                    self._utterance_task = asyncio.create_task(
                        self._process_utterance_async(snapshot, uid_for_final)
                    )
                self.utterance_buffer = np.array([], dtype=np.float32)
                self._last_stream_offset = 0
                self._current_uid = None

        # Accumulate audio while speech is detected
        if self.is_speech:
            self.utterance_buffer = np.concatenate([self.utterance_buffer, audio_chunk])

            # Throttle streaming partials: only fire once the buffer has grown
            # by `_stream_interval_samples` since the last fire, and skip when
            # a previous call is still running.
            grown = len(self.utterance_buffer) - self._last_stream_offset
            if grown >= self._stream_interval_samples:
                self._last_stream_offset = len(self.utterance_buffer)
                if not self._asr_in_flight:
                    self._asr_in_flight = True
                    asyncio.create_task(self._stream_asr_guarded(self._current_uid))
                if not self._emotion_in_flight:
                    self._emotion_in_flight = True
                    asyncio.create_task(self._update_emotion_guarded())

    async def _stream_asr_guarded(self, uid: Optional[str]) -> None:
        try:
            await self._stream_asr(uid)
        finally:
            self._asr_in_flight = False

    async def _update_emotion_guarded(self) -> None:
        try:
            await self._update_emotion()
        finally:
            self._emotion_in_flight = False

    async def _stream_asr(self, uid: Optional[str]) -> None:
        if not uid:
            return
        if len(self.utterance_buffer) < self.sample_rate:  # Less than 1 second
            return
        try:
            buf_ms = int(len(self.utterance_buffer) / max(1, self.sample_rate) * 1000)
            logger.info(f"ASR streaming on {buf_ms}ms buffer (uid={uid})")
            result = await self.asr.transcribe(self.utterance_buffer, self.sample_rate)
            logger.info(f"ASR partial: uid={uid} text={result.text!r} conf={result.confidence:.2f}")
            if result.text:
                await self.send_message({
                    "type": "transcript.partial",
                    "uid": uid,
                    "ts_ms": self._ts_ms(),
                    "text": result.text,
                })
        except Exception as e:
            logger.error(f"ASR error: {e}")

    async def _update_emotion(self) -> None:
        """Update emotion estimate from the in-progress buffer (kept for the final fan-out)."""
        try:
            emotion_result = await self.emotion.classify(self.utterance_buffer, self.sample_rate)
            self.last_emotion = emotion_result
        except Exception as e:
            logger.error(f"Emotion error: {e}")

    @staticmethod
    def _looks_unusable(text: str) -> bool:
        """Heuristics for Whisper outputs we shouldn't feed to the LLM."""
        t = (text or "").strip().strip(".!?,;:")
        if len(t) < 3:
            return True
        words = t.split()
        if len(words) < 2:
            return True
        if len(words) >= 4 and len(set(w.lower() for w in words)) <= 2:
            return True
        if len(words) >= 9:
            tri = [" ".join(words[i:i + 3]).lower() for i in range(len(words) - 2)]
            from collections import Counter
            most_common, count = Counter(tri).most_common(1)[0]
            if count >= 3:
                return True
        hallucinations = {
            "köszönöm", "köszönöm a figyelmet", "köszönöm szépen",
            "kösz", "fogadjátok", "fogadjátok!",
        }
        return t.lower() in hallucinations

    async def _process_utterance_async(self, audio_snapshot: np.ndarray, uid: str) -> None:
        """Background-finalize a completed utterance from a snapshot."""
        if audio_snapshot.size == 0:
            return
        try:
            result = await self.asr.transcribe(audio_snapshot, self.sample_rate)
            await self._emit_utterance(uid, result, audio_snapshot)
        except Exception as e:
            logger.error(f"Utterance processing error: {e}")
            await self.send_message({
                "type": "error",
                "code": "PROCESSING_ERROR",
                "message": str(e),
            })

    async def _emit_utterance(self, uid: str, result, audio_snapshot: np.ndarray) -> None:
        raw_text = (result.text or "").strip()
        unusable = self._looks_unusable(raw_text)
        display_text = raw_text if not unusable else "(nem érthető)"

        # Biomarkers from this utterance's audio.
        biomarkers = _compute_biomarkers(audio_snapshot, self.sample_rate)

        # Emotion: refresh on the full snapshot (more reliable than streaming windows).
        try:
            emotion_result = await self.emotion.classify(audio_snapshot, self.sample_rate)
            self.last_emotion = emotion_result
        except Exception as e:
            logger.error(f"emotion classify (final) error: {e}")
            emotion_result = self.last_emotion

        emo_scores = emotion_result.scores if emotion_result else {}
        emo_label = emotion_result.label if emotion_result else "neutral"
        emo_conf = float(max(emo_scores.values())) if emo_scores else 0.0

        await self.send_message({
            "type": "transcript.final",
            "uid": uid,
            "ts_ms": self._ts_ms(),
            "transcript": {
                "text": display_text,
                "en": "",
                "language": result.language or "hu",
                "confidence": float(result.confidence or 0.0),
                "tokens": [{"t": display_text}],
            },
            "emotion": {
                "label": emo_label,
                "confidence": emo_conf,
                "scores": emo_scores,
            },
            "biomarkers": biomarkers,
        })

        if unusable:
            ask_back = "Bocsánat, nem értettem tisztán. Kérem mondja el még egyszer."
            await self.send_message({
                "type": "intent.update",
                "ts_ms": self._ts_ms(),
                "prediction": _synthesize_prediction(raw_text, emotion_result),
                "questions": [{"p": "high", "hu": ask_back, "en": "", "tags": ["retry"]}],
            })
            return

        self.session_context.append(raw_text)

        # Collect the full fusion output before emitting the v1 intent.update message.
        full_text = ""
        try:
            async for chunk in self.fusion.generate_stream(raw_text, emotion_result, self.session_context):
                full_text += chunk
        except Exception as e:
            logger.error(f"Fusion error: {e}")
            full_text = "Nem sikerült a kérdések generálása."

        await self.send_message({
            "type": "intent.update",
            "ts_ms": self._ts_ms(),
            "prediction": _synthesize_prediction(raw_text, emotion_result),
            "questions": _split_questions(full_text),
        })

    async def shutdown(self) -> None:
        logger.info(f"Shutting down orchestrator for session {self.session_id}")
        if self._utterance_task and not self._utterance_task.done():
            self._utterance_task.cancel()
        if self._owns_models:
            await asyncio.gather(
                self.vad.shutdown(),
                self.asr.shutdown(),
                self.emotion.shutdown(),
                self.fusion.shutdown(),
                return_exceptions=True,
            )
        else:
            await self.vad.shutdown()
