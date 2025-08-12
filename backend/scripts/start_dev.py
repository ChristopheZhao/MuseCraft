#!/usr/bin/env python3
"""
Development server startup script
"""
import os
import sys
import subprocess
import signal
import time
from pathlib import Path

# Add the parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_dependencies():
    """Check if required services are running"""
    
    print("Checking dependencies...")
    
    # Check Database (MySQL or PostgreSQL)
    try:
        from app.core.config import settings
        from sqlalchemy import create_engine, text
        
        # Support both MySQL and PostgreSQL
        sync_database_url = settings.DATABASE_URL
        if settings.DATABASE_URL.startswith("mysql://"):
            sync_database_url = settings.DATABASE_URL.replace("mysql://", "mysql+pymysql://")
        
        engine = create_engine(sync_database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        db_type = "MySQL" if settings.DATABASE_URL.startswith("mysql://") else "PostgreSQL"
        print(f"✓ {db_type} connection successful")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        db_type = "MySQL" if settings.DATABASE_URL.startswith("mysql://") else "PostgreSQL"
        print(f"Please ensure {db_type} is running and database is created")
        return False
    
    # Check Redis
    try:
        import redis
        from app.core.config import settings
        
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        print("✓ Redis connection successful")
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        print("Please ensure Redis is running")
        return False
    
    return True


def run_migrations():
    """Run database migrations"""
    
    print("Running database migrations...")
    
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True
        )
        print("✓ Database migrations completed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Migration failed: {e}")
        print("stdout:", e.stdout)
        print("stderr:", e.stderr)
        return False
    
    return True


def start_celery_worker():
    """Start Celery worker in background"""
    
    print("Starting Celery worker...")
    
    celery_cmd = [
        "celery", "-A", "app.services.celery_app", "worker",
        "--loglevel=info",
        "--concurrency=2",
        "--queues=video_processing"
    ]
    
    try:
        process = subprocess.Popen(
            celery_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        if process.poll() is None:
            print("✓ Celery worker started")
            return process
        else:
            stdout, stderr = process.communicate()
            print(f"✗ Celery worker failed to start")
            print("stdout:", stdout.decode())
            print("stderr:", stderr.decode())
            return None
    except Exception as e:
        print(f"✗ Failed to start Celery worker: {e}")
        return None


def start_celery_beat():
    """Start Celery beat scheduler in background"""
    
    print("Starting Celery beat...")
    
    beat_cmd = [
        "celery", "-A", "app.services.celery_app", "beat",
        "--loglevel=info"
    ]
    
    try:
        process = subprocess.Popen(
            beat_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        if process.poll() is None:
            print("✓ Celery beat started")
            return process
        else:
            stdout, stderr = process.communicate()
            print(f"✗ Celery beat failed to start")
            print("stdout:", stdout.decode())
            print("stderr:", stderr.decode())
            return None
    except Exception as e:
        print(f"✗ Failed to start Celery beat: {e}")
        return None


def start_api_server():
    """Start FastAPI server"""
    
    print("Starting FastAPI server...")
    
    api_cmd = [
        "uvicorn", "app.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload",
        "--log-level", "info"
    ]
    
    try:
        process = subprocess.Popen(api_cmd)
        print("✓ FastAPI server started on http://localhost:8000")
        return process
    except Exception as e:
        print(f"✗ Failed to start FastAPI server: {e}")
        return None


def cleanup_processes(processes):
    """Clean up background processes"""
    
    print("\nShutting down services...")
    
    for name, process in processes.items():
        if process and process.poll() is None:
            print(f"Stopping {name}...")
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main():
    """Main function"""
    
    print("Starting Short Video Maker Backend (Development Mode)")
    print("=" * 50)
    
    processes = {}
    
    try:
        # Check dependencies
        if not check_dependencies():
            sys.exit(1)
        
        # Run migrations
        if not run_migrations():
            sys.exit(1)
        
        # Start Celery worker
        worker_process = start_celery_worker()
        processes["celery_worker"] = worker_process
        
        # Start Celery beat
        beat_process = start_celery_beat()
        processes["celery_beat"] = beat_process
        
        # Start API server
        api_process = start_api_server()
        processes["api_server"] = api_process
        
        if not api_process:
            sys.exit(1)
        
        print("\n" + "=" * 50)
        print("All services started successfully!")
        print("API Documentation: http://localhost:8000/api/v1/docs")
        print("Health Check: http://localhost:8000/health")
        print("Press Ctrl+C to stop all services")
        print("=" * 50)
        
        # Wait for API server
        api_process.wait()
        
    except KeyboardInterrupt:
        print("\nReceived interrupt signal")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        cleanup_processes(processes)
        print("All services stopped")


if __name__ == "__main__":
    main()