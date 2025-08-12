"""
WebSocket API endpoints
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
import logging

from ....services.websocket import websocket_manager


router = APIRouter()
logger = logging.getLogger("websocket_api")


@router.websocket("/connect")
async def websocket_endpoint(
    websocket: WebSocket, 
    task_id: Optional[str] = Query(None)
):
    """WebSocket endpoint for real-time updates"""
    
    try:
        # Connect WebSocket
        await websocket_manager.connect(websocket, task_id)
        
        logger.info(f"WebSocket connected for task: {task_id}")
        
        # Listen for messages
        while True:
            try:
                # Receive message from client
                message = await websocket.receive_text()
                
                # Handle client message
                await websocket_manager.handle_client_message(websocket, message)
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for task: {task_id}")
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {str(e)}")
                # Send error message to client
                try:
                    await websocket_manager.send_to_connection(websocket, {
                        "type": "error",
                        "message": "Internal server error"
                    })
                except:
                    pass  # Connection might be closed
                break
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
    
    finally:
        # Clean up connection
        await websocket_manager.disconnect(websocket)


@router.get("/stats")
async def get_websocket_stats():
    """Get WebSocket connection statistics"""
    
    return websocket_manager.get_connection_stats()


@router.post("/broadcast")
async def broadcast_message(message: dict):
    """Broadcast message to all connected clients (admin only)"""
    
    # In a production app, this would require admin authentication
    
    await websocket_manager.broadcast_to_all({
        "type": "admin_broadcast",
        "message": message.get("message", ""),
        "level": message.get("level", "info")
    })
    
    return {"message": "Broadcast sent successfully"}


@router.post("/notify/{task_id}")
async def notify_task_subscribers(task_id: str, message: dict):
    """Send notification to subscribers of a specific task"""
    
    # In a production app, this would require proper authentication
    
    await websocket_manager.broadcast_to_task(task_id, {
        "type": "task_notification",
        "task_id": task_id,
        "message": message.get("message", ""),
        "level": message.get("level", "info")
    })
    
    return {"message": f"Notification sent to task {task_id} subscribers"}