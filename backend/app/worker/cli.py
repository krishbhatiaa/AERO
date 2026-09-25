"""CLI entry point for the Redis-backed worker process.

Usage::

    python -m backend.app.worker.cli --redis-url redis://localhost:6379/0
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="Start the extreme-weather-ai worker process")
    ap.add_argument("--redis-url", default="redis://localhost:6379/0", help="Redis connection URL")
    args = ap.parse_args()

    from app.core.logging import configure_logging

    configure_logging("INFO")

    from app.worker.worker import run_worker

    try:
        run_worker(args.redis_url)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
