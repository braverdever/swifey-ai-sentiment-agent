from fastapi import APIRouter, Request, HTTPException, Depends
import logging
from ..utils.telegram import (
    send_to_telegram, 
    format_profile_update_message, 
    handle_callback_query,
    send_profile_to_telegram
)
from ..services.metrics import process_metrics_webhook
from ..config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

router = APIRouter()
logger = logging.getLogger(__name__)

# Store the metrics chat ID separately
METRICS_CHAT_ID = "2185680092/10120"

async def verify_telegram_token(request: Request):
    """Verify that the request is coming from Telegram."""
    auth = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not auth or auth != TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

@router.post("/profiles")
async def profile_webhook(request: Request):
    """
    Webhook endpoint for Supabase profile table events.
    This endpoint receives profile updates and sends notifications to Telegram.
    """
    try:
        payload = await request.json()
        print(payload)

        record = payload.get("record", {})
        event_type = payload.get("type")
        
        # Only process UPDATE events
        if event_type != "UPDATE":
            return {
                "status": "ignored",
                "message": f"Event type {event_type} not handled"
            }

        # Required fields to check
        required_fields = ["name", "bio", "photos", "matching_prompt", 
                          "gender", "gender_preference", "date_of_birth"]
        
        # Check if required fields exist and have valid values
        for field in required_fields:
            if field not in record or record[field] is None or record[field] == "" or record[field] == []:
                return {
                    "status": "ignored",
                    "message": f"Required field {field} is missing or empty"
                }
            
        # Check verification status - only proceed if initial_review
        if record.get("verification_status") != "initial_review":
            return {
                "status": "ignored", 
                "message": "Profile not in initial review status"
            }

        # Format message and get photos to send
        telegram_message, photos_to_send = format_profile_update_message(record)
        
        if not photos_to_send:
            # If no photos, use regular send_to_telegram
            success = await send_to_telegram(telegram_message, profile_id=record.get("id"))
        else:
            # Use specialized function for profile updates with photos
            success = await send_profile_to_telegram(telegram_message, photos_to_send, profile_id=record.get("id"))
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to send Telegram notification"
            )
        
        return {
            "status": "success",
            "message": "Profile notification sent to Telegram"
        }
        
    except Exception as e:
        logger.error(f"Error processing profile webhook: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process webhook: {str(e)}"
        )

@router.post("/telegram/callback", dependencies=[Depends(verify_telegram_token)])
async def telegram_callback(request: Request):
    """
    Webhook endpoint for Telegram callback queries.
    This endpoint handles button interactions from Telegram.
    """
    try:
        payload = await request.json()
        callback_query = payload.get("callback_query")
        
        if callback_query:
            success = await handle_callback_query(callback_query)
            return {
                "status": "success" if success else "error",
                "message": "Callback processed" if success else "Failed to process callback"
            }
            
        return {"status": "ignored", "message": "No callback query found"}
        
    except Exception as e:
        logger.error(f"Error processing Telegram callback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process callback: {str(e)}"
        )

@router.post("/metrics")
async def metrics_webhook(request: Request):
    """
    Webhook endpoint for daily metrics updates.
    This endpoint receives daily metrics and sends them to the metrics channel.
    """
    try:
        payload = await request.json()
        result = await process_metrics_webhook(payload, METRICS_CHAT_ID)
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
            
        return result
        
    except Exception as e:
        logger.error(f"Error processing metrics webhook: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process metrics: {str(e)}"
        ) 