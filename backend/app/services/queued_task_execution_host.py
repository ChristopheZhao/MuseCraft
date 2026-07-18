"""Process host for persistence-free Agent execution."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from ..domain import AgentExecutionRequest, AgentExecutionResult
from ..events.provider import reset_event_bus
from .execution_host_lease import (
    AttemptLeaseKeepaliveController,
    ExecutionHostLeaseContext,
    reset_current_execution_host_lease_context,
    set_current_execution_host_lease_context,
)


class AgentExecutor(Protocol):
    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        ...


def prepare_queued_execution_host(*, logger: logging.Logger | None = None) -> None:
    """Prepare process-local tools and events before Agent execution."""

    logger = logger or logging.getLogger("queued_execution_host")
    from ..agents.tools import register_default_tools

    register_default_tools()
    reset_event_bus()
    logger.info("Queued execution host process state initialized")


def run_agent_execution_in_host(
    *,
    request: AgentExecutionRequest,
    executor: AgentExecutor,
    attempt_lease_keepalive: AttemptLeaseKeepaliveController | None = None,
) -> AgentExecutionResult:
    """Run one typed Agent request while owning process lifecycle only."""

    if not isinstance(request, AgentExecutionRequest):
        raise TypeError("queued execution host requires AgentExecutionRequest")

    logger = logging.getLogger("queued_execution_host")
    loop: asyncio.AbstractEventLoop | None = None
    host_context_token = None

    try:
        prepare_queued_execution_host(logger=logger)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        host_context_token = set_current_execution_host_lease_context(
            ExecutionHostLeaseContext(attempt_lease_keepalive=attempt_lease_keepalive)
        )
        result = loop.run_until_complete(executor.execute(request))
        if not isinstance(result, AgentExecutionResult):
            raise TypeError("Agent executor returned a non-AgentExecutionResult value")
        return result
    finally:
        if host_context_token is not None:
            reset_current_execution_host_lease_context(host_context_token)
        if attempt_lease_keepalive is not None:
            attempt_lease_keepalive.close()
        if loop is not None:
            loop.close()
            asyncio.set_event_loop(None)
