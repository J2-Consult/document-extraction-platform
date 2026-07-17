"""E11 chunkers: decoded document rows -> indexable `Chunk`s, two tiers.

One `Chunker` protocol, two implementations (architecture §6.3):

- `SemanticChunker` — masked documents. Consumes the decoded view (E07's
  query surface joined through the ONE selected mask): each row already
  carries text + semantic_role + section_path + system_context + provenance,
  and each row IS a chunk — the mask's semantic boundaries are the chunk
  boundaries, no windowing.
- `StructuralChunker` — unmasked documents. Token window + overlap over each
  element's text; `section_path` comes from the template's heading hierarchy
  (`assign_section_paths_from_heading_hierarchy`); page + bbox ride on every
  chunk.

Provenance is mandatory on every chunk (criterion 9 extension): a chunk
without provenance is unrepresentable — `DecodedElement.provenance` is not
optional and both chunkers copy it through verbatim.

Pure service logic: no I/O, no DB drivers, no framework imports.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol, runtime_checkable

from domain.artifacts.template import TemplateElement

# Leading dotted section number of a heading label, e.g. "13.4 Bearing
# Inspection" -> "13.4". A heading without one has no section_path.
_SECTION_NUMBER_PATTERN = re.compile(r"^(\d+(?:\.\d+)+)\s")


class MissingSemanticRoleError(Exception):
    """A row reached the semantic tier without a mask-resolved semantic_role."""


class InvalidWindowError(Exception):
    """Structural window/overlap parameters that cannot produce forward progress."""


@dataclass(frozen=True, slots=True)
class DecodedElement:
    """One decoded value row, chunker input (from E07's typed read seam)."""

    document_id: str
    element_id: str
    text: str
    page: int
    bbox: tuple[float, float, float, float]
    provenance: Mapping[str, Any]
    semantic_role: str | None = None
    system_context: str | None = None
    section_path: str | None = None


@dataclass(frozen=True, slots=True)
class Chunk:
    """One indexable unit: text + metadata + provenance, never more."""

    chunk_id: str
    document_id: str
    element_id: str
    chunk_index: int
    text: str
    page: int
    bbox: tuple[float, float, float, float]
    provenance: Mapping[str, Any]
    semantic_role: str | None = None
    system_context: str | None = None
    section_path: str | None = None


@runtime_checkable
class Chunker(Protocol):
    def chunk(self, elements: Sequence[DecodedElement]) -> tuple[Chunk, ...]:
        """Turn decoded rows into chunks; every chunk carries provenance."""
        ...


def _chunk_id(document_id: str, element_id: str, index: int) -> str:
    return f"{document_id}:{element_id}:{index}"


def _chunk_from_element(element: DecodedElement, index: int, text: str) -> Chunk:
    return Chunk(
        chunk_id=_chunk_id(element.document_id, element.element_id, index),
        document_id=element.document_id,
        element_id=element.element_id,
        chunk_index=index,
        text=text,
        page=element.page,
        bbox=element.bbox,
        provenance=element.provenance,
        semantic_role=element.semantic_role,
        system_context=element.system_context,
        section_path=element.section_path,
    )


class SemanticChunker:
    """Semantic tier: one chunk per mask-resolved decoded row."""

    def chunk(self, elements: Sequence[DecodedElement]) -> tuple[Chunk, ...]:
        for element in elements:
            if element.semantic_role is None:
                raise MissingSemanticRoleError(
                    f"element {element.element_id} of {element.document_id} has no "
                    "semantic_role — semantic chunking requires mask-resolved rows"
                )
        return tuple(_chunk_from_element(element, 0, element.text) for element in elements)


class StructuralChunker:
    """Structural tier: whitespace-token windows with explicit overlap."""

    def __init__(self, *, window_tokens: int, overlap_tokens: int) -> None:
        if window_tokens < 1:
            raise InvalidWindowError(f"window_tokens must be >= 1, got {window_tokens}")
        if not 0 <= overlap_tokens < window_tokens:
            raise InvalidWindowError(
                f"overlap_tokens must satisfy 0 <= overlap < window ({window_tokens}), got {overlap_tokens}"
            )
        self._window = window_tokens
        self._stride = window_tokens - overlap_tokens

    def chunk(self, elements: Sequence[DecodedElement]) -> tuple[Chunk, ...]:
        chunks: list[Chunk] = []
        for element in elements:
            for index, window in enumerate(self._windows(element.text.split())):
                chunks.append(_chunk_from_element(element, index, " ".join(window)))
        return tuple(chunks)

    def _windows(self, tokens: list[str]) -> list[list[str]]:
        if not tokens:
            return []
        windows: list[list[str]] = []
        start = 0
        while True:
            windows.append(tokens[start : start + self._window])
            if start + self._window >= len(tokens):
                return windows
            start += self._stride


def _heading_section_paths(template_elements: Sequence[TemplateElement]) -> dict[str, str]:
    """element_id -> section_path, parsed from each value region's heading anchor."""
    paths: dict[str, str] = {}
    for element in template_elements:
        if element.kind != "value_region" or element.anchor is None:
            continue
        match = _SECTION_NUMBER_PATTERN.match(element.anchor.label_text)
        if match is not None:
            paths[element.element_id] = match.group(1)
    return paths


def assign_section_paths_from_heading_hierarchy(
    template_elements: Sequence[TemplateElement],
    decoded: Sequence[DecodedElement],
) -> tuple[DecodedElement, ...]:
    """Structural-tier addressing: derive section_path from the template's
    heading hierarchy (a value region's anchor is its section heading)."""
    paths = _heading_section_paths(template_elements)
    return tuple(
        replace(element, section_path=paths[element.element_id]) if element.element_id in paths else element
        for element in decoded
    )
