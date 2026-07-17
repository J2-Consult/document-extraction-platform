"""Embedding pipeline application services (epic E11).

Two-tier, version-paired embedding sets: `chunkers.py` turns decoded document
rows into indexable `Chunk`s (semantic tier for masked documents, structural
tier for unmasked ones); `embedder.py` is the deterministic fake embedding
model; `decoded_view.py` converts E07's typed read-side rows into chunker
input; `builds.py` orchestrates async, version-paired, idempotently-resumable
builds against the E03 `JobQueue` and the `VectorIndex` port.

Constructor injection only; no globals, no service locator.
"""

from __future__ import annotations
