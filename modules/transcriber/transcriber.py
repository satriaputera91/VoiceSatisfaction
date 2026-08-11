import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Optional
import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger("VoiceSatisfaction.Transcriber")


class WhisperTranscriber:
    _instance = None
    _model = None

    @classmethod
    def get_model(
        cls,
        model_size: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        if cls._model is None:
            logger.info(f"Loading faster-whisper model ({model_size}) on {device}...")
            cls._model = WhisperModel(
                model_size_or_path=model_size,
                device=device,
                compute_type=compute_type,
            )
            logger.info("faster-whisper model loaded successfully.")
        return cls._model

    def __init__(
        self,
        model_size: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = None,
    ):
        self.model = self.get_model(model_size, device, compute_type)
        self.language = language if language else None
        self.executor = ThreadPoolExecutor(max_workers=2)

    def _sync_transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        if not pcm_bytes:
            return ""

        # Convert 16-bit PCM bytes to float32 numpy array normalized to [-1.0, 1.0]
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        if len(audio_float32) == 0:
            return ""

        segments, _ = self.model.transcribe(
            audio_float32,
            beam_size=5,
            language=self.language,
            task="transcribe",
            vad_filter=False,
        )

        texts = [segment.text.strip() for segment in segments if segment.text]
        full_text = " ".join(texts).strip()
        logger.info(f"Transcribed text: {full_text!r}")
        return full_text

    async def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                self.executor,
                self._sync_transcribe,
                pcm_bytes,
                sample_rate,
            )
        except Exception as e:
            logger.error(f"Transcription error (non-fatal): {e}")
            return ""
