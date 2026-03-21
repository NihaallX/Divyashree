from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import os
from loguru import logger
from shared.database import get_db, RelayDB
from shared.llm_client import get_llm_client, LLMClient

router = APIRouter()

VOICE_GATEWAY_URL = os.getenv("VOICE_GATEWAY_URL", "https://your-ngrok-url.ngrok.io")

# In-memory storage for voice gateway URL (auto-registered by voice gateway on startup)
_registered_voice_gateway_url = None

# ==================== ROUTES ====================

@router.post("/system/register-voice-gateway")
async def register_voice_gateway(payload: dict):
    """
    Voice gateway auto-registers its URL on startup
    This allows dynamic URL updates without redeploying backend
    """
    global _registered_voice_gateway_url
    
    url = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    _registered_voice_gateway_url = url
    logger.info(f"✅ Voice gateway registered: {url}")
    
    return {
        "success": True,
        "message": "Voice gateway URL registered",
        "url": url
    }

@router.get("/system/voice-gateway-url")
async def get_voice_gateway_url():
    """Get the current voice gateway URL (prioritizes registered URL)"""
    url = _registered_voice_gateway_url or VOICE_GATEWAY_URL
    return {
        "url": url,
        "source": "registered" if _registered_voice_gateway_url else "environment"
    }

@router.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "RelayX Backend",
        "status": "running",
        "version": "1.0.0"
    }


@router.get("/health")
async def health_check(db: RelayDB = Depends(get_db), llm: LLMClient = Depends(get_llm_client)):
    """Comprehensive health check"""
    # Check Twilio status indirectly or pass it in?
    # For now simply check if env vars are set
    twilio_configured = all([
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN"),
        os.getenv("TWILIO_PHONE_NUMBER")
    ])

    health_status = {
        "status": "ok",
        "backend": "healthy",
        "database": "unknown",
        "llm": "unknown",
        "twilio": "configured" if twilio_configured else "not configured"
    }
    
    # Check LLM
    try:
        llm_healthy = await llm.health_check()
        health_status["llm"] = "healthy" if llm_healthy else "unhealthy"
    except Exception as e:
        health_status["llm"] = f"error: {str(e)}"
    
    # Check database (simple check)
    try:
        await db.list_agents()
        health_status["database"] = "healthy"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
    
    return health_status


@router.get("/info")
async def get_info(db: RelayDB = Depends(get_db)):
    """Get backend info including ngrok URL"""
    try:
        # Get today's calls count
        calls = await db.list_calls()
        today = datetime.now().strftime("%Y-%m-%d")
        today_calls = [c for c in calls if c.get("started_at") and str(c.get("started_at")).startswith(today)]
        
        # Get ngrok URL from voice gateway
        ngrok_url = VOICE_GATEWAY_URL
        import httpx
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                vg_response = await client.get("http://localhost:8001/info")
                vg_data = vg_response.json()
                ngrok_url = vg_data.get("ngrok_url", VOICE_GATEWAY_URL)
        except:
            pass
        
        return {
            "service": "RelayX Backend",
            "status": "running",
            "today_calls": len(today_calls),
            "ngrok_url": ngrok_url,
            "public_url": ngrok_url
        }
        
    except Exception as e:
        logger.warning(f"Could not get info: {e}")
        return {
            "service": "RelayX Backend",
            "status": "running",
            "today_calls": 0,
            "ngrok_url": VOICE_GATEWAY_URL,
            "public_url": VOICE_GATEWAY_URL
        }


@router.get("/api-credits")
async def get_api_credits(db: RelayDB = Depends(get_db)):
    """Get real-time API credit usage from Groq"""
    import httpx
    credits = {
        "groq": {
            "status": "unknown",
            "requests_limit": 30,
            "requests_remaining": "?",
            "tokens_limit": 8000,
            "tokens_remaining": "?"
        }
    }
    
    try:
        # Get today's calls for usage estimation
        calls = await db.list_calls()
        today = datetime.now().strftime("%Y-%m-%d")
        today_calls = [c for c in calls if c.get("started_at") and str(c.get("started_at")).startswith(today)]
        
        # Estimate Groq usage (tokens and requests)
        # Approximate: 500 tokens per call (STT + LLM combined)
        estimated_tokens_used = len(today_calls) * 500
        groq_tokens_remaining = max(0, 8000 - estimated_tokens_used)
        groq_requests_remaining = max(0, 30 - len(today_calls))
        
        credits["groq"]["status"] = "estimated"
        credits["groq"]["tokens_remaining"] = groq_tokens_remaining
        credits["groq"]["requests_remaining"] = groq_requests_remaining
        credits["groq"]["today_calls"] = len(today_calls)
        
        logger.debug(f"API Credits - Groq: {groq_tokens_remaining} tokens")
        
    except Exception as e:
        logger.warning(f"Could not estimate API credits: {e}")
        credits["groq"]["status"] = "error"
    
    return credits


@router.get("/logs")
async def get_logs():
    """Get recent voice gateway logs (legacy endpoint)"""
    try:
        log_file = "logs/voice_gateway.log"
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                # Read last 50 lines
                lines = f.readlines()
                logs = ''.join(lines[-50:])
        else:
            logs = "Voice gateway log file not found"
        return {"logs": logs, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"logs": f"Error fetching logs: {str(e)}", "timestamp": datetime.now().isoformat()}


from admin_routes import verify_admin_token

@router.get("/api/logs/backend")
async def get_backend_logs(admin: dict = Depends(verify_admin_token)):
    """Get recent backend logs"""
    try:
        # Try multiple possible log locations
        log_paths = ["logs/backend.log", "../logs/backend.log", "backend/logs/backend.log"]
        logs = ""
        
        for log_file in log_paths:
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    logs = ''.join(lines[-100:])
                break
        
        if not logs:
            logs = "Backend log file not found. Checked: " + ", ".join(log_paths)
            
        return {"logs": logs, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error(f"Error fetching backend logs: {e}")
        return {"logs": f"Error fetching logs: {str(e)}", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/api/logs/voice-gateway")
async def get_voice_gateway_logs(admin: dict = Depends(verify_admin_token)):
    """Get recent voice gateway logs"""
    try:
        # Try multiple possible log locations
        log_paths = [
            "logs/voice_gateway.log",
            "../logs/voice_gateway.log",
            "voice_gateway/logs/voice_gateway.log",
            "../voice_gateway/logs/voice_gateway.log"
        ]
        logs = ""
        
        for log_file in log_paths:
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    logs = ''.join(lines[-100:])
                break
        
        if not logs:
            logs = "Voice gateway log file not found. Checked: " + ", ".join(log_paths)
            
        return {"logs": logs, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error(f"Error fetching voice gateway logs: {e}")
        return {"logs": f"Error fetching logs: {str(e)}", "timestamp": datetime.now(timezone.utc).isoformat()}
