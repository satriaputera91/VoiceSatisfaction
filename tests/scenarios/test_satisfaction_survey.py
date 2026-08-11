import asyncio
import json
import random
import time
import subprocess
import pytest
import websockets
import urllib.request
from tests.fixtures import generate_pcm_audio

INTENTS = [
    ("sangat tidak puas", 1),
    ("tidak puas", 2),
    ("cukup puas", 3),
    ("puas", 4),
    ("sangat puas", 5),
]

WS_URL = "ws://127.0.0.1:8000/ws/test-satisfaction-scenario-001"


@pytest.fixture(autouse=True, scope="module")
def server_process():
    """Start uvicorn server in a subprocess for scenario tests."""
    # Flush Redis DB to ensure clean stream state before test session
    try:
        subprocess.run(["/usr/local/opt/redis/bin/redis-cli", "FLUSHDB"], check=True, capture_output=True)
    except Exception:
        pass

    cmd = ["./venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
    env = {**subprocess.os.environ, "KMP_DUPLICATE_LIB_OK": "TRUE", "PYTHONPATH": "."}
    proc = subprocess.Popen(cmd, env=env)

    # Wait for server liveness
    url = "http://127.0.0.1:8000/health"
    start = time.time()
    ready = False
    while time.time() - start < 20.0:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    ready = True
                    time.sleep(3.0)  # Allow workers to finish consumer group init and stream listening
                    break
        except Exception:
            time.sleep(0.5)

    if not ready:
        proc.terminate()
        pytest.skip("FastAPI server failed to start on 127.0.0.1:8000")

    yield proc

    proc.terminate()
    proc.wait(timeout=2.0)


async def recv_for_question(ws, q_num: int, timeout: float = 10.0):
    """Wait for a result message matching the expected question number, discarding stale results."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"Timed out waiting for question={q_num}")
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        result = json.loads(raw)
        if result.get("question") == q_num:
            return result


@pytest.mark.asyncio
async def test_satisfaction_survey_5_questions():
    """
    5-question CSAT survey scenario test over WebSocket.

    Exchange pattern per question:
        1. Client → JSON  {"question": N}              (question signal)
        2. Client → bytes <PCM audio>                  (voice response)
        3. Server → JSON  {"question":N, "status":..., "intent":..., "score":...}
    """
    async with websockets.connect(WS_URL) as ws:
        survey_questions = random.sample(INTENTS, len(INTENTS))

        for q_num, (expected_intent, expected_score) in enumerate(survey_questions, start=1):

            # ── Step 1: Send question signal {"question": N} ──────────────
            await ws.send(json.dumps({"question": q_num}))

            # ── Step 2: Stream PCM audio in 100ms chunks ──────────────────
            pcm_audio = generate_pcm_audio(expected_intent)
            CHUNK_SIZE = 3200  # 100ms @ 16kHz 16-bit mono
            for i in range(0, len(pcm_audio), CHUNK_SIZE):
                await ws.send(pcm_audio[i: i + CHUNK_SIZE])
                await asyncio.sleep(0.05)

            # Small pause to let silence timeout trigger utterance flush
            await asyncio.sleep(0.5)

            # ── Step 3: Receive result for this question ───────────────────
            result = await recv_for_question(ws, q_num, timeout=12.0)

            # Always assert structural fields
            assert result["question"] == q_num, \
                f"Q{q_num}: expected question={q_num}, got {result.get('question')}"
            assert "status" in result, f"Q{q_num}: missing 'status' field"
            assert "intent" in result, f"Q{q_num}: missing 'intent' field"
            assert "score" in result,  f"Q{q_num}: missing 'score' field"

            print(
                f"  Q{q_num}: question={result['question']}, "
                f"status={result['status']!r}, "
                f"intent={result['intent']!r}, "
                f"score={result['score']}  ✅"
            )


@pytest.mark.asyncio
async def test_satisfaction_survey_expected_responses():
    """
    Verify the exact expected response format from the user request & implementation plan:
        Input question signal: {"question": 1}
        Followed by input: text / audio
        Response: {"question": 1, "status": "success", "intent": "sangat puas", "score": 5}
    """
    url = "ws://127.0.0.1:8000/ws/test-satisfaction-text-001"
    async with websockets.connect(url) as ws:
        test_cases = [
            (1, "sangat puas",       5),
            (2, "tidak puas",        2),
            (3, "cukup puas",        3),
            (4, "sangat tidak puas", 1),
            (5, "puas",              4),
        ]

        for q_num, intent_phrase, expected_score in test_cases:
            # Send question + text payload together
            await ws.send(json.dumps({"question": q_num, "text": intent_phrase}))

            result = await recv_for_question(ws, q_num, timeout=8.0)

            assert result["question"] == q_num,        f"Q{q_num}: wrong question number"
            assert result["status"]   == "success",    f"Q{q_num}: status={result['status']!r}, expected 'success'"
            assert result["intent"]   == intent_phrase, f"Q{q_num}: intent={result['intent']!r}"
            assert result["score"]    == expected_score, f"Q{q_num}: score={result['score']}"
            assert result["confidence"] >= 70.0,       f"Q{q_num}: low confidence {result['confidence']}"

            print(
                f"  Q{q_num}: question={result['question']}, "
                f"status={result['status']!r}, "
                f"intent={result['intent']!r}, "
                f"score={result['score']}, "
                f"confidence={result['confidence']}  ✅"
            )
