"""Postgres reachability check shared by Makefile targets and test fixtures.

This checks TCP reachability only, not authentication — enough to decide
whether a DB-backed test target should run for real or degrade to a skip.
Tooling, not domain code: intentionally outside the hexagonal src/ layout.
"""

from __future__ import annotations

import os
import socket
import sys

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 5432
DEFAULT_TIMEOUT = 2.0


def postgres_available(
    host: str | None = None,
    port: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """Return True iff a TCP connection to the Postgres host:port succeeds."""
    resolved_host = host or os.environ.get("POSTGRES_HOST", DEFAULT_HOST)
    resolved_port = port or int(os.environ.get("POSTGRES_PORT", str(DEFAULT_PORT)))
    try:
        with socket.create_connection((resolved_host, resolved_port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    return 0 if postgres_available() else 1


if __name__ == "__main__":
    sys.exit(main())
