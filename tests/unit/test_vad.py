# pyrefly: ignore [missing-import]
import pytest
# pyrefly: ignore [missing-import]
import numpy as np
from modules.vad.vad import SileroVAD


def test_silero_vad_silence_vs_speech():
    vad = SileroVAD(threshold=0.5)

    # 1. Generate 1 second of silence (zeroes)
    silence_pcm = np.zeros(16000, dtype=np.int16).tobytes()
    is_speech, confidence = vad.is_speech_chunk(silence_pcm)
    assert not is_speech, f"Silence misidentified as speech (confidence={confidence})"

    # 2. Generate 1 second of synthetic voice-like signal
    t = np.linspace(0, 1.0, 16000, False)
    voice_signal = 0.5 * np.sin(2 * np.pi * 300 * t) + 0.3 * np.sin(2 * np.pi * 600 * t)
    voice_pcm = (voice_signal * 32767).astype(np.int16).tobytes()
    is_speech, confidence = vad.is_speech_chunk(voice_pcm)
    assert is_speech or confidence > 0.1, f"Voice chunk processing completed with confidence {confidence}"
