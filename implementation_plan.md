# VoiceSatisfaction — Modular Monolith with Redis Streams

Voice command detection & satisfaction analysis for telephony customers.
Built as a **modular monolith** — all modules in a single deployable unit today,
with clean boundaries that allow any module to be extracted into an independent microservice tomorrow.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         VoiceSatisfaction (Monolith Boundary)                    │
│                                                                                  │
│  ┌──────────────────┐      Redis Streams (Message Broker)                        │
│  │   Module: Gateway│ ──[vs:audio]──▶ ┌───────────────────────────────────────┐ │
│  │  (FastAPI WS/HTTP│                 │     Module: Speech Engine             │ │
│  │   API Entrypoint)│ ◀─[vs:result]── │  (VAD + Whisper workers, isolated)    │ │
│  │                  │                 │  Consumer Group: cg:speech_engine      │ │
│  │  ┌─────────────┐ │                 └──────────────┬────────────────────────┘ │
│  │  │Session State│ │                                │ [vs:transcript]           │
│  │  │  (Redis)    │ │                                ▼                           │
│  └──────────────────┘                 ┌───────────────────────────────────────┐ │
│                                       │     Module: Command Service           │ │
│  ┌──────────────────┐                 │  (Parser + RapidFuzz workers)         │ │
│  │  Module: Session │                 │  Consumer Group: cg:command_service   │ │
│  │  Manager         │                 └──────────────┬────────────────────────┘ │
│  │  (WS registry,   │                                │ [vs:result]              │
│  │   active session │◀───────────────────────────────┘                          │
│  │   context)       │                                                            │
│  └──────────────────┘                                                            │
│                                                                                  │
│  ┌─────────────────────────────────────────┐                                     │
│  │         Module: Shared                  │                                     │
│  │  (Events, Schemas, Broker abstraction)  │                                     │
│  └─────────────────────────────────────────┘                                     │
└──────────────────────────────────────────────────────────────────────────────────┘
                        │                    ▲
                  WebSocket (bytes/JSON)     │ JSON responses
                        │                    │
                   Telephony Client / Test Client
```

### Why Redis Streams (not Pub/Sub)

| Feature | Redis Pub/Sub | Redis Streams + Consumer Groups |
|---|---|---|
| Delivery guarantee | Fire-and-forget (at-most-once) | At-least-once (with XACK) |
| Persistence | None — lost on subscriber disconnect | Durable — survives restarts |
| Load balancing | Broadcasts to **all** consumers | **One** consumer per message |
| Horizontal scaling | ❌ No | ✅ Add workers to consumer group |
| Fault recovery (PEL) | ❌ No | ✅ Pending Entries List |
| Backpressure | ❌ No | ✅ Configurable MAXLEN |

---

## Stream Topology

| Stream Key | Producer | Consumer Group | Description |
|---|---|---|---|
| `vs:audio` | Gateway | `cg:speech_engine` | Raw PCM chunks per session |
| `vs:text` | Gateway | `cg:command_service` | Text question inputs |
| `vs:transcript` | Speech Engine | `cg:command_service` | Whisper transcription results |
| `vs:result` | Command Service | `cg:gateway` | Final parsed command + confidence |

Each message carries a `session_id` field so the Gateway can route responses back to the correct WebSocket client.

---

## Project Structure

```
VoiceSatisfaction/
├── modules/
│   ├── gateway/                    # Module: API Gateway
│   │   ├── __init__.py
│   │   ├── router.py               # WebSocket + REST routes
│   │   ├── session.py              # In-memory WS connection registry
│   │   └── result_consumer.py     # Subscribes vs:result → push to WS client
│   │
│   ├── speech_engine/              # Module: Speech Processing (isolated)
│   │   ├── __init__.py
│   │   ├── vad.py                  # Silero VAD wrapper (per-session VADIterator)
│   │   ├── transcriber.py          # faster-whisper tiny (int8/CPU)
│   │   ├── audio_buffer.py         # PCM chunk accumulator + speech segmentation
│   │   └── worker.py               # Redis consumer: reads vs:audio → writes vs:transcript
│   │
│   ├── command_service/            # Module: Command Parsing
│   │   ├── __init__.py
│   │   ├── registry.py             # Intent definitions + phrase aliases
│   │   ├── matcher.py              # RapidFuzz fuzzy matcher
│   │   ├── parser.py               # Pre-processing + context-aware parse logic
│   │   └── worker.py               # Redis consumer: reads vs:transcript+vs:text → writes vs:result
│   │
│   ├── session_manager/            # Module: Session State
│   │   ├── __init__.py
│   │   └── store.py                # Redis-backed session context (IVR menu state)
│   │
│   └── shared/                     # Module: Shared Contracts (no business logic)
│       ├── __init__.py
│       ├── events.py               # Event type constants + stream key names
│       ├── schemas.py              # Pydantic models for all stream messages
│       └── broker.py               # Redis Streams producer/consumer abstraction
│
├── app/
│   ├── main.py                     # App factory: wires lifespan, mounts routers
│   └── settings.py                 # Pydantic Settings (reads .env)
│
├── client/
│   └── test_client.py              # Async WebSocket test client (text + PCM audio)
│
├── tests/
│   ├── unit/
│   │   ├── test_vad.py
│   │   ├── test_transcriber.py
│   │   └── test_command_parser.py
│   ├── integration/
│   │   └── test_websocket.py
│   └── scenarios/
│       └── test_satisfaction_survey.py   # 5-question satisfaction scenario test
│
├── docker-compose.yml              # Redis + app services
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

---

## Module Contracts (Shared Events)

### Stream Message Schemas (Pydantic)

```python
# AudioChunkEvent  →  vs:audio
class AudioChunkEvent(BaseModel):
    session_id: str
    question: int             # current survey question number (1-based)
    chunk_index: int
    pcm_bytes_b64: str        # base64-encoded 16kHz mono PCM
    sample_rate: int = 16000
    timestamp_ms: int

# TranscriptEvent  →  vs:transcript
class TranscriptEvent(BaseModel):
    session_id: str
    question: int             # passed through from AudioChunkEvent
    transcript: str
    is_final: bool            # True = end-of-utterance detected by VAD
    vad_confidence: float
    audio_duration_ms: int

# TextInputEvent  →  vs:text  (sent first, before audio)
class TextInputEvent(BaseModel):
    session_id: str
    question: int             # survey question number e.g. 1, 2, 3 …

# CommandResultEvent  →  vs:result  (WebSocket response to client)
class CommandResultEvent(BaseModel):
    session_id: str
    question: int             # mirrors the question number sent by client
    intent: str               # Indonesian satisfaction label (see registry)
    score: int                # Likert score 1–5 (0 if unknown)
    confidence: float         # 0.0 – 100.0 (RapidFuzz score)
    transcript: str           # Whisper output (empty for direct text inputs)
    status: str               # "success" | "low_confidence" | "unknown"
```

---

## Proposed Changes

### Component 1: Shared Infrastructure

#### [NEW] [shared/events.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/shared/events.py)
Stream key constants and event type enums. **No module may hardcode stream names** — always import from here.
```python
STREAM_AUDIO      = "vs:audio"
STREAM_TEXT       = "vs:text"
STREAM_TRANSCRIPT = "vs:transcript"
STREAM_RESULT     = "vs:result"

GROUP_SPEECH_ENGINE   = "cg:speech_engine"
GROUP_COMMAND_SERVICE = "cg:command_service"
GROUP_GATEWAY         = "cg:gateway"
```

#### [NEW] [shared/broker.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/shared/broker.py)
Redis Streams abstraction — encapsulates `XADD`, `XREADGROUP`, `XACK`, `XGROUP CREATE`:
- `StreamProducer.publish(stream, event, maxlen=10_000)`
- `StreamConsumer.consume(stream, group, consumer_name, handler_coro)` — blocking loop with PEL recovery on startup
- Handles `BUSYGROUP` error on group creation (idempotent)
- Structured logging with `trace_id` propagated from event

#### [NEW] [shared/schemas.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/shared/schemas.py)
All Pydantic v2 models for stream messages and WebSocket payloads (listed in contracts above).

---

### Component 2: Gateway Module

#### [NEW] [gateway/router.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/gateway/router.py)
**Single unified WebSocket endpoint** (text + audio on same connection — matches real telephony flow):
- **`/ws/{session_id}`** — multiplexed endpoint:
  - JSON frame received → parsed as `TextInputEvent` (question number signal) → published to `vs:text`
  - Binary frame received → treated as raw PCM chunk → published to `vs:audio` (with `question` carried from session state)
  - Inbound frames are correlated by `question` field stored in session context

REST endpoints:
- `GET /health` — liveness + Redis ping
- `GET /sessions` — active session count
- `GET /commands` — list registered intents and scores

#### [NEW] [gateway/session.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/gateway/session.py)
In-memory `WebSocketRegistry`: `session_id → WebSocket` mapping. Used by `result_consumer` to route responses.

#### [NEW] [gateway/result_consumer.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/gateway/result_consumer.py)
Background asyncio task (started in `lifespan`):
- Consumes `vs:result` stream (consumer group `cg:gateway`)
- Looks up `session_id` in `WebSocketRegistry`
- Sends `CommandResultEvent` as JSON to the correct WebSocket client
- `XACK`s message after successful send

---

### Component 3: Speech Engine Module

#### [NEW] [speech_engine/vad.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/speech_engine/vad.py)
Silero VAD wrapper:
- Singleton model loaded once at startup via `torch.hub.load`
- Per-session `VADIterator` (maintains silence/speech state across chunks)
- `process(pcm_bytes) → (is_speech: bool, confidence: float, is_end_of_speech: bool)`
- 16kHz, mono, 16-bit PCM → float32 tensor; configurable `threshold` & `min_silence_ms`

#### [NEW] [speech_engine/audio_buffer.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/speech_engine/audio_buffer.py)
Per-session audio accumulator:
- Collects PCM chunks during active speech
- Emits complete utterance buffer on `is_end_of_speech=True`
- Drops silence-only buffers to avoid Whisper hallucinations

#### [NEW] [speech_engine/transcriber.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/speech_engine/transcriber.py)
faster-whisper transcriber:
- `WhisperModel("tiny", device="cpu", compute_type="int8")` singleton
- `transcribe(pcm_bytes: bytes) → str` — runs in `ThreadPoolExecutor` (CPU-bound, non-blocking)
- Auto-detects language (configurable via `WHISPER_LANGUAGE` env var)

#### [NEW] [speech_engine/worker.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/speech_engine/worker.py)
Redis Stream consumer worker:
```
Read vs:audio (XREADGROUP, group=cg:speech_engine)
    │
    ▼
Decode AudioChunkEvent → PCM bytes
    │
    ▼
VAD.process() → is_speech, is_end_of_speech
    │
    ├── silence → XACK, continue
    │
    └── speech accumulated → transcriber.transcribe()
            │
            ▼
        Publish TranscriptEvent → vs:transcript
            │
            ▼
        XACK vs:audio message
```
Spawned as N asyncio tasks (configurable `SPEECH_WORKER_COUNT`, default 2).

---

### Component 4: Command Service Module

#### [NEW] [command_service/registry.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/command_service/registry.py)
Intent registry — **Indonesian satisfaction Likert scale** (primary domain) plus general telephony commands:

**Satisfaction Intents (Likert 1–5)**

| Intent | Score | Phrase Aliases (Indonesian) |
|---|---|---|
| `sangat_tidak_puas` | 1 | "sangat tidak puas", "sangat kecewa", "tidak puas sekali", "buruk sekali", "sangat buruk" |
| `tidak_puas` | 2 | "tidak puas", "kurang puas", "kecewa", "kurang memuaskan", "tidak memuaskan" |
| `cukup_puas` | 3 | "cukup puas", "lumayan", "cukup", "biasa saja", "cukup memuaskan", "standar" |
| `puas` | 4 | "puas", "memuaskan", "bagus", "baik", "senang", "oke" |
| `sangat_puas` | 5 | "sangat puas", "sangat memuaskan", "luar biasa", "sempurna", "sangat bagus", "sangat baik" |

**Score map** (`SATISFACTION_SCORE_MAP`) is defined in `registry.py` and imported by the matcher:
```python
SATISFACTION_SCORE_MAP: dict[str, int] = {
    "sangat_tidak_puas": 1,
    "tidak_puas":        2,
    "cukup_puas":        3,
    "puas":              4,
    "sangat_puas":       5,
}
```

**General Telephony Intents (score = 0)**

| Intent | Phrase Aliases |
|---|---|
| `repeat_question` | "ulangi", "mohon ulangi", "tidak jelas", "repeat", "say again" |
| `speak_to_agent` | "bicara dengan agen", "operator", "manusia", "speak to agent" |
| `end_call` | "selesai", "sudah", "terima kasih", "bye", "goodbye" |

#### [NEW] [command_service/matcher.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/command_service/matcher.py)
RapidFuzz fuzzy matcher:
- `match(text: str, context: dict) → MatchResult(intent, phrase, score)`
- Normalizes input (lowercase, strip punctuation)
- Uses `fuzz.WRatio` scorer; falls back to `fuzz.token_sort_ratio` for multi-word
- Narrows candidate list based on `context["current_menu"]` for lower false-positive rate
- Threshold: 75 (configurable `COMMAND_MATCH_THRESHOLD`)

#### [NEW] [command_service/worker.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/command_service/worker.py)
Dual-stream consumer worker (reads both `vs:transcript` and `vs:text`):
```
Read vs:transcript OR vs:text
    │
    ▼
Fetch session context (session_manager.store)
    │
    ▼
parser.parse(text, context) → CommandResultEvent
    │
    ▼
Publish CommandResultEvent → vs:result
    │
    ▼
XACK consumed message
```

---

### Component 5: Session Manager Module

#### [NEW] [session_manager/store.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/modules/session_manager/store.py)
Redis-backed session store:
- `get_session(session_id) → SessionContext` (current IVR menu, language, call metadata)
- `update_session(session_id, **kwargs)`
- `delete_session(session_id)` — called on WebSocket disconnect
- TTL: 30 minutes (configurable `SESSION_TTL_SECONDS`)

---

### Component 6: App Factory & Lifecycle

#### [NEW] [app/main.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/app/main.py)
FastAPI app factory with `lifespan` context manager:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize Redis connection pool
    # 2. Initialize stream consumer groups (idempotent)
    # 3. Load Silero VAD model
    # 4. Load faster-whisper model
    # 5. Start Speech Engine workers (N tasks)
    # 6. Start Command Service workers (M tasks)
    # 7. Start Gateway result consumer
    yield
    # Graceful shutdown: cancel all worker tasks, flush connections
```

#### [NEW] [app/settings.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/app/settings.py)
Pydantic `BaseSettings` — all configuration from environment:

```env
# Redis
REDIS_URL=redis://localhost:6379
STREAM_MAXLEN=10000

# Speech Engine
SPEECH_WORKER_COUNT=2
VAD_THRESHOLD=0.5
VAD_MIN_SILENCE_MS=300
WHISPER_MODEL=tiny
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=       # empty = auto-detect

# Command Service
COMMAND_WORKER_COUNT=2
COMMAND_MATCH_THRESHOLD=75

# Session
SESSION_TTL_SECONDS=1800
SAMPLE_RATE=16000

# Server
HOST=0.0.0.0
PORT=8000
```

---

### Component 7: Infrastructure

#### [NEW] [docker-compose.yml](file:///Users/rnd/Program/Personal/VoiceSatisfaction/docker-compose.yml)
```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru

  app:
    build: .
    ports: ["8000:8000"]
    environment:
      REDIS_URL: redis://redis:6379
    depends_on: [redis]
    # Scale speech engine workers horizontally:
    # docker compose up --scale app=3
```

#### [NEW] [Dockerfile](file:///Users/rnd/Program/Personal/VoiceSatisfaction/Dockerfile)
Multi-stage build: base Python 3.11-slim → install deps → copy app → `uvicorn app.main:app`

#### [NEW] [requirements.txt](file:///Users/rnd/Program/Personal/VoiceSatisfaction/requirements.txt)
```
fastapi>=0.115
uvicorn[standard]>=0.30
redis[hiredis]>=5.0          # async redis with C extension
torch>=2.0                    # Silero VAD
faster-whisper>=1.0
rapidfuzz>=3.0
numpy
pydantic>=2.0
pydantic-settings>=2.0
python-dotenv
```

---

## Scalability Path

### Today (Modular Monolith)
All modules run in one process. Scale vertically or add workers via env vars.

### Tomorrow (Extract Speech Engine)
1. Move `modules/speech_engine/` to its own repo
2. Point it to the same Redis instance
3. No code change needed in Gateway or Command Service — only stream contracts matter

### Full Microservices
```
Gateway Service  ──[vs:audio]──▶  Speech Engine Service (N replicas)
                                        │ [vs:transcript]
                 ◀─[vs:result]──  Command Service  (M replicas)
```
Each service scales independently. Redis Streams consumer groups handle load distribution automatically.

---

## Open Questions

> [!IMPORTANT]
> **Audio format from telephony**: Standard telephony sends **8kHz G.711 µ-law (PCMU)**. Should we include an audio resampler (8kHz → 16kHz linear PCM) in the Speech Engine? Or will the client resample before sending?

> [!NOTE]
> **Language setting**: Should Whisper auto-detect language, or should we pin to a specific language (e.g., Indonesian `id`, English `en`) for better accuracy in your telephony context?

> [!NOTE]
> **Worker count defaults**: `SPEECH_WORKER_COUNT=2` and `COMMAND_WORKER_COUNT=2` are the defaults. These can be tuned per deployment without code changes.

---

## Verification Plan

### Unit Tests
```bash
pytest tests/unit/ -v --tb=short
```
- `test_vad.py` — silence vs. speech detection on synthetic PCM
- `test_transcriber.py` — stub faster-whisper, verify output normalisation
- `test_command_parser.py` — fuzzy match accuracy for all 5 satisfaction intents + edge cases

### Integration Tests
```bash
docker compose up redis -d
uvicorn app.main:app --reload &
pytest tests/integration/ -v --tb=short
```
- `test_websocket.py` — WebSocket connect/disconnect, JSON + binary frame routing

---

## Satisfaction Survey Scenario Test

> [!IMPORTANT]
> This is the primary end-to-end scenario. File: [test_satisfaction_survey.py](file:///Users/rnd/Program/Personal/VoiceSatisfaction/tests/scenarios/test_satisfaction_survey.py)

### Scenario: 5-Question CSAT Survey over WebSocket

Each question follows this exact exchange pattern:
```
Client  ──[JSON]──▶  {"question": N}                          # 1. Signal question number
Client  ──[bytes]──▶  <raw PCM audio — customer voice response># 2. Stream audio
Server  ──[JSON]──▶  {"question":N,"status":"success",         # 3. Parsed result
                       "intent":"<label>","score":<1-5>}
```

### Full 5-Question Exchange

| Q# | Customer Says (spoken) | Expected Intent | Expected Score |
|---|---|---|---|
| 1 | "sangat puas" | `sangat_puas` | 5 |
| 2 | "tidak puas" | `tidak_puas` | 2 |
| 3 | "cukup puas" | `cukup_puas` | 3 |
| 4 | "sangat tidak puas" | `sangat_tidak_puas` | 1 |
| 5 | "puas" | `puas` | 4 |

### Scenario Test Code

```python
# tests/scenarios/test_satisfaction_survey.py
import asyncio
import json
import random
import pytest
import websockets
from tests.fixtures import generate_pcm_audio  # synth audio helper

INTENTS = [
    ("sangat_tidak_puas", 1),
    ("tidak_puas",        2),
    ("cukup_puas",        3),
    ("puas",              4),
    ("sangat_puas",       5),
]

WS_URL = "ws://localhost:8000/ws/test-session-001"

@pytest.mark.asyncio
async def test_satisfaction_survey_5_questions():
    """Full 5-question CSAT survey: text signal → PCM audio → parse result."""
    async with websockets.connect(WS_URL) as ws:
        # Shuffle to test random intent ordering
        survey_questions = random.sample(INTENTS, len(INTENTS))

        for q_num, (expected_intent, expected_score) in enumerate(survey_questions, start=1):

            # ── Step 1: Send question signal ──────────────────────────────────
            await ws.send(json.dumps({"question": q_num}))

            # ── Step 2: Stream synthesised PCM audio (voice utterance) ────────
            pcm_audio = generate_pcm_audio(expected_intent)  # synth fixture
            CHUNK_SIZE = 3200  # 100ms @ 16kHz 16-bit mono
            for i in range(0, len(pcm_audio), CHUNK_SIZE):
                await ws.send(pcm_audio[i : i + CHUNK_SIZE])
                await asyncio.sleep(0.1)  # simulate real-time telephony pacing

            # ── Step 3: Receive & assert result ──────────────────────────────
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            result = json.loads(raw)

            assert result["question"] == q_num,             f"Q{q_num}: wrong question number"
            assert result["status"]   == "success",          f"Q{q_num}: status not success"
            assert result["intent"]   == expected_intent,    f"Q{q_num}: wrong intent"
            assert result["score"]    == expected_score,     f"Q{q_num}: wrong score"
            assert result["confidence"] >= 70.0,             f"Q{q_num}: low confidence"

            print(f"  Q{q_num}: intent={result['intent']!r:22s}  "
                  f"score={result['score']}  "
                  f"confidence={result['confidence']:.1f}  ✅")


@pytest.mark.asyncio
async def test_low_confidence_fallback():
    """Garbled audio should return status='low_confidence', score=0."""
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"question": 1}))
        # Send noise-only PCM (random bytes)
        await ws.send(bytes(random.getrandbits(8) for _ in range(16000 * 2)))
        raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
        result = json.loads(raw)
        assert result["status"] in ("low_confidence", "unknown")
        assert result["score"] == 0
```

### PCM Audio Fixture (`tests/fixtures.py`)

```python
# tests/fixtures.py
import numpy as np

# Pre-recorded 16kHz PCM WAV files per intent stored in tests/audio/
# generate_pcm_audio() loads the corresponding file and returns raw PCM bytes.
INTENT_AUDIO_MAP = {
    "sangat_tidak_puas": "tests/audio/sangat_tidak_puas.wav",
    "tidak_puas":        "tests/audio/tidak_puas.wav",
    "cukup_puas":        "tests/audio/cukup_puas.wav",
    "puas":              "tests/audio/puas.wav",
    "sangat_puas":       "tests/audio/sangat_puas.wav",
}

def generate_pcm_audio(intent: str) -> bytes:
    """Load pre-recorded 16kHz mono PCM WAV for the given intent."""
    import soundfile as sf
    data, sr = sf.read(INTENT_AUDIO_MAP[intent], dtype="int16")
    assert sr == 16000, "Audio fixtures must be 16kHz"
    return data.tobytes()
```

> [!NOTE]
> **Audio fixtures**: 5 short WAV files (one per intent phrase spoken in Indonesian) must be recorded at 16kHz mono and placed in `tests/audio/`. These simulate real telephony customer responses.

### Running the Scenario Test
```bash
# Start infrastructure
docker compose up redis -d
uvicorn app.main:app &

# Run the scenario
pytest tests/scenarios/test_satisfaction_survey.py -v -s

# Expected output:
#  Q1: intent='sangat_puas'        score=5  confidence=92.3  ✅
#  Q2: intent='tidak_puas'         score=2  confidence=88.1  ✅
#  Q3: intent='cukup_puas'         score=3  confidence=85.7  ✅
#  Q4: intent='sangat_tidak_puas'  score=1  confidence=90.0  ✅
#  Q5: intent='puas'               score=4  confidence=87.4  ✅
```

### Manual Verification Checklist
- [ ] WebSocket connects → session created in Redis
- [ ] JSON `{"question":1}` received → session context updated with `current_question=1`
- [ ] PCM silence sent → no transcript published, `vs:transcript` stream empty
- [ ] PCM speech ("sangat puas") → full pipeline → `{"question":1,"status":"success","intent":"sangat_puas","score":5}`
- [ ] Next question `{"question":2}` resets question context, does NOT inherit previous intent
- [ ] Garbled audio → `{"status":"low_confidence","score":0}`
- [ ] Kill speech engine worker mid-question → PEL recovery, message not lost, result still delivered
- [ ] 5 questions in sequence complete → all 5 results have correct `question` numbers
