from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Request, HTTPException
from typing import Dict, List, Optional, Union
from datetime import datetime
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[Dict[str, any]]] = {}
        self.user_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        
        # Store connection with user info
        connection_info = {"socket": websocket, "user_id": user_id}
        self.active_connections[room_id].append(connection_info)
        
        # Track user's connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(websocket)
        
        logger.info(f"User {user_id} connected to room {room_id}. Total connections in room: {len(self.active_connections[room_id])}")

    def disconnect(self, websocket: WebSocket, room_id: str, user_id: str):
        if room_id in self.active_connections:
            # Remove from room connections
            self.active_connections[room_id] = [
                conn for conn in self.active_connections[room_id] 
                if conn["socket"] != websocket
            ]
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
            
            # Remove from user connections
            if user_id in self.user_connections:
                self.user_connections[user_id].remove(websocket)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
            
            logger.info(f"User {user_id} disconnected from room {room_id}")

    async def broadcast_to_room(self, message: str, room_id: str, exclude_user: Optional[str] = None):
        if room_id in self.active_connections:
            for conn in self.active_connections[room_id]:
                if exclude_user and conn["user_id"] == exclude_user:
                    continue
                try:
                    await conn["socket"].send_text(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to client: {e}")

    async def send_to_user(self, message: str, target_user_id: str):
        if target_user_id in self.user_connections:
            for websocket in self.user_connections[target_user_id]:
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    logger.error(f"Error sending message to user {target_user_id}: {e}")

    async def broadcast_to_all(self, message: Union[str, dict], exclude_users: Optional[List[str]] = None):
        """Send a message to all connected users across all rooms."""
        message_str = json.dumps(message) if isinstance(message, dict) else message
        sent_to = set()  # Track users we've sent to
        
        for room_connections in self.active_connections.values():
            for conn in room_connections:
                user_id = conn["user_id"]
                if user_id not in sent_to and (not exclude_users or user_id not in exclude_users):
                    try:
                        await conn["socket"].send_text(message_str)
                        sent_to.add(user_id)  # Mark this user as sent to
                    except Exception as e:
                        logger.error(f"Error broadcasting to user {user_id}: {e}")

    async def send_to_users(self, message: Union[str, dict], user_ids: List[str]):
        """Send a message to a specific list of users."""
        message_str = json.dumps(message) if isinstance(message, dict) else message
        successful_sends = []
        failed_sends = []

        for user_id in user_ids:
            try:
                if user_id in self.user_connections:
                    # Send to all connections of this user
                    for websocket in self.user_connections[user_id]:
                        await websocket.send_text(message_str)
                    successful_sends.append(user_id)
                else:
                    failed_sends.append(user_id)
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                failed_sends.append(user_id)

        return {
            "successful": successful_sends,
            "failed": failed_sends
        }

    async def send_message(self, message: Union[str, dict], target: Union[str, List[str], None] = None):
        """
        Universal helper function to send messages to different targets.
        
        Args:
            message: The message to send (string or dict that will be converted to JSON)
            target: The target(s) to send to:
                   - None: send to all users
                   - str: send to specific user
                   - List[str]: send to list of users
        
        Returns:
            dict: Information about the message delivery
        """
        message_str = json.dumps(message) if isinstance(message, dict) else message
        
        if target is None:
            # Broadcast to all users
            await self.broadcast_to_all(message_str)
            return {"type": "broadcast", "status": "completed"}
            
        elif isinstance(target, str):
            # Send to specific user
            await self.send_to_user(message_str, target)
            success = target in self.user_connections
            return {
                "type": "single_user",
                "target": target,
                "status": "delivered" if success else "failed"
            }
            
        elif isinstance(target, list):
            # Send to multiple users
            result = await self.send_to_users(message_str, target)
            return {
                "type": "multiple_users",
                "status": result
            }
        
        else:
            raise ValueError("Invalid target type. Must be None, str, or List[str]")

manager = ConnectionManager()

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    room_id: str,
    user_id: str = Query(..., description="ID of the connecting user")
):
    await manager.connect(websocket, room_id, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                # Parse the message as JSON
                message_data = json.loads(data)
                # Add a timestamp if not present
                if "timestamp" not in message_data:
                    message_data["timestamp"] = str(datetime.utcnow())
                
                # Handle direct messages if target_user_id is specified
                if "target_user_id" in message_data:
                    await manager.send_to_user(
                        json.dumps(message_data),
                        message_data["target_user_id"]
                    )
                else:
                    # Broadcast to room (optionally excluding sender)
                    exclude_self = message_data.get("exclude_self", False)
                    await manager.broadcast_to_room(
                        json.dumps(message_data),
                        room_id,
                        exclude_user=user_id if exclude_self else None
                    )
            except json.JSONDecodeError:
                # If not JSON, broadcast the raw message to room
                await manager.broadcast_to_room(data, room_id)
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id, user_id)
        await manager.broadcast_to_room(
            json.dumps({
                "type": "system",
                "content": f"User {user_id} has left the room",
                "timestamp": str(datetime.utcnow())
            }),
            room_id
        )
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, room_id, user_id) 