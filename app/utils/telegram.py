import aiohttp
import logging
import json
from ..config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
from datetime import datetime

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

async def send_to_telegram(message: str, profile_id: str = None, chat_id: str = None) -> bool:
    """
    Send a simple text message to Telegram with optional approval button.
    
    Args:
        message: The text message to send
        profile_id: Optional profile ID for approval button
        chat_id: Optional specific chat ID to use instead of default
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        async with aiohttp.ClientSession() as session:
            target_chat_id = chat_id or TELEGRAM_CHAT_ID
            channel_id, thread_id = target_chat_id.split('/')
            channel_id = f"-100{channel_id}"
            
            # Create approval button if profile_id is provided
            reply_markup = None
            if profile_id:
                callback_data = json.dumps({
                    "a": "ap",
                    "id": profile_id
                })
                if len(callback_data.encode('utf-8')) <= 64:
                    reply_markup = {
                        "inline_keyboard": [[{
                            "text": "✅ Approve Profile",
                            "callback_data": callback_data
                        }]]
                    }

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": channel_id,
                "message_thread_id": thread_id,
                "text": message,
                "parse_mode": "HTML"
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Failed to send message. Status: {response.status}")
                    return False
                return True
                    
    except Exception as e:
        logger.error(f"Error sending to Telegram: {e}")
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

def format_profile_update_message(profile_data: dict) -> tuple[str, list]:
    """
    Format profile data into a readable Telegram message and collect photos to send.
    
    Args:
        profile_data: The current profile data
        
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

    def format_gender_preference(prefs):
        if not prefs:
            return "Not specified"
        return ", ".join(p.title() for p in prefs)
    
    def calculate_age(dob_str):
        try:
            if not dob_str:
                return "N/A"
                
            dob_date = datetime.strptime(dob_str, "%Y-%m-%d")
            today = datetime.now()
            
            # Calculate age
            age = today.year - dob_date.year
            
            # Check if birthday hasn't occurred this year
            m = today.month - dob_date.month
            if m < 0 or (m == 0 and today.day < dob_date.day):
                age -= 1
                
            if age < 0:
                return "N/A"
            
            return str(age)
        except Exception as e:
            logger.error(f"Error calculating age for date {dob_str}: {e}")
            return "N/A"

    photos_to_send = format_photo_urls(profile_data.get('photos', []))
    
    # Calculate age from date of birth
    age = calculate_age(profile_data.get('date_of_birth', ''))

    message = [
        f"👤 <b>Profile Completed</b>",
        f"\n<b>Basic Information:</b>",
        f"• Name: {profile_data.get('name', 'N/A')}",
        f"• Age: {age}",
        f"• Gender: {profile_data.get('gender', 'N/A').title()}",
        f"• Looking for: {format_gender_preference(profile_data.get('gender_preference'))}",
        f"\n<b>About:</b>",
        f"• Bio: {profile_data.get('bio', 'N/A')}",
        f"• Matching Prompt: {profile_data.get('matching_prompt', 'N/A')}",
        f"\n<b>Status:</b>",
        f"• Verification: {profile_data.get('verification_status', 'N/A').replace('_', ' ').title()}",
        f"• Active: {'Yes' if profile_data.get('is_active') else 'No'}"
    ]

    if photos_to_send:
        message.append(f"\n<b>Photos:</b> {len(photos_to_send)} attached")
    
    return "\n".join(message), photos_to_send

def format_daily_metrics_message(metrics_data: dict) -> str:
    """
    Format daily metrics data into a readable Telegram message.
    
    Args:
        metrics_data: The metrics data
        
    Returns:
        str: Formatted message
    """
    try:
        # Format date nicely
        date_str = metrics_data.get("date")
        if date_str:
            date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
        else:
            date = "Not specified"
        
        daily = metrics_data.get("daily_metrics", {})
        gender_stats = metrics_data.get("gender_stats", {})
        profiles_under_review = daily.get("profiles_under_review", {})
        
        message = [
            f"📊 <b>Daily Metrics Report</b> - {date}",
            "",
            "👥 <b>User Statistics:</b>",
            f"• Total Users: {metrics_data.get('total_users', 0):,}",
            f"• Verified Users: {metrics_data.get('total_verified_users', 0):,}",
            "",
            "⚡ <b>Daily Activity:</b>",
            f"• New Users: {daily.get('new_users', 0)}",
            f"• New Agents: {daily.get('new_agents', 0)}",
            f"• Profiles Approved: {daily.get('profiles_approved', 0)}",
            "",
            "🔍 <b>Profiles Under Review:</b>",
            f"• Initial Review: {profiles_under_review.get('initial_review', 0)}",
            f"• Pending: {profiles_under_review.get('pending', 0)}",
            "",
            "👤 <b>Gender Distribution:</b>"
        ]
        
        # Add gender distribution
        distribution = gender_stats.get("distribution", {})
        total = sum(distribution.values())
        if total > 0:
            for gender, count in distribution.items():
                percentage = (count / total) * 100
                message.append(f"• {gender.title()}: {count:,} ({percentage:.1f}%)")
        
        # Add gender ratio if available
        ratio = gender_stats.get("male_to_female_ratio")
        if ratio:
            message.append(f"\n👫 <b>Male to Female Ratio:</b> {ratio:.2f}")
        
        # Add generation timestamp
        generated_at = metrics_data.get("generated_at", "")
        if generated_at:
            try:
                dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                message.append(f"\n🕒 Generated at: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            except (ValueError, AttributeError):
                message.append(f"\n🕒 Generated at: {generated_at}")
        
        return "\n".join(message)
        
    except Exception as e:
        logger.error(f"Error formatting metrics message: {e}", exc_info=True)
        # Return a basic message if formatting fails
        return (
            "📊 <b>Daily Metrics Report</b>\n\n"
            f"Total Users: {metrics_data.get('total_users', 0):,}\n"
            f"Verified Users: {metrics_data.get('total_verified_users', 0):,}"
        )

async def send_photos_to_telegram(photo_urls: list, channel_id: str, thread_id: str) -> bool:
    """
    Send multiple photos as a media group to Telegram.
    
    Args:
        photo_urls: List of photo URLs to send
        channel_id: The channel ID
        thread_id: The thread ID
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not photo_urls:
        return True
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
    
    try:
        # Format photos into a media group
        media = [
            {
                "type": "photo",
                "media": photo_url
            } for photo_url in photo_urls
        ]
        
        async with aiohttp.ClientSession() as session:
            payload = {
                "chat_id": channel_id,
                "message_thread_id": thread_id,
                "media": media
            }
            
            async with session.post(url, json=payload) as response:
                response_data = await response.json()
                if response.status == 200:
                    logger.info(f"Successfully sent {len(photo_urls)} photos to Telegram thread")
                    return True
                else:
                    logger.error(f"Failed to send photos. Status: {response.status}, Response: {response_data}")
                    return False
    except Exception as e:
        logger.error(f"Error sending photos: {e}")
        return False 

async def send_profile_to_telegram(message: str, photos_to_send: list, profile_id: str = None, chat_id: str = None) -> bool:
    """
    Send profile update with photos, message, and approval button as a single media group message.
    
    Args:
        message: The profile update message
        photos_to_send: List of photo URLs to send
        profile_id: Optional profile ID for approval button
        chat_id: Optional specific chat ID to use instead of default
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"Preparing to send profile update to Telegram...")
    
    try:
        async with aiohttp.ClientSession() as session:
            target_chat_id = chat_id or TELEGRAM_CHAT_ID
            channel_id, thread_id = target_chat_id.split('/')
            channel_id = f"-100{channel_id}"
            
            # Create approval button
            reply_markup = None
            if profile_id:
                callback_data = json.dumps({
                    "a": "ap",
                    "id": profile_id
                })
                if len(callback_data.encode('utf-8')) <= 64:
                    reply_markup = {
                        "inline_keyboard": [[{
                            "text": "✅ Approve Profile",
                            "callback_data": callback_data
                        }]]
                    }

            # Create media group with all photos
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
            
            # First photo with caption and approval button
            media = [{
                "type": "photo",
                "media": photos_to_send[0],
                "caption": message,
                "parse_mode": "HTML",
                "reply_markup": reply_markup
            }]
            
            # Add remaining photos
            media.extend([{
                "type": "photo",
                "media": photo_url
            } for photo_url in photos_to_send[1:]])
            
            # Send everything in one request
            payload = {
                "chat_id": channel_id,
                "message_thread_id": thread_id,
                "media": media
            }

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Failed to send profile update. Status: {response.status}")
                    return False
                return True
                    
    except Exception as e:
        logger.error(f"Error sending profile update: {e}")
        return False 