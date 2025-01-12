from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, Set
import json
from datetime import datetime
from ..auth.middleware import verify_app_token

router = APIRouter()

class ChatConnectionManager:
    def __init__(self):
        # Store active chat connections: user_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        
    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)
        
    async def send_to_user(self, message: dict, target_user_id: str):
        """Send message to a specific user's all active connections"""
        if target_user_id in self.active_connections:
            for connection in self.active_connections[target_user_id]:
                await connection.send_json(message)

chat_manager = ChatConnectionManager()

async def get_token(websocket: WebSocket) -> str:
    """Extract and verify token from WebSocket query params"""
    try:
        token = websocket.query_params.get("token")
        if not token:
            raise HTTPException(status_code=401, detail="No token provided")
            
        # Verify token and get user_id
        user_id = await verify_app_token(type("Request", (), {"headers": {"Authorization": f"Bearer {token}"}})())
        return user_id
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.websocket("/chat/{conversation_id}")
async def chat_websocket_endpoint(websocket: WebSocket, conversation_id: str):
    """
    WebSocket endpoint for chat functionality.
    Requires token in query params for authentication.
    """
    try:
        # Authenticate user
        user_id = await get_token(websocket)
        
        # Accept connection and add to manager
        await chat_manager.connect(websocket, user_id)
        
        # Send connection confirmation
        await chat_manager.send_personal_message(
            {
                "type": "chat_connected",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            },
            websocket
        )
        
        try:
            while True:
                # Wait for messages
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Add metadata to message
                message.update({
                    "conversation_id": conversation_id,
                    "from_user_id": user_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                # Handle chat message
                if "to_user_id" in message:
                    # Send to specific user
                    await chat_manager.send_to_user(message, message["to_user_id"])
                    # Also send confirmation back to sender
                    await chat_manager.send_personal_message(
                        {
                            "type": "message_sent",
                            "message_id": message.get("message_id"),
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        websocket
                    )
                else:
                    await chat_manager.send_personal_message(
                        {
                            "type": "error",
                            "message": "Missing recipient (to_user_id)",
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        websocket
                    )
                    
        except WebSocketDisconnect:
            chat_manager.disconnect(websocket, user_id)
            
    except HTTPException as e:
        await websocket.close(code=1008, reason=str(e.detail))
    except Exception as e:
        await websocket.close(code=1011, reason=str(e)) 