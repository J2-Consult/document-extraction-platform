"""Coordinate-space and transform model for provenance (E06).

Extends E01's `domain.artifacts.provenance.Provenance` shape (owned there,
never edited here) with the mechanics that make "provenance to pixels"
mechanically true: per-page geometry, preprocessing records, and the affine
transform utilities that map a bbox between working space and source space.

Pure Python throughout: no I/O, no framework imports (not even pydantic —
these are computational value objects, not artifact-boundary shapes).
"""

from __future__ import annotations
