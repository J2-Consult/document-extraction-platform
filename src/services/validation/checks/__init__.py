"""One module per invariant (or tightly related invariant group), each
implementing `InvariantCheck` (src/services/validation/bundle.py). New
invariant = new module here + a registration in `validator.default_validator`;
existing checks are never edited (open/closed)."""

from __future__ import annotations
