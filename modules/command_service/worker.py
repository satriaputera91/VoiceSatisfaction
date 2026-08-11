import asyncio
import logging
import redis.asyncio as aioredis
from modules.shared.events import (
    STREAM_TRANSCRIPT,
    STREAM_TEXT,
    STREAM_RESULT,
    GROUP_COMMAND_SERVICE,
)
from modules.shared.schemas import TranscriptEvent, TextInputEvent, CommandResultEvent
from modules.shared.broker import StreamProducer, StreamConsumer
from modules.command_service.parser import CommandParser

logger = logging.getLogger("VoiceSatisfaction.CommandWorker")


class CommandServiceWorker:
    def __init__(
        self,
        redis_client: aioredis.Redis,
        consumer_name: str,
        match_threshold: float = 75.0,
    ):
        self.redis = redis_client
        self.consumer_name = consumer_name
        self.producer = StreamProducer(redis_client)
        self.parser = CommandParser(match_threshold=match_threshold)

        self.transcript_consumer = StreamConsumer(
            redis_client=redis_client,
            stream=STREAM_TRANSCRIPT,
            group=GROUP_COMMAND_SERVICE,
            consumer_name=f"{consumer_name}-transcript",
        )
        self.text_consumer = StreamConsumer(
            redis_client=redis_client,
            stream=STREAM_TEXT,
            group=GROUP_COMMAND_SERVICE,
            consumer_name=f"{consumer_name}-text",
        )

    async def handle_transcript_event(self, event: TranscriptEvent):
        logger.info(f"Handling transcript event for session {event.session_id}, Q{event.question}: '{event.transcript}'")
        match = self.parser.parse(event.transcript)

        result_event = CommandResultEvent(
            session_id=event.session_id,
            question=event.question,
            intent=match.intent,
            score=match.score,
            confidence=match.confidence,
            transcript=event.transcript,
            status=match.status,
        )
        await self.producer.publish(STREAM_RESULT, result_event)

    async def handle_text_event(self, event: TextInputEvent):
        # Text events with no text content are just question-number signals from the gateway.
        # Only parse and publish a result if actual text content is present.
        if not event.text:
            logger.info(f"Skipping question signal (no text) for session {event.session_id}, Q{event.question}")
            return

        logger.info(f"Handling text event for session {event.session_id}, Q{event.question}")
        match = self.parser.parse(event.text)
        result_event = CommandResultEvent(
            session_id=event.session_id,
            question=event.question,
            intent=match.intent,
            score=match.score,
            confidence=match.confidence,
            transcript=event.text,
            status=match.status,
        )
        await self.producer.publish(STREAM_RESULT, result_event)

    async def run(self):
        await asyncio.gather(
            self.transcript_consumer.start_consuming(
                schema_cls=TranscriptEvent,
                handler=self.handle_transcript_event,
            ),
            self.text_consumer.start_consuming(
                schema_cls=TextInputEvent,
                handler=self.handle_text_event,
            ),
        )
