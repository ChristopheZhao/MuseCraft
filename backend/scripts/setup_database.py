#!/usr/bin/env python3
"""Apply the tracked database schema migrations."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_CONFIG = BACKEND_ROOT / "alembic.ini"


def run_migrations() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_CONFIG),
            "upgrade",
            "head",
        ],
        cwd=BACKEND_ROOT,
        check=True,
    )


def main() -> int:
    try:
        run_migrations()
    except FileNotFoundError as exc:
        print(f"Database setup failed: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"Database migration failed with exit code {exc.returncode}.",
            file=sys.stderr,
        )
        return exc.returncode or 1

    print("Database schema is at the tracked Alembic head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
