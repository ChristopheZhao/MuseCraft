"""
Integration test configuration and fixtures
"""
import asyncio
import os
import pytest
import tempfile
import shutil
from typing import Generator, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from httpx import AsyncClient
import redis.asyncio as redis

# Import application components
from app.main import app
from app.core.config import settings
from app.core.database import Base, get_db
from app.models import Task, AgentExecution, Scene, Resource
from app.services.celery_app import celery_app
from app.services.websocket import websocket_manager


# Test database configuration
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
TEST_REDIS_URL = "redis://localhost:6379/15"  # Use different DB for tests


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def test_db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    TestSessionLocal = sessionmaker(
        test_engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
    
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def test_redis():
    """Create test Redis connection."""
    redis_client = redis.from_url(TEST_REDIS_URL)
    
    # Clear test database
    await redis_client.flushdb()
    
    yield redis_client
    
    # Cleanup
    await redis_client.flushdb()
    await redis_client.close()


@pytest.fixture
def test_storage_dirs():
    """Create temporary storage directories for testing."""
    temp_dir = tempfile.mkdtemp()
    
    storage_dirs = {
        'upload': os.path.join(temp_dir, 'uploads'),
        'generated': os.path.join(temp_dir, 'generated'),
        'temp': os.path.join(temp_dir, 'temp')
    }
    
    # Create directories
    for path in storage_dirs.values():
        os.makedirs(path, exist_ok=True)
    
    yield storage_dirs
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_ai_services():
    """Mock AI service providers for testing."""
    mocks = {
        'openai': AsyncMock(),
        'anthropic': AsyncMock(),
        'stability': AsyncMock(),
        'runway': AsyncMock(),
        'pika_labs': AsyncMock()
    }
    
    # Configure mock responses
    mocks['openai'].chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="Mock OpenAI response"))
    ]
    
    mocks['anthropic'].messages.create.return_value.content = [
        MagicMock(text="Mock Anthropic response")
    ]
    
    mocks['stability'].generate.return_value = MagicMock(
        artifacts=[MagicMock(seed=12345, binary=b"mock_image_data")]
    )
    
    yield mocks


@pytest.fixture
def mock_celery_tasks():
    """Mock Celery tasks for testing."""
    with patch('app.services.celery_app.celery_app.send_task') as mock_send:
        mock_send.return_value = MagicMock(id="test-task-id-123")
        yield mock_send


@pytest.fixture
async def test_client(test_db_session, test_redis, test_storage_dirs, mock_ai_services):
    """Create test FastAPI client with overridden dependencies."""
    
    # Override database dependency
    async def override_get_db():
        yield test_db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Override storage paths
    with patch.multiple(
        'app.core.config.settings',
        UPLOAD_PATH=test_storage_dirs['upload'],
        GENERATED_PATH=test_storage_dirs['generated'],
        TEMP_PATH=test_storage_dirs['temp'],
        REDIS_URL=TEST_REDIS_URL
    ):
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sync_test_client(test_db_session, test_storage_dirs):
    """Create synchronous test client for simple tests."""
    
    async def override_get_db():
        yield test_db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch.multiple(
        'app.core.config.settings',
        UPLOAD_PATH=test_storage_dirs['upload'],
        GENERATED_PATH=test_storage_dirs['generated'],
        TEMP_PATH=test_storage_dirs['temp']
    ):
        with TestClient(app) as client:
            yield client
    
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_task(test_db_session) -> Task:
    """Create a sample task for testing."""
    task = Task(
        task_id="test-task-12345",
        title="Test Video Generation",
        description="Testing video generation workflow",
        user_prompt="Create a professional video about AI technology",
        input_parameters={
            "video_style": "professional",
            "duration": 30,
            "aspect_ratio": "16:9"
        },
        task_type="video_generation",
        status="pending"
    )
    
    test_db_session.add(task)
    await test_db_session.commit()
    await test_db_session.refresh(task)
    
    return task


@pytest.fixture
def websocket_test_client():
    """Create WebSocket test client."""
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    return client


@pytest.fixture
def load_test_config():
    """Configuration for load testing."""
    return {
        'concurrent_users': 10,
        'requests_per_user': 5,
        'ramp_up_time': 30,  # seconds
        'test_duration': 300,  # seconds
        'acceptable_response_time': 2.0,  # seconds
        'acceptable_error_rate': 0.05  # 5%
    }


@pytest.fixture
def performance_thresholds():
    """Performance test thresholds."""
    return {
        'api_response_time': 2.0,  # seconds
        'websocket_latency': 0.5,  # seconds
        'task_processing_time': 60.0,  # seconds for simple tasks
        'memory_usage': 500,  # MB
        'cpu_usage': 80,  # percentage
        'database_query_time': 0.1  # seconds
    }


class MockWebSocketConnection:
    """Mock WebSocket connection for testing."""
    
    def __init__(self):
        self.messages = []
        self.closed = False
    
    async def send_text(self, data: str):
        if not self.closed:
            self.messages.append(data)
    
    async def send_json(self, data: dict):
        if not self.closed:
            self.messages.append(data)
    
    async def close(self):
        self.closed = True


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    return MockWebSocketConnection()


# Integration test helpers
class IntegrationTestHelper:
    """Helper class for integration testing."""
    
    @staticmethod
    async def wait_for_task_completion(
        task_id: str, 
        db: AsyncSession, 
        timeout: int = 60
    ) -> Task:
        """Wait for task to complete with timeout."""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            stmt = select(Task).where(Task.task_id == task_id)
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()
            
            if task and task.status in ['completed', 'failed', 'error']:
                return task
            
            await asyncio.sleep(1)
        
        raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")
    
    @staticmethod
    async def create_test_files(storage_dir: str) -> dict:
        """Create test files for upload testing."""
        test_files = {}
        
        # Create test image
        image_path = os.path.join(storage_dir, 'test_image.jpg')
        with open(image_path, 'wb') as f:
            f.write(b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xFF\xDB')
        test_files['image'] = image_path
        
        # Create test video
        video_path = os.path.join(storage_dir, 'test_video.mp4')
        with open(video_path, 'wb') as f:
            f.write(b'\x00\x00\x00\x20ftypmp41\x00\x00\x00\x00mp41isom')
        test_files['video'] = video_path
        
        # Create test audio
        audio_path = os.path.join(storage_dir, 'test_audio.mp3')
        with open(audio_path, 'wb') as f:
            f.write(b'ID3\x03\x00\x00\x00\x00\x00\x00\x00')
        test_files['audio'] = audio_path
        
        return test_files


@pytest.fixture
def integration_helper():
    """Integration test helper fixture."""
    return IntegrationTestHelper


# Test data factories
@pytest.fixture
def task_factory():
    """Factory for creating test tasks."""
    def _create_task(**kwargs):
        defaults = {
            'task_id': f"test-task-{os.urandom(4).hex()}",
            'title': "Test Task",
            'description': "Test task description",
            'user_prompt': "Generate a test video",
            'input_parameters': {
                'video_style': 'professional',
                'duration': 30,
                'aspect_ratio': '16:9'
            },
            'task_type': 'video_generation',
            'status': 'pending'
        }
        defaults.update(kwargs)
        return Task(**defaults)
    
    return _create_task


@pytest.fixture
def agent_execution_factory():
    """Factory for creating test agent executions."""
    def _create_execution(**kwargs):
        defaults = {
            'agent_type': 'concept_planner',
            'agent_name': 'test_agent',
            'status': 'pending',
            'input_data': {},
            'output_data': {},
            'execution_metadata': {}
        }
        defaults.update(kwargs)
        return AgentExecution(**defaults)
    
    return _create_execution


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "load: mark test as load test"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# Test environment setup
@pytest.fixture(autouse=True)
async def setup_test_environment():
    """Set up test environment before each test."""
    # Clear any existing WebSocket connections
    websocket_manager.active_connections.clear()
    
    # Reset Celery task registry
    celery_app.control.purge()
    
    yield
    
    # Cleanup after test
    websocket_manager.active_connections.clear()