import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

DEFAULT_SCHEMA_VERSION = "1.0"
# 约束：事件载荷建议 <16KB，超出时需截断并标记
DEFAULT_MAX_PAYLOAD_BYTES = 16 * 1024


class EventKind(str, Enum):
    PROGRESS = "progress"
    STATE = "state"
    ARTIFACT = "artifact"
    ERROR = "error"
    DIAGNOSTIC = "diagnostic"


logger = logging.getLogger(__name__)


@dataclass
class Event:
    """
    统一的事件结构，供 Agent 发布、监听器消费。
    注意：payload 需可 JSON 序列化，超出大小时会截断并标记。
    """

    event_kind: EventKind
    payload: Dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    workflow_state_id: Optional[str] = None
    agent_type: Optional[str] = None
    agent_name: Optional[str] = None
    iteration: Optional[int] = None
    scene_number: Optional[int] = None
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = DEFAULT_SCHEMA_VERSION
    sequence: Optional[int] = None

    def clamp_payload(self, max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES) -> None:
        """
        确保 payload 可序列化且不超大小限制。
        超限时保留预览并标记 truncated，避免监听器 silent fail。
        """
        try:
            payload_json = json.dumps(self.payload, default=str)
        except Exception as exc:
            raise ValueError(f"Payload not JSON-serializable: {exc}") from exc

        payload_bytes = payload_json.encode("utf-8")
        if len(payload_bytes) <= max_payload_bytes:
            return

        # 截断：保留预览与统计，避免破坏 schema
        preview = payload_json[: min(len(payload_json), 512)]
        omitted = len(payload_bytes) - max_payload_bytes
        self.payload = {
            "truncated": True,
            "omitted_bytes": omitted,
            "preview": f"{preview}...<truncated>",
        }
        logger.warning(
            "Event payload truncated (kind=%s, omitted=%s bytes)",
            self.event_kind.value,
            omitted,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "schema_version": self.schema_version,
            "event_kind": self.event_kind.value,
            "task_id": self.task_id,
            "workflow_state_id": self.workflow_state_id,
            "agent_type": self.agent_type,
            "agent_name": self.agent_name,
            "iteration": self.iteration,
            "scene_number": self.scene_number,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "payload": self.payload,
        }
