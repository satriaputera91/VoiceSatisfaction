import logging
from typing import Dict, Optional
from fastapi import WebSocket

logger = logging.getLogger("VoiceSatisfaction.WebSocketRegistry")


class WebSocketRegistry:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}

    def register(self, session_id: str, websocket: WebSocket):
        self.connections[session_id] = websocket
        logger.info(f"Registered WebSocket session: {session_id}")

    def unregister(self, session_id: str):
        if session_id in self.connections:
            del self.connections[session_id]
            logger.info(f"Unregistered WebSocket session: {session_id}")

    def get(self, session_id: str) -> Optional[WebSocket]:
        return self.connections.get(session_id)


# Global instance
registry = WebSocketRegistry()
