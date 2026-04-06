#!/usr/bin/env python3
"""Reset development Celery broker/result state for quick-mode HITL debugging.

This script is intentionally narrow:
- It only operates on CELERY_BROKER_URL and CELERY_RESULT_BACKEND.
- It refuses non-Redis backends.
- It prints the target DBs first and requires --yes to perform the reset.

Use it only in the local development environment after stopping the worker/API.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from urllib.parse import urlparse

import redis

from app.core.config import settings


@dataclass(frozen=True)
class RedisTarget:
    label: str
    url: str
    host: str
    port: int
    db: int


def _parse_redis_target(label: str, url: str) -> RedisTarget:
    parsed = urlparse(url)
    if parsed.scheme not in {"redis", "rediss"}:
        raise ValueError(f"{label} must use a redis:// or rediss:// URL, got: {url}")
    if not parsed.hostname:
        raise ValueError(f"{label} missing hostname: {url}")
    db = int((parsed.path or "/0").lstrip("/") or "0")
    return RedisTarget(
        label=label,
        url=url,
        host=parsed.hostname,
        port=parsed.port or 6379,
        db=db,
    )


def _build_targets() -> list[RedisTarget]:
    targets = [
        _parse_redis_target("CELERY_BROKER_URL", settings.CELERY_BROKER_URL),
        _parse_redis_target("CELERY_RESULT_BACKEND", settings.CELERY_RESULT_BACKEND),
    ]
    deduped: list[RedisTarget] = []
    seen = set()
    for target in targets:
        key = (target.host, target.port, target.db)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return deduped


def _flush_target(target: RedisTarget) -> None:
    client = redis.Redis.from_url(target.url)
    client.ping()
    client.flushdb()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset local Celery broker/result Redis state.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually flush the configured Celery broker/result Redis DBs.",
    )
    args = parser.parse_args()

    targets = _build_targets()

    print("Celery Redis targets:")
    for target in targets:
        print(f"- {target.label}: {target.host}:{target.port}/{target.db}")

    if not args.yes:
        print("\nDry run only. Re-run with --yes after stopping API and Celery worker.")
        return 0

    for target in targets:
        _flush_target(target)
        print(f"Flushed {target.label} ({target.host}:{target.port}/{target.db})")

    print("\nCelery broker/result Redis state reset completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
