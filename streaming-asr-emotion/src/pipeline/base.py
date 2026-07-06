from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any
import numpy as np
from ..schemas import VADResult, ASRResult, EmotionResult, FusionResult


class BaseVAD(ABC):
    """Voice Activity Detection interface."""

    @abstractmethod
    async def process(
        self, audio_chunk: np.ndarray, sample_rate: int
    ) -> list[VADResult]:
        """
        Process audio chunk and return VAD events.
        Returns list of VAD results (speech_start, speech_end, silence).
        """
        pass

    @abstractmethod
    def load(self, config: Dict[str, Any]) -> None:
        """Load VAD model/resources from config."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources."""
        pass


class BaseASR(ABC):
    """Automatic Speech Recognition interface."""

    @abstractmethod
    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> ASRResult:
        """Transcribe audio chunk, return final result."""
        pass

    @abstractmethod
    async def transcribe_stream(
        self, audio_generator: AsyncIterator[np.ndarray], sample_rate: int
    ) -> AsyncIterator[ASRResult]:
        """Stream transcription results as audio chunks arrive."""
        pass

    @abstractmethod
    def load(self, config: Dict[str, Any]) -> None:
        """Load ASR model from config."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources."""
        pass


class BaseEmotion(ABC):
    """Emotion/Sentiment Analysis interface."""

    @abstractmethod
    async def classify(self, audio: np.ndarray, sample_rate: int) -> EmotionResult:
        """Classify emotion from audio."""
        pass

    @abstractmethod
    async def classify_text(self, text: str) -> EmotionResult:
        """Classify emotion from text (optional fallback)."""
        pass

    @abstractmethod
    def load(self, config: Dict[str, Any]) -> None:
        """Load emotion model from config."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources."""
        pass


class BaseFusion(ABC):
    """Question Generation / Fusion interface."""

    @abstractmethod
    async def generate(
        self, transcript: str, emotion: EmotionResult, session_ctx: list[str]
    ) -> FusionResult:
        """Generate clarification questions given transcript and emotion."""
        pass

    @abstractmethod
    async def generate_stream(
        self, transcript: str, emotion: EmotionResult, session_ctx: list[str]
    ) -> AsyncIterator[str]:
        """Stream question generation token by token."""
        pass

    @abstractmethod
    def load(self, config: Dict[str, Any]) -> None:
        """Load fusion model from config."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources."""
        pass
