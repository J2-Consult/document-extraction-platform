"""Adapters: Postgres, object storage, model providers, Validation Service client.

Each adapter implements exactly one port and must be substitutable with the
in-memory fake used in tests (Liskov substitution).
"""
