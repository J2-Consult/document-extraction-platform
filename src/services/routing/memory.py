"""In-memory reference implementations of the routing ports (E04's own — the
Postgres adapter lands with E07's query surface, per the architect design
doc). Used by unit tests and the `benchmarks/routing/` harness.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from domain.artifacts.template import TemplateBody, TemplateRef
from ports.routing_store import RoutingDecision, TemplateCandidate


class InMemoryTemplateCandidateIndex:
    """`TemplateCandidateIndex` backed by a plain dict keyed on fingerprint."""

    def __init__(self, candidates: Sequence[TemplateCandidate] = ()) -> None:
        self._by_key: dict[str, list[TemplateCandidate]] = defaultdict(list)
        for candidate in candidates:
            self.register(candidate)

    def register(self, candidate: TemplateCandidate) -> None:
        self._by_key[candidate.fingerprint_key].append(candidate)

    def find_by_key(self, fingerprint_key: str) -> Sequence[TemplateCandidate]:
        return tuple(self._by_key.get(fingerprint_key, ()))


class InMemoryRoutingDecisionStore:
    """`RoutingDecisionStore` backed by an append-only in-process list."""

    def __init__(self) -> None:
        self._decisions: list[RoutingDecision] = []

    def append(self, decision: RoutingDecision) -> None:
        self._decisions.append(decision)

    @property
    def decisions(self) -> tuple[RoutingDecision, ...]:
        return tuple(self._decisions)


def candidate_from_template_body(body: TemplateBody) -> TemplateCandidate:
    """Build a `TemplateCandidate` from a loaded `TemplateBody` — convenience
    for tests and the benchmark harness, which both need to register the
    fixture template with an `InMemoryTemplateCandidateIndex`."""
    return TemplateCandidate(
        template_ref=TemplateRef(template_id=body.template_id, version=body.version),
        fingerprint_key=body.fingerprint,
        body=body,
    )
