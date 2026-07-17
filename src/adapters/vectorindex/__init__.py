"""`VectorIndex` port adapters (epic E11).

`in_memory.py` is the reference implementation the shared contract suite
(`tests/unit/adapters/vectorindex/test_contract.py`) runs against; a future
real backend (pgvector, a managed vector DB, ...) implements the same port
and is exercised by the identical suite.
"""

from __future__ import annotations
