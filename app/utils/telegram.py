import aiohttp
import logging
import json
from ..config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client

logger = logging.getLogger(__name__)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

async def update_profile_status(profile_id: str, status: str = "approved") -> bool:
    """
    Update the verification status of a profile in Supabase.
    """
    try:
        result = supabase.table('profiles').update(
            {"verification_status": status}
        ).eq('id', profile_id).execute()
        
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Error updating profile status: {e}")
        return False

async def send_to_telegram(message: str, photos_to_send: list = None, profile_id: str = None) -> bool:
    """
    Send a message and optional photos to the configured Telegram chat thread.
    
    Args:
        message: The text message to send
        photos_to_send: Optional list of photo URLs to send as a media group
        profile_id: Optional profile ID for approval button
        
    Returns:
        bool: True if successful, False otherwise
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    logger.info(f"Sending message to Telegram: {message[:100]}...")
    
    try:
        async with aiohttp.ClientSession() as session:
            channel_id, thread_id = TELEGRAM_CHAT_ID.split('/')
            channel_id = f"-100{channel_id}"
            
            # Create inline keyboard for approval if profile_id is provided
            payload = {
                "chat_id": channel_id,
                "message_thread_id": thread_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            if profile_id:
                # Ensure callback data is not too long (max 64 bytes)
                callback_data = json.dumps({
                    "a": "ap",  # shortened "action": "approve_profile"
                    "id": profile_id
                })
                if len(callback_data.encode('utf-8')) <= 64:
                    payload["reply_markup"] = {
                        "inline_keyboard": [[{
                            "text": "✅ Approve Profile",
                            "callback_data": callback_data
                        }]]
                    }
            
            async with session.post(url, json=payload) as response:
                response_data = await response.json()
                if response.status != 200:
                    logger.error(f"Failed to send text message. Status: {response.status}, Response: {response_data}")
                    return False
            
            # Send photos if any
            if photos_to_send:
                await send_photos_to_telegram(photos_to_send, channel_id, thread_id)
            
            return True
                    
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False

async def handle_callback_query(callback_query: dict) -> bool:
    """
    Handle callback queries from Telegram inline buttons.
    """
    try:
        data = json.loads(callback_query.get("data", "{}"))
        # Handle shortened callback data
        if data.get("a") == "ap":  # "action": "approve_profile"
            profile_id = data.get("id")
            if profile_id:
                # Update profile status
                success = await update_profile_status(profile_id)
                if success:
                    # Send confirmation message
                    message = f"✅ Profile {profile_id} has been approved!"
                    await send_to_telegram(message)
                    return True
        return False
    except Exception as e:
        logger.error(f"Error handling callback query: {e}")
        return False

def format_profile_update_message(profile_data: dict, old_profile_data: dict = None) -> tuple[str, list]:
    """
    Format profile data into a readable Telegram message and collect photos to send.
    
    Args:
        profile_data: The current profile data
        old_profile_data: The previous profile data (for updates)
        
    Returns:
        tuple: (formatted message, list of photo URLs to send)
    """
    STORAGE_URL_PREFIX = "https://exftzdxtyfbiwlpmecmd.supabase.co/storage/v1/object/public/photos/"
    
    def format_photo_urls(photos):
        if not photos:
            return []
        formatted_urls = []
        for photo in photos:
            if not photo.startswith(('http://', 'https://')):
                formatted_urls.append(f"{STORAGE_URL_PREFIX}{photo}")
            else:
                formatted_urls.append(photo)
        return formatted_urls

    action = "Updated" if old_profile_data else "New"
    photos_to_send = []
    
    message = [
        f"🔔 <b>{action} Profile</b>",
        f"Name: {profile_data.get('name', 'N/A')}",
        f"Gender: {profile_data.get('gender', 'N/A')}",
        f"Age: {profile_data.get('date_of_birth', 'N/A')}",
        f"Bio: {profile_data.get('bio', 'N/A')}",
        f"Verification Status: {profile_data.get('verification_status', 'N/A')}",
        f"Active: {'Yes' if profile_data.get('is_active') else 'No'}"
    ]
    
    # Handle photos for new profile or updates
    current_photos = format_photo_urls(profile_data.get('photos', []))
    if current_photos:
        message.append("\n<b>Photos:</b>")
        for url in current_photos:
            message.append(f"<a href='{url}'>🖼️ Photo</a>")
            if not old_profile_data:  # If new profile, send all photos
                photos_to_send.append(url)
    
    if old_profile_data:
        changes = []
        for key, new_value in profile_data.items():
            old_value = old_profile_data.get(key)
            if old_value != new_value:
                if key == 'photos':
                    old_photos = format_photo_urls(old_value or [])
                    new_photos = format_photo_urls(new_value or [])
                    
                    removed_photos = set(old_photos) - set(new_photos)
                    added_photos = set(new_photos) - set(old_photos)
                    
                    if removed_photos:
                        changes.append("\n<b>Removed Photos:</b>")
                        for url in removed_photos:
                            changes.append(f"<a href='{url}'>🖼️ Photo</a>")
                    
                    if added_photos:
                        changes.append("\n<b>Added Photos:</b>")
                        for url in added_photos:
                            changes.append(f"<a href='{url}'>🖼️ Photo</a>")
                            photos_to_send.append(url)
                else:
                    changes.append(f"• {key}: {old_value} ➜ {new_value}")
        
        if changes:
            message.append("\n<b>Changes:</b>")
            message.extend(changes)
    
    return "\n".join(message), photos_to_send 