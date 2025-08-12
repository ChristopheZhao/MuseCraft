#!/usr/bin/env python3
"""
Database setup script
"""
import os
import sys
import asyncio
from pathlib import Path

# Add the parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def create_database():
    """Create database and tables"""
    
    from app.core.database import async_engine
    from app.models.base import BaseModel
    from app.models import Task, Scene, Resource, AgentExecution
    
    print("Creating database tables...")
    
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
        
        print("✓ Database tables created successfully")
        return True
        
    except Exception as e:
        print(f"✗ Failed to create database tables: {e}")
        return False


def create_initial_migration():
    """Create initial Alembic migration"""
    
    import subprocess
    
    print("Creating initial migration...")
    
    try:
        # Create initial migration
        result = subprocess.run([
            "alembic", "revision", 
            "--autogenerate", 
            "-m", "Initial migration"
        ], check=True, capture_output=True, text=True)
        
        print("✓ Initial migration created")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to create migration: {e}")
        print("stdout:", e.stdout)
        print("stderr:", e.stderr)
        return False


def run_migrations():
    """Run database migrations"""
    
    import subprocess
    
    print("Running database migrations...")
    
    try:
        result = subprocess.run([
            "alembic", "upgrade", "head"
        ], check=True, capture_output=True, text=True)
        
        print("✓ Database migrations completed")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Migration failed: {e}")
        print("stdout:", e.stdout)
        print("stderr:", e.stderr)
        return False


async def create_sample_data():
    """Create sample data for testing"""
    
    from app.core.database import AsyncSessionLocal
    from app.models import Task, TaskType, TaskStatus
    
    print("Creating sample data...")
    
    try:
        async with AsyncSessionLocal() as db:
            # Check if sample data already exists
            existing_task = await db.get(Task, 1)
            if existing_task:
                print("Sample data already exists, skipping...")
                return True
            
            # Create sample task
            sample_task = Task(
                title="Sample Video Generation",
                description="This is a sample video generation task for testing",
                task_type=TaskType.VIDEO_GENERATION,
                status=TaskStatus.PENDING,
                input_parameters={
                    "user_prompt": "Create a promotional video for a tech startup",
                    "video_style": "modern",
                    "duration": 30,
                    "aspect_ratio": "16:9"
                }
            )
            
            db.add(sample_task)
            await db.commit()
        
        print("✓ Sample data created")
        return True
        
    except Exception as e:
        print(f"✗ Failed to create sample data: {e}")
        return False


def check_dependencies():
    """Check if required dependencies are available"""
    
    print("Checking dependencies...")
    
    # Check database drivers based on DATABASE_URL
    from app.core.config import settings
    
    if settings.DATABASE_URL.startswith("mysql://"):
        try:
            import pymysql
            print("✓ pymysql available")
        except ImportError:
            print("✗ pymysql not available")
            return False
        
        try:
            import aiomysql
            print("✓ aiomysql available")
        except ImportError:
            print("✗ aiomysql not available")
            return False
    else:
        try:
            import psycopg2
            print("✓ psycopg2 available")
        except ImportError:
            print("✗ psycopg2 not available")
            return False
        
        try:
            import asyncpg
            print("✓ asyncpg available")
        except ImportError:
            print("✗ asyncpg not available")
            return False
    
    try:
        import alembic
        print("✓ alembic available")
    except ImportError:
        print("✗ alembic not available")
        return False
    
    return True


async def main():
    """Main function"""
    
    print("Setting up Short Video Maker Database")
    print("=" * 40)
    
    # Check dependencies
    if not check_dependencies():
        print("\nPlease install required dependencies:")
        print("pip install psycopg2-binary asyncpg alembic")
        sys.exit(1)
    
    # Check database connection
    try:
        from app.core.config import settings
        from sqlalchemy import create_engine, text
        
        print("Testing database connection...")
        # Use SQLAlchemy to test connection (works with both PostgreSQL and MySQL)
        engine = create_engine(settings.DATABASE_URL.replace("mysql://", "mysql+pymysql://") if settings.DATABASE_URL.startswith("mysql://") else settings.DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Database connection successful")
        
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("\nPlease ensure:")
        if settings.DATABASE_URL.startswith("mysql://"):
            print("1. MySQL is running")
            print("2. Database exists")
        else:
            print("1. PostgreSQL is running") 
            print("2. Database exists")
        print("3. Connection parameters are correct in .env file")
        sys.exit(1)
    
    # Create database tables
    success = await create_database()
    if not success:
        sys.exit(1)
    
    # Create initial migration (optional, for future schema changes)
    print("\nSetting up migrations...")
    
    # Initialize alembic if not already done
    if not os.path.exists("alembic/versions"):
        import subprocess
        try:
            subprocess.run(["alembic", "init", "alembic"], check=True)
            print("✓ Alembic initialized")
        except:
            pass  # Might already be initialized
    
    # Create sample data
    await create_sample_data()
    
    print("\n" + "=" * 40)
    print("Database setup completed successfully!")
    print("You can now start the application with:")
    print("python scripts/start_dev.py")


if __name__ == "__main__":
    asyncio.run(main())