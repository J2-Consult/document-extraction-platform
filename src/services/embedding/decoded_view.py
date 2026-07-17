"""Decoded view -> chunker input (epic E11).

Builders that turn typed artifact bodies into `DecodedElement`s:

- `semantic_elements` mirrors the E07 decoded view's join semantics — the
  document's present values joined through ONE mask's entries (selection,
  never merge), each row carrying semantic_role + section_path +
  system_context + provenance. This is the semantic tier's input; in
  production the same rows arrive via `adapters.postgres.queries`
  (`document_values` ⋈ `resolved_active_masks`).
- `structural_elements` reads the content observations directly (the
  unmasked path) and derives section_path from the template's heading
  hierarchy when a template is known.

Only `state == "present"` observations are embeddable — the absence states
have no text, and their review/provenance story lives in E05/E09, not in a
vector index.

Pure service logic: domain models in, dataclasses out; no I/O.
"""

from __future__ import annotations

from domain.artifacts.content import ContentBody, Observation
from domain.artifacts.mask import DecoderMaskBody
from domain.artifacts.template import TemplateBody
from services.embedding.chunkers import DecodedElement, assign_section_paths_from_heading_hierarchy


def _element_from_observation(
    content: ContentBody,
    observation: Observation,
    *,
    semantic_role: str | None = None,
    system_context: str | None = None,
    section_path: str | None = None,
) -> DecodedElement:
    text = observation.value
    if text is None:  # guarded by the caller's state filter; defensive here
        raise ValueError(f"observation {observation.element_id} has no text")
    bbox = observation.provenance.bbox
    return DecodedElement(
        document_id=content.document_id,
        element_id=observation.element_id,
        text=text,
        page=observation.provenance.source.page,
        bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
        provenance=observation.provenance.model_dump(),
        semantic_role=semantic_role,
        system_context=system_context,
        section_path=section_path,
    )


def semantic_elements(content: ContentBody, mask: DecoderMaskBody) -> tuple[DecodedElement, ...]:
    """Present observations joined through ONE mask's entries (decoded view)."""
    entries_by_element = {entry.element_id: entry for entry in mask.entries}
    elements: list[DecodedElement] = []
    for observation in content.observations:
        entry = entries_by_element.get(observation.element_id)
        if observation.state != "present" or entry is None:
            continue
        elements.append(
            _element_from_observation(
                content,
                observation,
                semantic_role=entry.semantic_role,
                system_context=mask.system_context,
                section_path=entry.section_path,
            )
        )
    return tuple(elements)


def structural_elements(content: ContentBody, template: TemplateBody | None) -> tuple[DecodedElement, ...]:
    """Present observations, structurally addressed via the template's headings."""
    elements = tuple(
        _element_from_observation(content, observation)
        for observation in content.observations
        if observation.state == "present"
    )
    if template is None:
        return elements
    return assign_section_paths_from_heading_hierarchy(template.elements, elements)
