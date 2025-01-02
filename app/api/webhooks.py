from fastapi import APIRouter, Request, HTTPException, Depends
from datetime import datetime
import json
import logging
from ..utils.telegram import send_to_telegram, format_profile_update_message, handle_callback_query
from ..config.settings import TELEGRAM_BOT_TOKEN

router = APIRouter()
logger = logging.getLogger(__name__)

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
        old_record = payload.get("old_record")
        event_type = payload.get("type")
        
        # Format message and get photos to send
        telegram_message, photos_to_send = format_profile_update_message(record, old_record)
        
        # Show approval button only for:
        # 1. New profiles (INSERT)
        # 2. When verification_status changes to initial_review or pending
        show_approval = False
        if event_type == "INSERT":
            show_approval = True
        elif event_type == "UPDATE" and old_record:
            old_status = old_record.get("verification_status")
            new_status = record.get("verification_status")
            if new_status in ["initial_review", "pending"] and old_status != new_status:
                show_approval = True
        
        if show_approval:
            await send_to_telegram(telegram_message, photos_to_send, profile_id=record.get("id"))
        else:
            await send_to_telegram(telegram_message, photos_to_send)
        
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