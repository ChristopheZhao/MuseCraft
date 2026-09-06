"""
Published stage-deliverable helpers for gate/resume/downstream stable references.
"""
from __future__ import annotations

import json
import os
from enum import Enum
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from ..core.config import settings
from ..domain import JsonObjectPayload, RuntimePublishedDeliverableRecord

PUBLISHED_DELIVERABLES_PAYLOAD_KEY = "published_deliverables"
PUBLISHED_DELIVERABLE_REF_TYPE = "published_deliverable"
PUBLISHED_DELIVERABLE_REF_FIELDS = frozenset(
    {
        "type",
        "deliverable_id",
        "deliverable_type",
        "scope_type",
        "scope_id",
        "attempt_id",
        "revision_no",
        "payload_ref",
        "summary",
        "is_candidate",
        "is_approved",
    }
)


class PublishedDeliverablePayloadReason(str, Enum):
    REF_INVALID = "published_payload_ref_invalid"
    MISSING = "published_payload_missing"
    JSON_INVALID = "published_payload_json_invalid"
    READ_FAILED = "published_payload_read_failed"
    DELETE_FAILED = "published_payload_delete_failed"
    CONTRACT_INVALID = "published_payload_contract_invalid"


class PublishedDeliverableContractReason(str, Enum):
    PAYLOAD_INVALID = "published_deliverables_payload_invalid"
    COLLECTION_INVALID = "published_deliverables_collection_invalid"
    NODE_KEY_INVALID = "published_deliverables_node_key_invalid"
    REF_INVALID = "published_deliverable_ref_invalid"
    REF_UNKNOWN_KEYS = "published_deliverable_ref_unknown_keys"
    REF_MISSING_KEYS = "published_deliverable_ref_missing_keys"


class PublishedDeliverablePayloadError(ValueError):
    """Raised when a published deliverable payload violates its contract."""

    def __init__(
        self,
        reason_code: PublishedDeliverablePayloadReason,
        message: str,
        *,
        payload_ref: Optional[str] = None,
    ) -> None:
        self.reason_code = reason_code
        self.payload_ref = str(payload_ref or "")
        super().__init__(f"{self.reason_code.value}: {message}")


class PublishedDeliverableContractError(ValueError):
    """Raised when a published deliverable reference violates its contract."""

    def __init__(
        self,
        reason_code: PublishedDeliverableContractReason,
        message: str,
    ) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code.value}: {message}")


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_config_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (_project_root() / path).resolve()


def _published_deliverable_dir() -> Path:
    return _resolve_config_path(str(settings.TEMP_PATH)) / "published_deliverables"


def _resolve_payload_path(payload_ref: str) -> Path:
    ref_path = Path(str(payload_ref or ""))
    if ref_path.is_absolute():
        return ref_path
    return (_backend_root() / ref_path).resolve()


def persist_published_payload(
    *,
    workflow_id: str,
    deliverable_type: str,
    attempt_id: int,
    revision_no: int,
    payload: Dict[str, Any],
) -> str:
    base_dir = _published_deliverable_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{deliverable_type}_{workflow_id}_attempt{attempt_id}_rev{revision_no}_"
        f"{uuid4().hex}.json"
    )
    target_path = (base_dir / filename).resolve()
    temporary_path = target_path.with_suffix(".tmp")
    try:
        with open(temporary_path, "x", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(temporary_path, target_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return str(target_path)


def discard_published_payload(payload_ref: str) -> None:
    payload_path = _resolve_payload_path(payload_ref)
    owned_root = _published_deliverable_dir().resolve()
    try:
        payload_path.relative_to(owned_root)
    except ValueError as exc:
        raise PublishedDeliverablePayloadError(
            PublishedDeliverablePayloadReason.REF_INVALID,
            "Refusing to delete a payload outside the published deliverable directory",
            payload_ref=payload_ref,
        ) from exc
    try:
        payload_path.unlink(missing_ok=True)
    except OSError as exc:
        raise PublishedDeliverablePayloadError(
            PublishedDeliverablePayloadReason.DELETE_FAILED,
            f"Payload file cannot be deleted: {type(exc).__name__}",
            payload_ref=payload_ref,
        ) from exc


def load_published_payload(payload_ref: Optional[str]) -> Optional[JsonObjectPayload]:
    if not payload_ref:
        return None
    payload_ref_value = str(payload_ref)
    try:
        payload_path = _resolve_payload_path(payload_ref_value)
    except Exception as exc:
        raise PublishedDeliverablePayloadError(
            PublishedDeliverablePayloadReason.REF_INVALID,
            f"Cannot resolve payload_ref: {type(exc).__name__}",
            payload_ref=payload_ref_value,
        ) from exc
    if not payload_path.exists():
        raise PublishedDeliverablePayloadError(
            PublishedDeliverablePayloadReason.MISSING,
            f"Payload file does not exist: {payload_path}",
            payload_ref=payload_ref_value,
        )
    try:
        with open(payload_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except JSONDecodeError as exc:
        raise PublishedDeliverablePayloadError(
            PublishedDeliverablePayloadReason.JSON_INVALID,
            f"Payload JSON is invalid: {exc.msg}",
            payload_ref=payload_ref_value,
        ) from exc
    except OSError as exc:
        raise PublishedDeliverablePayloadError(
            PublishedDeliverablePayloadReason.READ_FAILED,
            f"Payload file cannot be read: {type(exc).__name__}",
            payload_ref=payload_ref_value,
        ) from exc
    if not isinstance(payload, dict):
        raise PublishedDeliverablePayloadError(
            PublishedDeliverablePayloadReason.CONTRACT_INVALID,
            f"Payload root must be dict, got {type(payload).__name__}",
            payload_ref=payload_ref_value,
        )
    try:
        return JsonObjectPayload.from_mapping(
            payload,
            field_path="published_deliverable.payload",
        )
    except (TypeError, ValueError) as exc:
        raise PublishedDeliverablePayloadError(
            PublishedDeliverablePayloadReason.CONTRACT_INVALID,
            "Payload contains values outside the JSON object contract",
            payload_ref=payload_ref_value,
        ) from exc


def build_deliverable_ref(deliverable: RuntimePublishedDeliverableRecord) -> Dict[str, Any]:
    return {
        "type": PUBLISHED_DELIVERABLE_REF_TYPE,
        "deliverable_id": deliverable.deliverable_id,
        "deliverable_type": deliverable.deliverable_type,
        "scope_type": deliverable.scope_type,
        "scope_id": deliverable.scope_id,
        "attempt_id": deliverable.attempt_id,
        "revision_no": deliverable.revision_no,
        "payload_ref": deliverable.payload_ref,
        "summary": deliverable.summary.to_dict(),
        "is_candidate": deliverable.is_candidate,
        "is_approved": deliverable.is_approved,
    }


def normalize_published_deliverable_ref(ref: object) -> Dict[str, Any]:
    if not isinstance(ref, dict):
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.REF_INVALID,
            "published deliverable reference must be an object",
        )
    unknown_keys = set(ref) - PUBLISHED_DELIVERABLE_REF_FIELDS
    if unknown_keys:
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.REF_UNKNOWN_KEYS,
            "unknown keys: " + ",".join(sorted(str(key) for key in unknown_keys)),
        )
    missing_keys = PUBLISHED_DELIVERABLE_REF_FIELDS - set(ref)
    if missing_keys:
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.REF_MISSING_KEYS,
            "missing keys: " + ",".join(sorted(missing_keys)),
        )
    if ref["type"] != PUBLISHED_DELIVERABLE_REF_TYPE:
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.REF_INVALID,
            "reference type must be published_deliverable",
        )
    for field_name in ("deliverable_id", "attempt_id"):
        value = ref[field_name]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise PublishedDeliverableContractError(
                PublishedDeliverableContractReason.REF_INVALID,
                f"{field_name} must be a positive integer",
            )
    revision_no = ref["revision_no"]
    if not isinstance(revision_no, int) or isinstance(revision_no, bool) or revision_no < 0:
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.REF_INVALID,
            "revision_no must be a non-negative integer",
        )
    for field_name in ("deliverable_type", "scope_type", "payload_ref"):
        value = ref[field_name]
        if not isinstance(value, str) or not value.strip():
            raise PublishedDeliverableContractError(
                PublishedDeliverableContractReason.REF_INVALID,
                f"{field_name} must be a non-empty string",
            )
    scope_id = ref["scope_id"]
    if scope_id is not None and not isinstance(scope_id, str):
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.REF_INVALID,
            "scope_id must be a string or null",
        )
    if not isinstance(ref["is_candidate"], bool) or not isinstance(ref["is_approved"], bool):
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.REF_INVALID,
            "candidate and approval flags must be booleans",
        )
    try:
        summary = JsonObjectPayload.from_mapping(
            ref["summary"],
            field_path="published_deliverable_ref.summary",
        ).to_dict()
    except (TypeError, ValueError) as exc:
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.REF_INVALID,
            "summary must satisfy the JSON object contract",
        ) from exc
    normalized = dict(ref)
    normalized["summary"] = summary
    return normalized


def get_published_deliverables(payload: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.PAYLOAD_INVALID,
            "runtime payload must be an object",
        )
    deliverables = payload.get(PUBLISHED_DELIVERABLES_PAYLOAD_KEY)
    if deliverables is None:
        return {}
    if not isinstance(deliverables, dict):
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.COLLECTION_INVALID,
            "published_deliverables must be an object",
        )
    normalized: Dict[str, Dict[str, Any]] = {}
    for node_key, ref in deliverables.items():
        if not isinstance(node_key, str) or not node_key.strip():
            raise PublishedDeliverableContractError(
                PublishedDeliverableContractReason.NODE_KEY_INVALID,
                "published deliverable node keys must be non-empty strings",
            )
        normalized[node_key] = normalize_published_deliverable_ref(ref)
    return normalized


def get_published_deliverable_ref(
    payload: Optional[Dict[str, Any]],
    *,
    node_key: str,
) -> Optional[Dict[str, Any]]:
    refs = get_published_deliverables(payload)
    ref = refs.get(node_key)
    return dict(ref) if isinstance(ref, dict) else None


def set_published_deliverable_ref(
    payload: Optional[Dict[str, Any]],
    *,
    node_key: str,
    ref: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(node_key, str) or not node_key.strip():
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.NODE_KEY_INVALID,
            "published deliverable node key must be a non-empty string",
        )
    if payload is not None and not isinstance(payload, dict):
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.PAYLOAD_INVALID,
            "runtime payload must be an object",
        )
    merged = dict(payload or {})
    deliverables = get_published_deliverables(merged)
    deliverables[node_key] = normalize_published_deliverable_ref(ref)
    merged[PUBLISHED_DELIVERABLES_PAYLOAD_KEY] = deliverables
    return merged


def clear_published_deliverable_ref(
    payload: Optional[Dict[str, Any]],
    *,
    node_key: str,
) -> Dict[str, Any]:
    if not isinstance(node_key, str) or not node_key.strip():
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.NODE_KEY_INVALID,
            "published deliverable node key must be a non-empty string",
        )
    if payload is not None and not isinstance(payload, dict):
        raise PublishedDeliverableContractError(
            PublishedDeliverableContractReason.PAYLOAD_INVALID,
            "runtime payload must be an object",
        )
    merged = dict(payload or {})
    deliverables = get_published_deliverables(merged)
    deliverables.pop(node_key, None)
    if deliverables:
        merged[PUBLISHED_DELIVERABLES_PAYLOAD_KEY] = deliverables
    else:
        merged.pop(PUBLISHED_DELIVERABLES_PAYLOAD_KEY, None)
    return merged
