"""
WebSocket Real-time Communication Integration Tests

Tests WebSocket functionality for real-time updates:
- Connection establishment and management
- Message broadcasting and delivery
- Progress updates and agent status
- Error handling and reconnection
- Session management and cleanup
- Performance under load
"""
import pytest
import asyncio
import json
import time
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.websocket import websocket_manager, WebSocketManager
from app.models import Task


@pytest.mark.websocket
@pytest.mark.asyncio
class TestWebSocketIntegration:
    """WebSocket integration tests."""
    
    async def test_websocket_connection_establishment(
        self,
        websocket_test_client: TestClient
    ):
        """Test WebSocket connection establishment."""
        
        session_id = "test-session-123"
        
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            # Connection should be established
            assert websocket is not None
            
            # Should be able to send and receive messages
            test_message = {
                "type": "ping",
                "timestamp": time.time()
            }
            
            websocket.send_json(test_message)
            
            # Should receive acknowledgment
            response = websocket.receive_json()
            assert response["type"] in ["pong", "ack"]
    
    async def test_websocket_session_management(
        self,
        websocket_test_client: TestClient
    ):
        """Test WebSocket session management."""
        
        session_id = "test-session-123"
        
        # Test connection tracking
        initial_connection_count = len(websocket_manager.active_connections)
        
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            # Should have one more connection
            assert len(websocket_manager.active_connections) == initial_connection_count + 1
            assert session_id in websocket_manager.active_connections
        
        # After closing, connection should be removed
        await asyncio.sleep(0.1)  # Allow cleanup
        assert len(websocket_manager.active_connections) == initial_connection_count
        assert session_id not in websocket_manager.active_connections
    
    async def test_progress_update_broadcasting(
        self,
        websocket_test_client: TestClient,
        test_db_session: AsyncSession,
        sample_task: Task
    ):
        """Test progress update broadcasting to WebSocket clients."""
        
        session_id = "test-session-123"
        task_id = sample_task.task_id
        
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            # Subscribe to task updates
            subscribe_message = {
                "type": "subscribe",
                "task_id": task_id
            }
            websocket.send_json(subscribe_message)
            
            # Should receive subscription confirmation
            response = websocket.receive_json()
            assert response["type"] == "subscription_confirmed"
            
            # Send progress update through manager
            await websocket_manager.send_progress_update(
                session_id=session_id,
                task_id=task_id,
                progress=50,
                status="processing",
                agent_name="script_writer",
                estimated_time_remaining=120
            )
            
            # Should receive progress update
            progress_message = websocket.receive_json()
            
            assert progress_message["type"] == "progress-update"
            assert progress_message["data"]["task_id"] == task_id
            assert progress_message["data"]["progress"] == 50
            assert progress_message["data"]["status"] == "processing"
            assert progress_message["data"]["agent_name"] == "script_writer"
            assert progress_message["data"]["estimated_time_remaining"] == 120
    
    async def test_agent_status_updates(
        self,
        websocket_test_client: TestClient,
        test_db_session: AsyncSession,
        sample_task: Task
    ):
        """Test agent status update broadcasting."""
        
        session_id = "test-session-123"
        task_id = sample_task.task_id
        
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            # Subscribe to task updates
            websocket.send_json({
                "type": "subscribe",
                "task_id": task_id
            })
            
            # Confirm subscription
            websocket.receive_json()
            
            # Send agent status update
            await websocket_manager.send_agent_status_update(
                session_id=session_id,
                task_id=task_id,
                agent_type="image_generator",
                status="working",
                progress=75,
                current_task="Generating scene 2 of 5",
                metadata={
                    "model": "stable-diffusion-xl",
                    "style": "photorealistic"
                }
            )
            
            # Should receive agent status update
            status_message = websocket.receive_json()
            
            assert status_message["type"] == "agent-status-update"
            assert status_message["data"]["task_id"] == task_id
            assert status_message["data"]["agent_type"] == "image_generator"
            assert status_message["data"]["status"] == "working"
            assert status_message["data"]["progress"] == 75
            assert status_message["data"]["current_task"] == "Generating scene 2 of 5"
            assert status_message["data"]["metadata"]["model"] == "stable-diffusion-xl"
    
    async def test_result_ready_notification(
        self,
        websocket_test_client: TestClient,
        test_db_session: AsyncSession,
        sample_task: Task
    ):
        """Test result ready notification."""
        
        session_id = "test-session-123"
        task_id = sample_task.task_id
        
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            # Subscribe to task updates
            websocket.send_json({
                "type": "subscribe",
                "task_id": task_id
            })
            
            # Confirm subscription
            websocket.receive_json()
            
            # Send result ready notification
            await websocket_manager.send_result_ready(
                session_id=session_id,
                task_id=task_id,
                result_type="video",
                result_data={
                    "video_url": "https://example.com/generated-video.mp4",
                    "thumbnail_url": "https://example.com/thumbnail.jpg",
                    "duration": 60,
                    "resolution": "1920x1080",
                    "file_size": 15728640
                }
            )
            
            # Should receive result ready notification
            result_message = websocket.receive_json()
            
            assert result_message["type"] == "result-ready"
            assert result_message["data"]["task_id"] == task_id
            assert result_message["data"]["result_type"] == "video"
            assert result_message["data"]["result_data"]["video_url"] == "https://example.com/generated-video.mp4"
            assert result_message["data"]["result_data"]["duration"] == 60
    
    async def test_error_broadcasting(
        self,
        websocket_test_client: TestClient,
        test_db_session: AsyncSession,
        sample_task: Task
    ):
        """Test error message broadcasting."""
        
        session_id = "test-session-123"
        task_id = sample_task.task_id
        
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            # Subscribe to task updates
            websocket.send_json({
                "type": "subscribe",
                "task_id": task_id
            })
            
            # Confirm subscription
            websocket.receive_json()
            
            # Send error message
            await websocket_manager.send_error(
                session_id=session_id,
                task_id=task_id,
                error_type="agent_error",
                error_message="Image generation failed: API quota exceeded",
                error_code="QUOTA_EXCEEDED",
                recoverable=True,
                suggested_action="Please try again in a few minutes"
            )
            
            # Should receive error message
            error_message = websocket.receive_json()
            
            assert error_message["type"] == "error"
            assert error_message["data"]["task_id"] == task_id
            assert error_message["data"]["error_type"] == "agent_error"
            assert error_message["data"]["error_message"] == "Image generation failed: API quota exceeded"
            assert error_message["data"]["error_code"] == "QUOTA_EXCEEDED"
            assert error_message["data"]["recoverable"] is True
            assert error_message["data"]["suggested_action"] == "Please try again in a few minutes"
    
    async def test_multiple_client_broadcasting(
        self,
        websocket_test_client: TestClient,
        test_db_session: AsyncSession,
        sample_task: Task
    ):
        """Test broadcasting to multiple WebSocket clients."""
        
        task_id = sample_task.task_id
        session_ids = ["session-1", "session-2", "session-3"]
        
        # Create multiple WebSocket connections
        websockets = []
        for session_id in session_ids:
            ws = websocket_test_client.websocket_connect(f"/ws?session_id={session_id}")
            websocket = ws.__enter__()
            websockets.append((ws, websocket))
            
            # Subscribe each client to the task
            websocket.send_json({
                "type": "subscribe",
                "task_id": task_id
            })
            # Confirm subscription
            websocket.receive_json()
        
        try:
            # Broadcast update to all subscribers
            await websocket_manager.broadcast_to_task_subscribers(
                task_id=task_id,
                message_type="system-message",
                data={
                    "message": "Video generation starting",
                    "timestamp": time.time()
                }
            )
            
            # All clients should receive the message
            for _, websocket in websockets:
                message = websocket.receive_json()
                assert message["type"] == "system-message"
                assert message["data"]["message"] == "Video generation starting"
        
        finally:
            # Close all connections
            for ws_context, _ in websockets:
                ws_context.__exit__(None, None, None)
    
    async def test_websocket_message_queuing(
        self,
        websocket_test_client: TestClient,
        test_db_session: AsyncSession,
        sample_task: Task
    ):
        """Test message queuing when client is temporarily disconnected."""
        
        session_id = "test-session-123"
        task_id = sample_task.task_id
        
        # First connection
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            websocket.send_json({
                "type": "subscribe",
                "task_id": task_id
            })
            websocket.receive_json()  # Confirmation
        
        # Send messages while client is disconnected
        await websocket_manager.send_progress_update(
            session_id=session_id,
            task_id=task_id,
            progress=25,
            status="processing"
        )
        
        await websocket_manager.send_progress_update(
            session_id=session_id,
            task_id=task_id,
            progress=50,
            status="processing"
        )
        
        # Reconnect - should receive queued messages
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            websocket.send_json({
                "type": "subscribe",
                "task_id": task_id
            })
            websocket.receive_json()  # Confirmation
            
            # Should receive the latest state or queued messages
            # (Implementation dependent - might receive latest state only)
            message = websocket.receive_json()
            assert message["type"] in ["progress-update", "state-sync"]
    
    async def test_websocket_authentication(
        self,
        websocket_test_client: TestClient
    ):
        """Test WebSocket authentication and authorization."""
        
        # Test connection without session ID (should be rejected or get default session)
        try:
            with websocket_test_client.websocket_connect("/ws") as websocket:
                # Should either reject connection or assign default session
                pass
        except Exception as e:
            # Connection rejection is acceptable
            assert "session" in str(e).lower()
        
        # Test connection with invalid session format
        try:
            with websocket_test_client.websocket_connect("/ws?session_id=") as websocket:
                pass
        except Exception as e:
            # Connection rejection is acceptable for empty session ID
            pass
        
        # Test valid session ID
        with websocket_test_client.websocket_connect("/ws?session_id=valid-session-123") as websocket:
            # Should succeed
            assert websocket is not None
    
    async def test_websocket_connection_limits(
        self,
        websocket_test_client: TestClient
    ):
        """Test WebSocket connection limits and resource management."""
        
        max_connections = 10  # Reasonable limit for testing
        connections = []
        
        try:
            # Create multiple connections up to limit
            for i in range(max_connections):
                session_id = f"test-session-{i}"
                ws_context = websocket_test_client.websocket_connect(f"/ws?session_id={session_id}")
                websocket = ws_context.__enter__()
                connections.append((ws_context, websocket))
            
            # All connections should be successful
            assert len(connections) == max_connections
            
            # Verify connections are tracked
            assert len(websocket_manager.active_connections) >= max_connections
        
        finally:
            # Clean up connections
            for ws_context, _ in connections:
                try:
                    ws_context.__exit__(None, None, None)
                except:
                    pass
    
    async def test_websocket_message_validation(
        self,
        websocket_test_client: TestClient
    ):
        """Test WebSocket message validation."""
        
        session_id = "test-session-123"
        
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            # Test invalid message format
            try:
                websocket.send_text("invalid json")
                response = websocket.receive_json()
                assert response["type"] == "error"
                assert "invalid" in response["message"].lower()
            except:
                # Connection might be closed for invalid messages
                pass
            
            # Test missing required fields
            websocket.send_json({"invalid": "message"})
            response = websocket.receive_json()
            # Should handle gracefully or send error response
            assert response is not None
            
            # Test valid message
            websocket.send_json({
                "type": "ping",
                "timestamp": time.time()
            })
            response = websocket.receive_json()
            assert response["type"] in ["pong", "ack"]
    
    @pytest.mark.slow
    async def test_websocket_performance_under_load(
        self,
        websocket_test_client: TestClient,
        performance_thresholds: Dict[str, float]
    ):
        """Test WebSocket performance under load."""
        
        concurrent_connections = 5
        messages_per_connection = 20
        
        async def connection_handler(session_id: str) -> Dict[str, Any]:
            """Handle a single WebSocket connection with multiple messages."""
            results = {
                "session_id": session_id,
                "messages_sent": 0,
                "messages_received": 0,
                "total_time": 0,
                "errors": 0
            }
            
            start_time = time.time()
            
            try:
                with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
                    # Send multiple messages rapidly
                    for i in range(messages_per_connection):
                        try:
                            message = {
                                "type": "ping",
                                "sequence": i,
                                "timestamp": time.time()
                            }
                            
                            websocket.send_json(message)
                            results["messages_sent"] += 1
                            
                            # Receive response
                            response = websocket.receive_json()
                            if response:
                                results["messages_received"] += 1
                            
                            # Small delay to avoid overwhelming
                            await asyncio.sleep(0.01)
                            
                        except Exception as e:
                            results["errors"] += 1
                            print(f"Message error in {session_id}: {e}")
                            
            except Exception as e:
                results["errors"] += 1
                print(f"Connection error for {session_id}: {e}")
            
            results["total_time"] = time.time() - start_time
            return results
        
        # Run concurrent connections
        tasks = [
            connection_handler(f"load-test-session-{i}")
            for i in range(concurrent_connections)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        successful_results = [r for r in results if isinstance(r, dict)]
        
        total_messages_sent = sum(r["messages_sent"] for r in successful_results)
        total_messages_received = sum(r["messages_received"] for r in successful_results)
        total_errors = sum(r["errors"] for r in successful_results)
        
        message_success_rate = total_messages_received / total_messages_sent if total_messages_sent > 0 else 0
        error_rate = total_errors / (total_messages_sent + total_errors) if (total_messages_sent + total_errors) > 0 else 0
        
        # Verify performance criteria
        websocket_threshold = performance_thresholds.get('websocket_latency', 0.5)
        acceptable_error_rate = 0.05  # 5%
        
        assert len(successful_results) == concurrent_connections, f"Only {len(successful_results)} connections succeeded"
        assert message_success_rate >= 0.95, f"Message success rate {message_success_rate:.3f} too low"
        assert error_rate <= acceptable_error_rate, f"Error rate {error_rate:.3f} exceeds threshold"
        
        print(f"\\nWebSocket Load Test Results:")
        print(f"Concurrent connections: {concurrent_connections}")
        print(f"Messages per connection: {messages_per_connection}")
        print(f"Total messages sent: {total_messages_sent}")
        print(f"Total messages received: {total_messages_received}")
        print(f"Message success rate: {message_success_rate:.3f}")
        print(f"Error rate: {error_rate:.3f}")
    
    async def test_websocket_cleanup_on_disconnect(
        self,
        websocket_test_client: TestClient,
        test_db_session: AsyncSession
    ):
        """Test proper cleanup when WebSocket connections are closed."""
        
        session_id = "test-session-cleanup"
        initial_connections = len(websocket_manager.active_connections)
        
        # Create connection and verify it's tracked
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket:
            assert len(websocket_manager.active_connections) == initial_connections + 1
            
            # Subscribe to updates
            websocket.send_json({
                "type": "subscribe",
                "task_id": "test-task-123"
            })
            websocket.receive_json()  # Confirmation
        
        # Connection should be cleaned up after closing
        await asyncio.sleep(0.1)  # Allow cleanup
        
        assert len(websocket_manager.active_connections) == initial_connections
        assert session_id not in websocket_manager.active_connections
        
        # Subscriptions should also be cleaned up
        # (This would depend on the specific implementation)
    
    async def test_websocket_reconnection_handling(
        self,
        websocket_test_client: TestClient,
        test_db_session: AsyncSession,
        sample_task: Task
    ):
        """Test WebSocket reconnection handling."""
        
        session_id = "test-session-reconnect"
        task_id = sample_task.task_id
        
        # Initial connection
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket1:
            websocket1.send_json({
                "type": "subscribe",
                "task_id": task_id
            })
            websocket1.receive_json()  # Confirmation
        
        # Simulate disconnection and reconnection
        with websocket_test_client.websocket_connect(f"/ws?session_id={session_id}") as websocket2:
            # Should be able to resubscribe
            websocket2.send_json({
                "type": "subscribe",
                "task_id": task_id
            })
            confirmation = websocket2.receive_json()
            assert confirmation["type"] == "subscription_confirmed"
            
            # Should receive current state
            websocket2.send_json({
                "type": "get_status",
                "task_id": task_id
            })
            
            status_response = websocket2.receive_json()
            assert status_response["type"] in ["status_update", "current_state"]