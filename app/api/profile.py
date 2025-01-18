from fastapi import APIRouter, HTTPException, Request, Depends, File, UploadFile
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import date
from ..auth.middleware import verify_app_token
from ..db.supabase import get_supabase
from .utils.cache import get_user_by_id, update_user_cache, invalidate_user_cache
import uuid
from fastapi import UploadFile, File
from typing import List
import uuid
import asyncio


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
    profile_reviews: Optional[List[Dict[str, Any]]] = None

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

class ProfileCountResponse(BaseModel):
    success: bool
    message: str
    count: int

class WeMet(BaseModel):
    user_1: str
    user_2: str
    we_met_on_this_day: Optional[str] = None

class InviteCode(BaseModel):
    code: str
    profile_id: str
    status: Optional[str] = "active"

class UserInvitation(BaseModel):
    invite_code: str
    invited_user_id: str

class UserReport(BaseModel):
    report_user_id: str
    report_reason: str
    profile_id: str

class VerifyInviteCode(BaseModel):
    code: str

class CreateInvitation(BaseModel):
    inviter_code: str
    invited_user_id: str

class GetInviteCodesRequest(BaseModel):
    user_id: str

class EmailCheckRequest(BaseModel):
    email: EmailStr


@router.get("/count", response_model=ProfileCountResponse)
async def get_profile_count():
    """
    Get total number of approved profiles in the app.
    """
    try:
        supabase = get_supabase()
        
        # Query profiles table for approved profiles
        response = supabase.from_("profiles").select("id", count="exact").eq("verification_status", "approved").execute()

        count = response.count if response.count is not None else 0

        return {
            "success": True,
            "message": "Profile count fetched successfully",
            "count": count
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/update")
async def update_user_profile(
    request: UpdateProfileRequest,
    user_id: str = Depends(verify_app_token)
):
    """
    Update user profile details.
    For name, bio, and photos:
    - If they were previously null/empty, update directly
    - If they already had values, create review entries
    Other fields are updated directly.
    """
    try:
        supabase = get_supabase()
        
        # Remove None values to only update provided fields
        update_data = request.model_dump(exclude_none=True)
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Get current profile data
        current_profile = await get_user_by_id(user_id)
        
        if not current_profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        # Fields that need review after initial setup
        review_fields = {"name", "bio", "photos"}
        direct_update_data = {}
        review_entries = []

        for field, new_value in update_data.items():
            if field in review_fields:
                current_value = current_profile.get(field)
                
                # If current value is None/empty, update directly
                if current_value is None or current_value == "" or (isinstance(current_value, list) and len(current_value) == 0):
                    direct_update_data[field] = new_value
                else:
                    # Create review entry
                    review_entries.append({
                        "id": str(uuid.uuid4()),
                        "profile_id": user_id,
                        "attribute": field,
                        "current_value": str(current_value),
                        "proposed_value": str(new_value),
                        "review_status": "pending",
                        "created_at": "now()",
                    })
            else:
                # Other fields update directly
                direct_update_data[field] = new_value

        # Perform direct updates if any
        if direct_update_data:
            result = supabase.table("profiles").update(
                direct_update_data
            ).eq("id", user_id).execute()

            if result.data:
                # Invalidate the old cache
                invalidate_user_cache(user_id)
                # Update cache with new data
                await update_user_cache(user_id, result.data[0])

        # Create review entries if any
        if review_entries:
            supabase.table("profile_reviews").insert(review_entries).execute()

        # Get updated profile with reviews
        updated_profile = await get_user_by_id(user_id)
        reviews_response = supabase.from_("profile_reviews").select("*").eq("profile_id", user_id).execute()
        updated_profile["profile_reviews"] = reviews_response.data
            
        return {
            "success": True,
            "message": "Profile update processed successfully",
            "profile": updated_profile
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/me" )
async def get_my_profile(request: Request, user_id: str = Depends(verify_app_token)):
    """
    Get the current user's profile using their access token.
    """
    try:
        # First try to get from cache
        print("user_id", user_id)
        profile_data = await get_user_by_id(user_id)
        print("profile_data", profile_data)
        
        if not profile_data:
            raise HTTPException(
                status_code=404,
                detail="Profile not found"
            )

        # Get reviews separately since they're not cached
        supabase = get_supabase()
        reviews_response = supabase.from_("profile_reviews").select("*").eq("profile_id", user_id).execute()
        
        # Add reviews data to profile
        profile_data["profile_reviews"] = reviews_response.data
            
        return {
            "success": True,
            "message": "Profile fetched successfully",
            "user": profile_data
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        print(e)
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

@router.get("/get-approved-profiles-count")
async def get_approved_profiles_count(user_id: str = Depends(verify_app_token)):
    try:
        supabase = get_supabase()
        response = supabase.from_("profiles").select("*").eq("verification_status", "approved").execute()
        
        return {
            "success": True,
            "count": len(response.data) if response.data is not None else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/we-met", response_model=dict)
async def record_we_met(
    request: WeMet
):
    """
    Record when two users meet in person.
    request.user_1 is the first user and request.user_2 is the second user.
    """
    try:
        supabase = get_supabase()
        
        we_met_data = {
            "user_1": request.user_1,
            "user_2": request.user_2,
            "created_at": "now()"  
        }

        response = supabase.table("we_met").insert(we_met_data).execute()

        return {
            "success": True,
            "message": "Meeting recorded successfully",
            "data": response.data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error recording meeting: {str(e)}"
        )

@router.post("/invite-code", response_model=dict)
async def create_invite_code(
    request: InviteCode,
):
    """
    Create and store an invite code for a user.
    The code is automatically generated and associated with the user's profile.
    """
    try:
        supabase = get_supabase()
        
        
        invite_data = {
            "code": request.code,
            "profile_id": request.profile_id,
            "status": "active"
        }

        response = supabase.table("invite_codes").insert(invite_data).execute()

        return {
            "success": True,
            "message": "Invite code created successfully",
            "data": response.data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating invite code: {str(e)}"
        )

@router.post("/verify-invite-code", response_model=dict)
async def verify_invite_code(
    request: VerifyInviteCode
):
    """
    Verify if an invite code is valid and active.
    Returns the associated profile_id if valid.
    """
    try:
        supabase = get_supabase()
        
        invite_code_response = supabase.table("invite_codes") \
            .select("profile_id") \
            .eq("code", request.code) \
            .eq("status", "active") \
            .single() \
            .execute()

        if not invite_code_response.data:
            raise HTTPException(
                status_code=404,
                detail="Invalid or inactive invite code"
            )

        return {
            "success": True,
            "message": "Valid invite code",
            "inviter_user_id": invite_code_response.data['profile_id']
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error verifying invite code: {str(e)}"
        )

@router.post("/create-invitation", response_model=dict)
async def create_invitation(
    invitation: CreateInvitation
):
    """
    Create a record of a user inviting another user.
    Stores the invitation details in the user_invitations table.
    """
    try:
        supabase = get_supabase()
        
        invitation_data = {
            "inviter_code": invitation.inviter_code,
            "invited_user_id": invitation.invited_user_id,
            "created_at": "now()",
            "updated_at": "now()"
        }

        response = supabase.table("user_invitations").insert(invitation_data).execute()

        return {
            "success": True,
            "message": "User invitation created successfully",
            "data": response.data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating invitation: {str(e)}"
        )

@router.post("/report", response_model=dict)
async def report_user(
    report: UserReport,
):
    """
    Create a report for a user.
    The authenticated user (profile_id) reports another user (report_user_id) with a reason.
    """
    try:
        supabase = get_supabase()
        
        report_data = {
            "profile_id": report.profile_id,  
            "report_user_id": report.report_user_id,  
            "report_reason": report.report_reason,
            "created_at": "now()"
        }

        response = supabase.table("reports").insert(report_data).execute()

        return {
            "success": True,
            "message": "Report submitted successfully",
            "data": response.data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error submitting report: {str(e)}"
        )

@router.post("/invite-codes", response_model=dict)
async def get_invite_codes(
    request: GetInviteCodesRequest
):
    """
    Fetch all invite codes associated with a profile ID.
    Returns both active and used codes with their status.
    """
    try:
        supabase = get_supabase()
        
        if request.user_id is None or request.user_id.strip() == "":
            raise HTTPException(
                status_code=400,
                detail="user_id is required"
            )
        
        response = supabase.table("invite_codes") \
            .select("code, status, created_at") \
            .eq("profile_id", request.user_id) \
            .order("created_at", desc=True) \
            .execute()

        if not response.data:
            return {
                "success": True,
                "message": "No invite codes found",
                "data": []
            }

        return {
            "success": True,
            "message": "Invite codes fetched successfully",
            "data": response.data
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching invite codes: {str(e)}"
        )

@router.post("/check-email", response_model=dict)
async def check_email_exists(
    request: EmailCheckRequest
):
    """
    Check if an email exists in the profiles table.
    """
    try:
        supabase = get_supabase()
        
        response = supabase.table("profiles") \
            .select("id") \
            .eq("email", request.email) \
            .execute()

        exists = len(response.data) > 0

        return {
            "success": True,
            "exists": exists,
            "message": "Email already exists" if exists else "Email is available"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error checking email: {str(e)}"
        )

