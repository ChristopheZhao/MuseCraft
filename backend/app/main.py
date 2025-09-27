"""
FastAPI main application
"""
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
import os

from .core.config import settings
from .core.logging_utils import configure_mas_logging
from .api.v1.api import api_router
from .services.websocket import websocket_manager


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
configure_mas_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    
    # Startup events
    logger.info("Starting Short Video Maker API")
    
    # Initialize tool registry
    from .agents.tools import register_default_tools
    register_default_tools()
    logger.info("✅ Tool registry initialized")
    
    # Create storage directories
    os.makedirs(settings.UPLOAD_PATH, exist_ok=True)
    os.makedirs(settings.GENERATED_PATH, exist_ok=True)
    os.makedirs(settings.TEMP_PATH, exist_ok=True)
    
    # Start periodic cleanup task for WebSocket connections
    import asyncio
    cleanup_task = asyncio.create_task(periodic_websocket_cleanup())
    
    yield
    
    # Shutdown events
    logger.info("Shutting down Short Video Maker API")
    
    # Cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI-powered short video generation platform API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware for debugging (DISABLED - causing hanging)
# @app.middleware("http")
# async def log_requests(request: Request, call_next):
#     """Log all requests for debugging"""
#     if request.method == "POST":
#         # Read body for POST requests (always log, not just in DEBUG)
#         body = await request.body()
#         logger.info(f"POST {request.url.path} - Request body: {body.decode('utf-8') if body else 'empty'}")
#         # Recreate request with body
#         import io
#         request._body = body
#         request._stream = io.BytesIO(body)
#     
#     response = await call_next(request)
#     return response


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed info"""
    
    logger.error(f"Validation error: {exc.errors()}")
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": exc.errors(),
            "body": exc.body if hasattr(exc, 'body') else None
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    
    logger.error(f"Global exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": "internal_error",
            "debug": str(exc) if settings.DEBUG else None
        }
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": "development" if settings.DEBUG else "production"
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "docs_url": f"{settings.API_V1_STR}/docs",
        "api_url": settings.API_V1_STR
    }


# Include API routes
app.include_router(api_router, prefix=settings.API_V1_STR)


# Mount static file directories
if os.path.exists(settings.UPLOAD_PATH):
    app.mount("/files/uploads", StaticFiles(directory=settings.UPLOAD_PATH), name="uploads")

if os.path.exists(settings.GENERATED_PATH):
    app.mount("/files/generated", StaticFiles(directory=settings.GENERATED_PATH), name="generated")

if os.path.exists(settings.TEMP_PATH):
    app.mount("/files/temp", StaticFiles(directory=settings.TEMP_PATH), name="temp")

# Final outputs (e.g., composed videos/audio) live under storage/outputs
if os.path.exists(settings.FINAL_OUTPUT_ROOT):
    app.mount("/files/outputs", StaticFiles(directory=settings.FINAL_OUTPUT_ROOT), name="outputs")


# Periodic tasks
async def periodic_websocket_cleanup():
    """Periodic cleanup of stale WebSocket connections"""
    
    import asyncio
    
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            await websocket_manager.cleanup_stale_connections()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"WebSocket cleanup error: {str(e)}")


# Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests"""
    
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Log request
    process_time = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )
    
    return response


if __name__ == "__main__":
    import uvicorn
    import time
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
