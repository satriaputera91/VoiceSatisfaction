import logging
from typing import Dict

logger = logging.getLogger("VoiceSatisfaction.AudioBuffer")


class SessionAudioBuffer:
    def __init__(self, min_silence_duration_ms: int = 300, sample_rate: int = 16000):
        self.buffers: Dict[str, bytearray] = {}
        self.silence_durations: Dict[str, int] = {}
        self.min_silence_ms = min_silence_duration_ms
        self.sample_rate = sample_rate

    def append(self, session_id: str, pcm_bytes: bytes, is_speech: bool):
        if session_id not in self.buffers:
            self.buffers[session_id] = bytearray()
            self.silence_durations[session_id] = 0

        self.buffers[session_id].extend(pcm_bytes)

        # Calculate chunk duration in milliseconds (16-bit mono = 2 bytes/sample)
        chunk_ms = int((len(pcm_bytes) / (self.sample_rate * 2)) * 1000)

        if is_speech:
            self.silence_durations[session_id] = 0
        else:
            self.silence_durations[session_id] += chunk_ms

    def is_utterance_complete(self, session_id: str) -> bool:
        if session_id not in self.buffers:
            return False
        has_audio = len(self.buffers[session_id]) > 0
        silence_exceeded = self.silence_durations[session_id] >= self.min_silence_ms
        return has_audio and silence_exceeded

    def flush(self, session_id: str) -> bytes:
        if session_id not in self.buffers:
            return b""
        data = bytes(self.buffers[session_id])
        self.buffers[session_id] = bytearray()
        self.silence_durations[session_id] = 0
        return data

    def clear(self, session_id: str):
        self.buffers.pop(session_id, None)
        self.silence_durations.pop(session_id, None)
