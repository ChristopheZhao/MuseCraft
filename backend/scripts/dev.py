#!/usr/bin/env python3
"""Forward the short development command to the canonical uv launcher."""

from __future__ import annotations

if __package__:
    from .start_dev_uv import main
else:
    from start_dev_uv import main


if __name__ == "__main__":
    raise SystemExit(main())
