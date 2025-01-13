from fastapi import APIRouter, HTTPException, Request, Depends, File, UploadFile
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import date
from ..auth.middleware import verify_app_token
from ..db.supabase import get_supabase
import uuid
from fastapi import UploadFile, File
from typing import List
import uuid

router = APIRouter()

class Location(BaseModel):
    coords: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None
    accuracy: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = None
    photos: Optional[List[str]] = None
    date_of_birth: Optional[str] = None
    location: Optional[Location] = None
    gender_preference: Optional[List[str]] = None
    geographical_location: Optional[str] = None
    selfie_url: Optional[str] = None
    matching_prompt: Optional[str] = None
    fcm_token: Optional[str] = None
    agent_id: Optional[str] = None

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

class ProfileResponse(BaseModel):
    success: bool
    message: str
    user: UserProfile

class MatchedUserProfile(BaseModel):
    id: str
    name: str
    date_of_birth: Optional[str] = None
    photos: Optional[List[str]] = None
    bio: Optional[str] = None
    email: str
    gender: str
    gender_preference: List[str]
    location: Optional[Location] = None
    debug_info: Optional[str] = None
    selfie_url: Optional[str] = None

class MatchedProfileResponse(BaseModel):
    success: bool
    message: str
    profiles: List[MatchedUserProfile]
      
class SignedUrlRequest(BaseModel):
    count: int

class SignedUrlResponse(BaseModel):
    success: bool
    message: str
    urls: List[dict]

@router.put("/update")
async def update_user_profile(
    request: UpdateProfileRequest,
    user_id: str = Depends(verify_app_token)
):
    """
    Update user profile details.
    Requires a valid access token in Authorization header.
    """
    try:
        supabase = get_supabase()
        
        # Remove None values to only update provided fields
        update_data = request.model_dump(exclude_none=True)
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
            
        # Update the profile
        result = supabase.table("profiles").update(
            update_data
        ).eq("id", user_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")
            
        return {
            "success": True,
            "message": "Profile updated successfully",
            "profile": result.data[0]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@router.post("/new/photos")
async def upload_photos(
    files: List[UploadFile] = File(...),
    user_id: str = Depends(verify_app_token)
):
    """
    Upload photos to Supabase storage and return their IDs.
    Requires a valid access token in Authorization header.
    """
    try:
        supabase = get_supabase()
        uploaded_ids = []
        
        for file in files:
            # Generate unique ID for the file
            file_id = str(uuid.uuid4())
            file_path = f"{user_id}/{file_id}"
            
            # Read file content
            content = await file.read()
            
            # Upload to Supabase storage
            result = supabase.storage.from_("photos").upload(
                file_path,
                content,
                {"content-type": file.content_type}
            )
            
            uploaded_ids.append({
                "id": file_id,
                "path": file_path
            })
            
        return {
            "success": True,
            "message": f"Successfully uploaded {len(uploaded_ids)} photos",
            "photo_ids": uploaded_ids
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(request: Request, user_id: str = Depends(verify_app_token)):
    """
    Get the current user's profile using their access token.
    """
    try:
        supabase = get_supabase()
        response = supabase.from_("profiles").select("""
            *,
            profile_reviews(*),
            profile_reviews(*)
        """).eq("id", user_id).single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=404,
                detail="Profile not found"
            )
            
        return {
            "success": True,
            "message": "Profile fetched successfully", 
            "user": response.data
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching profile: {str(e)}"
        )
    
@router.get("/matched_profiles", response_model=MatchedProfileResponse)
async def get_matched_profiles(
    user_id: str = Depends(verify_app_token),
    limit: int = 20,
    offset: int = 0
):
    try: 
        supabase = get_supabase()
        response = supabase.rpc("get_matched_profiles", {
            "p_user_id": user_id,
            "p_limit": limit,
            "p_offset": offset
        }).execute()  

        if response is None:
            return {
                "success": True,
                "message": "No matched profiles found",
                "profiles": [] 
            }
        
        return {
            "success": True,
            "message": "Matched profiles fetched successfully",
            "profiles": response.data 
        }
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))
    

@router.post("/get-signed-urls", response_model=SignedUrlResponse)
async def get_signed_urls(
    request: SignedUrlRequest,
    user_id: str = Depends(verify_app_token)
):
    """
    Generate signed URLs for photo uploads.
    Requires a valid access token in Authorization header.
    """
    try:
        if request.count <= 0 or request.count > 6:
            raise HTTPException(
                status_code=400,
                detail="Count must be between 1 and 6"
            )

        supabase = get_supabase()
        signed_urls = []

        for _ in range(request.count):
            file_id = str(uuid.uuid4())
            file_path = f"{user_id}/{file_id}.jpg"
            
            # Get signed URL for upload
            signed_data = supabase.storage.from_("photos").create_signed_upload_url(
                file_path
            )
            
            # The response contains signed_url, token and path
            signed_urls.append({
                "id": file_id,
                "path": signed_data["path"],
                "signed_url": signed_data["signed_url"]
            })

        return {
            "success": True,
            "message": f"Generated {request.count} signed URLs",
            "urls": signed_urls
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        print("Error details:", e)  # Add debug print
        raise HTTPException(
            status_code=500,
            detail=f"Error generating signed URLs: {str(e)}"
        )
