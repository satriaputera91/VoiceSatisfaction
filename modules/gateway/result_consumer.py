import json
import logging
import redis.asyncio as aioredis
from modules.shared.events import STREAM_RESULT, GROUP_GATEWAY
from modules.shared.schemas import CommandResultEvent
from modules.shared.broker import StreamConsumer
from modules.gateway.session import registry

logger = logging.getLogger("VoiceSatisfaction.ResultConsumer")


class GatewayResultConsumer:
    def __init__(self, redis_client: aioredis.Redis, consumer_name: str = "gateway-1"):
        self.consumer = StreamConsumer(
            redis_client=redis_client,
            stream=STREAM_RESULT,
            group=GROUP_GATEWAY,
            consumer_name=consumer_name,
        )

    async def handle_result_event(self, event: CommandResultEvent):
        ws = registry.get(event.session_id)
        if ws:
            response_payload = {
                "question": event.question,
                "status": event.status,
                "intent": event.intent,
                "score": event.score,
                "confidence": event.confidence,
                "transcript": event.transcript,
            }
            try:
                await ws.send_json(response_payload)
                logger.info(
                    f"Sent result to session {event.session_id}: Q{event.question} -> {event.intent} (score={event.score})"
                )
            except Exception as e:
                logger.error(f"Error sending payload to session {event.session_id}: {e}")
        else:
            logger.warning(f"No active WebSocket found for session {event.session_id}")

    async def run(self):
        await self.consumer.start_consuming(
            schema_cls=CommandResultEvent,
            handler=self.handle_result_event,
        )
