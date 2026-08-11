import time
from typing import Optional
from pydantic import BaseModel, Field


class AudioChunkEvent(BaseModel):
    session_id: str
    question: int
    chunk_index: int
    pcm_bytes_b64: str
    sample_rate: int = 16000
    timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))


class SpeechAudioEvent(BaseModel):
    session_id: str
    question: int
    pcm_bytes_b64: str
    sample_rate: int = 16000
    vad_confidence: float = 1.0
    audio_duration_ms: int = 0


class TranscriptEvent(BaseModel):
    session_id: str
    question: int
    transcript: str
    is_final: bool = True
    vad_confidence: float = 1.0
    audio_duration_ms: int = 0


class TextInputEvent(BaseModel):
    session_id: str
    question: int
    text: Optional[str] = None


class CommandResultEvent(BaseModel):
    session_id: str
    question: int
    intent: str
    score: int
    confidence: float
    transcript: str = ""
    status: str = "success"
