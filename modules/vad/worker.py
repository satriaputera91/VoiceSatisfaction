import base64
import logging
import redis.asyncio as aioredis
from modules.shared.events import STREAM_AUDIO, STREAM_SPEECH_AUDIO, GROUP_VAD
from modules.shared.schemas import AudioChunkEvent, SpeechAudioEvent
from modules.shared.broker import StreamProducer, StreamConsumer
from modules.vad.vad import SileroVAD
from modules.vad.audio_buffer import SessionAudioBuffer

logger = logging.getLogger("VoiceSatisfaction.VADWorker")


class VADWorker:
    def __init__(
        self,
        redis_client: aioredis.Redis,
        consumer_name: str,
        vad_threshold: float = 0.5,
        min_silence_ms: int = 300,
    ):
        self.producer = StreamProducer(redis_client)
        self.consumer = StreamConsumer(
            redis_client=redis_client,
            stream=STREAM_AUDIO,
            group=GROUP_VAD,
            consumer_name=consumer_name,
        )
        self.vad = SileroVAD(threshold=vad_threshold)
        self.audio_buffer = SessionAudioBuffer(min_silence_duration_ms=min_silence_ms)

    async def handle_audio_chunk(self, event: AudioChunkEvent):
        try:
            pcm_bytes = base64.b64decode(event.pcm_bytes_b64)
        except Exception as e:
            logger.error(f"Failed to decode base64 pcm_bytes for session {event.session_id}: {e}")
            return

        is_speech, confidence = self.vad.is_speech_chunk(pcm_bytes)
        self.audio_buffer.append(event.session_id, pcm_bytes, is_speech)

        if self.audio_buffer.is_utterance_complete(event.session_id):
            speech_pcm = self.audio_buffer.flush(event.session_id)
            if speech_pcm:
                b64_pcm = base64.b64encode(speech_pcm).decode("utf-8")
                duration_ms = int((len(speech_pcm) / (event.sample_rate * 2)) * 1000)

                speech_event = SpeechAudioEvent(
                    session_id=event.session_id,
                    question=event.question,
                    pcm_bytes_b64=b64_pcm,
                    sample_rate=event.sample_rate,
                    vad_confidence=confidence,
                    audio_duration_ms=duration_ms,
                )
                await self.producer.publish(STREAM_SPEECH_AUDIO, speech_event)
                logger.info(
                    f"VAD detected speech utterance for session {event.session_id}, "
                    f"Q{event.question} ({duration_ms}ms)"
                )

    async def run(self):
        await self.consumer.start_consuming(
            schema_cls=AudioChunkEvent,
            handler=self.handle_audio_chunk,
        )
