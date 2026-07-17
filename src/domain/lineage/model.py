"""Lineage report shapes (specs/design/E08-interfaces.md).

One `LineageEntry` relates a set of old-template elements to a set of
new-template elements with a closed relation vocabulary. Cardinality is part
of each relation's meaning (a "compatible" element is 1:1 by definition), so
the model enforces it — an entry that claims "split" with one new element is
malformed, not a judgement call.

Extraction-oriented ONLY: entries carry element ids and an evidence note about
geometry/anchor text. No business meaning is inferred or represented.

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.artifacts.template import TemplateRef

ElementRelation = Literal["compatible", "split", "merged", "added", "removed", "ambiguous"]

# relation -> (old-side cardinality predicate, new-side cardinality predicate),
# expressed as inclusive (min, max) bounds; None means unbounded.
_CARDINALITY: dict[str, tuple[tuple[int, int | None], tuple[int, int | None]]] = {
    "compatible": ((1, 1), (1, 1)),
    "split": ((1, 1), (2, None)),
    "merged": ((2, None), (1, 1)),
    "added": ((0, 0), (1, 1)),
    "removed": ((1, 1), (0, 0)),
    "ambiguous": ((0, None), (0, None)),
}


def _within(count: int, bounds: tuple[int, int | None]) -> bool:
    minimum, maximum = bounds
    return count >= minimum and (maximum is None or count <= maximum)


class LineageEntry(BaseModel):
    """One relation between old-template elements and new-template elements."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    old_element_ids: tuple[str, ...]
    new_element_ids: tuple[str, ...]
    relation: ElementRelation
    evidence: str = Field(min_length=1)

    @model_validator(mode="after")
    def _cardinality_matches_relation(self) -> LineageEntry:
        old_bounds, new_bounds = _CARDINALITY[self.relation]
        if not _within(len(self.old_element_ids), old_bounds):
            raise ValueError(f"relation '{self.relation}' does not allow {len(self.old_element_ids)} old elements")
        if not _within(len(self.new_element_ids), new_bounds):
            raise ValueError(f"relation '{self.relation}' does not allow {len(self.new_element_ids)} new elements")
        if self.relation == "ambiguous" and not (self.old_element_ids or self.new_element_ids):
            raise ValueError("an ambiguous entry must involve at least one element")
        for side, ids in (("old", self.old_element_ids), ("new", self.new_element_ids)):
            if len(set(ids)) != len(ids):
                raise ValueError(f"duplicate {side} element ids in lineage entry")
        return self


class LineageReport(BaseModel):
    """Per-element lineage between two versions of one template."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    from_ref: TemplateRef
    to_ref: TemplateRef
    entries: tuple[LineageEntry, ...]

    def entry_for_old(self, element_id: str) -> LineageEntry | None:
        """The single entry whose old side contains `element_id`, if any."""
        for entry in self.entries:
            if element_id in entry.old_element_ids:
                return entry
        return None
