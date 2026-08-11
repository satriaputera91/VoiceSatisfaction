import base64
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from modules.shared.events import STREAM_AUDIO, STREAM_TEXT
from modules.shared.schemas import AudioChunkEvent, TextInputEvent
from modules.shared.broker import StreamProducer
from modules.gateway.session import registry
from modules.session_manager.store import SessionStore
from modules.command_service.registry import SATISFACTION_INTENTS, GENERAL_TELEPHONY_INTENTS

logger = logging.getLogger("VoiceSatisfaction.GatewayRouter")

router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    redis_client = request.app.state.redis
    try:
        await redis_client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    return {
        "status": "ok" if redis_ok else "unhealthy",
        "redis": redis_ok,
    }


@router.get("/sessions")
async def active_sessions():
    return {
        "active_sessions": list(registry.connections.keys()),
        "count": len(registry.connections),
    }


@router.get("/commands")
async def list_commands():
    intents = []
    for intent, score, phrases in SATISFACTION_INTENTS + GENERAL_TELEPHONY_INTENTS:
        intents.append({
            "intent": intent,
            "score": score,
            "sample_phrases": phrases,
        })
    return {"intents": intents}


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    registry.register(session_id, websocket)

    redis_client = websocket.app.state.redis
    producer = StreamProducer(redis_client)
    session_store = SessionStore(redis_client)

    chunk_index = 0
    current_question = 1

    try:
        while True:
            message = await websocket.receive()
            if "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                    if "question" in payload:
                        current_question = int(payload["question"])
                        await session_store.update_session(
                            session_id,
                            {"current_question": current_question},
                        )

                        # Publish text question event signal
                        text_event = TextInputEvent(
                            session_id=session_id,
                            question=current_question,
                            text=payload.get("text"),
                        )
                        await producer.publish(STREAM_TEXT, text_event)

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received from session {session_id}: {message['text']}")

            elif "bytes" in message and message["bytes"]:
                pcm_bytes = message["bytes"]
                chunk_index += 1

                # Retrieve active session context
                session_data = await session_store.get_session(session_id)
                q_num = session_data.get("current_question", current_question)

                b64_audio = base64.b64encode(pcm_bytes).decode("utf-8")
                audio_event = AudioChunkEvent(
                    session_id=session_id,
                    question=q_num,
                    chunk_index=chunk_index,
                    pcm_bytes_b64=b64_audio,
                )
                await producer.publish(STREAM_AUDIO, audio_event)

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error in session {session_id}: {e}")
    finally:
        registry.unregister(session_id)
        await session_store.delete_session(session_id)
