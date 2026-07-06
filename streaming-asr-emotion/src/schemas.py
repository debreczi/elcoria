from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict
from dataclasses import dataclass
from enum import Enum
import uuid
from datetime import datetime


class VADResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    event: str  # 'speech_start', 'speech_end', 'silence'
    confidence: float
    frame_ms: int


class ASRResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str
    language: str
    confidence: float
    is_final: bool
    start_ms: int
    end_ms: int


class EmotionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    label: str
    scores: Dict[str, float]
    window_ms: tuple[int, int]


class FusionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    questions: str
    utterance_id: str


# WebSocket Messages

class PartialTranscriptMessage(BaseModel):
    type: str = "partial_transcript"
    session_id: str
    timestamp_ms: int
    text: str
    language: str
    confidence: float
    is_final: bool = False


class FinalTranscriptMessage(BaseModel):
    type: str = "final_transcript"
    session_id: str
    timestamp_ms: int
    text: str
    language: str
    confidence: float
    is_final: bool = True
    utterance_id: str


class EmotionUpdateMessage(BaseModel):
    type: str = "emotion_update"
    session_id: str
    timestamp_ms: int
    label: str
    scores: Dict[str, float]
    window_ms: tuple[int, int]


class QuestionChunkMessage(BaseModel):
    type: str = "question_chunk"
    session_id: str
    utterance_id: str
    delta: str
    is_final: bool = False


class QuestionFinalMessage(BaseModel):
    type: str = "question_final"
    session_id: str
    utterance_id: str
    full_text: str
    is_final: bool = True


class ErrorMessage(BaseModel):
    type: str = "error"
    session_id: str
    code: str
    message: str


class ControlMessage(BaseModel):
    type: str = "control"
    event: str
    config_name: Optional[str] = None
    filename: Optional[str] = None
