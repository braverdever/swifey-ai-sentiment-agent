from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from typing import Dict, Set, Optional
from pydantic import BaseModel
import json
from ..auth.middleware import verify_app_token
from ..db.supabase import get_supabase
from ..api.utils.notification import send_notification

router = APIRouter()

# Store active connections
class ConnectionManager:
    def __init__(self):
        # Map of user_id to their WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}
        
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        print(f"User {user_id} connected. Total connections: {len(self.active_connections)}")
        
    async def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            print(f"User {user_id} disconnected. Total connections: {len(self.active_connections)}")
            
    async def send_message(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)
            return True
        return False

    def is_connected(self, user_id: str) -> bool:
        return user_id in self.active_connections

manager = ConnectionManager()

class ChatMessage(BaseModel):
    type: str  # message, typing, etc.
    conversation_id: str  # receiver's user_id
    content: Optional[str] = None
    message_type: Optional[str] = None  # text, image, etc.

@router.websocket("/chat")
async def chat_websocket(
    websocket: WebSocket,
    token: str
):
    try:
        # Create a Request-like object with headers
        mock_request = type('Request', (), {'headers': {'Authorization': f'Bearer {token}'}})()
        
        # Verify token and get user_id
        user_id = await verify_app_token(mock_request)
        
        await manager.connect(websocket, user_id)
        
        try:
            while True:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                print(f"Received message data: {message_data}")
                
                # Parse the message
                chat_message = ChatMessage(**message_data)
                
                if chat_message.type == "message":
                    try:
                        # Store message in database first
                        supabase = get_supabase()
                        message_data = {
                            "sender_id": user_id,
                            "recipient_id": chat_message.conversation_id,
                            "content": chat_message.content,
                            "message_type": chat_message.message_type or "text"
                        }
                        print(f"Storing message: {message_data}")
                        
                        result = supabase.from_("direct_messages").insert(message_data).execute()
                        print(f"Database response: {result.data}")
                        
                        if not result.data:
                            raise Exception("No data returned from message insert")
                            
                        stored_message = result.data[0]
                        print(f"Stored message: {stored_message}")
                        
                        # Create message payload
                        message_payload = {
                            "type": "message",
                            "sender_id": user_id,
                            "content": chat_message.content,
                            "message_type": chat_message.message_type or "text",
                            "conversation_id": chat_message.conversation_id,
                            "message_id": stored_message.get("id")
                        }
                        print(f"Created message payload: {message_payload}")
                        
                        # Send acknowledgment to sender
                        ack_payload = {
                            "type": "message_sent",
                            "status": "success",
                            "message_id": stored_message.get("id"),
                            "timestamp": stored_message.get("created_at")
                        }
                        print(f"Sending acknowledgment: {ack_payload}")
                        await websocket.send_json(ack_payload)
                        
                        # Try to send to receiver if connected
                        if manager.is_connected(chat_message.conversation_id):
                            print(f"Receiver {chat_message.conversation_id} is connected, sending message")
                            await manager.send_message(chat_message.conversation_id, message_payload)
                        else:
                            print(f"Receiver {chat_message.conversation_id} is not connected, trying FCM")
                            # Fallback to FCM notification if receiver not connected
                            try:
                                # Get receiver's FCM token from Supabase
                                receiver = supabase.from_("profiles").select("fcm_token").eq("id", chat_message.conversation_id).single().execute()
                                print(f"Receiver FCM data: {receiver.data}")
                                
                                # Only attempt to send notification if FCM token exists
                                if receiver.data and receiver.data.get("fcm_token"):
                                    notification_data = {
                                        "type": "chat_message",
                                        "sender_id": user_id,
                                        "conversation_id": chat_message.conversation_id,
                                        "message_id": stored_message.get("id")
                                    }
                                    print(f"Sending FCM notification: {notification_data}")
                                    await send_notification(
                                        token=receiver.data["fcm_token"],
                                        title="New Message",
                                        body=chat_message.content[:100],  # Truncate long messages
                                        data=notification_data
                                    )
                            except Exception as e:
                                # Log notification error but don't stop message processing
                                print(f"Failed to send notification: {str(e)}")
                                
                    except Exception as e:
                        print(f"Failed to process message: {str(e)}")
                        print(f"Error details: {type(e).__name__}, {str(e)}")
                        # Send error message back to sender
                        await websocket.send_json({
                            "type": "error",
                            "message": "Failed to process message"
                        })
                
                # Handle other message types here
                # elif chat_message.type == "typing":
                #     ...
                
        except WebSocketDisconnect:
            await manager.disconnect(user_id)
            
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
        await websocket.close() 