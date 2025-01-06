import logging
from ..utils.twitter import get_twitter_followers
from ..utils.telegram import send_to_telegram, format_daily_metrics_message

logger = logging.getLogger(__name__)

async def process_metrics_webhook(payload: dict, metrics_chat_id: str) -> dict:
    """
    Process metrics webhook payload and send to Telegram
    """
    try:
        logger.info("Processing metrics webhook payload")
        
        # Handle Supabase event format
        if payload.get("type") != "INSERT":
            logger.info("Ignoring non-INSERT event")
            return {
                "status": "ignored",
                "message": "Not an insert event"
            }
        
        # Get metrics from the record's metrics field
        record = payload.get("record", {})
        metrics_data = record.get("metrics", {})
        if not metrics_data:
            logger.error("No metrics data found in payload")
            return {
                "status": "error",
                "message": "No metrics data found"
            }
        
        # Get Twitter followers count
        # twitter_followers = await get_twitter_followers()
        # if twitter_followers is not None:
        #     metrics_data['twitter_followers'] = twitter_followers
        
        # logger.info(f"Processing metrics data for date: {metrics_data.get('date')}")
        
        # Format the metrics message
        message = format_daily_metrics_message(metrics_data)
        logger.info("Formatted metrics message")
        
        # Send to the metrics channel
        logger.info(f"Sending to metrics channel: {metrics_chat_id}")
        success = await send_to_telegram(message, chat_id=metrics_chat_id)
        
        if not success:
            return {
                "status": "error",
                "message": "Failed to send message to Telegram"
            }
        
        logger.info("Successfully sent metrics to Telegram")
        return {
            "status": "success",
            "message": "Metrics sent to Telegram"
        }
        
    except Exception as e:
        logger.error(f"Error processing metrics webhook: {e}")
        raise 