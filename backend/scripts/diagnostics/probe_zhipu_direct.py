#!/usr/bin/env python3
"""Measure Zhipu chat completion latency with system proxy bypassed."""

from __future__ import annotations

import sys

from _zhipu_latency_probe import main as probe_main


if __name__ == "__main__":
    argv = ["--mode", "direct", *sys.argv[1:]]
    raise SystemExit(probe_main(argv))
