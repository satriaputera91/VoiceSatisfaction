import os
import asyncio
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
import redis.asyncio as aioredis

# Must be set before torch/ctranslate2/onnxruntime load their OpenMP libs on macOS
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from app.settings import settings
from modules.gateway.router import router as gateway_router
from modules.gateway.result_consumer import GatewayResultConsumer
from modules.vad.worker import VADWorker
from modules.transcriber.worker import TranscriberWorker
from modules.command_service.worker import CommandServiceWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("VoiceSatisfaction.Main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing VoiceSatisfaction Modular Monolith...")
    app.state.redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=False,
    )

    # Pre-load ML models during startup so workers start without delay
    from modules.vad.vad import SileroVAD
    from modules.transcriber.transcriber import WhisperTranscriber
    SileroVAD.get_model()
    WhisperTranscriber.get_model(
        model_size=settings.WHISPER_MODEL,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
    )

    worker_tasks = []

    # 1. Start VAD workers (consume vs:audio → produce vs:speech_audio)
    for i in range(settings.VAD_WORKER_COUNT):
        worker = VADWorker(
            redis_client=app.state.redis,
            consumer_name=f"vad-worker-{i+1}",
            vad_threshold=settings.VAD_THRESHOLD,
            min_silence_ms=settings.VAD_MIN_SILENCE_MS,
        )
        task = asyncio.create_task(worker.run())
        worker_tasks.append(task)
        logger.info(f"Started VADWorker {i+1}")

    # 2. Start Transcriber workers (consume vs:speech_audio → produce vs:transcript)
    for i in range(settings.TRANSCRIBER_WORKER_COUNT):
        worker = TranscriberWorker(
            redis_client=app.state.redis,
            consumer_name=f"transcriber-worker-{i+1}",
            whisper_model=settings.WHISPER_MODEL,
            whisper_device=settings.WHISPER_DEVICE,
            whisper_compute_type=settings.WHISPER_COMPUTE_TYPE,
            language=settings.WHISPER_LANGUAGE,
        )
        task = asyncio.create_task(worker.run())
        worker_tasks.append(task)
        logger.info(f"Started TranscriberWorker {i+1}")

    # 3. Start Command Service workers (consume vs:transcript + vs:text → produce vs:result)
    for i in range(settings.COMMAND_WORKER_COUNT):
        worker = CommandServiceWorker(
            redis_client=app.state.redis,
            consumer_name=f"command-worker-{i+1}",
            match_threshold=settings.COMMAND_MATCH_THRESHOLD,
        )
        task = asyncio.create_task(worker.run())
        worker_tasks.append(task)
        logger.info(f"Started CommandServiceWorker {i+1}")

    # 4. Start Gateway Result Consumer (consume vs:result → push to WebSocket)
    gateway_consumer = GatewayResultConsumer(
        redis_client=app.state.redis,
        consumer_name="gateway-result-consumer",
    )
    result_task = asyncio.create_task(gateway_consumer.run())
    worker_tasks.append(result_task)
    logger.info("Started GatewayResultConsumer")

    yield

    logger.info("Shutting down VoiceSatisfaction application...")
    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    await app.state.redis.aclose()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="VoiceSatisfaction API",
    description="Voice Command Detection & Satisfaction Analysis for Telephony",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(gateway_router)
