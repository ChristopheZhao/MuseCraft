"""Environment-loading contract tests."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_process_environment_overrides_local_dotenv() -> None:
    expected_url = "postgresql://explicit:explicit@localhost:5432/explicit"
    env = os.environ.copy()
    env["DATABASE_URL"] = expected_url
    env["PYTHONPATH"] = str(BACKEND_ROOT)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.core.config import settings; print(settings.DATABASE_URL)",
        ],
        cwd=BACKEND_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == expected_url
