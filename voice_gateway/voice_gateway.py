"""
Voice Gateway for Divyashree AI Caller
Handles Twilio Media Streams via WebSocket
Real-time pipeline: Audio â†’ STT â†’ LLM â†’ TTS â†’ Audio

ARCHITECTURE (Vapi-style, optimized for <4s response):
- 3-state machine: LISTENING, USER_SPEAKING, AI_SPEAKING
- VAD edge-trigger: 240ms speech start, 300ms silence end
- TRUE barge-in: Interrupt AI mid-speech with intent-based validation
- Intent pre-classifier: Handle casual responses before LLM
- NO adaptive silence, NO post-TTS sleep, NO cooldowns

INTERRUPTION HANDLING (Refined):
- Grace period: 300ms after AI starts speaking (ignore echo onset)
- Sustained speech: 300ms minimum to trigger valid interrupt
- Acknowledgement detection: "yeah", "okay" continue AI flow
- Context hygiene: Only commit complete turns to transcript
- Thread safety: Locks for state transitions and buffer access
- Edge case guards: Timeouts, double-processing prevention, buffer limits
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from enum import Enum
import asyncio
import base64
import json
import sys
import os
import re
from difflib import SequenceMatcher
from loguru import logger
from datetime import datetime, timedelta
import audioop
import webrtcvad
import torch
import numpy as np
import io
import wave
import subprocess

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from shared.database import get_db, RelayDB
from shared.llm_client import get_llm_client, LLMClient
from shared.stt_client import get_stt_client, STTClient
from shared.tts_client import get_tts_client, TTSClient
from shared.cache_client import get_cache_client
from shared.prompts.wow_prompt import PRIYA_SYSTEM_PROMPT
from shared.wow_qualification import normalize_wow_analysis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ==================== RAG: KNOWLEDGE BASE RETRIEVAL ====================
async def retrieve_relevant_knowledge(agent_id: str, user_query: str, db: RelayDB) -> str:
    """
    RAG (Retrieval Augmented Generation): Search KB for relevant info
    
    Args:
        agent_id: Agent whose KB to search
        user_query: User's question/message
        db: Database client
    
    Returns:
        Relevant KB entries as formatted string, or empty string if none found
    """
    try:
        # Fetch all KB entries for this agent
        knowledge = await db.get_agent_knowledge(agent_id)
        
        if not knowledge:
            return ""
        
        # Simple keyword-based relevance scoring (can be improved with embeddings later)
        query_words = set(user_query.lower().split())
        relevant_entries = []
        
        for entry in knowledge:
            # Search in title and content
            content = (entry.get("title", "") + " " + entry.get("content", "")).lower()
            
            # Count matching words
            matches = sum(1 for word in query_words if word in content and len(word) > 3)
            
            if matches > 0:
                relevant_entries.append({
                    "entry": entry,
                    "score": matches
                })
        
        # Sort by relevance and take top 2
        relevant_entries.sort(key=lambda x: x["score"], reverse=True)
        top_entries = relevant_entries[:2]
        
        if not top_entries:
            return ""
        
        # Format KB context for LLM
        kb_context = "\\n\\nRELEVANT KNOWLEDGE BASE:\\n"
        for item in top_entries:
            entry = item["entry"]
            kb_context += f"- {entry.get('title', 'Info')}: {entry.get('content', '')[:200]}\\n"
        
        return kb_context
        
    except Exception as e:
        logger.error(f"RAG retrieval error: {e}")
        return ""


WOW_DEFAULT_AGENT_ID = "c4083449-3d67-4696-9822-15770d9c0371"
WOW_PHASE_1_2 = "PHASE_1_2"
WOW_PHASE_3 = "PHASE_3"
WOW_PHASE_4 = "PHASE_4"
WOW_CHECKPOINT_PENDING = "PENDING"


def new_wow_checkpoint_state() -> dict[str, str]:
    """Create a deterministic runtime state map for WOW checkpoints."""
    return {
        "INTENT": WOW_CHECKPOINT_PENDING,
        "GEOGRAPHY": WOW_CHECKPOINT_PENDING,
        "BUDGET": WOW_CHECKPOINT_PENDING,
        "TIMELINE": WOW_CHECKPOINT_PENDING,
    }


def classify_wow_exit_case(user_text: str) -> Optional[str]:
    """Classify explicit graceful-exit cases for deterministic runtime branching."""
    text = (user_text or "").lower()
    if any(p in text for p in ["busy", "not now", "call later", "stop calling", "don't call"]):
        return "busy"
    if any(p in text for p in ["too expensive", "too high", "not in my budget", "outside budget", "can't afford"]):
        return "budget_low"
    if any(p in text for p in ["wrong location", "too far", "not nandi", "not devanahalli", "different location"]):
        return "location_mismatch"
    return None


def infer_wow_checkpoint_question(ai_text: str) -> Optional[str]:
    """Best-effort classifier for which WOW checkpoint the assistant just asked."""
    text = (ai_text or "").lower()
    if any(p in text for p in ["weekend home", "personal use", "investment opportunity"]):
        return "INTENT"
    if any(p in text for p in ["nandi", "devanahalli", "north bengaluru", "bangalore north"]):
        return "GEOGRAPHY"
    if any(p in text for p in ["budget", "lakh", "crore", "laak"]):
        return "BUDGET"
    if any(p in text for p in ["timeline", "2029", "possession", "ready to move"]):
        return "TIMELINE"
    return None


def update_runtime_wow_checkpoint_state(session: "CallSession", user_text: str) -> None:
    """Update deterministic runtime checkpoint map from latest user turn."""
    checkpoint_hits = infer_wow_checkpoint_state([], user_text)

    negative_signals = (user_text or "").lower()
    if any(p in negative_signals for p in ["not interested", "no interest"]):
        session.wow_checkpoint_state["INTENT"] = "FAIL"
    if any(p in negative_signals for p in ["wrong location", "too far", "not nandi", "not devanahalli"]):
        session.wow_checkpoint_state["GEOGRAPHY"] = "FAIL"
    if any(p in negative_signals for p in ["too expensive", "too high", "not in my budget", "can't afford"]):
        session.wow_checkpoint_state["BUDGET"] = "FAIL"
    if any(p in negative_signals for p in ["need now", "ready now", "too long", "can't wait", "cannot wait"]):
        session.wow_checkpoint_state["TIMELINE"] = "FAIL"

    asked_checkpoint = getattr(session, "last_checkpoint_asked", None)
    for checkpoint, hit in checkpoint_hits.items():
        if not hit:
            continue
        current_state = session.wow_checkpoint_state.get(checkpoint, WOW_CHECKPOINT_PENDING)
        if current_state in {"PASS", "SKIP", "FAIL"}:
            continue
        session.wow_checkpoint_state[checkpoint] = "PASS" if checkpoint == asked_checkpoint else "SKIP"


def build_runtime_wow_checkpoint_guidance(session: "CallSession") -> str:
    """Render runtime checkpoint state as deterministic guidance for generation."""
    order = getattr(session, "wow_checkpoint_order", ["INTENT", "GEOGRAPHY", "BUDGET", "TIMELINE"])
    state = getattr(session, "wow_checkpoint_state", new_wow_checkpoint_state())
    next_checkpoint = next((cp for cp in order if state.get(cp) == WOW_CHECKPOINT_PENDING), None)

    lines = [
        "\n\nWOW RUNTIME CHECKPOINT STATE (deterministic):",
        f"INTENT={state.get('INTENT', WOW_CHECKPOINT_PENDING)}",
        f"GEOGRAPHY={state.get('GEOGRAPHY', WOW_CHECKPOINT_PENDING)}",
        f"BUDGET={state.get('BUDGET', WOW_CHECKPOINT_PENDING)}",
        f"TIMELINE={state.get('TIMELINE', WOW_CHECKPOINT_PENDING)}",
    ]

    if next_checkpoint:
        lines.append(f"Ask NEXT checkpoint: {next_checkpoint}")
    else:
        lines.append("All checkpoints are resolved. Move to pitch/CTA per flow.")

    return "\n".join(lines)


def _message_role(msg: dict) -> str:
    return str(msg.get("role") or msg.get("speaker") or "").strip().lower()


def _collect_user_context_text(conversation_history: list[dict], current_user_text: str) -> str:
    """Collect only USER utterances for checkpoint inference.

    Never include assistant text; that would cause false checkpoint skips.
    """
    user_chunks: list[str] = []
    for msg in conversation_history:
        if _message_role(msg) == "user":
            content = str(msg.get("content") or msg.get("text") or "").strip()
            if content:
                user_chunks.append(content)

    if current_user_text and current_user_text.strip():
        user_chunks.append(current_user_text.strip())

    return " ".join(user_chunks).lower()


def infer_wow_checkpoint_state(conversation_history: list[dict], current_user_text: str) -> dict[str, bool]:
    """Infer caller-provided checkpoint coverage from user utterances only."""
    user_text = _collect_user_context_text(conversation_history, current_user_text)

    return {
        "INTENT": any(p in user_text for p in ["weekend home", "personal use", "investment", "investor"]),
        "GEOGRAPHY": any(p in user_text for p in ["nandi", "devanahalli", "north bengaluru", "bangalore north"]),
        "BUDGET": any(p in user_text for p in ["lakh", "lac", "crore", "budget", "1 cr", "1 crore", "2 crore"]),
        "TIMELINE": any(p in user_text for p in ["2029", "ready to move", "timeline", "possession", "phase"]),
    }


def infer_wow_phase(conversation_history: list[dict], current_user_text: str) -> str:
    """Best-effort WOW phase inference for phase-aware runtime constraints."""
    checkpoint_state = infer_wow_checkpoint_state(conversation_history, current_user_text)
    all_checkpoints_known = all(checkpoint_state.values())

    assistant_text = " ".join(
        str(msg.get("content") or msg.get("text") or "").strip()
        for msg in conversation_history
        if _message_role(msg) in {"assistant", "agent"}
    ).lower()

    cta_signals = [
        "property expert",
        "20-minute call",
        "booking link",
        "book a call",
        "connect you",
    ]
    pitch_signals = [
        "let me paint a picture",
        "74 percent of the land",
        "private valley",
        "20,000 square-foot clubhouse",
        "20,000 square foot clubhouse",
    ]

    if any(signal in assistant_text for signal in cta_signals):
        return WOW_PHASE_4
    if any(signal in assistant_text for signal in pitch_signals) or all_checkpoints_known:
        return WOW_PHASE_3
    return WOW_PHASE_1_2


def _is_wow_agent_config(agent_config: Optional[dict]) -> bool:
    if not isinstance(agent_config, dict):
        return False

    agent_id = str(agent_config.get("id") or "").strip().lower()
    template_source = str(agent_config.get("template_source") or "").strip().lower()
    name = str(agent_config.get("name") or "").strip().lower()

    return (
        agent_id == WOW_DEFAULT_AGENT_ID
        or name == "priya"
        or "wow" in template_source
    )


def resolve_agent_system_prompt(agent_config: Optional[dict]) -> str:
    """Resolve source-of-truth system prompt for an agent config."""
    if _is_wow_agent_config(agent_config):
        return PRIYA_SYSTEM_PROMPT

    if isinstance(agent_config, dict):
        return (
            agent_config.get("resolved_system_prompt")
            or agent_config.get("prompt_text")
            or agent_config.get("system_prompt")
            or "You are a helpful assistant."
        )

    return "You are a helpful assistant."


def infer_wow_checkpoint_guidance(conversation_history: list[dict], current_user_text: str) -> str:
    """Infer already-volunteered WOW checkpoints from USER utterances only."""
    checkpoint_state = infer_wow_checkpoint_state(conversation_history, current_user_text)
    known = [name for name, is_known in checkpoint_state.items() if is_known]

    if not known:
        return ""

    return (
        "\n\nWOW CHECKPOINT GUIDANCE:\n"
        f"Known checkpoints from caller context: {', '.join(known)}.\n"
        "Do NOT re-ask these checkpoints. Acknowledge and continue to next missing checkpoint."
    )

# Configure logger
logger.add("logs/voice_gateway.log", rotation="1 day", retention="7 days", level="INFO")

# Initialize FastAPI
app = FastAPI(
    title="Divyashree Voice Gateway",
    description="Twilio Media Stream handler for AI voice calls",
    version="2.0.0"  # Major rewrite with barge-in support
)

# ==================== SILERO VAD INITIALIZATION (CPU-ONLY, LIGHTWEIGHT) ====================
# Download and cache the lightweight Silero VAD model (~2-5MB)
# Configured for CPU to avoid heavy GPU dependencies
try:
    torch.set_num_threads(1)  # Limit CPU threads for small device
    silero_model, silero_utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,  # Use cached model
        onnx=False,  # Use PyTorch (smaller)
        trust_repo=True
    )
    silero_model.eval()  # Set to evaluation mode
    (get_speech_timestamps, _, read_audio, *_) = silero_utils
    logger.info("âœ… Silero VAD loaded successfully (CPU-only, ~5MB)")
except Exception as e:
    logger.error(f"âš ï¸ Failed to load Silero VAD: {e}")
    silero_model = None
    silero_utils = None

# Add CORS middleware to allow dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Audio settings for Twilio
TWILIO_SAMPLE_RATE = 8000  # Twilio uses 8kHz
TWILIO_AUDIO_FORMAT = "mulaw"  # Î¼-law encoding

# WebRTC VAD (lightweight, <1ms per frame)
# Mode: 0=Quality, 1=Low Bitrate, 2=Aggressive, 3=Very Aggressive
# Changed from mode=3 to mode=2 - mode 3 was detecting breathing/noise as continuous speech
# Mode 2 allows natural pauses to be detected as silence
vad = webrtcvad.Vad(mode=2)

# Call sessions storage
active_sessions = {}


# ==================== SIMPLIFIED 3-STATE MACHINE ====================
class ConversationState(Enum):
    """Simple 3-state conversation model (like Vapi.ai)"""
    LISTENING = "listening"        # Waiting for user to speak
    USER_SPEAKING = "user_speaking"  # User is actively speaking
    AI_SPEAKING = "ai_speaking"    # AI is outputting audio

class CallStage(Enum):
    """Call progression stages for context-aware timeouts (Vapi-like)"""
    LANGUAGE_SELECT = "language_select"  # User selecting language (1-2 words)
    YES_NO = "yes_no"                    # Simple confirmation (1-3 words)
    SHORT_ANSWER = "short_answer"        # Name, number, date (1-5 words)
    OPEN_ENDED = "open_ended"            # Detailed response (sentences)


# ==================== INTENT PRE-CLASSIFIER (Before LLM) ====================
# These patterns are handled WITHOUT calling LLM - saves 200-500ms
AFFIRM_PATTERNS = ["yeah", "yes", "yep", "yup", "haan", "ok", "okay", "sure", "exactly", "right", "correct", "absolutely", "definitely", "of course", "alright", "fine", "go ahead", "please", "i'm down", "im down", "down for that", "down for it", "sounds good", "let's do it", "lets do it", "i'm in", "im in", "count me in", "deal", "perfect", "great", "awesome", "cool", "bet"]
ACK_PATTERNS = ["hmm", "uh huh", "uh-huh", "huh", "mm", "mhm", "mmhmm", "i see", "got it"]
OPEN_PATTERNS = ["what's up", "whats up", "what is this", "who is this", "who's calling", "whos calling", "what do you want", "yes what", "yeah what", "hello", "hi"]
NEGATIVE_PATTERNS = ["no", "nope", "nah", "not interested", "no thanks", "no thank you", "busy", "not now", "call later", "don't call", "wrong number"]
GOODBYE_PATTERNS = ["bye", "goodbye", "see you", "thanks bye", "thank you bye", "gotta go", "have to go", "talk later", "bye-bye", "bye bye"]

# NOISE WORDS - Single words that are likely STT errors from echo/noise
# These should NEVER create a user turn or reach LLM context
NOISE_WORDS = [
    # Common STT noise artifacts
    "you", "the", "a", "i", "um", "uh", "ah", "oh", "er", "hmm", "hm",
    # Partial words / fragments
    "it", "is", "to", "in", "on", "an", "and", "or", "so", "be",
    # Very short non-meaningful
    "k", "m", "n", "s", "t", "y",
]

# ==================== INTERRUPTION HANDLING CONSTANTS ====================
# Grace period after AI starts speaking - ignore ALL VAD triggers
# This prevents echo onset from causing false interrupts
AI_SPEECH_GRACE_PERIOD_MS = 300

# Minimum sustained speech duration to trigger a valid interrupt
# Short blips (<300ms) should NOT interrupt
MIN_INTERRUPT_SPEECH_MS = 300

# Maximum time to stay in USER_SPEAKING before timeout
USER_SPEAKING_TIMEOUT_MS = 30000  # 30 seconds

# ACKNOWLEDGEMENT PATTERNS - Short utterances that should continue AI flow
# NOT be treated as topic changes even if they interrupt
ACKNOWLEDGEMENT_PATTERNS = [
    "yeah", "yes", "yep", "okay", "ok", "right", "uh-huh", "uh huh",
    "mhm", "mm-hmm", "mmhmm", "got it", "sure", "i see", "alright"
]

# ECHO PHRASES - Multi-word patterns that match AI speech (potential echo)
# If detected within 2 seconds of AI speaking, treat as echo
ECHO_PHRASE_PATTERNS = [
    "thank you", "thanks", "got a moment", "this is", "from relay",
    "no problem", "you're welcome", "have a great", "you"
]


def classify_intent(text: str, time_since_ai_spoke_ms: float = 9999) -> tuple[str, str | None]:
    """
    Fast intent classification for short utterances (runs in <1ms)
    Returns: (intent, scripted_response or None)
    
    Intents:
    - "noise" â†’ Likely STT error from echo/noise, ignore
    - "echo" â†’ Detected AI echo pattern, ignore
    - "affirm" â†’ User said yes/okay, continue with pitch
    - "ack" â†’ User acknowledged, continue naturally  
    - "open" â†’ User wants context, explain purpose
    - "negative" â†’ User declined, offer callback
    - "goodbye" â†’ User ending call
    - "llm" â†’ Need full LLM processing
    
    Args:
        text: The transcribed text
        time_since_ai_spoke_ms: Milliseconds since AI finished speaking (for echo detection)
    """
    text_lower = text.lower().strip()
    words = text_lower.split()
    
    # ==================== NOISE DETECTION ====================
    # Single word that's likely STT noise - SKIP entirely
    # "you" is ALWAYS noise as single word (common phone echo artifact)
    if len(words) == 1 and (text_lower in NOISE_WORDS or text_lower == "you"):
        return ("noise", None)  # Will be skipped
    
    # Very short gibberish (1-2 chars) - likely noise
    if len(text_lower) <= 2:
        return ("noise", None)
    
    # ==================== ECHO DETECTION ====================
    # If AI just spoke and this matches AI speech patterns, it's likely echo
    if time_since_ai_spoke_ms < 2000:  # Within 2 seconds of AI speaking (increased from 1.5s)
        for pattern in ECHO_PHRASE_PATTERNS:
            if pattern in text_lower:
                return ("echo", None)  # Detected as AI echo
    
    # Very short utterances - classify directly
    if len(words) <= 5:
        # Check patterns (order matters - more specific first)
        for pattern in GOODBYE_PATTERNS:
            if pattern in text_lower:
                return ("goodbye", "Thanks for your time! Goodbye!")
        
        for pattern in NEGATIVE_PATTERNS:
            if pattern in text_lower:
                return ("negative", None)  # Let LLM handle graceful decline
        
        for pattern in OPEN_PATTERNS:
            if text_lower.startswith(pattern) or pattern in text_lower:
                return ("open", None)  # Let LLM explain context
        
        for pattern in AFFIRM_PATTERNS:
            if pattern in text_lower or text_lower == pattern:
                return ("affirm", None)  # Continue with pitch
        
        for pattern in ACK_PATTERNS:
            if pattern in text_lower:
                return ("ack", None)  # Continue naturally
    
    # Longer utterances need LLM
    return ("llm", None)


def detect_turn_language(text: str) -> str | None:
    """Best-effort language detection for English/Hindi/Marathi switching during active calls."""
    text_lower = text.lower().strip()
    if not text_lower:
        return None

    if any(k in text_lower for k in ["hindi", "à¤¹à¤¿à¤‚à¤¦à¥€", "à¤¹à¤¿à¤¨à¥à¤¦à¥€"]):
        return "hi"
    if any(k in text_lower for k in ["marathi", "à¤®à¤°à¤¾à¤ à¥€"]):
        return "mr"
    if "english" in text_lower:
        return "en"

    # Script-based fallback: if Devanagari appears, prefer Hindi unless Marathi keyword was explicit.
    if re.search(r"[\u0900-\u097f]", text_lower):
        return "hi"

    # Latin-only heuristics - leave as None to avoid aggressive switching.
    return None


class CallSession:
    """
    Manages state for an active call
    
    SIMPLIFIED STATE MACHINE (Vapi-style):
    - Only 3 states: LISTENING, USER_SPEAKING, AI_SPEAKING
    - VAD edge-trigger with HYSTERESIS: 200ms speech start, 240ms silence end
    - TRUE barge-in: User can interrupt AI mid-speech
    - ECHO PROTECTION: 1000ms ignore window after TTS completes
    - ENERGY SANITY: Filter out non-speech noise
    - POST-NOISE COOLDOWN: Brief delay after noise detection
    """
    
    # VAD HYSTERESIS TIMINGS (synced with FRAME counts)
    SPEECH_START_MS = 180      # 6 frames Ã— 30ms = 180ms â†’ USER_SPEAKING
    SPEECH_END_MS = 700        # 23 frames Ã— 30ms = 700ms â†’ End utterance (Vapi's timing)
    
    # AUDIO DURATION THRESHOLDS (critical for filtering noise)
    MIN_AUDIO_DURATION_MS = 300   # Minimum 300ms to consider processing
    MIN_STT_DURATION_MS = 350     # Minimum 350ms before sending to STT
    DISCARD_FIRST_IF_SHORT_MS = 300  # Discard first utterance after AI if < 300ms
    
    # ENERGY THRESHOLDS (mulaw: 127 is zero-crossing/silence center)
    # Vapi uses simple fixed threshold ~30-40, NO adaptive calibration
    MIN_SPEECH_ENERGY = 30     # Fixed threshold like Vapi (simple and reliable)
    
    # PROTECTION WINDOWS
    ECHO_IGNORE_MS = 1000      # Ignore VAD for 1000ms after TTS completes (prevent echo detection)
    POST_NOISE_COOLDOWN_MS = 150  # Cooldown after noise detection
    
    # WebRTC VAD frame settings
    VAD_FRAME_DURATION_MS = 30  # 30ms frames for accuracy
    VAD_FRAME_BYTES = 240       # 30ms at 8kHz = 240 bytes
    
    # Frame counts for hysteresis (at 30ms per frame)
    SPEECH_START_FRAMES = 6    # 6 frames Ã— 30ms = 180ms of speech to trigger (optimized from 8)
    SPEECH_END_FRAMES = 15     # 15 frames Ã— 30ms = 450ms of silence to end (REDUCED from 23/700ms - dynamic per stage)
    
    # BARGE-IN THRESHOLDS (stricter - AI speaking, user wants to interrupt)
    # Require LOUDER and LONGER speech to interrupt the AI
    MIN_SPEECH_ENERGY_BARGEIN = 75   # Higher energy required to interrupt (vs 60 for listening)
    SPEECH_START_FRAMES_BARGEIN = 10 # 10 frames Ã— 30ms = 300ms sustained speech to interrupt

    # LANGUAGE SELECTION
    LANGUAGE_SELECTION_ENABLED = True
    
    # ==================== VAPI-LIKE CONTEXT-AWARE TIMEOUTS ====================
    # Dynamic max speech duration based on expected answer type
    MAX_SPEECH_DURATION_BY_STAGE = {
        CallStage.LANGUAGE_SELECT: 1.0,   # "English" - short keyword
        CallStage.YES_NO: 1.5,             # "Yes", "No", "Maybe" - brief
        CallStage.SHORT_ANSWER: 2.5,       # "John Smith", "Monday" - concise
        CallStage.OPEN_ENDED: 6.0          # Full explanation - allow pauses
    }
    
    # Hotwords for immediate cutoff (Phrase Clamping)
    LANGUAGE_HOTWORDS = ["english", "hindi", "marathi", "à¤¹à¤¿à¤‚à¤¦à¥€", "à¤®à¤°à¤¾à¤ à¥€"]
    
    # Adaptive noise calibration
    CALIBRATION_DURATION_MS = 500  # Sample 500ms at call start
    NOISE_THRESHOLD_MARGIN = 15     # Add this to baseline noise
    
    def __init__(self, call_id: str, agent_id: str, stream_sid: str, voice_settings: dict = None):
        self.call_id = call_id
        self.agent_id = agent_id
        self.stream_sid = stream_sid
        self.audio_buffer = bytearray()
        self.vad_buffer = bytearray()  # Buffer for VAD frame alignment
        
        # Apply voice settings if provided, otherwise use defaults
        if voice_settings:
            self.SPEECH_START_MS = voice_settings.get('speech_start_ms', 200)
            self.SPEECH_END_MS = voice_settings.get('speech_end_ms', 240)
            self.MIN_AUDIO_DURATION_MS = voice_settings.get('min_audio_duration_ms', 400)
            self.MIN_STT_DURATION_MS = voice_settings.get('silence_threshold_ms', 500)
            self.MIN_SPEECH_ENERGY = voice_settings.get('min_speech_energy', 30)
            self.ECHO_IGNORE_MS = voice_settings.get('echo_ignore_ms', 400)
            vad_mode = voice_settings.get('vad_mode', 2)
            logger.info(f"Applying custom voice settings for call {call_id}: VAD mode={vad_mode}, silence={self.MIN_STT_DURATION_MS}ms, energy={self.MIN_SPEECH_ENERGY}")
        else:
            # Use class-level defaults (keep existing behavior)
            logger.info(f"Using default voice settings for call {call_id}")
        
        # Update VAD mode if custom settings provided
        if voice_settings and 'vad_mode' in voice_settings:
            global vad
            vad_mode = voice_settings['vad_mode']
            vad = webrtcvad.Vad(vad_mode)
            logger.info(f"Updated WebRTC VAD mode to {vad_mode}")
        
        # SIMPLIFIED STATE (3 states only)
        self.state = ConversationState.LISTENING
        
        # VAD edge detection with hysteresis
        self.speech_start_time = None
        self.silence_start_time = None
        self.consecutive_speech_frames = 0
        self.consecutive_silence_frames = 0
        
        # ECHO PROTECTION: Track when TTS finished
        self.tts_end_time = None  # Set when TTS completes
        
        # LLM IN-FLIGHT PROTECTION
        self.llm_in_flight = False  # True while waiting for LLM response
        
        # POST-NOISE COOLDOWN
        self.noise_detected_time = None  # Set when noise is detected
        
        # TURN TRACKING (for first-utterance-after-AI logic)
        self.ai_turn_count = 0  # Increments each time AI speaks
        self.last_ai_turn_end = None  # When AI last finished speaking
        self.utterances_since_ai = 0  # Count of user utterances since AI spoke
        
        # Conversation context
        self.conversation_history = []
        self.agent_config = None
        self.last_user_text = None
        self.last_user_text_time = None
        self.last_ai_response = None  # Track last AI response to prevent repetition
        self.created_at = datetime.now()
        
        # Barge-in support
        self.ai_audio_task = None  # Track ongoing AI audio for interruption
        self.interrupted = False    # Flag to stop AI audio
        
        # ==================== REFINED INTERRUPTION HANDLING ====================
        # Track when AI started speaking (for grace period)
        self.ai_speech_start_time = None
        # Track when user started speaking during interrupt (for sustained speech check)
        self.interrupt_speech_start = None
        # Consecutive speech frames during interrupt detection
        self.interrupt_speech_frames = 0
        # Pending AI text that hasn't been committed yet (cleared on interrupt)
        self.pending_ai_text = None
        # Track if current interrupt is an acknowledgement (continue AI flow)
        self.is_acknowledgement_interrupt = False
        # Thread safety lock for state transitions and buffer access
        self._state_lock = asyncio.Lock()
        # Flag to prevent double-processing
        self._processing_speech = False
        # USER_SPEAKING timeout tracking
        self.user_speaking_start_time = None
        
        # Language Selection State
        self.language_verified = not self.LANGUAGE_SELECTION_ENABLED
        self.selected_language = "en"
        self.language_retry_count = 0  # Track failed language detection attempts (max 2)

        # Deterministic call-flow runtime state
        self.awaiting_permission = False
        self.permission_granted = True
        self.call_closed = False

        # Deterministic WOW checkpoint state machine (PASS/SKIP/FAIL/PENDING)
        self.wow_checkpoint_state = new_wow_checkpoint_state()
        self.wow_checkpoint_order = ["INTENT", "GEOGRAPHY", "BUDGET", "TIMELINE"]
        self.last_checkpoint_asked = None
        
        # Call Stage (for context-aware timeouts)
        self.call_stage = CallStage.LANGUAGE_SELECT if self.LANGUAGE_SELECTION_ENABLED else CallStage.OPEN_ENDED
        
        # ==================== ADAPTIVE USER PATTERNS (Phase 1) ====================
        # Learn user's speaking patterns for smarter endpointing
        self.user_pause_history = []  # Track user's natural pause durations
        self.user_utterance_durations = []  # Track typical response lengths
        self.user_avg_pause_ms = 500  # Start with 500ms default
        self.early_stt_enabled = True  # Enable parallel STT processing
        self.early_stt_attempted = False  # Track if early STT was already tried for this utterance
        
        logger.info(f"CallSession created: {call_id} | StreamSID: {stream_sid} | Stage: {self.call_stage.value}")
    
    def get_dynamic_speech_end_frames(self) -> int:
        """
        Smart dual-threshold + adaptive timeout endpointing (Option B).
        
        Reduced thresholds to actually trigger speech_end (was never reaching threshold).
        WebRTC VAD detecting silence but we were waiting too long.
        """
        # Calculate buffer duration if available
        buffer_duration = len(self.audio_buffer) / TWILIO_SAMPLE_RATE if self.audio_buffer else 0.0
        
        # Calculate speaking duration if available
        speaking_duration = 0.0
        if self.user_speaking_start_time:
            speaking_duration = (datetime.now() - self.user_speaking_start_time).total_seconds()
        
        # Stage-specific logic (REDUCED thresholds so speech_end actually triggers)
        if self.call_stage == CallStage.LANGUAGE_SELECT:
            return 6   # 180ms - very quick for "English", "Hindi"
        
        elif self.call_stage == CallStage.YES_NO:
            return 8  # 240ms - quick for "yes", "no"
        
        elif self.call_stage == CallStage.SHORT_ANSWER:
            # Short answer: Use buffer-based threshold
            if buffer_duration < 1.5:
                return 10  # 300ms - fast for quick answers
            else:
                return 15  # 450ms - patient for longer explanations
        
        else:  # OPEN_ENDED
            # Dual-threshold (REDUCED to actually trigger before 4s timeout)
            if buffer_duration < 2.0:
                # Short buffer: Fast response
                return 10  # 300ms
            else:
                # Long buffer: Patient but not too patient
                # Silero will double-check if this is truly the end
                if speaking_duration < 6.0:
                    return 20  # 600ms - patient for complex thoughts
                else:
                    return 15  # 450ms - faster for long monologues
    
    def detect_intent_completion(self, buffer_pcm: bytes, duration_ms: float) -> tuple[bool, str]:
        """Detect if speech sounds complete based on prosody (Phase 2)
        
        Returns: (is_complete, reason)
        """
        if duration_ms < 300:  # Too short to analyze
            return (False, "too_short")
        
        # Analyze energy distribution (falling energy = completion)
        import audioop
        try:
            # Split audio into 3 segments (beginning, middle, end)
            segment_size = len(buffer_pcm) // 3
            if segment_size < 100:  # Not enough data
                return (False, "insufficient_data")
            
            start_segment = buffer_pcm[:segment_size]
            middle_segment = buffer_pcm[segment_size:segment_size*2]
            end_segment = buffer_pcm[segment_size*2:]
            
            # Calculate RMS energy for each segment
            start_energy = audioop.rms(start_segment, 2)
            middle_energy = audioop.rms(middle_segment, 2)
            end_energy = audioop.rms(end_segment, 2)
            
            # Pattern 1: Falling energy (statement completion)
            if end_energy < middle_energy * 0.7 and middle_energy >= start_energy * 0.8:
                return (True, "falling_energy")
            
            # Pattern 2: Consistent low energy at end (pause/thinking)
            if end_energy < middle_energy * 0.5 and duration_ms > 800:
                return (True, "sustained_drop")
            
            return (False, "no_pattern")
            
        except Exception:
            return (False, "error")
    
    def add_audio_chunk(self, audio_data: bytes):
        """Add audio chunk to buffer"""
        self.audio_buffer.extend(audio_data)
    
    def get_and_clear_buffer(self) -> bytes:
        """Get audio buffer and clear it"""
        data = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        return data
    
    def has_sufficient_audio(self) -> bool:
        """Check if buffer has enough audio"""
        min_bytes = (TWILIO_SAMPLE_RATE * self.MIN_AUDIO_DURATION_MS) // 1000
        return len(self.audio_buffer) >= min_bytes
    
    def is_in_echo_window(self) -> bool:
        """Check if we're still in the echo ignore window after TTS"""
        if self.tts_end_time is None:
            return False
        elapsed_ms = (datetime.now() - self.tts_end_time).total_seconds() * 1000
        return elapsed_ms < self.ECHO_IGNORE_MS
    
    def is_in_noise_cooldown(self) -> bool:
        """Check if we're still in cooldown after noise detection"""
        if self.noise_detected_time is None:
            return False
        elapsed_ms = (datetime.now() - self.noise_detected_time).total_seconds() * 1000
        return elapsed_ms < self.POST_NOISE_COOLDOWN_MS
    
    def is_in_ai_grace_period(self) -> bool:
        """
        Check if we're in the grace period after AI started speaking.
        During this window, ignore ALL VAD triggers to prevent false interrupts
        from echo onset or audio overlap.
        """
        if self.ai_speech_start_time is None:
            return False
        elapsed_ms = (datetime.now() - self.ai_speech_start_time).total_seconds() * 1000
        return elapsed_ms < AI_SPEECH_GRACE_PERIOD_MS
    
    def check_user_speaking_timeout(self) -> bool:
        """
        Check if USER_SPEAKING state has timed out.
        Returns True if timeout exceeded (should reset to LISTENING).
        """
        if self.user_speaking_start_time is None:
            return False
        elapsed_ms = (datetime.now() - self.user_speaking_start_time).total_seconds() * 1000
        return elapsed_ms > USER_SPEAKING_TIMEOUT_MS
    
    def mark_noise_detected(self):
        """Mark that noise was detected, starting cooldown"""
        self.noise_detected_time = datetime.now()
    
    def is_first_utterance_after_ai(self) -> bool:
        """Check if this is the first utterance after AI finished speaking"""
        return self.utterances_since_ai == 0 and self.last_ai_turn_end is not None
    
    def mark_ai_turn_complete(self):
        """Mark that AI finished speaking"""
        self.ai_turn_count += 1
        self.last_ai_turn_end = datetime.now()
        self.utterances_since_ai = 0
    
    def mark_user_utterance(self):
        """Mark that user made a real utterance (not noise)"""
        self.utterances_since_ai += 1
    
    def detect_speech_vad(self, audio_data: bytes) -> bool:
        """
        WebRTC VAD speech detection with SANITY CHECKS
        
        Returns True ONLY if:
        1. Not in echo ignore window (1000ms after TTS)
        2. Energy is in valid speech range (not noise/clipping)
        3. WebRTC VAD confirms speech OR energy strongly suggests speech
        """
        global vad
        
        if len(audio_data) == 0:
            return False
        
        # Calculate energy (mulaw: 127 is silence, deviation indicates sound)
        energy = sum(abs(b - 127) for b in audio_data) / len(audio_data)
        
        # ==================== SANITY CHECK 1: Echo Window ====================
        if self.is_in_echo_window():
            # Still in echo ignore period - don't detect any speech
            return False
        
        # ==================== SANITY CHECK 2: Minimum Energy ====================
        # Dynamic threshold: stricter energy when AI is speaking (barge-in mode)
        # This prevents small noises from interrupting the AI
        min_energy = self.MIN_SPEECH_ENERGY_BARGEIN if self.state == ConversationState.AI_SPEAKING else self.MIN_SPEECH_ENERGY
        if energy < min_energy:
            return False  # Too quiet to be speech (or not loud enough to interrupt)
        
        # Add to VAD buffer for frame alignment
        self.vad_buffer.extend(audio_data)
        
        # ==================== VAD BUFFER OVERFLOW PROTECTION ====================
        # Prevent unbounded growth - max 10KB (about 1.25 seconds at 8kHz)
        MAX_VAD_BUFFER_SIZE = 10240
        if len(self.vad_buffer) > MAX_VAD_BUFFER_SIZE:
            logger.warning(f"âš ï¸ VAD buffer overflow ({len(self.vad_buffer)} bytes) - truncating")
            # Keep only the most recent data
            self.vad_buffer = self.vad_buffer[-MAX_VAD_BUFFER_SIZE:]
        
        # WebRTC VAD needs exact frame sizes
        if len(self.vad_buffer) < self.VAD_FRAME_BYTES:
            # Not enough for WebRTC VAD, use energy-only detection
            # Only trigger if energy is in strong speech range
            return 50 < energy < 100
        
        try:
            speech_frame_count = 0
            total_frames = 0
            
            # Process all complete frames
            while len(self.vad_buffer) >= self.VAD_FRAME_BYTES:
                frame_data = bytes(self.vad_buffer[:self.VAD_FRAME_BYTES])
                self.vad_buffer = self.vad_buffer[self.VAD_FRAME_BYTES:]
                
                # Convert mulaw to PCM for VAD
                pcm_data = audioop.ulaw2lin(frame_data, 2)
                total_frames += 1
                
                if vad.is_speech(pcm_data, TWILIO_SAMPLE_RATE):
                    speech_frame_count += 1
            
            # Require majority of frames to be speech (reduces false positives)
            is_speech = speech_frame_count > (total_frames / 2) if total_frames > 0 else False
            
            # Only trust energy fallback for STRONG speech indicators
            if not is_speech and 55 < energy < 90:
                # Energy suggests possible speech but VAD disagrees
                # Trust VAD more than energy (VAD is ML-based)
                pass  # Don't override VAD decision
            
            return is_speech
            
        except Exception as e:
            logger.warning(f"VAD error: {e}")
            self.vad_buffer.clear()
            # Fallback: stricter energy-based detection
            return 55 < energy < 90
    
    def detect_speech_silero(self, audio_chunk: bytes) -> float:
        """
        Use Silero VAD for more accurate speech probability detection.
        Returns probability (0.0 to 1.0) that audio contains speech.
        
        Silero is better than WebRTC VAD at:
        - Understanding natural speech pauses (thinking, breathing)
        - Detecting speech completion vs mid-sentence pauses
        - Handling varied accents and languages
        
        Args:
            audio_chunk: Raw audio bytes (8kHz mulaw from Twilio)
        
        Returns:
            Speech probability (0.0 = silence, 1.0 = definite speech)
        """
        if silero_model is None:
            # Fallback to WebRTC if Silero not loaded
            return 0.5
        
        try:
            # Convert mulaw to PCM 16-bit
            pcm_data = audioop.ulaw2lin(audio_chunk, 2)
            
            # Convert to numpy array
            audio_array = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Silero expects 16kHz - resample from 8kHz
            audio_16k = np.repeat(audio_array, 2)  # Simple upsampling
            
            # Silero VAD expects exactly 512 samples for 16kHz (32ms chunks)
            # If we have more, take the last 512 samples; if less, pad with zeros
            if len(audio_16k) > 512:
                audio_16k = audio_16k[-512:]  # Last 512 samples (most recent audio)
            elif len(audio_16k) < 512:
                audio_16k = np.pad(audio_16k, (0, 512 - len(audio_16k)), mode='constant')
            
            # Convert to torch tensor
            audio_tensor = torch.from_numpy(audio_16k)
            
            # Get speech probability (0.0 to 1.0)
            with torch.no_grad():
                speech_prob = silero_model(audio_tensor, 16000).item()
            
            return speech_prob
            
        except Exception as e:
            logger.error(f"Silero VAD error: {e}")
            return 0.5  # Neutral fallback
    
    def update_vad_state(self, is_speech: bool) -> str | None:
        """
        VAD edge-trigger state machine with HYSTERESIS
        Returns: "speech_start", "speech_end", or None
        
        HYSTERESIS prevents false triggers:
        - Speech start: 8 consecutive speech frames (~240ms)
        - Speech end: 10 consecutive silence frames (~300ms)
        
        PROTECTION:
        - Ignores VAD while LLM is in-flight
        """
        # ==================== PROTECTION CHECKS ====================
        if self.llm_in_flight:
            # LLM is processing - ignore VAD to prevent false triggers
            return None
        
        # ==================== STATE MACHINE ====================
        if is_speech:
            self.consecutive_speech_frames += 1
            self.consecutive_silence_frames = 0
            
            # Check for speech start trigger (LISTENING mode - standard threshold)
            if self.state == ConversationState.LISTENING and self.consecutive_speech_frames >= self.SPEECH_START_FRAMES:
                logger.info(f"ðŸŽ™ï¸ VAD: Speech detected for {self.consecutive_speech_frames} frames ({self.consecutive_speech_frames * 30}ms) - triggering speech_start")
                return "speech_start"
            
            # Check for BARGE-IN trigger (AI_SPEAKING mode - stricter threshold)
            if self.state == ConversationState.AI_SPEAKING and self.consecutive_speech_frames >= self.SPEECH_START_FRAMES_BARGEIN:
                logger.info(f"ðŸš¨ BARGE-IN: User spoke for {self.consecutive_speech_frames} frames ({self.consecutive_speech_frames * 30}ms) - interrupting AI")
                return "barge_in"
        else:
            self.consecutive_silence_frames += 1
            # DON'T reset speech frames immediately - allow gaps in speech
            # Only reset after significant silence (4 frames = 120ms)
            if self.consecutive_silence_frames >= 4:
                self.consecutive_speech_frames = 0
            
            # Check for speech end trigger (only during USER_SPEAKING)
            if self.state == ConversationState.USER_SPEAKING:
                # Use Silero VAD for smarter endpointing
                # Analyze recent audio buffer to check if speech is truly done
                buffer_duration = len(self.audio_buffer) / TWILIO_SAMPLE_RATE if self.audio_buffer else 0.0
                
                # Use dynamic endpointing based on call stage
                dynamic_end_frames = self.get_dynamic_speech_end_frames()
                
                if self.consecutive_silence_frames >= dynamic_end_frames:
                    # Double-check with Silero: Is this truly the end or just a pause?
                    if silero_model and buffer_duration > 1.0:
                        # Analyze last 480ms of buffer with Silero
                        check_bytes = min(3840, len(self.audio_buffer))  # 480ms = 3840 bytes at 8kHz
                        recent_audio = bytes(self.audio_buffer[-check_bytes:])
                        speech_prob = self.detect_speech_silero(recent_audio)
                        
                        # If Silero detects speech in recent buffer, user might still be speaking
                        if speech_prob > 0.4:
                            logger.debug(f"ðŸ” Silero: Speech prob {speech_prob:.2f} - user might continue, waiting...")
                            return None  # Keep waiting
                    
                    silence_ms = self.consecutive_silence_frames * 30
                    logger.info(f"ðŸ”‡ VAD: Silence for {self.consecutive_silence_frames} frames ({silence_ms}ms) - triggering speech_end [Stage: {self.call_stage.value}, Threshold: {dynamic_end_frames} frames, Buffer: {buffer_duration:.1f}s]")
                    return "speech_end"
        
        return None
    
    def reset_for_listening(self):
        """Reset state for listening mode - DOES NOT clear echo window"""
        self.speech_start_time = None
        self.silence_start_time = None
        self.consecutive_speech_frames = 0
        self.consecutive_silence_frames = 0
        self.vad_buffer.clear()
        self.llm_in_flight = False
        self.state = ConversationState.LISTENING
        # Reset interrupt-specific tracking
        self.interrupt_speech_start = None
        self.interrupt_speech_frames = 0
        self.is_acknowledgement_interrupt = False
        self.user_speaking_start_time = None
        self._processing_speech = False
        # NOTE: tts_end_time is NOT cleared - echo window must expire naturally
        # NOTE: ai_speech_start_time is NOT cleared - grace period must expire naturally
    
    def interrupt_ai(self):
        """Signal to interrupt ongoing AI audio"""
        self.interrupted = True
        # Clear pending AI text on interrupt (context hygiene)
        self.pending_ai_text = None
        logger.info("ðŸ›‘ BARGE-IN: User interrupted AI speech")
    
    def validate_interrupt_speech(self, is_speech: bool) -> bool:
        """
        Validate if user speech during AI_SPEAKING should trigger an interrupt.
        
        Returns True ONLY if ALL conditions are met:
        1. Not in AI speech grace period (first 300ms)
        2. Sustained speech duration >= MIN_INTERRUPT_SPEECH_MS (300ms)
        3. Speech is not a single blip that immediately stops
        
        This prevents false interrupts from:
        - Echo onset at start of AI speech
        - Short noise blips
        - Single syllables
        - Background noise
        """
        # Condition 1: Grace period check
        if self.is_in_ai_grace_period():
            self.interrupt_speech_frames = 0
            self.interrupt_speech_start = None
            return False
        
        if is_speech:
            self.interrupt_speech_frames += 1
            
            # Start tracking when speech first detected
            if self.interrupt_speech_start is None:
                self.interrupt_speech_start = datetime.now()
            
            # Condition 2: Check sustained speech duration
            elapsed_ms = (datetime.now() - self.interrupt_speech_start).total_seconds() * 1000
            
            # Require BOTH frame count AND duration to pass
            # Frame count: at least 10 frames (~300ms at 30ms/frame)
            # Duration: at least MIN_INTERRUPT_SPEECH_MS
            min_frames = int(MIN_INTERRUPT_SPEECH_MS / 30)  # ~10 frames for 300ms
            
            if self.interrupt_speech_frames >= min_frames and elapsed_ms >= MIN_INTERRUPT_SPEECH_MS:
                logger.info(f"âœ… Valid interrupt: {self.interrupt_speech_frames} frames, {elapsed_ms:.0f}ms sustained speech")
                return True
            else:
                logger.debug(f"â³ Interrupt pending: {self.interrupt_speech_frames}/{min_frames} frames, {elapsed_ms:.0f}/{MIN_INTERRUPT_SPEECH_MS}ms")
                return False
        else:
            # Condition 3: Speech stopped - reset if silence persists
            # Allow brief gaps (2 frames = 60ms) but reset on longer silence
            if self.interrupt_speech_frames > 0:
                # Track silence during interrupt detection
                if not hasattr(self, '_interrupt_silence_frames'):
                    self._interrupt_silence_frames = 0
                self._interrupt_silence_frames += 1
                
                # If silence > 60ms (2 frames), speech was just a blip
                if self._interrupt_silence_frames >= 2:
                    logger.debug(f"ðŸ”‡ Interrupt cancelled: speech stopped after {self.interrupt_speech_frames} frames")
                    self.interrupt_speech_frames = 0
                    self.interrupt_speech_start = None
                    self._interrupt_silence_frames = 0
            return False
    
    # ==================== CONTEXT TRACKING ====================
    
    def get_max_speech_duration(self) -> float:
        """
        Get context-aware max speech duration based on call stage.
        Simple timeout: 6 seconds for most cases, shorter for language selection.
        """
        return self.MAX_SPEECH_DURATION_BY_STAGE.get(self.call_stage, 6.0)
    
    def should_force_process_timeout(self) -> bool:
        """
        Check if we should force-process due to timeout.
        Prevents infinite buffering when user doesn't pause naturally.
        """
        if self.state != ConversationState.USER_SPEAKING:
            return False
        
        if not self.user_speaking_start_time:
            return False
        
        speaking_duration = (datetime.now() - self.user_speaking_start_time).total_seconds()
        max_duration = self.get_max_speech_duration()
        buffer_duration = len(self.audio_buffer) / TWILIO_SAMPLE_RATE
        
        # Force process if exceeded stage-specific max AND have meaningful audio
        if speaking_duration >= max_duration and buffer_duration >= 0.5:
            logger.warning(f"â±ï¸ Context-aware timeout: {speaking_duration:.1f}s >= {max_duration:.1f}s (stage: {self.call_stage.value})")
            return True
        
        # Additional safety: absolute max regardless of stage
        if speaking_duration >= 8.0 and buffer_duration >= 1.0:
            logger.warning(f"â±ï¸ Absolute timeout: {speaking_duration:.1f}s (hard limit)")
            return True
        
        return False
    
    def update_call_stage(self, ai_question: str = None):
        """
        Update call stage based on AI's question context (Phase 2: Enhanced with intent detection).
        Allows dynamic timeout adjustment as conversation progresses.
        """
        if not ai_question:
            return
        
        question_lower = ai_question.lower()
        
        # Detect question type from AI's last response (Phase 2: More patterns)
        if any(word in question_lower for word in ["english", "hindi", "marathi", "language", "prefer", "à¤­à¤¾à¤·à¤¾"]):
            self.call_stage = CallStage.LANGUAGE_SELECT
        elif any(word in question_lower for word in ["yes or no", "yes/no", "confirm", "interested", "okay", "good time", "moment", "available", "à¤¹à¤¾à¤ à¤¯à¤¾ à¤¨à¤¾", "à¤•à¥à¤¯à¤¾ à¤†à¤ª"]):
            self.call_stage = CallStage.YES_NO
        elif any(word in question_lower for word in ["name", "email", "phone", "number", "date", "time", "when", "which day", "how many", "à¤¨à¤¾à¤®", "à¤ˆà¤®à¥‡à¤²", "à¤«à¥‹à¤¨", "à¤•à¤¬", "à¤•à¤¿à¤¤à¤¨à¥‡"]):
            self.call_stage = CallStage.SHORT_ANSWER
        else:
            self.call_stage = CallStage.OPEN_ENDED
        
        logger.debug(f"ðŸ“Š Call stage updated to: {self.call_stage.value}")


def classify_interruption_intent(text: str) -> tuple[str, bool]:
    """
    Classify whether an interruption is an acknowledgement or a real topic change.
    
    Returns: (intent_type, should_continue_ai_flow)
    - ("acknowledgement", True) - User said "yeah", "okay", etc. - continue AI naturally
    - ("topic_change", False) - User has new input - process normally
    - ("question", False) - User asked a question - needs response
    """
    if not text:
        return ("empty", True)  # Empty = continue
    
    text_lower = text.lower().strip()
    words = text_lower.split()
    
    # Very short (1-3 words) and matches acknowledgement patterns
    if len(words) <= 3:
        for pattern in ACKNOWLEDGEMENT_PATTERNS:
            if text_lower == pattern or text_lower.startswith(pattern + " "):
                return ("acknowledgement", True)
    
    # Question detection (ends with ?, or starts with question words)
    if text_lower.endswith("?") or any(text_lower.startswith(q) for q in ["what", "when", "where", "why", "how", "who", "can", "could", "would", "is", "are", "do", "does"]):
        return ("question", False)
    
    # Longer utterances or non-acknowledgements = topic change
    return ("topic_change", False)


# ==================== TWIML ENDPOINTS ====================

@app.get("/")
async def root():
    """Health check"""
    return {
        "service": "Divyashree Voice Gateway",
        "status": "running",
        "active_calls": len(active_sessions)
    }


@app.get("/system/voice-gateway-url")
async def get_voice_gateway_url():
    """Get current voice gateway tunnel URL"""
    # Prefer detected ngrok/tunnel URL over env var
    effective_url = ngrok_public_url or os.getenv("VOICE_GATEWAY_URL") or "not configured"
    return {"url": effective_url}


@app.get("/info")
async def get_info():
    """Get gateway info including ngrok URL"""
    # Prefer detected ngrok/tunnel URL over env var
    effective_url = ngrok_public_url or os.getenv("VOICE_GATEWAY_URL") or "not configured"
    return {
        "service": "Divyashree Voice Gateway",
        "status": "running",
        "active_calls": len(active_sessions),
        "ngrok_url": effective_url,
        "port": int(os.getenv("VOICE_GATEWAY_PORT", 8001))
    }


@app.post("/twiml/{call_id}")
async def twiml_handler(call_id: str, request: Request):
    """
    Generate TwiML with Media Streams for real-time bidirectional audio
    This enables sub-1-second response times and natural interruptions
    """
    try:
        logger.info(f"TwiML requested for call: {call_id}")
        
        # Get call details from database
        db = get_db()
        call = await db.get_call(call_id)
        
        if not call:
            logger.error(f"Call {call_id} not found in database")
            return Response(content="<Response><Say>Call not found</Say></Response>", media_type="application/xml")
        
        # Update call status
        await db.update_call(call_id, status="in-progress", started_at=datetime.now())
        logger.info(f"Call {call_id} status updated to in-progress")
        
        # Get WebSocket URL (use VOICE_GATEWAY_WS_URL or convert HTTP to WSS)
        ws_url = os.getenv("VOICE_GATEWAY_WS_URL")
        if not ws_url:
            # Try to build from detected tunnel URL first, then env var
            base_url = ngrok_public_url or os.getenv("VOICE_GATEWAY_URL")
            if base_url:
                # Convert https:// to wss://
                ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
        
        if not ws_url or ws_url.startswith("wss://your-"):
            logger.error("WebSocket URL not configured properly")
            return Response(
                content="<Response><Say>WebSocket configuration error</Say></Response>",
                media_type="application/xml"
            )
        
        # Generate TwiML with Media Streams for real-time audio
        ws_endpoint = f"{ws_url}/ws/{call_id}"
        
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_endpoint}">
            <Parameter name="call_id" value="{call_id}"/>
        </Stream>
    </Connect>
</Response>"""
        
        logger.info(f"TwiML with Media Streams generated for {call_id} -> {ws_endpoint}")
        return Response(content=twiml, media_type="application/xml")
        
    except Exception as e:
        error_msg = str(e).replace("{", "{{").replace("}", "}}")
        logger.error(f"Error generating TwiML for {call_id}: {error_msg}", exc_info=False)
        return Response(
            content="<Response><Say>Sorry, there was an error</Say></Response>",
            media_type="application/xml"
        )


async def generate_call_analysis(call_id: str, db):
    """Generate AI-powered call analysis summary"""
    try:
        # Get transcripts
        transcripts = await db.get_transcripts(call_id) or []

        # Build conversation text
        conversation_text = "\n".join([
            f"{t['speaker'].upper()}: {t['text']}" 
            for t in transcripts
        ])

        # Persist a structured fallback analysis even when transcript data is sparse.
        if len(transcripts) < 2:
            logger.info(f"Insufficient transcript data for full analysis: {call_id}; saving default structured analysis")
            sparse_defaults = normalize_wow_analysis(
                {
                    "summary": "Call ended before enough conversation was captured for full analysis.",
                    "key_points": ["Insufficient transcript for deep analysis"],
                    "user_sentiment": "neutral",
                    "outcome": "other",
                    "next_action": "DO_NOT_CONTACT",
                    "intent_category": "UNCLEAR",
                    "budget_fit": "MAYBE",
                    "geography_fit": "HESITANT",
                    "timeline_fit": "HESITANT",
                    "overall_grade": "COLD",
                    "checkpoint_json": {
                        "c1_intent": "FAIL",
                        "c2_geography": "FAIL",
                        "c3_budget": "FAIL",
                        "c4_timeline": "FAIL",
                    },
                },
                conversation_text,
            )

            await db.save_call_analysis(
                call_id=call_id,
                summary=sparse_defaults.get("summary", ""),
                key_points=sparse_defaults.get("key_points", []),
                user_sentiment=sparse_defaults.get("user_sentiment", "neutral"),
                outcome=sparse_defaults.get("outcome", "other"),
                next_action=sparse_defaults.get("next_action", "DO_NOT_CONTACT"),
                intent_category=sparse_defaults.get("intent_category", "UNCLEAR"),
                budget_fit=sparse_defaults.get("budget_fit", "MAYBE"),
                geography_fit=sparse_defaults.get("geography_fit", "HESITANT"),
                timeline_fit=sparse_defaults.get("timeline_fit", "HESITANT"),
                overall_grade=sparse_defaults.get("overall_grade", "COLD"),
                checkpoint_json=sparse_defaults.get("checkpoint_json", {
                    "c1_intent": "FAIL",
                    "c2_geography": "FAIL",
                    "c3_budget": "FAIL",
                    "c4_timeline": "FAIL",
                }),
            )
            return
        
        # Use LLM to analyze the call
        llm = get_llm_client()
        
        analysis_prompt = f"""Analyze this phone call conversation. Read the ENTIRE conversation carefully and provide accurate analysis.

CONVERSATION:
{conversation_text}

ANALYSIS INSTRUCTIONS:

1. SUMMARY: Write 2-3 sentences describing what happened in the call

2. KEY POINTS: List 2-4 main topics or important details discussed

3. USER SENTIMENT: This is CRITICAL - analyze the user's actual emotional state throughout the conversation.
   
   Look for these indicators:
   - POSITIVE: Words like "great", "perfect", "excellent", "love it", "sounds good", "thank you", enthusiasm, eagerness
   - NEGATIVE: Words like "frustrated", "confused", "problem", "issue", "disappointed", "not happy", complaints, resistance
   - NEUTRAL: Purely factual responses, business-like tone, no emotional indicators either way
   
   Pay attention to:
   - How they started vs how they ended (did sentiment improve or worsen?)
   - Their willingness to engage (eager questions vs reluctant answers?)
   - Their word choices (positive/negative language)
   - Overall tone (friendly vs cold, cooperative vs resistant)
   
   DO NOT default to neutral - only choose neutral if there are truly no emotional indicators.
   
   Choose the sentiment that BEST matches the conversation:
   - very_positive: User is enthusiastic, excited, multiple positive words, highly engaged
   - positive: User is friendly, cooperative, satisfied, helpful
   - neutral: User is purely factual/business-like with NO emotional indicators either way
   - negative: User shows frustration, annoyance, dissatisfaction, or reluctance
   - very_negative: User is angry, hostile, very upset, or openly hostile

4. OUTCOME: Based on the conversation result:
   - interested: User wants to proceed/book/buy
   - not_interested: User declined or not interested
   - call_later: User wants to be contacted later
   - needs_more_info: User needs more information before deciding
   - wrong_number: Wrong person or misunderstanding
   - other: Doesn't fit above categories

5. NEXT ACTION: Specific recommended follow-up step

6. WOW QUALIFICATION FIELDS (use these exact enums):
     - intent_category: SELF_USE | INVESTMENT | UNCLEAR
     - budget_fit: YES | MAYBE | NO
     - geography_fit: YES | HESITANT | NO
     - timeline_fit: YES | HESITANT | NO
     - overall_grade: HOT | WARM | COLD
     - checkpoint_json:
         {{
             "c1_intent": "PASS|SKIP|FAIL",
             "c2_geography": "PASS|SKIP|FAIL",
             "c3_budget": "PASS|SKIP|FAIL",
             "c4_timeline": "PASS|SKIP|FAIL"
         }}
     - next_action must be one of: BOOK_EXPERT_CALL | SEND_BROCHURE | DO_NOT_CONTACT

Return ONLY valid JSON (no other text):
{{
  "summary": "",
  "key_points": [],
  "user_sentiment": "",
  "outcome": "",
    "next_action": "",
    "intent_category": "",
    "budget_fit": "",
    "geography_fit": "",
    "timeline_fit": "",
    "overall_grade": "",
    "checkpoint_json": {{}}
}}"""
        
        messages = [{"role": "user", "content": analysis_prompt}]
        response = await llm.generate_response(
            messages=messages,
            system_prompt="You are a call analysis assistant. Analyze conversations and provide structured insights.",
            temperature=0.3,
            max_tokens=300
        )
        
        # Parse JSON response
        import json
        try:
            analysis_data = json.loads(response)
        except:
            # Fallback if LLM doesn't return valid JSON
            logger.warning(f"Failed to parse LLM analysis as JSON for {call_id}")
            analysis_data = {
                "summary": response[:200],
                "key_points": ["Analysis failed to parse"],
                "user_sentiment": "neutral",
                "outcome": "other",
                "next_action": "DO_NOT_CONTACT",
                "intent_category": "UNCLEAR",
                "budget_fit": "MAYBE",
                "geography_fit": "HESITANT",
                "timeline_fit": "HESITANT",
                "overall_grade": "COLD",
                "checkpoint_json": {
                    "c1_intent": "FAIL",
                    "c2_geography": "FAIL",
                    "c3_budget": "FAIL",
                    "c4_timeline": "FAIL"
                }
            }

        # Normalize/repair WOW-specific fields with deterministic inference fallback.
        analysis_data = normalize_wow_analysis(analysis_data, conversation_text)
        
        # Save analysis
        await db.save_call_analysis(
            call_id=call_id,
            summary=analysis_data.get("summary", ""),
            key_points=analysis_data.get("key_points", []),
            user_sentiment=analysis_data.get("user_sentiment", "neutral"),
            outcome=analysis_data.get("outcome", "other"),
            next_action=analysis_data.get("next_action", "DO_NOT_CONTACT"),
            intent_category=analysis_data.get("intent_category", "UNCLEAR"),
            budget_fit=analysis_data.get("budget_fit", "MAYBE"),
            geography_fit=analysis_data.get("geography_fit", "HESITANT"),
            timeline_fit=analysis_data.get("timeline_fit", "HESITANT"),
            overall_grade=analysis_data.get("overall_grade", "COLD"),
            checkpoint_json=analysis_data.get("checkpoint_json", {
                "c1_intent": "FAIL",
                "c2_geography": "FAIL",
                "c3_budget": "FAIL",
                "c4_timeline": "FAIL"
            })
        )
        
        logger.info(f"âœ… Call analysis saved for {call_id}: {analysis_data.get('outcome')}")
        
        # Check for scheduling intent and create calendar event if detected
        outcome = analysis_data.get("outcome", "")
        if outcome in ["interested", "call_later"]:
            await auto_create_calendar_event(
                call_id=call_id,
                transcript=conversation_text,
                call_summary=analysis_data.get("summary", ""),
                outcome=outcome,
                db=db
            )
        
    except Exception as e:
        logger.error(f"Error generating call analysis for {call_id}: {e}")


async def auto_create_calendar_event(
    call_id: str,
    transcript: str,
    call_summary: str,
    outcome: str,
    db
):
    """
    Automatically detect scheduling intent and create calendar event + Cal.com booking.
    
    This is the core workflow for end-to-end calendar automation:
    1. Detect if a specific time was agreed upon during the call
    2. Extract event details (date, time, type, contact info)
    3. Create Cal.com booking via API
    4. Store event in database linked to this call
    5. Event appears in dashboard and Cal.com calendar
    """
    try:
        logger.info(f"ðŸ—“ï¸  Checking for scheduling intent in call {call_id}")
        
        # Import scheduling detector
        import sys
        sys.path.insert(0, '/app/shared')
        from scheduling_detector import scheduling_detector
        
        # Detect scheduling intent
        scheduling_data = await scheduling_detector.detect_scheduling_intent(
            transcript=transcript,
            call_summary=call_summary,
            outcome=outcome
        )
        
        if not scheduling_data or not scheduling_data.get("scheduled"):
            logger.info(f"No scheduling detected in call {call_id}")
            return
        
        logger.info(f"âœ… Scheduling detected: {scheduling_data}")
        
        # Get call details for contact info
        call_details = await db.get_call(call_id)
        if not call_details:
            logger.error(f"Could not find call details for {call_id}")
            return
        
        contact_phone = call_details.get("to_number")
        user_id = call_details.get("user_id")
        campaign_id = call_details.get("campaign_id")
        
        if not user_id:
            logger.error(f"No user_id found for call {call_id}")
            return
        
        # Prepare event data
        event_type = scheduling_data.get("event_type", "call")
        contact_name = scheduling_data.get("contact_name", "Customer")
        date_str = scheduling_data.get("date")
        time_str = scheduling_data.get("time")
        timezone = scheduling_data.get("timezone", "America/New_York")
        notes = scheduling_data.get("notes", "")
        
        # Convert to ISO datetime
        iso_datetime = scheduling_detector.convert_to_iso_datetime(
            date_str, time_str, timezone
        )
        
        # Generate event title
        event_titles = {
            "demo": "Product Demo",
            "followup": "Follow-up Call",
            "call": "Scheduled Call",
            "meeting": "Meeting"
        }
        title = event_titles.get(event_type, "Scheduled Call")
        
        # Create Cal.com booking if configured
        cal_booking_id = None
        cal_booking_uid = None
        contact_email = None  # We don't have email from call, use placeholder
        
        import httpx
        async with httpx.AsyncClient() as client:
            # Check Cal.com status
            cal_status_response = await client.get("http://backend:8000/cal/status")
            
            if cal_status_response.status_code == 200:
                cal_data = cal_status_response.json()
                
                if cal_data.get("configured") and cal_data.get("event_types"):
                    try:
                        # Get first available event type
                        event_type_id = cal_data["event_types"][0]["id"]
                        
                        # Generate email from phone if not available
                        if not contact_email:
                            # Use sanitized phone as email placeholder
                            sanitized_phone = contact_phone.replace("+", "").replace("-", "")
                            contact_email = f"customer_{sanitized_phone}@placeholder.com"
                        
                        # Create Cal.com booking
                        booking_payload = {
                            "event_type_id": event_type_id,
                            "start_time": iso_datetime,
                            "name": contact_name,
                            "email": contact_email,
                            "phone": contact_phone,
                            "notes": f"Auto-scheduled from call. {notes}",
                            "timezone": timezone
                        }
                        
                        booking_response = await client.post(
                            "http://backend:8000/cal/create-booking",
                            json=booking_payload,
                            timeout=30.0
                        )
                        
                        if booking_response.status_code == 200:
                            booking_data = booking_response.json()
                            cal_booking_id = booking_data.get("id")
                            cal_booking_uid = booking_data.get("uid")
                            booking_url = booking_data.get("booking_url") or booking_data.get("bookingUrl")
                            logger.info(f"âœ… Created Cal.com booking: {cal_booking_uid}")
                            
                            # Send SMS with booking link if we have a phone number and booking URL
                            if contact_phone and booking_url:
                                try:
                                    sms_body = f"Your {title} is confirmed for {date_str} at {time_str}. Join here: {booking_url}"
                                    twilio_client.messages.create(
                                        body=sms_body,
                                        from_=TWILIO_PHONE_NUMBER,
                                        to=contact_phone
                                    )
                                    logger.info(f"ðŸ“± Sent booking link SMS to {contact_phone}")
                                except Exception as sms_error:
                                    logger.warning(f"Failed to send booking SMS: {sms_error}")
                        else:
                            logger.warning(f"Cal.com booking failed ({booking_response.status_code}): {booking_response.text}")
                            # Log the payload for debugging
                            logger.warning(f"Booking payload: {booking_payload}")
                    
                    except Exception as e:
                        logger.warning(f"Failed to create Cal.com booking: {e}")
                        import traceback
                        logger.warning(traceback.format_exc())
            
            # Store event in database (even if Cal.com booking failed)
            event_payload = {
                "user_id": user_id,
                "call_id": call_id,
                "campaign_id": campaign_id,
                "event_type": event_type,
                "title": title,
                "scheduled_at": iso_datetime,
                "duration_minutes": 30,
                "timezone": timezone,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "cal_booking_id": cal_booking_id,
                "cal_booking_uid": cal_booking_uid,
                "status": "scheduled",
                "notes": notes,
                "created_automatically": True
            }
            
            # Use database client to insert event
            result = db.client.table("scheduled_events").insert(event_payload).execute()
            
            event_id = result.data[0]["id"] if result.data else None
            
            logger.info(f"ðŸŽ‰ Successfully created scheduled event {event_id} from call {call_id}")
            logger.info(f"   ðŸ“… {title} on {date_str} at {time_str}")
            logger.info(f"   ðŸ‘¤ Contact: {contact_name} ({contact_phone})")
            logger.info(f"   ðŸ”— Cal.com booking: {cal_booking_uid or 'Not created'}")
        
    except Exception as e:
        logger.error(f"Error creating calendar event for call {call_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def auto_schedule_booking(call_id: str, transcript: str):
    """
    Automatically create a Cal.com booking and send SMS when user shows interest.
    """
    try:
        logger.info(f"ðŸ—“ï¸ Auto-scheduling booking for interested customer in call {call_id}")
        
        # Get call details from database
        call_details = await db.get_call(call_id)
        if not call_details:
            logger.error(f"Could not find call details for {call_id}")
            return
        
        phone_number = call_details.get("to_number")
        if not phone_number:
            logger.error(f"No phone number found for call {call_id}")
            return
        
        # Create booking link via backend API
        import httpx
        async with httpx.AsyncClient() as client:
            # Get default event type (30 min meeting)
            cal_status = await client.get("http://backend:8000/cal/status")
            if cal_status.status_code != 200:
                logger.error("Cal.com not configured")
                return
            
            cal_data = cal_status.json()
            event_types = cal_data.get("event_types", [])
            if not event_types:
                logger.error("No event types available")
                return
            
            # Find 30 min or first available event type
            event_type = next(
                (et for et in event_types if "30" in et.get("title", "")),
                event_types[0]
            )
            
            # Create booking link
            link_response = await client.post(
                "http://backend:8000/cal/create-link",
                json={
                    "event_type_slug": event_type["slug"],
                    "username": cal_data["user"]["username"]
                }
            )
            
            if link_response.status_code != 200:
                logger.error(f"Failed to create booking link: {link_response.text}")
                return
            
            booking_data = link_response.json()
            booking_url = booking_data.get("booking_url")
            
            # Send SMS with booking link
            sms_response = await client.post(
                "http://backend:8000/cal/send-link-sms",
                json={
                    "phone": phone_number,
                    "name": "Interested Customer",
                    "email": "customer@example.com",
                    "booking_url": booking_url
                }
            )
            
            if sms_response.status_code == 200:
                logger.info(f"âœ… Booking link sent via SMS to {phone_number}")
            else:
                logger.error(f"Failed to send SMS: {sms_response.text}")
                
    except Exception as e:
        logger.error(f"Error auto-scheduling booking: {e}")


@app.post("/callbacks/status/{call_id}")
async def status_callback(call_id: str, request: Request):
    """
    Handle Twilio status callbacks
    Updates call status in database and campaign contact status
    """
    try:
        form_data = await request.form()
        status = form_data.get("CallStatus")
        call_sid = form_data.get("CallSid")
        duration = form_data.get("CallDuration")
        
        logger.info(f"Status callback for {call_id}: {status} | SID: {call_sid}")
        
        db = get_db()
        
        # Get call to check if it's part of a campaign
        call_result = db.client.table("calls").select("*").eq("id", call_id).execute()
        if not call_result.data:
            logger.error(f"Call {call_id} not found")
            return {"status": "error", "message": "Call not found"}
        
        call = call_result.data[0]
        campaign_id = call.get('campaign_id')
        
        # Idempotency check - only update if not already in terminal state
        if call['status'] in ["completed", "failed"]:
            logger.info(f"Call {call_id} already in terminal state {call['status']}, skipping")
            return {"status": "ok", "message": "already_processed"}
        
        update_data = {"status": status}
        
        # Handle terminal states (call is done)
        if status in ["completed", "busy", "no-answer", "failed", "canceled"]:
            update_data["ended_at"] = datetime.now()
            if duration:
                update_data["duration"] = int(duration)
            
            # Persist structured analysis for all terminal outcomes.
            try:
                await generate_call_analysis(call_id, db)
            except Exception as analysis_error:
                logger.error(f"Failed to generate call analysis for {call_id}: {analysis_error}")
            
            # Update campaign contact if this is a campaign call
            if campaign_id:
                await update_campaign_contact_status(call_id, status, db)
        
        await db.update_call(call_id, **update_data)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error in status callback for {call_id}: {e}")
        return {"status": "error", "message": str(e)}


async def update_campaign_contact_status(call_id: str, twilio_status: str, db):
    """Update campaign contact status based on call outcome"""
    try:
        # Get contact for this call
        contact_result = db.client.table("campaign_contacts").select("*").eq("call_id", call_id).execute()
        
        if not contact_result.data:
            return  # Not a campaign call
        
        contact = contact_result.data[0]
        
        # Only update if still in calling state (idempotency)
        if contact['state'] != 'calling':
            logger.info(f"Contact {contact['id']} already processed, skipping")
            return
        
        # Map Twilio status to contact outcome
        outcome_map = {
            "completed": "completed",
            "busy": "busy",
            "no-answer": "no-answer",
            "failed": "failed",
            "canceled": "failed"
        }
        
        outcome = outcome_map.get(twilio_status, "failed")
        
        # Determine if retryable
        retryable_outcomes = ["no-answer", "busy", "failed"]
        settings_result = db.client.table("bulk_campaigns").select("settings_snapshot").eq("id", contact['campaign_id']).execute()
        
        max_retries = 3
        if settings_result.data:
            max_retries = settings_result.data[0]['settings_snapshot'].get('retry_policy', {}).get('max_retries', 3)
        
        # Update contact
        update_data = {
            "outcome": outcome,
            "locked_until": None
        }
        
        # Check if we should retry
        if outcome in retryable_outcomes and contact['retry_count'] < max_retries:
            # Schedule for retry
            update_data['state'] = 'pending'
            update_data['retry_count'] = contact['retry_count'] + 1
            logger.info(f"Contact {contact['id']} scheduled for retry {update_data['retry_count']}/{max_retries}")
        else:
            # Terminal state
            if outcome == "completed":
                update_data['state'] = 'completed'
            else:
                update_data['state'] = 'failed'
            logger.info(f"Contact {contact['id']} marked as {update_data['state']}")
        
        db.client.table("campaign_contacts").update(update_data).eq("id", contact['id']).execute()
        
    except Exception as e:
        logger.error(f"Error updating campaign contact status: {e}")


@app.post("/callbacks/recording/{call_id}")
async def recording_callback(call_id: str, request: Request):
    """
    Handle Twilio recording callbacks
    Saves recording URL to database
    """
    try:
        form_data = await request.form()
        recording_url = form_data.get("RecordingUrl")
        recording_sid = form_data.get("RecordingSid")
        recording_duration = form_data.get("RecordingDuration")
        
        logger.info(f"Recording callback for {call_id}: {recording_sid} | Duration: {recording_duration}s")
        
        if recording_url:
            db = get_db()
            # Twilio recording URL needs .mp3 appended for direct download
            full_recording_url = f"{recording_url}.mp3"
            
            update_data = {
                "recording_url": full_recording_url,
            }
            
            if recording_duration:
                update_data["recording_duration"] = int(recording_duration)
            
            await db.update_call(call_id, **update_data)
            logger.info(f"âœ… Recording URL saved for {call_id}: {full_recording_url}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error in recording callback for {call_id}: {e}")
        return {"status": "error", "message": str(e)}


# ==================== WEBSOCKET HANDLER (VAPI-STYLE) ====================

@app.websocket("/ws/{call_id}")
async def websocket_handler(websocket: WebSocket, call_id: str):
    """
    Main WebSocket handler for Twilio Media Streams
    
    VAPI-STYLE ARCHITECTURE:
    - 3-state machine: LISTENING â†’ USER_SPEAKING â†’ AI_SPEAKING
    - VAD edge-trigger: 240ms speech start, 300ms silence end
    - TRUE barge-in: User can interrupt AI mid-speech
    - NO post-TTS sleep, NO cooldowns, NO adaptive silence
    
    Target: <4s total response time (including STT + LLM + TTS)
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for call {call_id}")
    
    session = None
    
    try:
        # Get call and agent details
        db = get_db()
        call = await db.get_call(call_id)
        
        if not call:
            logger.error(f"Call {call_id} not found")
            await websocket.close()
            return
        
        agent = await db.get_agent(call["agent_id"])
        if not agent:
            logger.error(f"Agent {call['agent_id']} not found")
            await websocket.close()
            return
        
        # Initialize AI clients
        llm = get_llm_client()
        stt = get_stt_client()
        tts = get_tts_client()
        
        stream_sid = None
        
        # Main message loop
        while True:
            try:
                # Receive message from Twilio
                message = await websocket.receive_text()
                data = json.loads(message)
                event = data.get("event")
                if event == "start":
                    # Stream started
                    stream_sid = data["start"]["streamSid"]
                    logger.info(f"Stream started: {stream_sid}")
                    
                    # Extract voice settings from agent config
                    voice_settings = agent.get("voice_settings", {})
                    
                    # Create session with voice settings
                    session = CallSession(call_id, agent["id"], stream_sid, voice_settings)
                    session.agent_config = agent

                    is_wow_call = _is_wow_agent_config(agent)
                    session.awaiting_permission = is_wow_call
                    session.permission_granted = not is_wow_call
                    session.wow_checkpoint_state = new_wow_checkpoint_state()

                    active_sessions[stream_sid] = session

                    # CHECK FOR LANGUAGE SELECTION
                    if session.LANGUAGE_SELECTION_ENABLED:
                        logger.info("ðŸ—£ï¸ Requesting language selection")
                        prompt = "Hello. Do you prefer English, Hindi, or Marathi?"
                        
                        # Save to database
                        await db.add_transcript(call_id=call_id, speaker="agent", text=prompt)
                        
                        # Set AI_SPEAKING state and send audio
                        session.state = ConversationState.AI_SPEAKING
                        session.interrupted = False
                        await send_ai_response_with_bargein(websocket, session, prompt, tts, db, call_id)
                        
                        session.mark_ai_turn_complete()
                        session.reset_for_listening()
                    else:
                        # STANDARD GREETING FLOW
                        # Generate opening line with LLM
                        GREETING_PROMPT = """You are making an OUTBOUND sales call. Generate your opening line.

CRITICAL RULES:
- Output ONLY the exact words you will speak - nothing else
- NO quotes, NO meta-commentary like "Here's my opening line:"
- Keep it to 2 sentences MAX (this is a phone call)
- Sound natural and confident, not robotic
- Use contractions: "I'm" not "I am", "you're" not "you are"

STRUCTURE:
1. Brief introduction (name + company)
2. Polite ask if they have a moment

VOICE FORMATTING:
- Write times as words: "twelve PM" not "12:00"
- Write "twenty four seven" not "24/7"
- Numbers as words for pronunciation"""
                        
                        base_prompt = resolve_agent_system_prompt(agent)
                        system_prompt = f"{GREETING_PROMPT}\n\n{base_prompt}"
                        
                        greeting = await llm.generate_response(
                            messages=[{"role": "user", "content": "Generate your opening line for this cold call."}],
                            system_prompt=system_prompt,
                            temperature=agent.get("temperature", 0.7),
                            max_tokens=50  # Increased for better greeting
                        )
                        
                        # Clean meta-commentary
                        import re
                        if any(word in greeting.lower() for word in ['here', 'opening', 'line:', 'say:', '"']):
                            match = re.search(r'[""]([^""]+)[""]', greeting)
                            if match:
                                greeting = match.group(1)
                            else:
                                greeting = re.sub(r'^.*?(?:opening line|here|say)s?:?\s*', '', greeting, flags=re.IGNORECASE).strip().strip('"\'')
                        
                        logger.info(f"Generated greeting: {greeting}")
                        
                        # Save to database
                        await db.add_transcript(call_id=call_id, speaker="agent", text=greeting)
                        
                        # Set AI_SPEAKING state and send audio
                        session.state = ConversationState.AI_SPEAKING
                        session.interrupted = False
                        await send_ai_response_with_bargein(websocket, session, greeting, tts, db, call_id)
                        
                        # Mark AI turn complete for first-utterance tracking
                        session.mark_ai_turn_complete()
                        
                        # Immediately ready for user input (NO SLEEP!)
                        session.reset_for_listening()
                        logger.info("ðŸŸ¢ AI finished speaking - ready for user input (state: LISTENING)")
                elif event == "media":
                    if not session:
                        continue
                    
                    # Decode audio
                    payload = data["media"]["payload"]
                    audio_data = base64.b64decode(payload)
                    
                    # ==================== USER_SPEAKING TIMEOUT CHECK ====================
                    # Prevent getting stuck in USER_SPEAKING indefinitely
                    if session.state == ConversationState.USER_SPEAKING and session.check_user_speaking_timeout():
                        logger.warning(f"â±ï¸ USER_SPEAKING timeout ({USER_SPEAKING_TIMEOUT_MS}ms) - resetting to LISTENING")
                        session.reset_for_listening()
                        continue
                    
                    # ==================== REFINED BARGE-IN: Check for interruption during AI speech ====================
                    if session.state == ConversationState.AI_SPEAKING:
                        # Run VAD on incoming audio even during AI speech
                        is_speech = session.detect_speech_vad(audio_data)
                        
                        # Use refined interrupt validation (grace period + sustained speech)
                        if session.validate_interrupt_speech(is_speech):
                            # Valid interrupt detected - user has been speaking long enough
                            session.interrupt_ai()
                            session.state = ConversationState.USER_SPEAKING
                            session.speech_start_time = datetime.now()
                            session.user_speaking_start_time = datetime.now()
                            session.audio_buffer.clear()  # Start fresh buffer for user speech
                            logger.info("ðŸ›‘ BARGE-IN DETECTED: Sustained speech validated - switching to USER_SPEAKING")
                        continue  # Don't buffer AI's own audio
                    
                    # ==================== VAD EDGE-TRIGGER STATE MACHINE ====================
                    is_speech = session.detect_speech_vad(audio_data)
                    vad_event = session.update_vad_state(is_speech)
                    
                    # ==================== AUDIO BUFFERING: ONLY in USER_SPEAKING ====================
                    # This is critical to prevent echo/noise from polluting the buffer
                    if session.state == ConversationState.USER_SPEAKING:
                        session.add_audio_chunk(audio_data)
                        
                        # ==================== EARLY STT WITH CONFIDENCE VALIDATION (Phase 1) ====================
                        # For short answer contexts, try STT early (500-600ms) and validate confidence
                        # Only attempt ONCE per utterance to avoid spam
                        if session.early_stt_enabled and not session.early_stt_attempted and session.user_speaking_start_time:
                            speaking_duration = (datetime.now() - session.user_speaking_start_time).total_seconds()
                            buffer_duration = len(session.audio_buffer) / TWILIO_SAMPLE_RATE
                            
                            # Early trigger for short answer contexts (language, yes/no)
                            if session.call_stage == CallStage.LANGUAGE_SELECT:
                                # Try at 600ms for language selection ("Hindi", "English")
                                if 0.6 <= buffer_duration < 0.65 and speaking_duration >= 0.55:
                                    session.early_stt_attempted = True  # Mark as attempted
                                    logger.info(f"âš¡ EARLY STT ATTEMPT: {buffer_duration:.2f}s buffered [Stage: {session.call_stage.value}]")
                                    await process_user_speech_fast(session, websocket, stt, llm, tts, db, early_attempt=True)
                                    if not session.audio_buffer:  # Successfully processed
                                        continue
                            elif session.call_stage == CallStage.YES_NO:
                                # Try at 500ms for yes/no questions
                                if 0.5 <= buffer_duration < 0.55 and speaking_duration >= 0.45:
                                    session.early_stt_attempted = True  # Mark as attempted
                                    logger.info(f"âš¡ EARLY STT ATTEMPT: {buffer_duration:.2f}s buffered [Stage: {session.call_stage.value}]")
                                    await process_user_speech_fast(session, websocket, stt, llm, tts, db, early_attempt=True)
                                    if not session.audio_buffer:  # Successfully processed
                                        continue
                        
                        # ==================== SIMPLE TIMEOUT (VAPI-LIKE) ====================
                        # Force process if speaking too long without natural pause (safety net)
                        if session.user_speaking_start_time:
                            speaking_duration = (datetime.now() - session.user_speaking_start_time).total_seconds()
                            buffer_duration = len(session.audio_buffer) / TWILIO_SAMPLE_RATE
                            
                            # Force process if speaking > 4s without natural pause (REDUCED from 6s - was causing ~10-20s waits)
                            if speaking_duration > 4.0 and buffer_duration > 3.5:
                                logger.warning(f"â±ï¸ FORCE PROCESS: {speaking_duration:.1f}s speaking, {buffer_duration:.1f}s buffered - processing now")
                                await process_user_speech_fast(session, websocket, stt, llm, tts, db)
                                continue
                    
                    # State transitions based on VAD edges
                    if vad_event == "speech_start" and session.state == ConversationState.LISTENING:
                        # User started speaking (210ms of speech detected)
                        session.state = ConversationState.USER_SPEAKING
                        session.user_speaking_start_time = datetime.now()  # CRITICAL: Required for early trigger
                        session.early_stt_attempted = False  # Reset for new utterance (Phase 1)
                        session.add_audio_chunk(audio_data)  # Add the triggering audio too
                        logger.info(f"ðŸŽ¤ Speech START detected - state: USER_SPEAKING | Echo window: {session.is_in_echo_window()}")
                    
                    elif vad_event == "speech_end" and session.state == ConversationState.USER_SPEAKING:
                        # User finished speaking (240ms of silence)
                        audio_duration = len(session.audio_buffer) / 8000
                        if session.has_sufficient_audio():
                            logger.info(f"ðŸŽ¤ Speech END detected - processing {len(session.audio_buffer)}B ({audio_duration:.2f}s)")
                            await process_user_speech_fast(session, websocket, stt, llm, tts, db)
                        else:
                            logger.debug(f"Speech end but insufficient audio ({len(session.audio_buffer)}B) - skipping")
                            session.reset_for_listening()
                    
                    elif vad_event == "barge_in" and session.state == ConversationState.AI_SPEAKING:
                        # User wants to interrupt AI (300ms of loud, sustained speech)
                        logger.info(f"ðŸš¨ BARGE-IN: Interrupting AI speech, switching to USER_SPEAKING")
                        session.interrupted = True  # Signal to stop TTS playback
                        session.state = ConversationState.USER_SPEAKING
                        session.user_speaking_start_time = datetime.now()
                        session.audio_buffer.clear()  # Start fresh buffer for user's input
                        session.add_audio_chunk(audio_data)  # Add the triggering audio
                    
                    # Periodic debug logging (every second)
                    if len(session.audio_buffer) % 8000 == 0 and len(session.audio_buffer) > 0:
                        energy = sum(abs(b - 127) for b in audio_data) / len(audio_data) if audio_data else 0
                        echo_status = "ECHO_WINDOW" if session.is_in_echo_window() else "clear"
                        logger.info(f"ðŸ“Š State: {session.state.value} | Buffer: {len(session.audio_buffer)}B | Speech: {is_speech} | Energy: {energy:.1f} | {echo_status}")
                
                elif event == "stop":
                    logger.info(f"Stream stopped: {stream_sid}")
                    break
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for call {call_id}")
                break
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON received: {e}")
                continue
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                continue
        
    except Exception as e:
        logger.error(f"WebSocket error for call {call_id}: {e}", exc_info=True)
    
    finally:
        if session:
            if session.stream_sid in active_sessions:
                del active_sessions[session.stream_sid]
            
            # ==================== BACKUP DATA SAVE (Fix for NaN/N/A) ====================
            # Ensure call is marked completed and analysis generated even if Twilio webhook fails
            try:
                # Check if call is still technically "in-progress" or "initiated"
                current_call = await db.get_call(call_id)
                current_status = current_call.get("status") if current_call else None
                
                if current_status not in ["completed", "failed", "busy", "no-answer", "canceled"]:
                    duration = int((datetime.now() - session.created_at).total_seconds())
                    logger.info(f"ðŸ”’ Backup: Marking call {call_id} as completed (Duration: {duration}s)")
                    
                    await db.update_call(
                        call_id, 
                        status="completed", 
                        ended_at=datetime.now(), 
                        duration=duration
                    )
                    
                    # Generate analysis immediately
                    logger.info(f"ðŸ“Š Generating analysis for {call_id} (Backup)")
                    await generate_call_analysis(call_id, db)
            except Exception as e:
                logger.error(f"Error in backup call completion: {e}")

        logger.info(f"WebSocket closed for call {call_id}")
        try:
            await websocket.close()
        except:
            pass


def _normalize_browser_audio_to_wav(audio_bytes: bytes) -> tuple[Optional[bytes], Optional[str]]:
    """
    Normalize browser MediaRecorder audio bytes to mono 16k WAV for STT.

    Accepts:
    - webm/opus bytes (preferred browser format)
    - wav bytes (already normalized, still re-encoded for consistency)
    """
    if not audio_bytes:
        return None, "Empty audio payload"

    # Fast path: if this is already a WAV file, pass through STT enhancer directly.
    if audio_bytes.startswith(b"RIFF"):
        return _sanitize_wav(audio_bytes), None

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        "pipe:1",
    ]

    try:
        proc = subprocess.run(
            ffmpeg_cmd,
            input=audio_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except FileNotFoundError:
        return None, "ffmpeg binary not found on server"
    except subprocess.TimeoutExpired:
        return None, "ffmpeg conversion timed out"
    except Exception as exc:
        return None, f"Audio conversion failure: {exc}"

    if proc.returncode != 0 or not proc.stdout:
        stderr = proc.stderr.decode("utf-8", errors="ignore")[:300]
        return None, f"ffmpeg failed to decode browser audio: {stderr or 'unknown error'}"

    return _sanitize_wav(proc.stdout), None


def _sanitize_wav(wav_bytes: bytes) -> bytes:
    """Rewrite WAV header to ensure frame counts are accurate for downstream STT logic."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_in:
            channels = wav_in.getnchannels()
            sampwidth = wav_in.getsampwidth()
            framerate = wav_in.getframerate()
            frames = wav_in.readframes(wav_in.getnframes())

        out = io.BytesIO()
        with wave.open(out, "wb") as wav_out:
            wav_out.setnchannels(channels)
            wav_out.setsampwidth(sampwidth)
            wav_out.setframerate(framerate)
            wav_out.writeframes(frames)
        return out.getvalue()
    except Exception:
        return wav_bytes


def _is_likely_silence(wav_bytes: bytes, rms_threshold: int = 220) -> bool:
    """Cheap silence gate to avoid wasting STT calls on empty chunks."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            sampwidth = wav_file.getsampwidth()

        if not frames:
            return True

        rms = audioop.rms(frames, sampwidth)
        return rms < rms_threshold
    except Exception:
        # If parsing fails, let STT decide rather than dropping audio.
        return False


def _wav_duration_seconds(wav_bytes: bytes) -> Optional[float]:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            fr = wav_file.getframerate()
            frames = wav_file.getnframes()
            channels = wav_file.getnchannels()
            sampwidth = wav_file.getsampwidth()
        if fr <= 0:
            return None
        duration_header = frames / float(fr)

        # Some streamed wavs can contain bogus nframes metadata (very large values).
        bytes_per_second = fr * channels * sampwidth
        duration_by_size = len(wav_bytes) / float(bytes_per_second) if bytes_per_second > 0 else duration_header

        if duration_header > duration_by_size * 12:
            return duration_by_size
        return duration_header
    except Exception:
        return None


def _trim_wav_to_seconds(wav_bytes: bytes, max_seconds: float) -> bytes:
    """Trim WAV payload to a safe duration cap for STT calls."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_in:
            channels = wav_in.getnchannels()
            sampwidth = wav_in.getsampwidth()
            framerate = wav_in.getframerate()
            max_frames = int(max_seconds * framerate)
            frames = wav_in.readframes(max_frames)

        out = io.BytesIO()
        with wave.open(out, "wb") as wav_out:
            wav_out.setnchannels(channels)
            wav_out.setsampwidth(sampwidth)
            wav_out.setframerate(framerate)
            wav_out.writeframes(frames)
        return out.getvalue()
    except Exception:
        return wav_bytes


@app.websocket("/ws/web/{agent_id}")
async def web_voice_session(websocket: WebSocket, agent_id: str):
    """
    Browser-native voice session endpoint.
    Accepts browser audio chunks (typically webm/opus), normalizes to WAV for STT,
    and returns assistant audio as base64 WAV chunks in JSON messages.
    """
    await websocket.accept()

    db = get_db()
    llm = get_llm_client()
    stt = get_stt_client()
    tts = get_tts_client()

    call_record = await db.create_call(
        agent_id=agent_id,
        to_number="web-client",
        from_number="web-widget",
        status="in-progress",
        metadata={"channel": "web", "source": "voice_widget"},
    )
    call_id = call_record["id"]
    started_at = datetime.now()

    agent = await db.get_agent(agent_id)
    if not agent:
        await websocket.send_json({"type": "error", "message": "Agent not found"})
        await websocket.close()
        return

    system_prompt = resolve_agent_system_prompt(agent)

    conversation_history: list[dict[str, str]] = []
    quota_exhausted_notified = False
    last_user_transcript = ""
    last_user_transcript_at: Optional[datetime] = None
    assistant_speaking_until: Optional[datetime] = None
    web_is_wow_call = _is_wow_agent_config(agent)
    web_awaiting_permission = web_is_wow_call
    web_call_closed = False
    web_default_language = os.getenv("WEB_DEFAULT_LANGUAGE", "en").strip().lower() or "en"
    if web_default_language not in {"en", "hi"}:
        web_default_language = "en"

    web_language_auto_switch = os.getenv("WEB_LANGUAGE_AUTO_SWITCH", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    web_selected_language = web_default_language

    stt_bilingual_prompt = (
        "Transcribe spoken audio exactly as spoken. Allowed languages: English and Hindi only. "
        "If Hindi is spoken, prefer Devanagari script. Do not output Urdu unless explicitly asked."
    )

    def apply_web_language_prompt(base_prompt: str, language: str) -> str:
        if language == "hi":
            return (
                f"{base_prompt}\n\n"
                "LANGUAGE MODE: Reply in natural conversational Hindi (Devanagari). "
                "Do not switch to English unless the user asks. Do not use Urdu script."
            )
        return (
            f"{base_prompt}\n\n"
            "LANGUAGE MODE: Reply in natural conversational English. "
            "If user asks for Hindi, switch to Hindi (Devanagari)."
        )

    def build_web_system_prompt(language: str, latest_user_text: str = "") -> str:
        prompt_with_language = apply_web_language_prompt(system_prompt, language)
        if web_is_wow_call:
            checkpoint_guidance = infer_wow_checkpoint_guidance(conversation_history, latest_user_text)
            if checkpoint_guidance:
                prompt_with_language = f"{prompt_with_language}{checkpoint_guidance}"
        return prompt_with_language

    def detect_web_turn_language(text: str, current_language: str) -> tuple[str | None, str]:
        text_lower = text.lower().strip()
        if not text_lower:
            return None, "empty"

        hindi_switch_patterns = [
            "hindi",
            "in hindi",
            "hindi mein",
            "hindi me",
            "हिंदी",
            "हिन्दी",
        ]
        english_switch_patterns = [
            "english",
            "in english",
            "speak english",
            "अंग्रेजी",
            "अंग्रेज़ी",
        ]

        if any(pattern in text_lower for pattern in hindi_switch_patterns):
            return "hi", "explicit_hindi_keyword"
        if any(pattern in text_lower for pattern in english_switch_patterns):
            return "en", "explicit_english_keyword"

        # Conservative fallback: only auto-upgrade EN -> HI when Devanagari is present.
        if web_language_auto_switch and current_language == "en" and re.search(r"[\u0900-\u097f]", text):
            return "hi", "devanagari_autoswitch"

        return None, "no_signal"

    try:
        logger.info(
            f"🌐 Web voice session language config: default={web_selected_language}, auto_switch={web_language_auto_switch}"
        )

        greeting = await llm.generate_response(
            system_prompt=build_web_system_prompt(web_selected_language),
            messages=[
                {
                    "role": "user",
                    "content": "[SESSION_START] Generate only the opening greeting under 30 words.",
                }
            ],
            max_tokens=80,
        )
        if not greeting:
            greeting = "Hi, this is Priya. How can I help you today?"

        greeting_audio = await tts.generate_speech_bytes(greeting, language=web_selected_language)
        if greeting_audio:
            greeting_duration = _wav_duration_seconds(greeting_audio) or 0.0
            if greeting_duration > 0:
                assistant_speaking_until = datetime.now() + timedelta(seconds=min(greeting_duration * 0.95, 10.0))
            await websocket.send_json(
                {
                    "type": "audio",
                    "audio": base64.b64encode(greeting_audio).decode("utf-8"),
                    "text": greeting,
                    "is_greeting": True,
                }
            )

        await db.add_transcript(call_id=call_id, speaker="agent", text=greeting)
        conversation_history.append({"role": "assistant", "content": greeting})

        while True:
            data = await websocket.receive()

            if "bytes" in data and data["bytes"] is not None:
                if assistant_speaking_until and datetime.now() < assistant_speaking_until:
                    continue

                raw_audio = data["bytes"]
                stt_audio, conversion_error = _normalize_browser_audio_to_wav(raw_audio)
                if not stt_audio:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": conversion_error or "Unable to process microphone audio",
                        }
                    )
                    continue

                duration_s = _wav_duration_seconds(stt_audio)
                if duration_s is not None and duration_s > 8.0:
                    logger.warning(
                        f"Web STT chunk unusually long ({duration_s:.2f}s). Trimming to 8.0s before STT."
                    )
                    stt_audio = _trim_wav_to_seconds(stt_audio, 8.0)

                logger.debug(
                    f"Web STT chunk bytes={len(stt_audio)} duration_s={duration_s if duration_s is not None else 'unknown'}"
                )

                if _is_likely_silence(stt_audio):
                    continue

                stt_attempt_language = web_selected_language
                fallback_used = False

                transcript = await stt.transcribe(
                    stt_audio,
                    language=stt_attempt_language,
                    prompt=stt_bilingual_prompt,
                )
                if not transcript or len(transcript.strip()) < 2:
                    if web_language_auto_switch:
                        alternate_lang = "hi" if web_selected_language == "en" else "en"
                        alternate_transcript = await stt.transcribe(
                            stt_audio,
                            language=alternate_lang,
                            prompt=stt_bilingual_prompt,
                        )
                        if alternate_transcript and len(alternate_transcript.strip()) >= 2:
                            logger.info(
                                f"🌐 Web STT fallback succeeded with {alternate_lang.upper()} while current={web_selected_language.upper()}"
                            )
                            transcript = alternate_transcript
                            stt_attempt_language = alternate_lang
                            fallback_used = True

                if not transcript or len(transcript.strip()) < 2:
                    stt_error = stt.get_last_error() if hasattr(stt, "get_last_error") else {}
                    stt_status = stt_error.get("status_code")
                    stt_code = (stt_error.get("error_code") or "").lower()

                    if (
                        not quota_exhausted_notified
                        and (
                            stt_status == 429
                            or stt_code in {"insufficient_quota_error", "rate_limit_exceeded_error"}
                        )
                    ):
                        quota_exhausted_notified = True
                        if stt_code == "rate_limit_exceeded_error":
                            message = (
                                "STT rate limit is currently exceeded on the server (Sarvam 429). "
                                "Please wait a moment and retry."
                            )
                        else:
                            message = (
                                "STT quota is exhausted on the server (Sarvam 429 insufficient_quota_error). "
                                "Please top up STT quota/credits and retry."
                            )
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": message,
                            }
                        )
                        break
                    continue

                # Guard against split chunk duplicates from browser recording windows.
                now = datetime.now()
                cleaned_current = re.sub(r"\s+", " ", transcript.strip().lower())
                cleaned_previous = re.sub(r"\s+", " ", last_user_transcript.strip().lower())
                if cleaned_previous and last_user_transcript_at:
                    age_s = (now - last_user_transcript_at).total_seconds()
                    similarity = SequenceMatcher(None, cleaned_current, cleaned_previous).ratio()
                    if age_s <= 6 and similarity >= 0.88:
                        logger.debug(
                            f"Dropping duplicate user transcript chunk (age={age_s:.2f}s, similarity={similarity:.2f})"
                        )
                        continue

                last_user_transcript = transcript
                last_user_transcript_at = now

                script_hint = "devanagari" if re.search(r"[\u0900-\u097f]", transcript) else "latin_or_other"
                detected_turn_lang, switch_reason = detect_web_turn_language(transcript, web_selected_language)
                logger.info(
                    "🌐 Web STT turn: "
                    f"selected={web_selected_language.upper()} "
                    f"stt_attempt={stt_attempt_language.upper()} "
                    f"fallback={fallback_used} "
                    f"chars={len(transcript.strip())} "
                    f"script={script_hint} "
                    f"switch_signal={switch_reason}"
                )
                if detected_turn_lang and detected_turn_lang != web_selected_language:
                    logger.info(
                        f"🌐 Web session language switch: {web_selected_language} -> {detected_turn_lang} "
                        f"reason={switch_reason}"
                    )
                    web_selected_language = detected_turn_lang

                if web_is_wow_call and web_awaiting_permission:
                    permission_intent, _ = classify_intent(transcript, 9999.0)
                    if permission_intent == "affirm":
                        web_awaiting_permission = False
                        logger.info("✅ Web permission gate passed: user explicitly allowed conversation")
                    elif permission_intent in {"negative", "goodbye"}:
                        web_awaiting_permission = False
                        web_call_closed = True
                        close_text = "I completely understand. I apologize for the interruption. Have a great day."

                        await websocket.send_json({"type": "transcript", "text": transcript, "role": "user"})
                        await db.add_transcript(call_id=call_id, speaker="user", text=transcript)
                        conversation_history.append({"role": "user", "content": transcript})

                        await websocket.send_json(
                            {"type": "transcript", "text": close_text, "role": "assistant"}
                        )
                        await db.add_transcript(call_id=call_id, speaker="agent", text=close_text)
                        conversation_history.append({"role": "assistant", "content": close_text})

                        close_audio = await tts.generate_speech_bytes(close_text, language=web_selected_language)
                        if close_audio:
                            await websocket.send_json(
                                {
                                    "type": "audio",
                                    "audio": base64.b64encode(close_audio).decode("utf-8"),
                                    "text": close_text,
                                }
                            )
                        break
                    else:
                        clarify_text = "Before we continue, do you want to speak now? Please answer yes or no."
                        await websocket.send_json({"type": "transcript", "text": clarify_text, "role": "assistant"})
                        await db.add_transcript(call_id=call_id, speaker="agent", text=clarify_text)
                        conversation_history.append({"role": "assistant", "content": clarify_text})

                        clarify_audio = await tts.generate_speech_bytes(clarify_text, language=web_selected_language)
                        if clarify_audio:
                            await websocket.send_json(
                                {
                                    "type": "audio",
                                    "audio": base64.b64encode(clarify_audio).decode("utf-8"),
                                    "text": clarify_text,
                                }
                            )
                        continue

                if web_is_wow_call and web_call_closed:
                    break

                await websocket.send_json({"type": "transcript", "text": transcript, "role": "user"})
                await db.add_transcript(call_id=call_id, speaker="user", text=transcript)
                conversation_history.append({"role": "user", "content": transcript})

                response_text = await llm.generate_response(
                    system_prompt=build_web_system_prompt(web_selected_language, transcript),
                    messages=conversation_history,
                    max_tokens=200,
                )
                if not response_text:
                    response_text = "Could you please repeat that?"

                conversation_history.append({"role": "assistant", "content": response_text})
                await db.add_transcript(call_id=call_id, speaker="agent", text=response_text)

                await websocket.send_json(
                    {"type": "transcript", "text": response_text, "role": "assistant"}
                )

                response_audio = await tts.generate_speech_bytes(response_text, language=web_selected_language)
                if response_audio:
                    response_duration = _wav_duration_seconds(response_audio) or 0.0
                    if response_duration > 0:
                        assistant_speaking_until = datetime.now() + timedelta(seconds=min(response_duration * 0.95, 10.0))
                    await websocket.send_json(
                        {
                            "type": "audio",
                            "audio": base64.b64encode(response_audio).decode("utf-8"),
                            "text": response_text,
                        }
                    )

            elif "text" in data and data["text"] is not None:
                try:
                    msg = json.loads(data["text"])
                except Exception:
                    continue

                if msg.get("type") == "end":
                    break

    except WebSocketDisconnect:
        logger.info(f"Web session disconnected: {call_id}")
    except Exception as exc:
        logger.error(f"Web session error for {call_id}: {exc}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": "Internal voice session error"})
        except Exception:
            pass
    finally:
        try:
            duration = int((datetime.now() - started_at).total_seconds())
            await db.update_call(call_id, status="completed", ended_at=datetime.now(), duration=duration)
            await generate_call_analysis(call_id, db)
        except Exception as exc:
            logger.warning(f"Failed to finalize web call {call_id}: {exc}")

        try:
            await websocket.close()
        except Exception:
            pass


# ==================== FAST USER SPEECH PROCESSING (Vapi-style) ====================

async def process_user_speech_fast(
    session: CallSession,
    websocket: WebSocket,
    stt: STTClient,
    llm: LLMClient,
    tts: TTSClient,
    db: RelayDB,
    early_attempt: bool = False
):
    """
    Process user speech with CONVERSATION INTEGRITY CHECKS
    
    Flow:
    1. DOUBLE-PROCESSING GUARD - Prevent concurrent calls
    2. AUDIO QUALITY GATES - Reject short/low-energy audio before STT
    3. STT transcription
    4. INTENT CLASSIFICATION - Detect noise, corrections, intents
    5. INTERRUPTION INTENT - Handle acknowledgements vs topic changes
    6. Response generation (scripted or LLM)
    7. TTS â†’ Send audio with barge-in support
    8. CONTEXT HYGIENE - Only commit AI text if not interrupted
    
    Args:
        early_attempt: If True, validate STT confidence before committing (Phase 1)
    """
    # ==================== DOUBLE-PROCESSING GUARD ====================
    if session._processing_speech:
        logger.warning("âš ï¸ Double-processing attempted - skipping")
        return
    
    session._processing_speech = True
    try:
        # Get audio
        audio_mulaw = session.get_and_clear_buffer()
        if not audio_mulaw:
            session.reset_for_listening()
            return
        
        audio_duration_ms = (len(audio_mulaw) / TWILIO_SAMPLE_RATE) * 1000
        logger.info(f"Processing {len(audio_mulaw)} bytes ({audio_duration_ms:.0f}ms) for call {session.call_id}")
        
        # ==================== ADAPTIVE PATTERN TRACKING (Phase 1 - DISABLED) ====================
        # DISABLED: Was incorrectly measuring total time (including silence) not speech duration
        # This caused feedback loop: learning force-timeout delays (10-22s) as "normal" user behavior
        # Example: user_avg_pause_ms went 8225ms â†’ 8747ms â†’ 9453ms â†’ 11294ms (all garbage data)
        # To fix: need VAD-based speech activity measurement, not wall-clock time from speech_start
        # logger.debug(f"ðŸ“Š Adaptive learning disabled to prevent feedback loop bug")
        
        # ==================== AUDIO QUALITY GATE 1: Duration ====================
        # Very short audio is almost certainly noise/echo, don't waste STT call
        if audio_duration_ms < session.MIN_STT_DURATION_MS:
            # Special case: First utterance after AI is more likely to be echo
            if session.is_first_utterance_after_ai() and audio_duration_ms < session.DISCARD_FIRST_IF_SHORT_MS:
                logger.info(f"ðŸš« First utterance after AI too short ({audio_duration_ms:.0f}ms < {session.DISCARD_FIRST_IF_SHORT_MS}ms) - likely echo, discarding")
                session.mark_noise_detected()
                session.reset_for_listening()
                return
            
            if audio_duration_ms < session.MIN_AUDIO_DURATION_MS:
                logger.info(f"ðŸš« Audio too short ({audio_duration_ms:.0f}ms < {session.MIN_AUDIO_DURATION_MS}ms) - skipping STT")
                session.mark_noise_detected()
                session.reset_for_listening()
                return
        
        # ==================== AUDIO QUALITY GATE 2: Energy (FIXED THRESHOLD) ====================
        # Use simple fixed threshold like Vapi (30) - reliable and proven
        avg_energy = sum(abs(b - 127) for b in audio_mulaw) / len(audio_mulaw)
        
        if avg_energy < session.MIN_SPEECH_ENERGY:
            logger.info(f"ðŸš« Energy too low ({avg_energy:.1f} < {session.MIN_SPEECH_ENERGY}) - skipping")
            session.mark_noise_detected()
            session.reset_for_listening()
            return
        
        # Convert to WAV for STT
        audio_pcm = audioop.ulaw2lin(audio_mulaw, 2)
        audio_pcm_16k, _ = audioop.ratecv(audio_pcm, 2, 1, TWILIO_SAMPLE_RATE, 16000, None)
        
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(audio_pcm_16k)
            
        # ==================== STT TRANSCRIPTION ====================
        wav_buffer.seek(0)
        audio_bytes = wav_buffer.read()
        
        # Get current language (default to "en" after language selection).
        current_lang = getattr(session, "selected_language", "en")

        if session.call_stage == CallStage.LANGUAGE_SELECT and not session.language_verified:
            # Keep auto-detection only during explicit language selection.
            stt_lang = "unknown"
        else:
            stt_lang = current_lang
        
        # Single STT call - reuse result for both language detection and main flow
        stt_start = datetime.now()
        user_text = await stt.transcribe(audio_bytes, language=stt_lang, prompt="English, Hindi, Marathi")
        stt_duration = (datetime.now() - stt_start).total_seconds() * 1000
        
        logger.info(f"ðŸ“ STT ({stt_duration:.0f}ms): '{user_text}'")
        
        # ==================== EARLY STT CONFIDENCE VALIDATION (Phase 1) ====================
        # If this was an early attempt, validate quality before committing
        if early_attempt:
            # Check if result is meaningful enough
            text_clean = user_text.strip()
            word_count = len(text_clean.split())
            
            # Reject if too short or empty
            if len(text_clean) < 2 or word_count < 1:
                logger.info(f"âš ï¸ Early STT rejected: too short ('{text_clean}') - continuing buffering")
                session._processing_speech = False
                return  # Keep buffering
            
            # Reject common filler/noise words
            if text_clean.lower() in ["um", "uh", "ah", "hmm", "mm", "er", "the", "a", "okay", "ok"]:
                logger.info(f"âš ï¸ Early STT rejected: filler word ('{text_clean}') - continuing buffering")
                session._processing_speech = False
                return  # Keep buffering
            
            # For language selection, require specific keywords
            if session.call_stage == CallStage.LANGUAGE_SELECT:
                text_lower = text_clean.lower()
                has_language = any(lang in text_lower for lang in ["hindi", "english", "marathi", "à¤¹à¤¿à¤¨à¥à¤¦à¥€", "à¤¹à¤¿à¤‚à¤¦à¥€", "à¤®à¤°à¤¾à¤ à¥€"])
                if not has_language:
                    logger.info(f"âš ï¸ Early STT rejected: no language keyword ('{text_clean}') - continuing buffering")
                    session._processing_speech = False
                    return  # Keep buffering
            
            # Valid early result - proceed with processing
            logger.info(f"âœ… Early STT validated: '{text_clean}' - processing immediately")
        
        if not user_text or len(user_text.strip()) < 2:
            logger.debug("No meaningful speech detected")
            session.mark_noise_detected()
            session.reset_for_listening()
            return
        
        # ==================== GARBAGE TRANSCRIPT FILTER ====================
        # Reject noise patterns that made it through STT (mobile mics pick up a lot of garbage)
        import re
        text_clean = user_text.strip().lower()
        
        # Garbage patterns: repeated chars, dots, pure noise sounds
        garbage_patterns = [
            r'^[aeiou]+h*$',      # "aaa", "uh", "ah", "ooh"
            r'^\.+$',              # "..."
            r'^[hmn]+$',           # "hmm", "mmm"
            r'^(um+|uh+|er+)$',   # "um", "umm", "uh", "er"
            r'^.{1,2}$',          # Single/double char gibberish
        ]
        
        for pattern in garbage_patterns:
            if re.match(pattern, text_clean):
                logger.info(f"ðŸ—‘ï¸ Garbage transcript filtered: '{user_text}'")
                session.mark_noise_detected()
                session.reset_for_listening()
                return
        
        # ==================== LANGUAGE SELECTION LOGIC ====================
        if not session.language_verified and session.LANGUAGE_SELECTION_ENABLED:
            text_lower = user_text.lower()
            detected_lang = None
            
            if "hindi" in text_lower or "à¤¹à¤¿à¤‚à¤¦à¥€" in text_lower:
                detected_lang = "hi"
                logger.info("âœ… Language selected: Hindi")
            elif "marathi" in text_lower or "à¤®à¤°à¤¾à¤ à¥€" in text_lower:
                detected_lang = "mr"
                logger.info("âœ… Language selected: Marathi")
            elif "english" in text_lower:
                detected_lang = "en"
                logger.info("âœ… Language selected: English")
            
            if detected_lang:
                session.selected_language = detected_lang
                session.language_verified = True
                
                lang_instruction = {
                    "hi": """The user speaks HINDI. You MUST reply in HINDI only using Devanagari script.

LANGUAGE STYLE - MODERN CONVERSATIONAL HINDI:
- Speak like today's urban Hindi speakers - mix Hindi with common English words naturally
- Use English words for: AI, technology, demo, call, team, business, service, app, system, online, email
- Examples: "AI calls", "demo à¤¦à¥‡à¤–à¤¨à¤¾ à¤šà¤¾à¤¹à¥‡à¤‚à¤—à¥‡?", "team à¤•à¤¿à¤¤à¤¨à¥€ busy à¤¹à¥ˆ?", "online booking system"
- DON'T translate: AI (à¤à¤†à¤ˆâŒ), technology (à¤¤à¤•à¤¨à¥€à¤•âŒ), demo (à¤ªà¥à¤°à¤¦à¤°à¥à¤¶à¤¨âŒ), app (à¤à¤ªà¥à¤²à¤¿à¤•à¥‡à¤¶à¤¨âŒ)
- DO use: "AI se à¤†à¤ª à¤…à¤ªà¤¨à¥‡ calls automate à¤•à¤° à¤¸à¤•à¤¤à¥‡ à¤¹à¥ˆà¤‚" (natural Hindi-English mix)
- Sound like a modern Indian professional, not a Hindi textbook""",
                    
                    "mr": """The user speaks MARATHI. You MUST reply in MARATHI only using Devanagari script.

LANGUAGE STYLE - MODERN CONVERSATIONAL MARATHI:
- Speak like today's urban Marathi speakers - mix Marathi with common English words naturally
- Use English words for: AI, technology, demo, call, team, business, service, app, system, online, email
- Examples: "AI calls", "demo à¤ªà¤¾à¤¹à¤¾à¤¯à¤²à¤¾ à¤†à¤µà¤¡à¥‡à¤² à¤•à¤¾?", "team à¤•à¤¿à¤¤à¥€ busy à¤†à¤¹à¥‡?", "online booking system"
- DON'T translate: AI (à¤à¤†à¤¯âŒ), technology (à¤¤à¤‚à¤¤à¥à¤°à¤œà¥à¤žà¤¾à¤¨âŒ), demo (à¤ªà¥à¤°à¤¾à¤¤à¥à¤¯à¤•à¥à¤·à¤¿à¤•âŒ), app (à¤…à¤¨à¥à¤ªà¥à¤°à¤¯à¥‹à¤—âŒ)
- DO use: "AI à¤šà¥à¤¯à¤¾ à¤®à¤¦à¤¤à¥€à¤¨à¥‡ à¤¤à¥à¤®à¥à¤¹à¥€ calls automate à¤•à¤°à¥‚ à¤¶à¤•à¤¤à¤¾" (natural Marathi-English mix)
- Sound like a modern Mumbaikar professional, not a Marathi textbook""",
                    
                    "en": "The user speaks ENGLISH."
                }
                
                # SAFE: Use resolved_system_prompt without mutating original agent_config
                current_prompt = getattr(session, "resolved_system_prompt", None) or resolve_agent_system_prompt(session.agent_config)
                session.resolved_system_prompt = f"{current_prompt}\n\nIMPORTANT: {lang_instruction[detected_lang]}"
                
                # Generate the REAL greeting using agent's full context and knowledge base
                GREETING_PROMPT = """You are making an OUTBOUND sales call and the user just selected their language. Generate your opening line.

CRITICAL RULES:
- Output ONLY the exact words you will speak - nothing else
- NO quotes, NO meta-commentary
- Keep it to 2-3 sentences MAX (this is a phone call)
- Sound natural and confident
- Use contractions: "I'm" not "I am"

STRUCTURE:
1. Brief introduction (name + company from your knowledge)
2. State purpose based on your role
3. Polite ask if they have a moment

Speak in the user's selected language consistently throughout."""
                
                system_prompt_with_greeting = f"{GREETING_PROMPT}\n\n{session.resolved_system_prompt}"
                messages = [{"role": "user", "content": "Generate your opening line for this call in the user's selected language."}]
                response_text = await llm.generate_response(messages=messages, system_prompt=system_prompt_with_greeting, max_tokens=150)
                
                # Send text -> TTS -> Audio
                session.state = ConversationState.AI_SPEAKING
                await send_ai_response_with_bargein(websocket, session, response_text, tts, db, session.call_id)
                session.mark_ai_turn_complete()
                session.reset_for_listening()
                return
            else:
                # No language detected - increment retry counter
                session.language_retry_count += 1
                logger.warning(f"âš ï¸ Language not detected (attempt {session.language_retry_count}/2): '{user_text}'")
                
                if session.language_retry_count >= 2:
                    # Fallback to English after 2 failed attempts
                    logger.info("ðŸ”„ Fallback: Defaulting to English after 2 failed attempts")
                    detected_lang = "en"
                    session.selected_language = detected_lang
                    session.language_verified = True
                    
                    current_prompt = getattr(session, "resolved_system_prompt", None) or resolve_agent_system_prompt(session.agent_config)
                    session.resolved_system_prompt = f"{current_prompt}\n\nIMPORTANT: The user speaks ENGLISH."
                    
                    # Generate greeting in English
                    GREETING_PROMPT = """You are making an OUTBOUND sales call. The user didn't specify a language, so use English.

CRITICAL RULES:
- Output ONLY the exact words you will speak
- Keep it to 2-3 sentences MAX
- Sound natural and confident"""
                    
                    system_prompt_with_greeting = f"{GREETING_PROMPT}\n\n{session.resolved_system_prompt}"
                    messages = [{"role": "user", "content": "Generate your opening line for this call in English."}]
                    response_text = await llm.generate_response(messages=messages, system_prompt=system_prompt_with_greeting, max_tokens=150)
                    
                    session.state = ConversationState.AI_SPEAKING
                    await send_ai_response_with_bargein(websocket, session, response_text, tts, db, session.call_id)
                    session.mark_ai_turn_complete()
                    session.reset_for_listening()
                    return
                else:
                    # First failed attempt - ask again with clearer prompt
                    clarify_text = "I didn't catch that. Please say English, Hindi, or Marathi."
                    session.state = ConversationState.AI_SPEAKING
                    await send_ai_response_with_bargein(websocket, session, clarify_text, tts, db, session.call_id)
                    session.mark_ai_turn_complete()
                    session.reset_for_listening()
                    return

        # ==================== MID-CALL LANGUAGE SWITCH ====================
        # Allow caller to change language after initial selection.
        detected_turn_lang = detect_turn_language(user_text)
        if (
            session.language_verified
            and detected_turn_lang
            and detected_turn_lang != getattr(session, "selected_language", "en")
        ):
            logger.info(
                f"ðŸŒ Mid-call language switch: {session.selected_language} -> {detected_turn_lang}"
            )
            session.selected_language = detected_turn_lang

            lang_instruction = {
                "hi": "The user now prefers HINDI. Reply in Hindi using Devanagari naturally.",
                "mr": "The user now prefers MARATHI. Reply in Marathi using Devanagari naturally.",
                "en": "The user now prefers ENGLISH. Reply only in English."
            }
            current_prompt = getattr(session, "resolved_system_prompt", None) or resolve_agent_system_prompt(session.agent_config)
            session.resolved_system_prompt = f"{current_prompt}\n\nIMPORTANT: {lang_instruction[detected_turn_lang]}"

        # ==================== INTENT CLASSIFICATION ====================

        # Detect "No, I said X" or "I said X" patterns and extract the real intent
        import re
        correction_match = re.match(r"^(?:no,?\s*)?i\s+said\s+['\"]?(.+?)['\"]?\.?$", user_text.lower().strip(), re.IGNORECASE)
        if correction_match:
            extracted_text = correction_match.group(1).strip()
            logger.info(f"ðŸ”„ Correction phrase detected - extracting: '{extracted_text}'")
            # Use the extracted text instead of the full correction phrase
            user_text = extracted_text
        
        # Duplicate/echo detection
        if session.last_user_text and session.last_user_text_time:
            time_since = (datetime.now() - session.last_user_text_time).total_seconds()
            if time_since < 2.0 and user_text.lower().strip() == session.last_user_text.lower().strip():
                logger.warning(f"ðŸš« Duplicate detected within {time_since:.1f}s - skipping")
                session.mark_noise_detected()
                session.reset_for_listening()
                return
        
        # ==================== INTENT PRE-CLASSIFICATION ====================
        # Calculate time since AI spoke for echo detection
        time_since_ai_ms = 9999.0
        if session.last_ai_turn_end:
            time_since_ai_ms = (datetime.now() - session.last_ai_turn_end).total_seconds() * 1000
        
        intent, scripted_response = classify_intent(user_text, time_since_ai_ms)
        logger.info(f"ðŸ§  Intent: {intent} (time since AI: {time_since_ai_ms:.0f}ms)")
        is_wow_call = _is_wow_agent_config(session.agent_config)
        
        # ==================== NOISE/ECHO DETECTION - Skip entirely ====================
        if intent in ("noise", "echo"):
            reason = "echo" if intent == "echo" else "noise"
            logger.info(f"ðŸ”‡ {reason.title()} detected ('{user_text}') - ignoring, starting cooldown")
            session.mark_noise_detected()
            session.reset_for_listening()
            return
        
        # ==================== INTERRUPTION INTENT CLASSIFICATION ====================
        # Check if this was an interruption and classify if it's an acknowledgement
        interrupt_type, should_continue = classify_interruption_intent(user_text)
        
        if session.interrupted and should_continue and interrupt_type == "acknowledgement":
            # User interrupted with "yeah", "okay", etc.
            # This is a conversational signal, not a topic change
            # Continue AI flow naturally without full LLM processing
            logger.info(f"ðŸ‘ Acknowledgement interrupt detected: '{user_text}' - continuing AI flow naturally")
            session.is_acknowledgement_interrupt = True
            
            # Don't add to transcript as a separate turn
            # Just continue naturally
            session.reset_for_listening()
            return
        
        # ==================== MARK REAL USER UTTERANCE ====================
        session.mark_user_utterance()
        session.last_user_text = user_text
        session.last_user_text_time = datetime.now()
        
        # Save user transcript
        await db.add_transcript(call_id=session.call_id, speaker="user", text=user_text)

        # Enforce explicit permission gate at runtime before any sales progression.
        if is_wow_call and getattr(session, "awaiting_permission", False):
            if intent == "affirm":
                session.permission_granted = True
                session.awaiting_permission = False
                logger.info("✅ Permission gate passed: user explicitly allowed conversation")
            elif intent in {"negative", "goodbye"}:
                close_text = "I completely understand. I apologize for the interruption. Have a great day."
                session.awaiting_permission = False
                session.permission_granted = False
                session.call_closed = True
                session.state = ConversationState.AI_SPEAKING
                session.interrupted = False
                await send_ai_response_with_bargein(websocket, session, close_text, tts, db, session.call_id)
                await db.add_transcript(call_id=session.call_id, speaker="agent", text=close_text)
                session.mark_ai_turn_complete()
                try:
                    await db.update_call(session.call_id, status="completed", ended_at=datetime.now())
                except Exception as close_error:
                    logger.warning(f"Permission-gate close update failed for {session.call_id}: {close_error}")
                session.reset_for_listening()
                return
            else:
                clarify_text = "Before we continue, do you want to speak now? Please answer yes or no."
                session.state = ConversationState.AI_SPEAKING
                session.interrupted = False
                await send_ai_response_with_bargein(websocket, session, clarify_text, tts, db, session.call_id)
                await db.add_transcript(call_id=session.call_id, speaker="agent", text=clarify_text)
                session.mark_ai_turn_complete()
                session.reset_for_listening()
                return

        if is_wow_call and getattr(session, "call_closed", False):
            session.reset_for_listening()
            return

        # Deterministic graceful-exit branches for key WOW scenarios.
        if is_wow_call:
            exit_case = classify_wow_exit_case(user_text)
            if exit_case:
                exit_messages = {
                    "busy": "I completely understand. I apologize for interrupting your schedule. Have a great day.",
                    "budget_low": "Understood. That budget concern makes sense. Thank you for your time, and have a great day.",
                    "location_mismatch": "I appreciate your honesty about location preferences. Thank you for your time, and have a wonderful day.",
                }
                close_text = exit_messages[exit_case]
                session.call_closed = True
                session.state = ConversationState.AI_SPEAKING
                session.interrupted = False
                await send_ai_response_with_bargein(websocket, session, close_text, tts, db, session.call_id)
                await db.add_transcript(call_id=session.call_id, speaker="agent", text=close_text)
                session.mark_ai_turn_complete()
                try:
                    await db.update_call(session.call_id, status="completed", ended_at=datetime.now())
                except Exception as close_error:
                    logger.warning(f"Graceful-exit close update failed for {session.call_id}: {close_error}")
                session.reset_for_listening()
                return

            # Keep deterministic checkpoint state synchronized per turn.
            update_runtime_wow_checkpoint_state(session, user_text)
        
        # Handle scripted responses (no LLM needed)
        if scripted_response:
            ai_response = scripted_response
            logger.info(f"âš¡ Scripted response (no LLM): {ai_response}")
        else:
            # ==================== SET LLM IN-FLIGHT FLAG ====================
            # This prevents VAD from triggering false speech during LLM wait
            session.llm_in_flight = True
            
            # Get conversation history (more context for better responses)
            conversation_history = await db.get_conversation_history(session.call_id, limit=10)
            messages = conversation_history + [{"role": "user", "content": user_text}]
            
            # ==================== RAG: RETRIEVE RELEVANT KB ====================
            kb_context = await retrieve_relevant_knowledge(session.agent_id, user_text, db)
            
            # Debug: Log conversation context being sent
            logger.debug(f"ðŸ“ Conversation context: {len(conversation_history)} previous messages + current: '{user_text}'")
            if conversation_history:
                logger.debug(f"ðŸ“ Last exchange: {conversation_history[-2:] if len(conversation_history) >= 2 else conversation_history}")
            if kb_context:
                logger.info(f"ðŸ“š RAG: Retrieved relevant KB context ({len(kb_context)} chars)")
            
            # Build system prompt based on intent
            if intent == "affirm":
                # User said yes/okay - add context to help LLM continue
                intent_hint = """
CONTEXT: User just confirmed/agreed (said yes, okay, sure, etc.)
ACTION: Continue with your pitch or next question. Do NOT ask them to clarify. Do NOT repeat your last question."""
            elif intent == "ack":
                # User acknowledged - continue naturally
                intent_hint = """
CONTEXT: User acknowledged (hmm, uh-huh, I see)
ACTION: Continue speaking naturally. They are listening."""
            elif intent == "open":
                # User wants context
                intent_hint = """
CONTEXT: User wants to know who you are or what this is about.
ACTION: Briefly explain your purpose in 1-2 sentences."""
            elif intent == "negative":
                # User declined
                intent_hint = """
CONTEXT: User seems uninterested or busy.
ACTION: Acknowledge respectfully and offer to call back at a better time. Don't be pushy."""
            else:
                intent_hint = ""
            
            inferred_phase = infer_wow_phase(conversation_history, user_text) if is_wow_call else WOW_PHASE_1_2
            turn_word_limit = 80 if is_wow_call and inferred_phase in {WOW_PHASE_3, WOW_PHASE_4} else 30

            # PROFESSIONAL SALES AGENT PROMPT - Applied to ALL calls
            SALES_AGENT_RULES = f"""CRITICAL RULES FOR PHONE CONVERSATION:

1. NEVER REPEAT - If you already asked something, MOVE FORWARD. Check the conversation history!
2. ONE QUESTION per response - Never combine multiple questions
3. UNDERSTAND SLANG:
   - "I'm down" / "down for that" / "bet" = YES, they agree
   - "sounds good" / "cool" / "awesome" = positive response
   - "yeah" / "yep" / "sure" = affirmative
4. UNDERSTAND NUMBERS:
   - "4-5" or "four to five" = the number 4 or 5 (SMALL)
   - NEVER interpret "4-5" as "400-500"
5. FOLLOW CONTEXT:
   - If user answered a question, move to the NEXT step
   - Don't re-ask what they already answered
6. TURN WORD LIMIT (phase-aware):
    - Inferred phase: {inferred_phase}
    - If PHASE_3 (pitch) or PHASE_4 (CTA), you may use up to 80 words.
    - All other turns must stay under 30 words.
    - Current turn limit: {turn_word_limit} words.
7. NATURAL SPEECH - Use "I'm", "you're", "that's", "cool", "got it"
8. ADVANCE THE CONVERSATION - Each response moves toward the goal
9. SCHEDULING FLOW:
   - First get DAY â†’ Then get TIME â†’ Then get EMAIL
   - Never skip steps!
10. PRONUNCIATION ENFORCEMENT (critical names):
    - Divyasree => Div-yaa-shree
    - Nandi => Nun-dhee
    - Devanahalli => Deh-vah-nah-hul-lee
    - Lakh => Laak
    - Crore => Krore
11. WOW QUALIFICATION ORDER:
    - Ask checkpoints in order: INTENT -> GEOGRAPHY -> BUDGET -> TIMELINE
    - If caller already volunteered a checkpoint, SKIP that checkpoint and move forward.
"""
            # Use session's resolved_system_prompt if set (for language selection), otherwise fallback to agent_config
            base_prompt = (
                getattr(session, "resolved_system_prompt", None)
                or resolve_agent_system_prompt(session.agent_config)
            )

            wow_checkpoint_guidance = infer_wow_checkpoint_guidance(conversation_history, user_text)
            if is_wow_call:
                wow_checkpoint_guidance = f"{wow_checkpoint_guidance}{build_runtime_wow_checkpoint_guidance(session)}"
            
            # Add last AI response context to prevent repetition
            repetition_guard = ""
            if session.last_ai_response:
                repetition_guard = f"\n\nIMPORTANT: Your last response was: \"{session.last_ai_response}\"\nDO NOT repeat this. Say something different or move the conversation forward.\n"
            
            # Combine all context: rules + intent + repetition guard + base prompt + KB context
            system_prompt = (
                f"{SALES_AGENT_RULES}{intent_hint}{repetition_guard}{wow_checkpoint_guidance}"
                f"\n\n{base_prompt}{kb_context}"
            )
            
            try:
                llm_start = datetime.now()
                ai_response = await llm.generate_response(
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=session.agent_config.get("temperature", 0.7),
                    max_tokens=200  # Increased for natural, complete responses
                )
                llm_duration = (datetime.now() - llm_start).total_seconds() * 1000
                logger.info(f"ðŸ¤– LLM response ({llm_duration:.0f}ms): {ai_response}")
                
                # Check if LLM repeated itself despite instructions
                if session.last_ai_response and ai_response.strip().lower() == session.last_ai_response.strip().lower():
                    logger.warning(f"ðŸ”„ LLM repeated itself - using fallback")
                    ai_response = "I understand. Is there anything specific you'd like to know?"
                    
            except Exception as e:
                logger.error(f"LLM error: {e}")
                ai_response = "Sorry, I'm having a technical issue. Can you say that again?"
            finally:
                # Clear LLM in-flight flag
                session.llm_in_flight = False
        
        # ==================== CONTEXT HYGIENE: Track pending AI text ====================
        # Don't commit AI response to transcript yet - wait until after TTS
        # If interrupted, pending_ai_text will be cleared by interrupt_ai()
        session.pending_ai_text = ai_response
        session.last_ai_response = ai_response

        if is_wow_call:
            asked_checkpoint = infer_wow_checkpoint_question(ai_response)
            if asked_checkpoint:
                session.last_checkpoint_asked = asked_checkpoint
        
        # ==================== UPDATE CALL STAGE (VAPI-LIKE) ====================
        # Detect question type from AI response to set context-aware timeout for next user turn
        session.update_call_stage(ai_response)
        
        # Send AI response with barge-in support
        session.state = ConversationState.AI_SPEAKING
        session.interrupted = False
        await send_ai_response_with_bargein(websocket, session, ai_response, tts, db, session.call_id)
        
        # ==================== CONTEXT HYGIENE: Only commit if not interrupted ====================
        if not session.interrupted and session.pending_ai_text:
            # AI finished speaking without interruption - commit to transcript
            await db.add_transcript(call_id=session.call_id, speaker="agent", text=session.pending_ai_text)
            logger.debug(f"âœ… AI transcript committed: '{session.pending_ai_text[:50]}...'")
        elif session.interrupted:
            # Was interrupted - don't commit partial AI text
            logger.info(f"ðŸš« AI interrupted - not committing partial transcript")
        
        session.pending_ai_text = None
        
        # Mark AI turn complete for turn tracking
        session.mark_ai_turn_complete()
        
        # Ready for next input (NO SLEEP!)
        session.reset_for_listening()
        logger.info("ðŸŸ¢ AI finished - ready for user input")
        
    except Exception as e:
        logger.error(f"Error in process_user_speech_fast: {e}", exc_info=True)
        session.pending_ai_text = None  # Clear pending on error
        session.reset_for_listening()


async def send_ai_response_with_bargein(
    websocket: WebSocket,
    session: CallSession,
    text: str,
    tts: TTSClient,
    db: RelayDB,
    call_id: str
) -> float:
    """
    Send AI audio with BARGE-IN support and STREAMING TTS
    
    STREAMING OPTIMIZATION:
    - Split text into sentences
    - Generate TTS for first sentence IMMEDIATELY
    - Start playing first sentence while generating rest in parallel
    - Target: 500-700ms faster response time
    
    Barge-in handling:
    - Check session.interrupted flag during streaming
    - Stop immediately if user interrupts
    """
    try:
        import asyncio
        
        # Split text into sentences for streaming
        lang = getattr(session, "selected_language", "en")
        sentences = re.split(r'([.!?]+(?:\s+|$))', text)
        
        # Reconstruct sentences with punctuation
        sentence_list = []
        for i in range(0, len(sentences) - 1, 2):
            if sentences[i].strip():
                sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
                sentence_list.append(sentence.strip())
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            sentence_list.append(sentences[-1].strip())
        
        if not sentence_list:
            logger.error("No sentences to generate TTS for")
            return 0.0
        
        # Generate FIRST sentence immediately
        tts_start = datetime.now()
        first_audio = await tts.generate_speech_bytes(sentence_list[0], language=lang)
        first_gen_time = (datetime.now() - tts_start).total_seconds() * 1000
        
        if not first_audio:
            logger.error("TTS failed for first sentence")
            return 0.0
        
        logger.info(f"âš¡ First sentence TTS: {first_gen_time:.0f}ms - STREAMING NOW")
        
        # Start generating remaining sentences in parallel (don't wait)
        remaining_tasks = []
        for sentence in sentence_list[1:]:
            if sentence and len(sentence) > 1:
                task = asyncio.create_task(tts.generate_speech_bytes(sentence, language=lang))
                remaining_tasks.append((sentence, task))
        
        # ==================== SET AI SPEECH START TIME (Grace Period) ====================
        session.ai_speech_start_time = datetime.now()
        session.interrupt_speech_frames = 0
        session.interrupt_speech_start = None
        logger.debug(f"ðŸ”‡ AI speech grace period started ({AI_SPEECH_GRACE_PERIOD_MS}ms)")
        
        total_duration = 0.0
        
        # Stream FIRST sentence immediately (already generated)
        sentence_chunks = [(sentence_list[0], first_audio)]
        
        # Stream first sentence
        for sentence_text, wav_bytes in sentence_chunks:
            if session.interrupted:
                logger.info(f"ðŸ›‘ BARGE-IN: Stopping TTS mid-stream")
                break
            
            logger.debug(f"Streaming: {sentence_text[:30]}...")
            
            # Convert WAV to Twilio format
            wav_buffer = io.BytesIO(wav_bytes)
            with wave.open(wav_buffer, 'rb') as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                framerate = wav.getframerate()
                audio_pcm = wav.readframes(wav.getnframes())
            
            # Resample to 8kHz
            if framerate != TWILIO_SAMPLE_RATE:
                audio_pcm, _ = audioop.ratecv(audio_pcm, sample_width, channels, framerate, TWILIO_SAMPLE_RATE, None)
            
            # Mono
            if channels == 2:
                audio_pcm = audioop.tomono(audio_pcm, sample_width, 1, 1)
            
            # Convert to mulaw
            audio_mulaw = audioop.lin2ulaw(audio_pcm, sample_width)
            
            # Send in 20ms chunks
            chunk_size = int(TWILIO_SAMPLE_RATE * 0.02)
            
            for i in range(0, len(audio_mulaw), chunk_size):
                if session.interrupted:
                    logger.info("ðŸ›‘ BARGE-IN during chunk streaming")
                    break
                
                chunk = audio_mulaw[i:i + chunk_size]
                payload = base64.b64encode(chunk).decode('utf-8')
                
                message = {
                    "event": "media",
                    "streamSid": session.stream_sid,
                    "media": {"payload": payload}
                }
                
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as ws_error:
                    logger.warning(f"WebSocket send failed: {ws_error}")
                    return total_duration
            
            if session.interrupted:
                break
            
            sentence_duration = len(audio_mulaw) / TWILIO_SAMPLE_RATE
            total_duration += sentence_duration
            logger.debug(f"Sent sentence: {sentence_duration:.2f}s")
        
        # Now stream REMAINING sentences as they're generated
        for sentence_text, task in remaining_tasks:
            if session.interrupted:
                # Cancel pending tasks
                for _, t in remaining_tasks:
                    if not t.done():
                        t.cancel()
                break
            
            # Wait for this sentence's TTS to complete
            try:
                wav_bytes = await task
            except Exception as e:
                logger.error(f"TTS generation failed for sentence: {e}")
                continue
            
            if not wav_bytes:
                logger.warning(f"Empty audio for: {sentence_text[:30]}")
                continue
            
            logger.debug(f"Streaming: {sentence_text[:30]}...")
            
            # Convert and stream (same as above)
            wav_buffer = io.BytesIO(wav_bytes)
            with wave.open(wav_buffer, 'rb') as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                framerate = wav.getframerate()
                audio_pcm = wav.readframes(wav.getnframes())
            
            if framerate != TWILIO_SAMPLE_RATE:
                audio_pcm, _ = audioop.ratecv(audio_pcm, sample_width, channels, framerate, TWILIO_SAMPLE_RATE, None)
            
            if channels == 2:
                audio_pcm = audioop.tomono(audio_pcm, sample_width, 1, 1)
            
            audio_mulaw = audioop.lin2ulaw(audio_pcm, sample_width)
            chunk_size = int(TWILIO_SAMPLE_RATE * 0.02)
            
            for i in range(0, len(audio_mulaw), chunk_size):
                if session.interrupted:
                    logger.info("ðŸ›‘ BARGE-IN during streaming")
                    break
                
                chunk = audio_mulaw[i:i + chunk_size]
                payload = base64.b64encode(chunk).decode('utf-8')
                
                message = {
                    "event": "media",
                    "streamSid": session.stream_sid,
                    "media": {"payload": payload}
                }
                
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as ws_error:
                    logger.warning(f"WebSocket send failed: {ws_error}")
                    return total_duration
            
            if session.interrupted:
                break
            
            sentence_duration = len(audio_mulaw) / TWILIO_SAMPLE_RATE
            total_duration += sentence_duration
            logger.debug(f"Sent sentence: {sentence_duration:.2f}s")
        
        # ==================== SET ECHO PROTECTION WINDOW ====================
        session.tts_end_time = datetime.now()
        logger.debug(f"ðŸ”‡ Echo protection window started (1000ms)")
        
        if session.interrupted:
            logger.info(f"âš¡ AI speech interrupted after {total_duration:.1f}s")
        else:
            logger.info(f"âœ… AI speech complete: {total_duration:.1f}s | Echo window active")
        
        return total_duration
        
    except Exception as e:
        logger.error(f"Error in send_ai_response_with_bargein: {e}", exc_info=True)
        session.tts_end_time = datetime.now()
        return 0.0


# ==================== STARTUP ====================

# Global ngrok URL storage
ngrok_public_url = None

@app.on_event("startup")
async def startup_event():
    """Initialize services and start ngrok tunnel"""
    global ngrok_public_url
    
    logger.info("Starting Divyashree Voice Gateway v2.0 (Vapi-style architecture)...")
    logger.info("Features: VAD edge-trigger, barge-in support, intent pre-classification")
    
    # Auto-detect and update tunnel URL
    try:
        from tunnel_utils import auto_detect_and_update_tunnel_url
        detected_url = auto_detect_and_update_tunnel_url()
        if detected_url:
            ngrok_public_url = detected_url
            logger.info(f"âœ… Using ngrok tunnel: {detected_url}")
            
            # Auto-register with backend
            try:
                import httpx
                backend_url = os.getenv("BACKEND_URL", "https://api.divyashree.tech")
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        f"{backend_url}/system/register-voice-gateway",
                        json={"url": detected_url}
                    )
                    if response.status_code == 200:
                        logger.info(f"âœ… Registered voice gateway URL with backend: {detected_url}")
                    else:
                        logger.warning(f"Failed to register with backend: {response.status_code}")
            except Exception as e:
                logger.warning(f"Could not register with backend: {e}")
                
    except Exception as e:
        logger.warning(f"Could not auto-detect tunnel URL: {e}")
    
    # Start ngrok tunnel automatically (fallback)
    if not ngrok_public_url:
        try:
            import subprocess
            import requests
            import time
            
            logger.info("Starting ngrok tunnel on port 8001...")
            
            subprocess.Popen(
                ["ngrok", "http", "8001", "--log=stdout"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            time.sleep(3)
            
            response = requests.get("http://localhost:4040/api/tunnels")
            tunnels = response.json()["tunnels"]
            
            if tunnels:
                ngrok_public_url = tunnels[0]["public_url"]
                logger.info(f"âœ… Ngrok tunnel ready: {ngrok_public_url}")
            else:
                logger.warning("âš ï¸ Ngrok started but no tunnels found")
                
        except Exception as e:
            logger.warning(f"Could not start ngrok automatically: {e}")
            logger.info("You can start ngrok manually: ngrok http 8001")
    
    logger.info("âœ… WebRTC VAD ready (Mode 3 aggressive, 180ms speech start, 700ms speech end) + Force-process @4s")
    
    try:
        logger.info("Loading cache client...")
        cache = await get_cache_client()
        if cache.enabled:
            logger.info("âœ… Redis cache ready")
        else:
            logger.info("âš ï¸ Redis cache disabled (continuing without cache)")
    except Exception as e:
        logger.warning(f"Cache initialization failed: {e}")
    
    try:
        logger.info("Loading STT client...")
        stt = get_stt_client()
        logger.info("âœ… STT ready")
    except Exception as e:
        logger.error(f"Failed to load STT: {e}")
    
    try:
        logger.info("Loading TTS client...")
        tts = get_tts_client()
        logger.info("âœ… TTS ready")
    except Exception as e:
        logger.error(f"Failed to load TTS: {e}")
    
    logger.info("ðŸŽ‰ Voice Gateway startup complete - Target: <4s response time")


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("VOICE_GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("VOICE_GATEWAY_PORT", 8001))
    
    uvicorn.run(
        "voice_gateway:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )

