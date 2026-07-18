#!/usr/bin/env python3
"""Reconcile stale quick runtimes from the control plane.

This script is intentionally narrow:
- It only inspects quick-mode sessions in RUNNING/RESUMING.
- It uses typed control-plane facts through the runtime store.
- It marks irrecoverable stale runtimes failed when the execution lease is gone
  and no continuation checkpoint exists.
"""

from __future__ import annotations

import argparse
import json

from app.core.database import SessionLocal
from app.infrastructure import SqlAlchemyRuntimeAttemptStore
from app.services.runtime_reconciler import RuntimeReconciler


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile irrecoverable stale quick runtimes.")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of non-terminal quick sessions to inspect.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        try:
            summary = RuntimeReconciler(
                SqlAlchemyRuntimeAttemptStore(db)
            ).reconcile_irrecoverable_quick_runtimes(limit=args.limit)
            db.commit()
        except Exception:
            db.rollback()
            raise

    print(json.dumps(summary.to_dict(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
