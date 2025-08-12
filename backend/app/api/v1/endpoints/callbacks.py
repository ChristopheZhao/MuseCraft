"""
Callback endpoints for external AI services
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from ....services.redis_service import redis_service

logger = logging.getLogger(__name__)

router = APIRouter()


class SunoCallbackPayload(BaseModel):
    """Suno AI callback payload model"""
    task_id: str = Field(..., description="Task ID from Suno AI")
    status: str = Field(..., description="Task status (completed, failed, etc.)")
    data: Dict[str, Any] = Field(default_factory=dict, description="Task result data")
    message: str = Field(default="", description="Status message")
    code: int = Field(default=200, description="Response code")


async def process_suno_callback(task_id: str, payload: Dict[str, Any]):
    """Process Suno AI callback in background"""
    try:
        logger.info(f"Processing Suno callback for task {task_id}")
        
        # Store the callback result in Redis
        await redis_service.store_callback_result(
            task_id=task_id,
            result=payload,
            ttl=3600  # 1 hour TTL
        )
        
        # Set event flag for waiting processes
        await redis_service.set_callback_event(task_id)
        
        logger.info(f"Successfully processed Suno callback for task {task_id}")
        
    except Exception as e:
        logger.error(f"Error processing Suno callback for task {task_id}: {e}")


@router.post("/suno/{task_id}")
async def suno_callback(
    task_id: str,
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Suno AI callback endpoint
    
    This endpoint receives POST callbacks from Suno AI when tasks are completed.
    The callback data is stored in Redis and an event is set to notify waiting processes.
    """
    try:
        # Get request body as JSON
        payload = await request.json()
        
        logger.info(f"Received Suno callback for task {task_id}: {payload}")
        
        # Validate basic structure
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=400,
                detail="Invalid callback payload format"
            )
        
        # Add task_id to payload if not present
        if "task_id" not in payload:
            payload["task_id"] = task_id
        
        # Process callback in background
        background_tasks.add_task(
            process_suno_callback,
            task_id=task_id,
            payload=payload
        )
        
        # Return immediate success response to Suno AI
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Callback received successfully",
                "task_id": task_id,
                "timestamp": payload.get("timestamp", "")
            }
        )
        
    except Exception as e:
        logger.error(f"Error handling Suno callback for task {task_id}: {e}")
        
        # Still return success to Suno AI to avoid retries
        return JSONResponse(
            status_code=200,
            content={
                "status": "error_logged",
                "message": "Callback received but processing failed",
                "task_id": task_id,
                "error": str(e)
            }
        )


@router.get("/suno/{task_id}/status")
async def get_suno_callback_status(task_id: str):
    """
    Check if callback has been received for a specific task
    
    This endpoint allows clients to check if a callback has been received
    without waiting for the actual callback processing.
    """
    try:
        # Check if callback result exists
        result = await redis_service.get_callback_result(task_id)
        
        if result:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "received",
                    "task_id": task_id,
                    "has_result": True,
                    "result_preview": {
                        "status": result.get("status", "unknown"),
                        "code": result.get("code", 0),
                        "message": result.get("message", "")
                    }
                }
            )
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "pending",
                    "task_id": task_id,
                    "has_result": False,
                    "message": "Callback not yet received"
                }
            )
            
    except Exception as e:
        logger.error(f"Error checking callback status for task {task_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check callback status: {str(e)}"
        )


@router.get("/suno/{task_id}/result")
async def get_suno_callback_result(task_id: str):
    """
    Retrieve the full callback result for a specific task
    
    This endpoint returns the complete callback payload received from Suno AI.
    """
    try:
        result = await redis_service.get_callback_result(task_id)
        
        if result:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "task_id": task_id,
                    "result": result
                }
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No callback result found for task {task_id}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving callback result for task {task_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve callback result: {str(e)}"
        )


@router.delete("/suno/{task_id}")
async def cleanup_suno_callback(task_id: str):
    """
    Clean up callback data for a specific task
    
    This endpoint removes all callback-related data from Redis for the given task.
    Useful for cleaning up completed or expired tasks.
    """
    try:
        cleaned = await redis_service.cleanup_callback_data(task_id)
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success" if cleaned else "not_found",
                "task_id": task_id,
                "message": "Callback data cleaned up" if cleaned else "No data to clean up"
            }
        )
        
    except Exception as e:
        logger.error(f"Error cleaning up callback data for task {task_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup callback data: {str(e)}"
        )


# Health check for callback system
@router.get("/health")
async def callback_health_check():
    """Health check for callback system"""
    try:
        # Test Redis connection
        test_task_id = "health_check_test"
        test_data = {"status": "test", "timestamp": "now"}
        
        # Try to store and retrieve test data
        stored = await redis_service.store_callback_result(
            test_task_id, 
            test_data, 
            ttl=10  # Short TTL for test
        )
        
        if stored:
            retrieved = await redis_service.get_callback_result(test_task_id)
            await redis_service.cleanup_callback_data(test_task_id)
            
            if retrieved == test_data:
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "healthy",
                        "redis_connection": "ok",
                        "callback_system": "operational"
                    }
                )
        
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "redis_connection": "failed",
                "callback_system": "not_operational"
            }
        )
        
    except Exception as e:
        logger.error(f"Callback health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "callback_system": "not_operational"
            }
        )