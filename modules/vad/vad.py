import logging
from typing import Tuple, Dict, Any
import numpy as np
import torch

logger = logging.getLogger("VoiceSatisfaction.VAD")


class SileroVAD:
    _instance = None
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            logger.info("Loading Silero VAD model via torch.hub...")
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
            )
            cls._model = model
            logger.info("Silero VAD model loaded successfully.")
        return cls._model

    def __init__(self, threshold: float = 0.5, sampling_rate: int = 16000):
        self.model = self.get_model()
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        self.iterators: Dict[str, Any] = {}

    def is_speech_chunk(self, pcm_bytes: bytes) -> Tuple[bool, float]:
        """Processes a single PCM audio chunk (16kHz 16-bit mono) and checks for speech."""
        if not pcm_bytes:
            return False, 0.0

        # Convert 16-bit PCM bytes to float32 tensor in range [-1.0, 1.0]
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        tensor = torch.from_numpy(audio_float32)

        # Silero VAD requires chunks of 512, 1024, or 1536 samples for 16kHz
        chunk_size = 512
        if len(tensor) < chunk_size:
            padded = torch.zeros(chunk_size, dtype=torch.float32)
            padded[: len(tensor)] = tensor
            tensor = padded

        confidences = []
        with torch.no_grad():
            for i in range(0, len(tensor) - chunk_size + 1, chunk_size):
                window = tensor[i : i + chunk_size]
                speech_prob = self.model(window, self.sampling_rate).item()
                confidences.append(speech_prob)

        if not confidences:
            return False, 0.0

        avg_confidence = float(np.mean(confidences))
        is_speech = avg_confidence >= self.threshold
        return is_speech, avg_confidence
