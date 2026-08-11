import asyncio
import json
import logging
from typing import Callable, Awaitable, Any, Type, TypeVar
from pydantic import BaseModel
import redis.asyncio as aioredis

logger = logging.getLogger("VoiceSatisfaction.Broker")

T = TypeVar("T", bound=BaseModel)


class StreamProducer:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def publish(self, stream: str, event: BaseModel, maxlen: int = 10000):
        data = {"payload": event.model_dump_json()}
        await self.redis.xadd(stream, data, maxlen=maxlen, approximate=True)


class StreamConsumer:
    def __init__(
        self,
        redis_client: aioredis.Redis,
        stream: str,
        group: str,
        consumer_name: str,
    ):
        self.redis = redis_client
        self.stream = stream
        self.group = group
        self.consumer_name = consumer_name

    async def init_group(self):
        try:
            await self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
            logger.info(f"Created consumer group {self.group} on stream {self.stream}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                pass
            else:
                logger.error(f"Error creating consumer group {self.group}: {e}")
                raise e

    async def start_consuming(
        self,
        schema_cls: Type[T],
        handler: Callable[[T], Awaitable[None]],
        batch_size: int = 10,
        block_ms: int = 2000,
    ):
        await self.init_group()

        # 1. Recover Pending Entries List (PEL) first
        logger.info(f"[{self.consumer_name}] Checking pending messages (PEL) on {self.stream}")
        try:
            pending_entries = await self.redis.xreadgroup(
                self.group,
                self.consumer_name,
                {self.stream: "0"},
                count=batch_size,
            )
            if pending_entries:
                for _, entries in pending_entries:
                    for msg_id, data in entries:
                        await self._process_entry(msg_id, data, schema_cls, handler)
        except Exception as e:
            logger.warning(f"Error processing PEL for {self.stream}: {e}")

        # 2. Main loop for new messages
        logger.info(f"[{self.consumer_name}] Listening for new messages on {self.stream}")
        while True:
            try:
                streams = await self.redis.xreadgroup(
                    self.group,
                    self.consumer_name,
                    {self.stream: ">"},
                    count=batch_size,
                    block=block_ms,
                )
                if streams:
                    for _, entries in streams:
                        for msg_id, data in entries:
                            await self._process_entry(msg_id, data, schema_cls, handler)
            except asyncio.CancelledError:
                logger.info(f"Consumer {self.consumer_name} on {self.stream} cancelled.")
                break
            except Exception as e:
                logger.error(f"Error reading stream {self.stream}: {e}")
                await asyncio.sleep(1)

    async def _process_entry(
        self,
        msg_id: str,
        data: dict,
        schema_cls: Type[T],
        handler: Callable[[T], Awaitable[None]],
    ):
        try:
            raw_payload = data.get("payload") or data.get(b"payload")
            if isinstance(raw_payload, bytes):
                raw_payload = raw_payload.decode("utf-8")
            payload_dict = json.loads(raw_payload)
            event = schema_cls.model_validate(payload_dict)
            await handler(event)
            await self.redis.xack(self.stream, self.group, msg_id)
        except Exception as e:
            logger.error(f"Error processing msg_id {msg_id} on {self.stream}: {e}")
            # Acknowledge to avoid blocking stream processing in retry loop
            await self.redis.xack(self.stream, self.group, msg_id)
