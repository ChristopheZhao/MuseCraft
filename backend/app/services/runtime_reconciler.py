"""Explicit control-plane maintenance for irrecoverable quick runtimes."""

from __future__ import annotations

import logging

from ..core.constants import GenerationMode
from ..domain import (
    JsonObjectPayload,
    RuntimeMaintenanceStore,
    WorkflowSessionStatus,
)
from .runtime_read_model_service import RuntimeReadModelService
from .runtime_session_control_plane import RuntimeSessionControlPlane


class RuntimeReconciler:
    """Turns committed runtime facts into explicit fail-closed transitions."""

    def __init__(
        self,
        store: RuntimeMaintenanceStore,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._store = store
        self._logger = logger or logging.getLogger("runtime_reconciler")

    def reconcile_irrecoverable_quick_runtimes(self, *, limit: int) -> JsonObjectPayload:
        if limit <= 0:
            raise ValueError("runtime reconcile limit must be positive")
        candidates = self._store.load_reconcilable_sessions(
            mode=GenerationMode.QUICK.value,
            statuses=(WorkflowSessionStatus.RUNNING, WorkflowSessionStatus.RESUMING),
            limit=limit,
        )
        inspected = 0
        failed = 0
        skipped = 0
        read_models = RuntimeReadModelService(self._store)
        control_plane = RuntimeSessionControlPlane(self._store)
        for candidate in candidates:
            inspected += 1
            model = read_models.load_for_session(candidate.session_id)
            if model is None:
                skipped += 1
                continue
            resume_control = (
                model.resume_control.to_dict() if model.resume_control is not None else None
            )
            if (
                resume_control is None
                or resume_control.get("state") != "resume_blocked"
                or resume_control.get("reason_code") != "missing_continuation_checkpoint"
            ):
                skipped += 1
                continue

            error_message = (
                "Stale quick runtime detected: execution lease is no longer active and "
                "continuation checkpoint is missing"
            )
            self._logger.warning(
                "Marking irrecoverable stale quick runtime failed: task_id=%s session_id=%s node=%s",
                candidate.task_id,
                candidate.session_id,
                candidate.current_node_key,
            )
            control_plane.mark_failed(
                candidate.session_id,
                error_message=error_message,
            )
            failed += 1

        return JsonObjectPayload.from_mapping(
            {
                "inspected": inspected,
                "failed": failed,
                "skipped": skipped,
            },
            field_path="runtime_reconciler.summary",
        )
