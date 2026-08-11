import json
import logging
from typing import Optional, Dict, Any
import redis.asyncio as aioredis

logger = logging.getLogger("VoiceSatisfaction.SessionStore")


class SessionStore:
    def __init__(self, redis_client: aioredis.Redis, ttl_seconds: int = 1800):
        self.redis = redis_client
        self.ttl = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"vs:session:{session_id}"

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        data = await self.redis.get(self._key(session_id))
        if data:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data)
        return {"current_question": 1}

    async def update_session(self, session_id: str, updates: Dict[str, Any]):
        session = await self.get_session(session_id)
        session.update(updates)
        await self.redis.setex(
            self._key(session_id),
            self.ttl,
            json.dumps(session),
        )

    async def delete_session(self, session_id: str):
        await self.redis.delete(self._key(session_id))
