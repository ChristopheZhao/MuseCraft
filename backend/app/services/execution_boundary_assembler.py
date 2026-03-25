"""
Compatibility wrapper for the retired ExecutionBoundaryAssembler host name.

Active paths should depend on ContextContractAssembler from context_assembler.py.
"""
from __future__ import annotations

from .context_assembler import ContextContractAssembler


class ExecutionBoundaryAssembler(ContextContractAssembler):
    """Compatibility alias for callers not yet migrated to ContextContractAssembler."""


__all__ = ["ExecutionBoundaryAssembler"]
