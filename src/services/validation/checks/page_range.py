"""`provenance.source.page` must fall within the document's actual page range
(`content.body.source.page_count`) — a page index pointing past the last page
of the source PDF is meaningless and cannot be dereferenced on a read path.

Silently passes when there is no content artifact under validation.
"""

from __future__ import annotations

from domain.artifacts.content import Observation, UnmappedContent
from domain.artifacts.errors import InvariantViolation
from services.validation.bundle import ArtifactBundle

CODE = "page-out-of-range"


class PageRangeCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.content is None:
            return []
        body = bundle.content.body
        page_count = body.source.page_count
        return [
            *self._check_observations(body.observations, page_count),
            *self._check_unmapped_content(body.unmapped_content, page_count),
        ]

    def _check_observations(self, observations: list[Observation], page_count: int) -> list[InvariantViolation]:
        violations = []
        for index, observation in enumerate(observations):
            if observation.provenance is None:
                continue
            page = observation.provenance.source.page
            if 1 <= page <= page_count:
                continue
            violations.append(
                InvariantViolation(
                    path=f"/body/observations/{index}/provenance/source/page",
                    code=CODE,
                    message=(f"page {page} for element_id '{observation.element_id}' is out of range 1..{page_count}"),
                )
            )
        return violations

    def _check_unmapped_content(self, notes: list[UnmappedContent], page_count: int) -> list[InvariantViolation]:
        violations = []
        for index, note in enumerate(notes):
            if note.provenance is None:
                continue
            page = note.provenance.source.page
            if 1 <= page <= page_count:
                continue
            violations.append(
                InvariantViolation(
                    path=f"/body/unmapped_content/{index}/provenance/source/page",
                    code=CODE,
                    message=f"page {page} for note '{note.note_id}' is out of range 1..{page_count}",
                )
            )
        return violations
