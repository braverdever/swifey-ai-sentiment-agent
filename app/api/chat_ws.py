from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from typing import Dict, Set, Optional, List, Union
from pydantic import BaseModel
import json
import hashlib
from ..auth.middleware import verify_app_token
from ..db.supabase import get_supabase
from ..api.utils.notification import send_notification
from ..core.agent_system import AgentSystem
from ..models import api as models

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

class ConversationData:
    def __init__(self, interaction_freq: int, agent_id: str, initiator_id: str):
        self.interaction_freq = interaction_freq
        self.agent_id = agent_id
        self.initiator_id = initiator_id
        self.current_count = 0


conversation_count: Dict[str, ConversationData] = {}

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

async def analyse_and_generate_truth_bomb(messages: List[dict], agent: AgentSystem) -> str:
    """Generate a truth bomb based on conversation analysis."""
    try:
        # Convert messages to the format expected by the agent
        formatted_messages = [
            models.Message(
                sender=msg.get("sender"),
                content=msg.get("content"),
                timestamp=msg.get("timestamp")
            ) for msg in messages
        ]

        analysis = agent.analyze_conversation(formatted_messages)
        print("Analysis:", analysis)
        truth_bomb = analysis.get("truth_bomb")
        print("Truth bomb:", truth_bomb)

        if not truth_bomb or not isinstance(truth_bomb, str):
            truth_bomb = "How's the conversation going?"

        return truth_bomb

    except Exception as e:
        print(f"Error generating truth bomb: {e}")
        return "How's the conversation going?"

def get_hash(user_id1: str, user_id2: str) -> str:
    sorted_ids = sorted([user_id1, user_id2])

    merged_string = str(sorted_ids[0]) + str(sorted_ids[1])
    return hashlib.sha256(merged_string.encode()).hexdigest()

async def generate_truth_bomb_and_send(user_id1: str, user_id2: str, interaction_freq: int) :
    print(f"generating truth bomb for {user_id1} and {user_id2}")
    try:
        # Check for active truth bombs first
        supabase = get_supabase()
        user_ids = sorted([user_id1, user_id2])

        # Query for active truth bombs between these users
        active_bombs = supabase.from_("truth_bombs").select("*").eq("user_id1", user_ids[0]).eq("user_id2", user_ids[1]).eq("status", True).execute()

        if active_bombs.data and len(active_bombs.data) > 0:
            return

        # Get agent system
        agent = get_agent_system()

        # Generate truth bomb
        # response = supabase.rpc("get_direct_messages", { 'user1_uuid': user_ids[0], 'user2_uuid': user_ids[1], 'page_size': interaction_freq }).execute()

        dummy_data = [ {
            "content": "Hey, I saw your hiking photos! That trail looks stunning—where is it?",
            "sender": "Alex",
            "timestamp": "2024-12-30T08:00:00Z",
            "metadata": {}
        },
        {
            "content": "Thanks! It’s called Eagle Ridge Trail, about an hour from here. The views at the top are absolutely worth the climb!",
            "sender": "Jordan",
            "timestamp": "2024-12-30T08:15:00Z",
            "metadata": {}
        },
        {
            "content": "It sounds amazing. I love trails with rewarding views like that. Is it beginner-friendly or more challenging?",
            "sender": "Alex",
            "timestamp": "2024-12-30T08:20:00Z",
            "metadata": {}
        } ]
        truth_bomb_text = await analyse_and_generate_truth_bomb( dummy_data, agent)

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
        await manager.send_message(user_id1, init_payload)
        await manager.send_message(user_id2, init_payload)

    except Exception as e:
        print(f"Failed to process truth bomb init: {str(e)}")
        await websocket.send_json({
            "type": "error",
            "message": "Failed to generate truth bomb"
        })

    pass

def initialise_conversation_count(user_id1: str, user_id2: str):
    hash = get_hash(user_id1, user_id2)
    supabase = get_supabase()
    result = supabase.rpc("get_initiator_and_agent_info", { 'user_id1': user_id1, 'user_id2': user_id2 }).execute()
    if not result.data[0]:
        return
    initiator = result.data[0]['initiator']
    agent = result.data[0]['agent_id']
    interaction_freq = result.data[0]['interaction_freq']
    if not initiator:
        return
    elif not agent:
        conversation_count[hash] = ConversationData( -1, '', initiator)
    conversation_count[hash] = ConversationData(interaction_freq, agent, initiator)

async def increase_count(user_id1: str, user_id2: str):
    print(f"increasing count {user_id1} and {user_id2}")
    hash = get_hash(user_id1, user_id2)
    if hash in conversation_count:
        print("old only object")
        print(conversation_count[hash].current_count)
        print(conversation_count[hash].agent_id)
        print(conversation_count[hash].interaction_freq)
        if conversation_count[hash].interaction_freq == -1 or conversation_count[hash].interaction_freq == None:
            conversation_count[hash].current_count += 1
            # if conversation_count[hash].current_count >= 50:
                # give a chance to the no agent users after 50 interactions to re initialize the conversation
                # initialise_conversation_count(user_id1, user_id2)
            print("conversation does not have an agent ")
            return
        try:
            print("current count" , conversation_count[hash].current_count)
            print("interaction freq" , conversation_count[hash].interaction_freq)
            conversation_count[hash].current_count += 1
            if conversation_count[hash].current_count >= conversation_count[hash].interaction_freq:
                await generate_truth_bomb_and_send(user_id1, user_id2, conversation_count[hash].interaction_freq)
                conversation_count[hash].current_count = 0
                return
        except Exception as e:
            print(e)
    else:
        print("new people intiating conversation....")
        try:
            initialise_conversation_count(user_id1, user_id2)
            print("object in else block" , conversation_count)
            conversation_count[hash].current_count += 1
            return 
        except Exception as e:
            print(e)

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
                
                # Parse the message
                chat_message = ChatMessage(**message_data)
                
                if chat_message.type == "truth_bomb_approved":
                    try:
                        supabase = get_supabase()
                        
                        # get the truth bomb
                        truth_bomb = supabase.from_("truth_bombs").select("*").eq("id", chat_message.truth_bomb_id).single().execute()
                        
                        if not truth_bomb.data:
                            raise exception("truth bomb not found")
                            
                        # determine which approval to update based on user id order
                        user_ids = sorted([truth_bomb.data["user_id1"], truth_bomb.data["user_id2"]])
                        is_user1 = user_id == user_ids[0]
                        
                        # update the appropriate approval field
                        update_data = {"approve1": True} if is_user1 else {"approve2": True}
                        result = supabase.from_("truth_bombs").update(update_data).eq("id", chat_message.truth_bomb_id).execute()
                        
                        if not result.data:
                            raise exception("failed to update approval")
                            
                        # check if both approved
                        updated_bomb = result.data[0]
                        if updated_bomb["approve1"] and updated_bomb["approve2"]:
                            # send truth bomb to both users and mark as inactive
                            truth_bomb_payload = {
                                "type": "truth_bomb",
                                "content": updated_bomb["truth_bomb"]
                            }
                            
                            await manager.send_message(updated_bomb["user_id1"], truth_bomb_payload)
                            await manager.send_message(updated_bomb["user_id2"], truth_bomb_payload)
                            
                            # mark truth bomb as inactive
                            supabase.from_("truth_bombs").update({"status": false}).eq("id", chat_message.truth_bomb_id).execute()
                            
                    except exception as e:
                        print(f"failed to process truth bomb approval: {str(e)}")
                        await websocket.send_json({
                            "type": "error",
                            "message": "failed to process truth bomb approval"
                        })
                
                elif chat_message.type == "message":
                    try:
                        # store message in database first
                        supabase = get_supabase()
                        message_data = {
                            "sender_id": user_id,
                            "recipient_id": chat_message.conversation_id,
                            "content": chat_message.content,
                            "message_type": chat_message.message_type or "text"
                        }
                        
                        result = supabase.from_("direct_messages").insert(message_data).execute()
                        
                        if not result.data:
                            raise exception("no data returned from message insert")
                            
                        await increase_count(user_id, chat_message.conversation_id)
                        
                        stored_message = result.data[0]
                        
                        # create message payload
                        message_payload = {
                            "type": "message",
                            "sender_id": user_id,
                            "content": chat_message.content,
                            "message_type": chat_message.message_type or "text",
                            "conversation_id": chat_message.conversation_id,
                            "message_id": stored_message.get("id")
                        }
                        
                        # send acknowledgment to sender
                        ack_payload = {
                            "type": "message_sent",
                            "status": "success",
                            "message_id": stored_message.get("id"),
                            "timestamp": stored_message.get("created_at")
                        }
                        await websocket.send_json(ack_payload)
                        
                        # try to send to receiver if connected
                        if manager.is_connected(chat_message.conversation_id):
                            await manager.send_message(chat_message.conversation_id, message_payload)
                        else:
                            # fallback to fcm notification if receiver not connected
                            try:
                                # get receiver's fcm token from supabase
                                receiver = supabase.from_("profiles").select("fcm_token").eq("id", chat_message.conversation_id).single().execute()
                                
                                # only attempt to send notification if fcm token exists
                                if receiver.data and receiver.data.get("fcm_token"):
                                    notification_data = {
                                        "type": "chat_message",
                                        "sender_id": user_id,
                                        "conversation_id": chat_message.conversation_id,
                                        "message_id": stored_message.get("id")
                                    }
                                    await send_notification(
                                        token=receiver.data["fcm_token"],
                                        title="new message",
                                        body=chat_message.content[:100],  # truncate long messages
                                        data=notification_data
                                    )
                            except Exception as e:
                                # log notification error but don't stop message processing
                                print(f"failed to send notification: {str(e)}")
                                
                            # increase the message count for the conversation for truth bomb
                    except Exception as e:
                        print(f"failed to process message: {str(e)}")
                        print(f"error details: {type(e).__name__}, {str(e)}")
                        # send error message back to sender
                        await websocket.send_json({
                            "type": "error",
                            "message": "failed to process message"
                        })
                
        except WebSocketDisconnect:
            await manager.disconnect(user_id)
            
    except Exception as e:
        print(f"websocket error: {str(e)}")
        await websocket.close() 



