"""Template lineage (epic E08): extraction-oriented element relations across
template versions.

`model.py` defines the closed relation vocabulary and report shapes;
`generator.py` computes them from geometry and anchor text only. No business
meaning is inferred here — what an element MEANS belongs in decoder masks.

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from domain.lineage.generator import LineageGenerator
from domain.lineage.model import ElementRelation, LineageEntry, LineageReport

__all__ = ["ElementRelation", "LineageEntry", "LineageGenerator", "LineageReport"]
