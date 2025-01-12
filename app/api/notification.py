from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from .utils.notification import send_notification
from typing import Optional
from ..db.supabase import get_supabase

router = APIRouter()

class SendNotificationRequest(BaseModel):
    user_id: str
    title: str
    body: str
    data: Optional[dict] = None

@router.post("/send")
async def send_user_notification(request: SendNotificationRequest):
    """
    Send a notification to a specific user.
    
    Args:
        user_id: The ID of the user to send notification to
        title: Notification title
        body: Notification body
        data: Optional data payload
    """
    try:
        # Get user's FCM token from Supabase
        supabase = get_supabase()
        response = supabase.from_("profiles").select("fcm_token").eq("id", request.user_id).execute()
        
        if not response.data or not response.data[0].get("fcm_token"):
            raise HTTPException(
                status_code=404,
                detail="FCM token not found for user"
            )
            
        fcm_token = response.data[0]["fcm_token"]
        
        # Send the notification
        success = await send_notification(
            token=fcm_token,
            title=request.title,
            body=request.body,
            data=request.data
        )
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to send notification"
            )
        
        return {
            "success": True,
            "message": "Notification sent successfully"
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error sending notification: {str(e)}"
        ) 