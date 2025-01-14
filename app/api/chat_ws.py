from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from typing import Dict, Set, Optional, List, Union
from pydantic import BaseModel
import json
from ..auth.middleware import verify_app_token
from ..db.supabase import get_supabase
from ..api.utils.notification import send_notification
from ..core.agent_system import AgentSystem
from ..models import api as models

router = APIRouter()

def get_agent_system() -> AgentSystem:
    """Dependency to get the agent system instance."""
    from ..config import settings
    
    try:
        agent = AgentSystem(
            redis_host=settings.REDIS_HOST,
            redis_port=settings.REDIS_PORT,
            cache_ttl=settings.REDIS_CACHE_TTL,
            flush_interval=settings.FLUSH_INTERVAL,
            buffer_size=settings.BUFFER_SIZE
        )
        return agent
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize agent system: {str(e)}"
        )

async def generate_truth_bomb(messages: List[dict], agent: AgentSystem) -> str:
    """Generate a truth bomb based on conversation analysis."""
    try:
        # Convert messages to the format expected by the agent
        formatted_messages = [
            models.Message(
                sender=msg.get("sender_id"),
                content=msg.get("content"),
                timestamp=msg.get("sent_at")
            ) for msg in messages
        ]
        
        analysis = agent.analyze_conversation(formatted_messages)
        truth_bomb = analysis.get("truth_bomb")
        
        if not truth_bomb or not isinstance(truth_bomb, str):
            truth_bomb = "How's the conversation going?"
            
        return truth_bomb
        
    except Exception as e:
        print(f"Error generating truth bomb: {e}")
        return "How's the conversation going?"

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
    type: str  # message, typing, truth_bomb_init, truth_bomb_approved
    conversation_id: Optional[str] = None  # receiver's user_id, optional for truth_bomb_approved
    content: Optional[str] = None
    message_type: Optional[str] = None  # text, image, etc.
    messages: Optional[List[dict]] = None  # For truth bomb init
    truth_bomb_id: Optional[Union[str, int]] = None  # For truth bomb approval, can be string or int

    def model_post_init(self, *args, **kwargs):
        super().model_post_init(*args, **kwargs)
        # Ensure conversation_id is present for message and truth_bomb_init types
        if self.type in ["message", "truth_bomb_init"] and not self.conversation_id:
            raise ValueError("conversation_id is required for message and truth_bomb_init types")
        # Convert truth_bomb_id to string if it's an integer
        if self.truth_bomb_id is not None:
            self.truth_bomb_id = str(self.truth_bomb_id)

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
                
                if chat_message.type == "truth_bomb_init":
                    try:
                        # Check for active truth bombs first
                        supabase = get_supabase()
                        user_ids = sorted([user_id, chat_message.conversation_id])
                        
                        # Query for active truth bombs between these users
                        active_bombs = supabase.from_("truth_bombs").select("*").eq("user_id1", user_ids[0]).eq("user_id2", user_ids[1]).eq("status", True).execute()
                        
                        if active_bombs.data and len(active_bombs.data) > 0:
                            # There is an active truth bomb, send message back to sender
                            await websocket.send_json({
                                "type": "error",
                                "message": "There is already an active truth bomb for this conversation"
                            })
                            return
                            
                        # Get agent system
                        agent = get_agent_system()
                        
                        # Generate truth bomb
                        truth_bomb_text = await generate_truth_bomb(chat_message.messages, agent)
                        
                        # Store in database with user IDs in ascending order
                        supabase = get_supabase()
                        user_ids = sorted([user_id, chat_message.conversation_id])
                        
                        result = supabase.from_("truth_bombs").insert({
                            "user_id1": user_ids[0],
                            "user_id2": user_ids[1],
                            "truth_bomb": truth_bomb_text,
                            "approve1": False,
                            "approve2": False,
                            "status": True  # Active truth bomb
                        }).execute()
                        
                        if not result.data:
                            raise Exception("Failed to store truth bomb")
                            
                        truth_bomb_id = result.data[0]["id"]
                        
                        # Send truth bomb init notification to both users
                        init_payload = {
                            "type": "truth_bomb_init",
                            "truth_bomb_id": truth_bomb_id
                        }
                        
                        # Send to both users
                        await manager.send_message(user_id, init_payload)
                        await manager.send_message(chat_message.conversation_id, init_payload)
                        
                    except Exception as e:
                        print(f"Failed to process truth bomb init: {str(e)}")
                        await websocket.send_json({
                            "type": "error",
                            "message": "Failed to generate truth bomb"
                        })
                        
                elif chat_message.type == "truth_bomb_approved":
                    try:
                        supabase = get_supabase()
                        
                        # Get the truth bomb
                        truth_bomb = supabase.from_("truth_bombs").select("*").eq("id", chat_message.truth_bomb_id).single().execute()
                        
                        if not truth_bomb.data:
                            raise Exception("Truth bomb not found")
                            
                        # Determine which approval to update based on user ID order
                        user_ids = sorted([truth_bomb.data["user_id1"], truth_bomb.data["user_id2"]])
                        is_user1 = user_id == user_ids[0]
                        
                        # Update the appropriate approval field
                        update_data = {"approve1": True} if is_user1 else {"approve2": True}
                        result = supabase.from_("truth_bombs").update(update_data).eq("id", chat_message.truth_bomb_id).execute()
                        
                        if not result.data:
                            raise Exception("Failed to update approval")
                            
                        # Check if both approved
                        updated_bomb = result.data[0]
                        if updated_bomb["approve1"] and updated_bomb["approve2"]:
                            # Send truth bomb to both users and mark as inactive
                            truth_bomb_payload = {
                                "type": "truth_bomb",
                                "content": updated_bomb["truth_bomb"]
                            }
                            
                            await manager.send_message(updated_bomb["user_id1"], truth_bomb_payload)
                            await manager.send_message(updated_bomb["user_id2"], truth_bomb_payload)
                            
                            # Mark truth bomb as inactive
                            supabase.from_("truth_bombs").update({"status": False}).eq("id", chat_message.truth_bomb_id).execute()
                            
                    except Exception as e:
                        print(f"Failed to process truth bomb approval: {str(e)}")
                        await websocket.send_json({
                            "type": "error",
                            "message": "Failed to process truth bomb approval"
                        })
                
                elif chat_message.type == "message":
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
                
        except WebSocketDisconnect:
            await manager.disconnect(user_id)
            
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
        await websocket.close() 