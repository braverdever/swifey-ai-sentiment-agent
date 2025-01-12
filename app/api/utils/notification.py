import json
import httpx
from pathlib import Path
import google.auth.transport.requests
import google.oauth2.service_account

async def get_firebase_access_token() -> str:
    """Get Firebase access token using service account credentials."""
    try:
        # Get the path to serviceAccount.json
        service_account_path = Path(__file__).parent / "serviceAccount.json"
        
        # Load credentials from the service account file
        credentials = google.oauth2.service_account.Credentials.from_service_account_file(
            str(service_account_path),
            scopes=['https://www.googleapis.com/auth/firebase.messaging']
        )
        
        # Request a token
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        
        return credentials.token
        
    except Exception as e:
        print(f"Error getting Firebase access token: {str(e)}")
        raise

async def send_notification(token: str, title: str, body: str, data: dict = None) -> bool:
    """
    Send a push notification using Firebase Cloud Messaging.
    
    Args:
        token: The FCM token of the device
        title: Notification title
        body: Notification body
        data: Optional data payload
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get Firebase access token
        access_token = await get_firebase_access_token()
        
        # Prepare the message
        message = {
            "message": {
                "token": token,
                "notification": {
                    "title": title,
                    "body": body
                }
            }
        }
        
        # Add data payload if provided
        if data:
            message["message"]["data"] = data
            
        # Get project ID from service account file
        service_account_path = Path(__file__).parent / "serviceAccount.json"
        with open(service_account_path) as f:
            project_id = json.load(f)["project_id"]
        
        # Make the request to Firebase
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=message
            )
            
            if response.status_code != 200:
                print(f"Firebase notification error: {response.text}")
                return False
                
            return True
            
    except Exception as e:
        print(f"Error sending notification: {str(e)}")
        return False
