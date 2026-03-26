"""
WebSocket integration tests aligned with the current endpoint and manager contract.
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.services.websocket import websocket_manager


@pytest.fixture(autouse=True)
def reset_websocket_manager_state():
    websocket_manager.task_connections.clear()
    websocket_manager.active_connections.clear()
    websocket_manager.connection_metadata.clear()
    yield
    websocket_manager.task_connections.clear()
    websocket_manager.active_connections.clear()
    websocket_manager.connection_metadata.clear()


@pytest.mark.websocket
@pytest.mark.asyncio
class TestWebSocketIntegration:
    """Focused coverage for the current `/api/v1/ws/connect` surface."""

    async def test_connection_establishment_and_ping(
        self,
        websocket_test_client: TestClient,
    ):
        with websocket_test_client.websocket_connect("/api/v1/ws/connect") as websocket:
            confirmation = websocket.receive_json()
            assert confirmation["type"] == "connection_established"
            assert confirmation["task_id"] is None

            websocket.send_json({
                "type": "ping",
                "timestamp": time.time(),
            })
            response = websocket.receive_json()
            assert response["type"] == "pong"

    async def test_connect_with_task_id_tracks_task_connection(
        self,
        websocket_test_client: TestClient,
    ):
        task_id = "task-123"

        with websocket_test_client.websocket_connect(f"/api/v1/ws/connect?task_id={task_id}") as websocket:
            confirmation = websocket.receive_json()
            assert confirmation["type"] == "connection_established"
            assert confirmation["task_id"] == task_id

            stats = websocket_manager.get_connection_stats()
            assert stats["total_connections"] == 1
            assert stats["task_connections"][task_id] == 1

    async def test_subscribe_task_message_enables_task_broadcast(
        self,
        websocket_test_client: TestClient,
    ):
        task_id = "task-123"

        with websocket_test_client.websocket_connect("/api/v1/ws/connect") as websocket:
            websocket.receive_json()

            websocket.send_json({
                "type": "subscribe_task",
                "task_id": task_id,
            })
            subscribed = websocket.receive_json()
            assert subscribed["type"] == "subscription_confirmed"
            assert subscribed["task_id"] == task_id

            await websocket_manager.broadcast_to_task(task_id, {
                "type": "event.progress",
                "agent_type": "script_writer",
                "payload": {
                    "progress": 50,
                    "current_step": "Drafting scene 2 of 5",
                },
            })

            message = websocket.receive_json()
            assert message["type"] == "event.progress"
            assert message["agent_type"] == "script_writer"
            assert message["payload"]["progress"] == 50

    async def test_broadcast_to_task_delivers_runtime_state_and_result(
        self,
        websocket_test_client: TestClient,
    ):
        task_id = "task-123"

        with websocket_test_client.websocket_connect(f"/api/v1/ws/connect?task_id={task_id}") as websocket:
            websocket.receive_json()

            await websocket_manager.broadcast_to_task(task_id, {
                "type": "event.state",
                "agent_name": "image_generator",
                "payload": {
                    "status": "running",
                },
            })
            state_message = websocket.receive_json()
            assert state_message["type"] == "event.state"
            assert state_message["agent_name"] == "image_generator"
            assert state_message["payload"]["status"] == "running"

            await websocket_manager.broadcast_to_task(task_id, {
                "type": "result-ready",
                "data": {
                    "requestId": task_id,
                    "type": "video",
                    "id": "video-result-123",
                    "status": "completed",
                    "content": {
                        "video_url": "https://example.com/generated-video.mp4",
                    },
                    "agent": "video-composer",
                },
            })
            result_message = websocket.receive_json()
            assert result_message["type"] == "result-ready"
            assert result_message["data"]["requestId"] == task_id
            assert result_message["data"]["content"]["video_url"] == "https://example.com/generated-video.mp4"

    async def test_send_system_notification_broadcasts_to_all_connections(
        self,
        websocket_test_client: TestClient,
    ):
        with websocket_test_client.websocket_connect("/api/v1/ws/connect") as websocket_a:
            websocket_a.receive_json()
            with websocket_test_client.websocket_connect("/api/v1/ws/connect") as websocket_b:
                websocket_b.receive_json()

                await websocket_manager.send_system_notification("Maintenance window", level="warning")

                message_a = websocket_a.receive_json()
                message_b = websocket_b.receive_json()
                assert message_a["type"] == "system_notification"
                assert message_b["type"] == "system_notification"
                assert message_a["message"] == "Maintenance window"
                assert message_b["message"] == "Maintenance window"

    async def test_invalid_messages_do_not_break_subsequent_ping(
        self,
        websocket_test_client: TestClient,
    ):
        with websocket_test_client.websocket_connect("/api/v1/ws/connect") as websocket:
            websocket.receive_json()

            websocket.send_text("invalid json")
            websocket.send_json({"invalid": "message"})

            websocket.send_json({
                "type": "ping",
                "timestamp": time.time(),
            })
            response = websocket.receive_json()
            assert response["type"] == "pong"

    async def test_cleanup_stale_connections_removes_idle_websockets(
        self,
        websocket_test_client: TestClient,
    ):
        with websocket_test_client.websocket_connect("/api/v1/ws/connect?task_id=task-123") as websocket:
            websocket.receive_json()
            assert len(websocket_manager.active_connections) == 1

            tracked_ws = next(iter(websocket_manager.connection_metadata.keys()))
            websocket_manager.connection_metadata[tracked_ws]["last_ping"] = datetime.now() - timedelta(minutes=31)

            await websocket_manager.cleanup_stale_connections(max_idle_minutes=30)
            await asyncio.sleep(0.1)

            assert len(websocket_manager.active_connections) == 0
            assert websocket_manager.task_connections == {}
