#!/usr/bin/env python3
"""Measure Zhipu chat completion latency with system proxy enabled."""

from __future__ import annotations

import os
import sys

from _zhipu_latency_probe import main as probe_main


if __name__ == "__main__":
    argv = ["--mode", "proxy", *sys.argv[1:]]
    raise SystemExit(probe_main(argv))
