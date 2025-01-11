from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date
from ..auth.middleware import verify_app_token
from ..db.supabase import get_supabase

router = APIRouter()

class Location(BaseModel):
    # Add location fields based on jsonb structure
    latitude: float
    longitude: float
    city: Optional[str] = None
    country: Optional[str] = None

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    location: Optional[Location] = None
    gender_preference: Optional[str] = None
    geographical_location: Optional[dict] = None
    selfie_url: Optional[str] = None
    matching_prompt: Optional[str] = None
    fcm_token: Optional[str] = None

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
    
from fastapi import UploadFile, File
from typing import List
import uuid

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


# TODO: complete these
@router.put("/name")
async def update_user_name(
    request: UpdateProfileRequest,
    user_id: str = Depends(verify_app_token)
):
    pass

async def update_user_dob(
    request: UpdateProfileRequest,
    user_id: str = Depends(verify_app_token)
):
    pass

async def update_user_photos(
    request: UpdateProfileRequest,
    user_id: str = Depends(verify_app_token)
):
    pass

async def update_user_gender(
    request: UpdateProfileRequest,
    user_id: str = Depends(verify_app_token)
):
    pass

async def update_user_gender_preference(
    request: UpdateProfileRequest,
    user_id: str = Depends(verify_app_token)
):
    pass
async def update_user_prompts(
    request: UpdateProfileRequest,
    user_id: str = Depends(verify_app_token)
):
    pass