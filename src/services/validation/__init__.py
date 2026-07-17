"""InvariantValidator: the platform's contract law.

Pure domain service (no I/O, no framework imports) enforcing the cross-field
and cross-artifact invariants src/domain/artifacts/'s Pydantic models cannot
express on their own. See validator.py for the composition root and
checks/ for one module per invariant group.
"""

from __future__ import annotations

from services.validation.bundle import ArtifactBundle, InvariantCheck
from services.validation.validator import InvariantValidator, default_validator

__all__ = ["ArtifactBundle", "InvariantCheck", "InvariantValidator", "default_validator"]
