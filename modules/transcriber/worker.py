import base64
import logging
import redis.asyncio as aioredis
from modules.shared.events import STREAM_SPEECH_AUDIO, STREAM_TRANSCRIPT, GROUP_TRANSCRIBER
from modules.shared.schemas import SpeechAudioEvent, TranscriptEvent
from modules.shared.broker import StreamProducer, StreamConsumer
from modules.transcriber.transcriber import WhisperTranscriber

logger = logging.getLogger("VoiceSatisfaction.TranscriberWorker")


class TranscriberWorker:
    def __init__(
        self,
        redis_client: aioredis.Redis,
        consumer_name: str,
        whisper_model: str = "tiny",
        whisper_device: str = "cpu",
        whisper_compute_type: str = "int8",
        language: str = "",
    ):
        self.producer = StreamProducer(redis_client)
        self.consumer = StreamConsumer(
            redis_client=redis_client,
            stream=STREAM_SPEECH_AUDIO,
            group=GROUP_TRANSCRIBER,
            consumer_name=consumer_name,
        )
        self.transcriber = WhisperTranscriber(
            model_size=whisper_model,
            device=whisper_device,
            compute_type=whisper_compute_type,
            language=language if language else None,
        )

    async def handle_speech_audio(self, event: SpeechAudioEvent):
        try:
            pcm_bytes = base64.b64decode(event.pcm_bytes_b64)
        except Exception as e:
            logger.error(f"Failed to decode base64 speech audio for session {event.session_id}: {e}")
            return

        transcript = await self.transcriber.transcribe(
            pcm_bytes,
            sample_rate=event.sample_rate,
        )

        if transcript:
            transcript_event = TranscriptEvent(
                session_id=event.session_id,
                question=event.question,
                transcript=transcript,
                is_final=True,
                vad_confidence=event.vad_confidence,
                audio_duration_ms=event.audio_duration_ms,
            )
            await self.producer.publish(STREAM_TRANSCRIPT, transcript_event)
            logger.info(
                f"Published transcript for session {event.session_id}, Q{event.question}: {transcript!r}"
            )

    async def run(self):
        await self.consumer.start_consuming(
            schema_cls=SpeechAudioEvent,
            handler=self.handle_speech_audio,
        )
