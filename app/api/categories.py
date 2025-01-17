from fastapi import APIRouter, HTTPException, Request, Depends, File, UploadFile
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
from ..auth.middleware import verify_app_token
from ..db.supabase import get_supabase
import uuid
from fastapi import UploadFile, File
from typing import List
import uuid
import asyncio


router = APIRouter()

class SwifeyOTD(BaseModel):
    gender_preference: str

class Location(BaseModel):
    coords: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None
    accuracy: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class UserProfile(BaseModel):
    id: str
    name: Optional[str] = None
    bio: Optional[str] = None
    photos: Optional[List[str]] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    location: Optional[Location] = None
    gender_preference: Optional[List[str]] = None
    geographical_location: Optional[str] = None
    selfie_url: Optional[str] = None
    matching_prompt: Optional[str] = None
    fcm_token: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_active: Optional[bool] = None
    verification_status: Optional[str] = None
    agent_id: Optional[str] = None
    profile_reviews: Optional[List[Dict[str, Any]]] = None

class NearbyProfilesResponse(BaseModel):
    success: bool
    message: str
    profiles: List[UserProfile]

@router.get("/nearby", response_model=NearbyProfilesResponse)
async def get_nearby_profiles(
    user_id: str = Depends(verify_app_token),
    radius_km: float = 50,
    limit: int = 20
):
    """
    Get nearby profiles within specified radius (default 50km).
    Returns up to 20 profiles by default, sorted by distance.
    """
    try:
        supabase = get_supabase()
        
        # First get the user's location
        user_location = supabase.from_("profiles") \
            .select("geographical_location") \
            .eq("id", user_id) \
            .single() \
            .execute()

        if not user_location.data or not user_location.data.get("geographical_location"):
            raise HTTPException(
                status_code=400,
                detail="User location not found"
            )

        nearby_profiles = supabase.rpc(
            "get_nearby_profiles",
            {
                "user_location": user_location.data["geographical_location"],
                "search_radius_km": radius_km,
                "p_limit": limit,
                "p_user_id": user_id
            }
        ).execute()
        
        return {
            "success": True,
            "message": "Nearby profiles fetched successfully",
            "profiles": nearby_profiles.data or []
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching nearby profiles: {str(e)}"
        )


@router.post("/swifey_otd" )
async def get_swifey_otd(
    request: SwifeyOTD,
    user_id: str = Depends(verify_app_token),
):
    """
        get the swifey of the day for the user
    """
    try:
        supabase = get_supabase()
        
        print(user_id)
        # First get the user's location
        swifey_otp = supabase.from_("swifey_otd") \
            .select(f"{request.gender_preference}, profiles!swifey_otd_{request.gender_preference}_fkey(*)") \
            .order("created_at", desc=True) \
            .limit(1) \
            .single() \
            .execute()

        return {
            "success": True,
            "message": "swifey of the day fetched successfully",
            "profile": swifey_otp.data or {}
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        print("Error details:", e)  # Add debug print
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching swifey of the day: {str(e)}"
        )


