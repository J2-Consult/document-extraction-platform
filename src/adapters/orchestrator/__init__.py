"""Postgres-backed implementation of the E10 retrieval port.

Lives in adapters/ (not services/orchestrator/) so the LLM-facing service
package stays free of DB drivers — enforced by the E10 architecture test.
"""
