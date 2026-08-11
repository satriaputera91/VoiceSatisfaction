# VoiceSatisfaction

Voice command detection and CSAT satisfaction analysis system for telephony customers.
Built as a **modular monolith** with FastAPI, Silero VAD, faster-whisper, RapidFuzz, and Redis Streams.

---

## Modular Monolith Architecture

The application is structured into 5 bounded modules:

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
```

---

## Stream Topology

- **`vs:audio`** — Gateway publishes PCM audio chunks from clients.
- **`vs:text`** — Gateway publishes text question signals.
- **`vs:transcript`** — Speech Engine publishes Whisper transcriptions.
- **`vs:result`** — Command Service publishes final parsed intent & CSAT score.

---

## Satisfaction Intent Scale (Indonesian CSAT)

| Intent | Score | Phrase Aliases |
|---|---|---|
| `sangat tidak puas` | 1 | "sangat tidak puas", "sangat kecewa", "buruk sekali" |
| `tidak puas` | 2 | "tidak puas", "kurang puas", "kecewa", "buruk" |
| `cukup puas` | 3 | "cukup puas", "lumayan", "cukup", "biasa saja" |
| `puas` | 4 | "puas", "memuaskan", "bagus", "baik", "oke" |
| `sangat puas` | 5 | "sangat puas", "sangat memuaskan", "luar biasa", "mantap" |

---

## Running Locally

### 1. Start Redis
```bash
docker compose up redis -d
```

### 2. Start Application
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Test Client & Scenario Tests

### Run Unit Tests
```bash
pytest tests/unit/ -v
```

### Run Scenario Test (5 Questions CSAT)
```bash
pytest tests/scenarios/test_satisfaction_survey.py -v -s
```

### Interactive Test Client
```bash
# Text question mode
python client/test_client.py --mode text --question 1 --text "sangat puas"

# Audio PCM mode
python client/test_client.py --mode audio --question 1 --file sample.wav
```
