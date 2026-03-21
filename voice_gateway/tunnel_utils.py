"""Ngrok tunnel URL auto-update utility.

Call this from voice_gateway.py on startup.
"""
import os
import re
import subprocess
import time
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv, set_key

def get_tunnel_url():
    """
    Get tunnel URL from multiple sources:
    1. Ngrok API (if running in Docker with ngrok container)
    2. VOICE_GATEWAY_URL env var
    3. Return None if not found
    """
    
    # First try ngrok API (Docker container exposes port 4040)
    try:
        import requests
        # Try ngrok container on Docker network
        response = requests.get("http://ngrok:4040/api/tunnels", timeout=3)
        if response.status_code == 200:
            tunnels = response.json().get("tunnels", [])
            for tunnel in tunnels:
                if tunnel.get("public_url", "").startswith("https://"):
                    url = tunnel["public_url"]
                    logger.info(f"✅ Found ngrok URL from API: {url}")
                    return url
    except Exception as e:
        logger.debug(f"Ngrok API not available: {e}")
    
    # Try localhost ngrok API (for local development)
    try:
        import requests
        response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3)
        if response.status_code == 200:
            tunnels = response.json().get("tunnels", [])
            for tunnel in tunnels:
                if tunnel.get("public_url", "").startswith("https://"):
                    url = tunnel["public_url"]
                    logger.info(f"✅ Found ngrok URL from localhost API: {url}")
                    return url
    except Exception as e:
        logger.debug(f"Localhost ngrok API not available: {e}")
    
    # Fall back to env var
    env_url = os.getenv("VOICE_GATEWAY_URL")
    if env_url and env_url.startswith("https://"):
        logger.info(f"✅ Using VOICE_GATEWAY_URL from env: {env_url}")
        return env_url

    logger.warning("⚠️ No tunnel URL found")
    return None

def update_voice_gateway_url_in_env(new_url: str) -> bool:
    """
    Update VOICE_GATEWAY_URL in .env file
    
    Args:
        new_url: The new public tunnel URL
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Find .env file (one level up from voice_gateway/)
        env_path = Path(__file__).parent.parent / '.env'
        
        if not env_path.exists():
            logger.error(f".env file not found at {env_path}")
            return False
        
        # Update the env file
        set_key(str(env_path), "VOICE_GATEWAY_URL", new_url)
        
        # Also update the current process environment
        os.environ["VOICE_GATEWAY_URL"] = new_url
        
        logger.info(f"✅ Updated VOICE_GATEWAY_URL: {new_url}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update VOICE_GATEWAY_URL: {e}")
        return False

def auto_detect_and_update_tunnel_url():
    """
    Auto-detect tunnel URL and update environment
    Call this on voice gateway startup
    """
    logger.info("🔍 Auto-detecting ngrok tunnel URL...")
    
    # Try to get current URL
    current_url = get_tunnel_url()
    
    if current_url:
        # Update env file if needed
        env_url = os.getenv("VOICE_GATEWAY_URL")
        
        if env_url != current_url:
            logger.info(f"🔄 Updating tunnel URL: {env_url} → {current_url}")
            update_voice_gateway_url_in_env(current_url)
        else:
            logger.info("✓ Tunnel URL already up to date")
        
        return current_url
    else:
        logger.warning("⚠️ Could not auto-detect tunnel URL. Manual configuration may be required.")
        return None

if __name__ == "__main__":
    # Test the auto-detection
    load_dotenv()
    url = auto_detect_and_update_tunnel_url()
    if url:
        print(f"\n✅ Detected URL: {url}")
    else:
        print("\n❌ Could not detect tunnel URL")
