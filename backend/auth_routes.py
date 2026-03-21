"""
Authentication routes for user signup, login, and token management
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, model_validator
from typing import Optional
import os
from datetime import datetime, timedelta, timezone

# Import from same directory
from auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    get_current_user_id,
)
from shared.database import get_db, RelayDB

router = APIRouter(prefix="/auth", tags=["Authentication"])


# Request/Response Models
class SignupRequest(BaseModel):
    email: str
    password: str
    username: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None

    @model_validator(mode="after")
    def validate_signup(self):
        if "@" not in self.email:
            raise ValueError("email must contain @")
        if not self.username and not self.name:
            self.name = self.email.split("@", 1)[0]
        return self


class LoginRequest(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: str

    @model_validator(mode="after")
    def validate_login(self):
        if not self.email and not self.username:
            raise ValueError("Either email or username is required")
        return self


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


@router.get("/verify-token")
async def verify_token_endpoint(user_id: str = Depends(get_current_user_id)):
    """Verify if the current access token is valid"""
    return {"valid": True, "user_id": user_id}


@router.post("/signup", response_model=TokenResponse)
async def signup(request: SignupRequest, db: RelayDB = Depends(get_db)):
    """Register a new user"""
    try:
        # Check if user already exists
        existing = db.client.table("users").select("id").eq("email", request.email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hash password
        password_hash = get_password_hash(request.password)
        
        # Create user
        user_data = {
            "email": request.email,
            "password_hash": password_hash,
            "name": request.name or request.username,
            "phone": request.phone,
            "company": request.company,
        }
        
        result = db.client.table("users").insert(user_data).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create user")
        
        user = result.data[0]
        user_id = user["id"]
        
        # Create default agent for the user
        agent_data = {
            "user_id": user_id,
            "name": request.name or request.username or "My Assistant",
            "prompt_text": "You are a helpful AI assistant.",
            "temperature": 0.7,
            "is_active": True,
        }
        db.client.table("agents").insert(agent_data).execute()
        
        # Generate tokens
        access_token = create_access_token(data={"sub": user_id})
        refresh_token = create_refresh_token(data={"sub": user_id})
        
        # Store refresh token
        token_data = {
            "user_id": user_id,
            "refresh_token": refresh_token,
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        }
        db.client.table("auth_tokens").insert(token_data).execute()
        
        # Remove sensitive data
        user.pop("password_hash", None)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Signup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: RelayDB = Depends(get_db)):
    """Login an existing user"""
    try:
        # Find user by email or username
        query = db.client.table("users").select("*")
        if request.email:
            result = query.eq("email", request.email).execute()
        else:
            result = query.eq("name", request.username).execute()
        if not result.data:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        user = result.data[0]
        
        # Verify password
        if not verify_password(request.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        user_id = user["id"]
        
        # Generate tokens
        access_token = create_access_token(data={"sub": user_id})
        refresh_token = create_refresh_token(data={"sub": user_id})
        
        # Store refresh token
        token_data = {
            "user_id": user_id,
            "refresh_token": refresh_token,
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        }
        db.client.table("auth_tokens").insert(token_data).execute()
        
        # Remove sensitive data
        user.pop("password_hash", None)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest, db: RelayDB = Depends(get_db)):
    """Refresh access token using refresh token"""
    try:
        # Verify refresh token
        payload = verify_token(request.refresh_token)
        
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Verify token exists in database
        token_result = db.client.table("auth_tokens").select("*").eq("refresh_token", request.refresh_token).execute()
        if not token_result.data:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        # Check expiration
        token_data = token_result.data[0]
        expires_raw = token_data["expires_at"]
        if isinstance(expires_raw, datetime):
            expires_at = expires_raw
        else:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))

        # Normalize to timezone-aware UTC for safe comparison.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) > expires_at:
            # Delete expired token
            db.client.table("auth_tokens").delete().eq("id", token_data["id"]).execute()
            raise HTTPException(status_code=401, detail="Refresh token expired")
        
        # Get user
        user_result = db.client.table("users").select("*").eq("id", user_id).execute()
        if not user_result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = user_result.data[0]
        
        # Generate new tokens
        access_token = create_access_token(data={"sub": user_id})
        new_refresh_token = create_refresh_token(data={"sub": user_id})
        
        # Update refresh token in database
        db.client.table("auth_tokens").update({
            "refresh_token": new_refresh_token,
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        }).eq("id", token_data["id"]).execute()
        
        # Remove sensitive data
        user.pop("password_hash", None)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            user=user
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Refresh error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout")
async def logout(request: RefreshRequest, db: RelayDB = Depends(get_db)):
    """Logout user by invalidating refresh token"""
    try:
        # Delete refresh token from database
        db.client.table("auth_tokens").delete().eq("refresh_token", request.refresh_token).execute()
        return {"message": "Logged out successfully"}
    except Exception as e:
        print(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me")
async def get_current_user(user_id: str = Depends(get_current_user_id), db: RelayDB = Depends(get_db)):
    """Get current authenticated user"""
    try:
        result = db.client.table("users").select("*").eq("id", user_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = result.data[0]
        user.pop("password_hash", None)
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Get user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/me")
async def update_current_user(
    name: Optional[str] = None,
    phone: Optional[str] = None,
    company: Optional[str] = None,
    calendly_api_key: Optional[str] = None,
    calendly_event_url: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    db: RelayDB = Depends(get_db)
):
    """Update current user profile"""
    try:
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if phone is not None:
            update_data["phone"] = phone
        if company is not None:
            update_data["company"] = company
        if calendly_api_key is not None:
            update_data["calendly_api_key"] = calendly_api_key
        if calendly_event_url is not None:
            update_data["calendly_event_url"] = calendly_event_url
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_data["updated_at"] = datetime.utcnow().isoformat()
        
        result = db.client.table("users").update(update_data).eq("id", user_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = result.data[0]
        user.pop("password_hash", None)
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Update user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
