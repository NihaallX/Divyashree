
"""
FastAPI Backend for Divyashree AI Caller
Handles API endpoints for agents, calls, and Twilio webhooks
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from twilio.rest import Client as TwilioClient
from loguru import logger
import os
import sys
from dotenv import load_dotenv

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.dirname(__file__))

# Load environment variables before importing modules that read env at import-time.
load_dotenv()

from shared.database import get_db
from shared.llm_client import get_llm_client

# Import routes
import auth_routes
import cal_routes
import campaign_routes
import contact_routes
import event_routes
import agent_routes
import call_routes
import template_routes
import knowledge_routes
import analytics_routes
import system_routes

# Configure logger
logger.add("logs/backend.log", rotation="1 day", retention="7 days", level="INFO")

# Initialize FastAPI
app = FastAPI(
    title="Divyashree AI Caller API",
    description="Backend for AI-powered outbound calling system",
    version="1.0.0"
)

# Apply global rate limiting
from limiter import check_rate_limit
from fastapi import Depends
app.router.dependencies.append(Depends(check_rate_limit))

# Include authentication routes
app.include_router(auth_routes.router)

# Include Cal.com routes
app.include_router(cal_routes.router)

# Include campaign routes
app.include_router(campaign_routes.router)

# Include contact routes
app.include_router(contact_routes.router)

# Include event routes
app.include_router(event_routes.router)

# Include new modular routes
app.include_router(agent_routes.router)
app.include_router(call_routes.router)
app.include_router(template_routes.router)
app.include_router(knowledge_routes.router)
app.include_router(analytics_routes.router)
app.include_router(system_routes.router)

# CORS middleware - API clients and local development
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://divyashree.tech",
    "https://www.divyashree.tech",
    "https://api.divyashree.tech",
]

extra_origins = os.getenv("CORS_ORIGINS", "").strip()
if extra_origins:
    allowed_origins.extend([origin.strip() for origin in extra_origins.split(",") if origin.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # Allow production/custom domains and Vercel preview domains.
    allow_origin_regex=r"https://.*\.divyashree\.tech|https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add validation error handler to debug 422 errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log and return validation errors for debugging"""
    body = None
    try:
        body = await request.body()
        body = body.decode('utf-8')
    except:
        pass
    
    logger.error(f"Validation error on {request.method} {request.url.path}")
    logger.error(f"Headers: {dict(request.headers)}")
    logger.error(f"Request body: {body}")
    logger.error(f"Content-Type: {request.headers.get('content-type')}")
    logger.error(f"Errors: {exc.errors()}")
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "body": body
        }
    )

# Twilio client
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
VOICE_GATEWAY_URL = os.getenv("VOICE_GATEWAY_URL", "https://your-ngrok-url.ngrok.io")

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    logger.warning("Twilio credentials not fully configured")
    twilio_client = None
else:
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    logger.info("Twilio client initialized")

# ==================== STARTUP ====================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting Divyashree Backend...")
    
    # Test database connection
    try:
        db = get_db()
        agents = await db.list_agents()
        logger.info(f"Database connected. Found {len(agents)} agents.")
        
        logger.info("Auth routes initialized")
        
        # Initialize contact routes with database
        contact_routes.init_db(db)
        logger.info("Contact routes initialized")
        
        # Initialize event routes with database
        event_routes.init_db(db)
        logger.info("Event routes initialized")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
    
    # Test LLM connection
    try:
        llm = get_llm_client()
        healthy = await llm.health_check()
        if healthy:
            models = await llm.list_models()
            logger.info(f"LLM connected. Available models: {models}")
        else:
            logger.warning("LLM health check failed")
    except Exception as e:
        logger.error(f"LLM connection failed: {e}")
    
    # Start campaign scheduler
    try:
        from scheduler import start_scheduler
        start_scheduler()
        logger.info("Campaign scheduler started")
    except Exception as e:
        logger.error(f"Failed to start campaign scheduler: {e}")
    
    logger.info("Backend startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Divyashree Backend...")
    
    try:
        from scheduler import stop_scheduler
        stop_scheduler()
        logger.info("Campaign scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
