"""
WebSocket Manager for real-time communication
"""
import asyncio
import json
import logging
from typing import Dict, Set, Any
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime


class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.logger = logging.getLogger("websocket")
        
        # Store active connections by task_id
        self.task_connections: Dict[str, Set[WebSocket]] = {}
        
        # Store all active connections
        self.active_connections: Set[WebSocket] = set()
        
        # Connection metadata
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket, task_id: str = None):
        """Accept a new WebSocket connection"""
        
        await websocket.accept()
        
        # Add to active connections
        self.active_connections.add(websocket)
        
        # Store connection metadata
        self.connection_metadata[websocket] = {
            "connected_at": datetime.now(),
            "task_id": task_id,
            "last_ping": datetime.now()
        }
        
        # Add to task-specific connections if task_id provided
        if task_id:
            if task_id not in self.task_connections:
                self.task_connections[task_id] = set()
            self.task_connections[task_id].add(websocket)
        
        self.logger.info(f"WebSocket connected. Task: {task_id}, Total connections: {len(self.active_connections)}")
        
        # Send connection confirmation
        await self._send_to_websocket(websocket, {
            "type": "connection_established",
            "task_id": task_id,
            "timestamp": datetime.now().isoformat()
        })
    
    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection"""
        
        # Remove from active connections
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        
        # Get connection metadata
        metadata = self.connection_metadata.get(websocket, {})
        task_id = metadata.get("task_id")
        
        # Remove from task-specific connections
        if task_id and task_id in self.task_connections:
            self.task_connections[task_id].discard(websocket)
            
            # Clean up empty task connection sets
            if not self.task_connections[task_id]:
                del self.task_connections[task_id]
        
        # Remove metadata
        if websocket in self.connection_metadata:
            del self.connection_metadata[websocket]
        
        self.logger.info(f"WebSocket disconnected. Task: {task_id}, Remaining connections: {len(self.active_connections)}")
    
    async def broadcast_to_task(self, task_id: str, message: Dict[str, Any]):
        """Broadcast message to all connections for a specific task"""
        
        if task_id not in self.task_connections:
            self.logger.debug(f"No connections for task {task_id}")
            return
        
        connections = self.task_connections[task_id].copy()  # Create copy to avoid modification during iteration
        
        if not connections:
            return
        
        # Add timestamp to message
        message["timestamp"] = datetime.now().isoformat()
        
        # Send to all connections for this task
        disconnected_connections = []
        
        for websocket in connections:
            try:
                await self._send_to_websocket(websocket, message)
            except Exception as e:
                self.logger.warning(f"Failed to send message to WebSocket: {str(e)}")
                disconnected_connections.append(websocket)
        
        # Clean up disconnected connections
        for websocket in disconnected_connections:
            await self.disconnect(websocket)
    
    async def broadcast_to_all(self, message: Dict[str, Any]):
        """Broadcast message to all active connections"""
        
        if not self.active_connections:
            return
        
        # Add timestamp to message
        message["timestamp"] = datetime.now().isoformat()
        
        connections = self.active_connections.copy()
        disconnected_connections = []
        
        for websocket in connections:
            try:
                await self._send_to_websocket(websocket, message)
            except Exception as e:
                self.logger.warning(f"Failed to send message to WebSocket: {str(e)}")
                disconnected_connections.append(websocket)
        
        # Clean up disconnected connections
        for websocket in disconnected_connections:
            await self.disconnect(websocket)
    
    async def send_to_connection(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to a specific WebSocket connection"""
        
        if websocket not in self.active_connections:
            self.logger.warning("Attempted to send message to inactive WebSocket")
            return
        
        message["timestamp"] = datetime.now().isoformat()
        
        try:
            await self._send_to_websocket(websocket, message)
        except Exception as e:
            self.logger.error(f"Failed to send message to WebSocket: {str(e)}")
            await self.disconnect(websocket)
    
    async def _send_to_websocket(self, websocket: WebSocket, message: Dict[str, Any]):
        """Internal method to send message to WebSocket"""
        
        try:
            message_str = json.dumps(message, default=str)
            await websocket.send_text(message_str)
        except Exception as e:
            self.logger.error(f"WebSocket send failed: {str(e)}")
            raise
    
    async def handle_client_message(self, websocket: WebSocket, message: str):
        """Handle incoming message from client"""
        
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "ping":
                await self._handle_ping(websocket, data)
            elif message_type == "subscribe_task":
                await self._handle_task_subscription(websocket, data)
            elif message_type == "unsubscribe_task":
                await self._handle_task_unsubscription(websocket, data)
            else:
                self.logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            self.logger.warning(f"Invalid JSON received from WebSocket: {message}")
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {str(e)}")
    
    async def _handle_ping(self, websocket: WebSocket, data: Dict[str, Any]):
        """Handle ping message from client"""
        
        # Update last ping time
        if websocket in self.connection_metadata:
            self.connection_metadata[websocket]["last_ping"] = datetime.now()
        
        # Send pong response
        await self.send_to_connection(websocket, {
            "type": "pong",
            "timestamp": datetime.now().isoformat()
        })
    
    async def _handle_task_subscription(self, websocket: WebSocket, data: Dict[str, Any]):
        """Handle task subscription request"""
        
        task_id = data.get("task_id")
        if not task_id:
            await self.send_to_connection(websocket, {
                "type": "error",
                "message": "Task ID required for subscription"
            })
            return
        
        # Add to task connections
        if task_id not in self.task_connections:
            self.task_connections[task_id] = set()
        
        self.task_connections[task_id].add(websocket)
        
        # Update connection metadata
        if websocket in self.connection_metadata:
            self.connection_metadata[websocket]["task_id"] = task_id
        
        await self.send_to_connection(websocket, {
            "type": "subscription_confirmed",
            "task_id": task_id
        })
        
        self.logger.info(f"WebSocket subscribed to task {task_id}")
    
    async def _handle_task_unsubscription(self, websocket: WebSocket, data: Dict[str, Any]):
        """Handle task unsubscription request"""
        
        task_id = data.get("task_id")
        if not task_id:
            return
        
        # Remove from task connections
        if task_id in self.task_connections:
            self.task_connections[task_id].discard(websocket)
            
            if not self.task_connections[task_id]:
                del self.task_connections[task_id]
        
        # Update connection metadata
        if websocket in self.connection_metadata:
            self.connection_metadata[websocket]["task_id"] = None
        
        await self.send_to_connection(websocket, {
            "type": "unsubscription_confirmed",
            "task_id": task_id
        })
        
        self.logger.info(f"WebSocket unsubscribed from task {task_id}")
    
    async def cleanup_stale_connections(self, max_idle_minutes: int = 30):
        """Clean up stale connections that haven't sent ping recently"""
        
        if not self.active_connections:
            return
        
        current_time = datetime.now()
        stale_connections = []
        
        for websocket, metadata in self.connection_metadata.items():
            last_ping = metadata.get("last_ping", metadata.get("connected_at"))
            idle_time = current_time - last_ping
            
            if idle_time.total_seconds() > (max_idle_minutes * 60):
                stale_connections.append(websocket)
        
        # Disconnect stale connections
        for websocket in stale_connections:
            try:
                await websocket.close(code=1000, reason="Connection timeout")
            except Exception:
                pass  # Connection might already be closed
            
            await self.disconnect(websocket)
        
        if stale_connections:
            self.logger.info(f"Cleaned up {len(stale_connections)} stale WebSocket connections")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about active connections"""
        
        task_stats = {}
        for task_id, connections in self.task_connections.items():
            task_stats[task_id] = len(connections)
        
        return {
            "total_connections": len(self.active_connections),
            "task_connections": task_stats,
            "tasks_with_connections": len(self.task_connections)
        }
    
    async def send_system_notification(self, message: str, level: str = "info"):
        """Send system notification to all connections"""
        
        await self.broadcast_to_all({
            "type": "system_notification",
            "level": level,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })


# Global WebSocket manager instance
websocket_manager = WebSocketManager()