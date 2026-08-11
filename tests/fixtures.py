import os
import numpy as np

INTENT_AUDIO_MAP = {
    "sangat_tidak_puas": "tests/audio/sangat_tidak_puas.wav",
    "tidak_puas": "tests/audio/tidak_puas.wav",
    "cukup_puas": "tests/audio/cukup_puas.wav",
    "puas": "tests/audio/puas.wav",
    "sangat_puas": "tests/audio/sangat_puas.wav",
}


def generate_synthetic_speech_pcm(duration_sec: float = 3.0, sample_rate: int = 16000) -> bytes:
    """
    Generates a louder multi-frequency sine signal that resembles voiced speech
    so Silero VAD reliably classifies it as speech (not silence).
    Uses formant frequencies similar to Indonesian vowels.
    """
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), False)

    # Fundamental + harmonics at voice-like amplitudes (full scale)
    signal = (
        0.6 * np.sin(2 * np.pi * 200 * t)   # F0 (fundamental)
        + 0.5 * np.sin(2 * np.pi * 400 * t)  # 2nd harmonic
        + 0.4 * np.sin(2 * np.pi * 800 * t)  # 3rd harmonic (F1 formant area)
        + 0.3 * np.sin(2 * np.pi * 1200 * t) # F2 formant area
        + 0.2 * np.sin(2 * np.pi * 2400 * t) # F3 formant area
    )

    # Normalize to near full int16 range
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak * 0.95

    audio_int16 = (signal * 32767).astype(np.int16)
    return audio_int16.tobytes()


def generate_pcm_audio(intent: str) -> bytes:
    """
    Loads pre-recorded 16kHz mono PCM WAV for the given intent if available.
    Falls back to synthetic speech-like PCM audio for CI/testing.
    """
    file_path = INTENT_AUDIO_MAP.get(intent)
    if file_path and os.path.exists(file_path):
        import soundfile as sf
        data, sr = sf.read(file_path, dtype="int16")
        assert sr == 16000, "Audio fixtures must be 16kHz"
        return data.tobytes()

    # Fallback: generate 3 seconds of voice-like synthetic audio
    return generate_synthetic_speech_pcm(duration_sec=3.0)
