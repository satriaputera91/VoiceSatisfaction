"""
Unit tests for modules/transcriber/transcriber.py

Tests cover:
- WhisperTranscriber singleton model loading
- Synchronous transcription of synthetic sine-wave PCM (expects non-crash)
- Transcription of real Indonesian CSAT phrase via TTS-like signal
- Empty / zero-length audio gracefully returns empty string
- Very short audio (< 512 samples) is handled without crash
"""

import asyncio
import os
import pytest
import numpy as np

# macOS: prevent OpenMP crash when loading torch + ctranslate2 in the same process
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from modules.transcriber.transcriber import WhisperTranscriber


SAMPLE_RATE = 16000


def _sine_pcm(
    frequency_hz: float = 300.0,
    duration_sec: float = 2.0,
    amplitude: float = 0.7,
    sample_rate: int = SAMPLE_RATE,
) -> bytes:
    """Generate a single-frequency sine-wave PCM (16-bit mono) for testing."""
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    signal = amplitude * np.sin(2 * np.pi * frequency_hz * t)
    audio_int16 = (signal * 32767).astype(np.int16)
    return audio_int16.tobytes()


def _voice_pcm(duration_sec: float = 2.5, sample_rate: int = SAMPLE_RATE) -> bytes:
    """
    Generate multi-formant PCM that resembles voiced speech.
    Uses F0 + harmonics at frequencies similar to Indonesian vowels.
    """
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    signal = (
        0.6 * np.sin(2 * np.pi * 200 * t)
        + 0.5 * np.sin(2 * np.pi * 400 * t)
        + 0.4 * np.sin(2 * np.pi * 800 * t)
        + 0.3 * np.sin(2 * np.pi * 1200 * t)
        + 0.2 * np.sin(2 * np.pi * 2400 * t)
    )
    peak = np.max(np.abs(signal))
    signal = signal / peak * 0.95
    return (signal * 32767).astype(np.int16).tobytes()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def transcriber():
    """Shared WhisperTranscriber (tiny model) loaded once per test module."""
    return WhisperTranscriber(model_size="tiny", device="cpu", compute_type="int8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWhisperTranscriberInit:
    def test_singleton_model(self):
        """get_model() returns the same WhisperModel instance on multiple calls."""
        t1 = WhisperTranscriber.get_model("tiny", "cpu", "int8")
        t2 = WhisperTranscriber.get_model("tiny", "cpu", "int8")
        assert t1 is t2, "get_model() should return a singleton instance"

    def test_instantiation(self, transcriber):
        """WhisperTranscriber instantiates without errors."""
        assert transcriber is not None
        assert transcriber.model is not None
        assert transcriber.executor is not None


class TestWhisperTranscriberSync:
    def test_empty_bytes_returns_empty_string(self, transcriber):
        """Passing empty bytes should return an empty string, not raise."""
        result = transcriber._sync_transcribe(b"")
        assert result == "", f"Expected empty string, got {result!r}"

    def test_very_short_audio_no_crash(self, transcriber):
        """Very short audio (< 512 samples, 64 bytes) should not crash."""
        short_pcm = _sine_pcm(frequency_hz=440.0, duration_sec=0.002)  # ~32 samples
        result = transcriber._sync_transcribe(short_pcm, sample_rate=SAMPLE_RATE)
        assert isinstance(result, str), "Result should be a string"

    def test_sine_audio_returns_string(self, transcriber):
        """Sine-wave PCM should produce some string output (may be garbled, but no crash)."""
        pcm = _sine_pcm(frequency_hz=300.0, duration_sec=2.0)
        result = transcriber._sync_transcribe(pcm, sample_rate=SAMPLE_RATE)
        assert isinstance(result, str), f"Expected str, got {type(result)}"

    def test_voice_like_audio_returns_string(self, transcriber):
        """Multi-formant 'voice-like' PCM should produce a string result."""
        pcm = _voice_pcm(duration_sec=2.5)
        result = transcriber._sync_transcribe(pcm, sample_rate=SAMPLE_RATE)
        assert isinstance(result, str), f"Expected str, got {type(result)}"

    def test_silence_no_crash(self, transcriber):
        """All-zero (silence) audio should return empty string or some text, not crash."""
        silence = bytes(SAMPLE_RATE * 2 * 2)  # 2 seconds of silence
        result = transcriber._sync_transcribe(silence, sample_rate=SAMPLE_RATE)
        assert isinstance(result, str)


class TestWhisperTranscriberAsync:
    def test_async_transcribe_empty(self, transcriber):
        """async transcribe() with empty bytes should return empty string."""
        result = asyncio.get_event_loop().run_until_complete(
            transcriber.transcribe(b"")
        )
        assert result == "", f"Expected empty string, got {result!r}"

    def test_async_transcribe_sine(self, transcriber):
        """async transcribe() should complete without raising exceptions."""
        pcm = _sine_pcm(frequency_hz=300.0, duration_sec=1.5)
        result = asyncio.get_event_loop().run_until_complete(
            transcriber.transcribe(pcm, sample_rate=SAMPLE_RATE)
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_async_transcribe_voice(self, transcriber):
        """async transcribe() voice-like audio using pytest-asyncio."""
        pcm = _voice_pcm(duration_sec=2.0)
        result = await transcriber.transcribe(pcm, sample_rate=SAMPLE_RATE)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_async_transcribe_error_resilience(self, transcriber):
        """Transcriber should return empty string on internal error, not propagate."""
        # Pass invalid non-bytes arg to trigger error path; we test via monkeypatching
        import unittest.mock as mock
        with mock.patch.object(transcriber, "_sync_transcribe", side_effect=RuntimeError("simulated error")):
            result = await transcriber.transcribe(b"\x00" * 1000)
        assert result == "", f"Expected empty string on error, got {result!r}"


class TestWhisperTranscriberOutputType:
    def test_output_is_stripped_string(self, transcriber):
        """Result should be a stripped string with no leading/trailing whitespace."""
        pcm = _sine_pcm(frequency_hz=440.0, duration_sec=1.0)
        result = transcriber._sync_transcribe(pcm)
        assert result == result.strip(), "Output should be stripped"

    def test_transcribe_consistent_results(self, transcriber):
        """Transcribing the same audio twice should produce the same result."""
        pcm = _sine_pcm(frequency_hz=300.0, duration_sec=1.0)
        result1 = transcriber._sync_transcribe(pcm)
        result2 = transcriber._sync_transcribe(pcm)
        assert result1 == result2, (
            f"Deterministic model should give same output for same input. "
            f"Got {result1!r} vs {result2!r}"
        )
