# Divyashree Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PHONE NETWORK (Twilio)                      │
│                                                                      │
│  Customer Phone  ←──── Twilio Cloud ────→  TwiML/WebSocket         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           │ 1. Call initiated via API
                           │ 2. Audio streams via WebSocket
                           │ 3. Status callbacks
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        YOUR INFRASTRUCTURE                           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    FastAPI Backend                           │  │
│  │                    (Port 8000)                               │  │
│  │                                                              │  │
│  │  • POST /calls/outbound ──→ Initiate call                   │  │
│  │  • GET  /calls          ──→ List calls                      │  │
│  │  • POST /agents         ──→ Create AI agent                 │  │
│  │  • GET  /health         ──→ System health                   │  │
│  │                                                              │  │
│  │  Triggers Twilio API ───────────────────────────┐           │  │
│  └────────────┬─────────────────────────────────────┼───────────┘  │
│               │                                     │               │
│               │ Reads/Writes                       │               │
│               ▼                                     │               │
│  ┌─────────────────────────────────────────────────┼───────────┐  │
│  │                Voice Gateway                     │           │  │
│  │                (Port 8001)                       │           │  │
│  │                                                  │           │  │
│  │  WebSocket Handler (Twilio Media Stream)        │           │  │
│  │                                                  │           │  │
│  │  ┌────────────────────────────────────────────┐ │           │  │
│  │  │     REAL-TIME AI PIPELINE                 │ │           │  │
│  │  │                                            │ │           │  │
│  │  │  1. Receive audio (mulaw from Twilio)     │ │           │  │
│  │  │           ▼                                │ │           │  │
│  │  │  2. Buffer & decode                       │ │           │  │
│  │  │           ▼                                │ │           │  │
│  │  │  3. Whisper STT → Text                    │ │           │  │
│  │  │           ▼                                │ │           │  │
│  │  │  4. Get conversation history from DB      │ │           │  │
│  │  │           ▼                                │ │           │  │
│  │  │  5. Send to LLM (via ngrok)               │ │           │  │
│  │  │           ▼                                │ │           │  │
│  │  │  6. Get AI response text                  │ │           │  │
│  │  │           ▼                                │ │           │  │
│  │  │  7. Coqui TTS → Audio (WAV)               │ │           │  │
│  │  │           ▼                                │ │           │  │
│  │  │  8. Convert to mulaw & stream to Twilio   │ │           │  │
│  │  │           ▼                                │ │           │  │
│  │  │  9. Save transcript to DB                 │ │           │  │
│  │  └────────────────────────────────────────────┘ │           │  │
│  │                                                  │           │  │
│  │  Exposed via ngrok (wss://)  ◀──────────────────┘           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           │ Database Operations
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Neon/PostgreSQL                                  │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   agents     │  │    calls     │  │ transcripts  │             │
│  │              │  │              │  │              │             │
│  │ • id         │  │ • id         │  │ • id         │             │
│  │ • name       │  │ • agent_id   │  │ • call_id    │             │
│  │ • prompt     │  │ • to_number  │  │ • speaker    │             │
│  │ • settings   │  │ • status     │  │ • text       │             │
│  └──────────────┘  │ • duration   │  │ • timestamp  │             │
│                    │ • metadata   │  └──────────────┘             │
│                    └──────────────┘                                │
│                                                                      │
│  ┌──────────────────────────────────┐                              │
│  │      call_analysis (future)      │                              │
│  │  • summary                        │                              │
│  │  • key_points                     │                              │
│  │  • sentiment                      │                              │
│  │  • outcome                        │                              │
│  └──────────────────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    LLM Infrastructure                                │
│                                                                      │
│  ┌────────────────────────────────────────────────────────┐         │
│  │           Ollama (Local)                               │         │
│  │           Port 11434                                   │         │
│  │                                                        │         │
│  │   Model: llama3:8b                                     │         │
│  │   API: /api/chat                                       │         │
│  │                                                        │         │
│  │   ┌──────────────────────────────────────┐            │         │
│  │   │     Conversation Processing          │            │         │
│  │   │                                      │            │         │
│  │   │  Input:  User message + history     │            │         │
│  │   │  Output: AI response text           │            │         │
│  │   │  Params: temperature, max_tokens    │            │         │
│  │   └──────────────────────────────────────┘            │         │
│  │                                                        │         │
│  └────────────────────────────────────────────────────────┘         │
│                           ▲                                          │
│                           │                                          │
│                           │ Exposed via ngrok                        │
│                           │                                          │
│                    ┌──────┴───────┐                                 │
│                    │    ngrok     │                                 │
│                    │              │                                 │
│                    │ Public URL   │                                 │
│                    │ https://...  │                                 │
│                    └──────────────┘                                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Request Flow: Outbound Call

```
User Request
    │
    ▼
1. POST /calls/outbound
    │
    ▼
2. Backend creates call record in DB
    │
    ▼
3. Backend triggers Twilio API
    │
    ▼
4. Twilio dials customer number
    │
    ▼
5. Customer answers → Twilio requests TwiML
    │
    ▼
6. Backend returns TwiML with <Stream> directive
    │
    ▼
7. Twilio establishes WebSocket to Voice Gateway
    │
    ▼
8. Voice Gateway sends greeting (TTS)
    │
    ▼
9. CONVERSATION LOOP:
    │
    ├─→ Customer speaks
    │       ▼
    ├─→ Audio buffered
    │       ▼
    ├─→ Whisper STT → Text
    │       ▼
    ├─→ Save to DB (transcripts)
    │       ▼
    ├─→ Get conversation history
    │       ▼
    ├─→ Send to LLM (via ngrok)
    │       ▼
    ├─→ LLM responds with text
    │       ▼
    ├─→ Save to DB (transcripts)
    │       ▼
    ├─→ Coqui TTS → Audio
    │       ▼
    └─→ Stream audio to Twilio → Customer hears
    │
    ▼
10. Call ends → Update DB (status, duration)
    │
    ▼
11. (Future) Post-call analysis runs
```

## Data Flow

```
┌──────────────┐
│   Customer   │
│    Phone     │
└──────┬───────┘
       │
       │ Voice (audio)
       ▼
┌──────────────┐
│   Twilio     │  ────────────┐
│   Cloud      │              │ HTTP Status Callbacks
└──────┬───────┘              │
       │                      ▼
       │ WebSocket         ┌──────────────┐
       │ (mulaw audio)     │   Backend    │
       ▼                   │   (8000)     │
┌──────────────┐           └──────┬───────┘
│    Voice     │                  │
│   Gateway    │◄─────────────────┤ Trigger Call
│   (8001)     │                  │ Get Agent Config
└──────┬───────┘                  │
       │                          ▼
       │                   ┌──────────────┐
    │ Store/Retrieve    │  Neon/Postgres │
       ├──────────────────►│  (Postgres)  │
       │                   └──────────────┘
       │
       │ Generate Response
       ▼
┌──────────────┐
│   Ollama     │
│  (via ngrok) │
│   llama3:8b  │
└──────────────┘
```

## Component Responsibilities

### Backend (FastAPI)
- 🎯 **Purpose:** API gateway & Twilio orchestration
- 📌 **Port:** 8000
- ✅ **Features:**
  - REST API endpoints
  - Agent CRUD operations
  - Call initiation via Twilio API
  - Call status tracking
  - Database operations

### Voice Gateway (FastAPI + WebSocket)
- 🎯 **Purpose:** Real-time voice AI processing
- 📌 **Port:** 8001
- ✅ **Features:**
  - Twilio Media Stream WebSocket handler
  - Audio buffering & format conversion
  - STT (Whisper) integration
  - LLM conversation management
  - TTS (Coqui) generation
  - Transcript storage

### Shared Services
- 🗄️ **database.py** - PostgreSQL operations
- 🧠 **llm_client.py** - Ollama LLM communication
- 🎙️ **stt_client.py** - Whisper speech-to-text
- 🔊 **tts_client.py** - Coqui text-to-speech

### Infrastructure
- 🐳 **Docker Compose** - Container orchestration
- 🌐 **ngrok** - Exposes local services publicly
- 📊 **Neon** - Managed PostgreSQL database
- ☁️ **Twilio** - Telephony infrastructure

## Network Ports

| Service | Port | Exposed | Protocol |
|---------|------|---------|----------|
| Backend | 8000 | Localhost | HTTP |
| Voice Gateway | 8001 | ngrok (wss) | HTTP/WS |
| Ollama | 11434 | ngrok (https) | HTTP |
| Neon/PostgreSQL | 5432 | Cloud | Postgres |
| Twilio | N/A | Cloud | HTTP/WS |

## Security Layers

```
Internet
   │
   ▼
Twilio (trusted)
   │
   ▼
ngrok tunnel (HTTPS/WSS)
   │
   ▼
Voice Gateway (local)
   │
   ▼
PostgreSQL credentials (DATABASE_URL)
   │
   ▼
Database (RLS policies)
```

## Scalability Considerations

### Current (MVP)
- Single instance of each service
- Local LLM (one machine)
- Synchronous processing

### Future (Production)
- Load balanced backend/voice gateway
- Cloud-hosted LLM (or distributed Ollama)
- Async task queue for post-call analysis
- CDN for static assets
- Database read replicas
- Redis for session management

---

**This architecture balances simplicity for MVP with extensibility for production.**
