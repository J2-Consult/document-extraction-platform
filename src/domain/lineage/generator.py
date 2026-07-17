"""LineageGenerator: compare template vN -> vN+1 (epic E08).

Matching is geometry + anchor-text based and extraction-oriented ONLY:

1. Anchor stage — elements sharing a (kind, anchor label text) signature are
   related regardless of position, so a moved field stays `compatible`.
2. Geometry stage — remaining elements are related by bbox overlap on the
   same page and kind (connected components of the overlap graph): 1:1 is
   `compatible` (or `ambiguous` when the label text changed — never guessed),
   1:N is `split`, N:1 is `merged`, denser components are `ambiguous`.
3. Leftovers — old-only elements are `removed`, new-only are `added`.

Determinism: no decision depends on element ids or list order — signatures,
overlap, and component discovery work on geometry/text sets, and every output
tuple is sorted — so shuffling or renumbering elements yields the same report
modulo the renaming (property-tested).

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from domain.artifacts.template import TemplateBody, TemplateElement, TemplateRef
from domain.lineage.model import LineageEntry, LineageReport

# An old and a new element "occupy the same region" when their intersection
# covers at least this fraction of the smaller bbox — generous enough for
# minor nudges, strict enough that neighbouring rows do not collide.
_OVERLAP_FRACTION_OF_SMALLER = 0.5


def _signature(element: TemplateElement) -> tuple[str, str] | None:
    if element.anchor is None:
        return None
    return (element.kind, element.anchor.label_text)


def _bbox_overlaps(a: TemplateElement, b: TemplateElement) -> bool:
    if a.page != b.page or a.kind != b.kind:
        return False
    ax0, ay0, ax1, ay1 = a.bbox
    bx0, by0, bx1, by1 = b.bbox
    width = min(ax1, bx1) - max(ax0, bx0)
    height = min(ay1, by1) - max(ay0, by0)
    if width <= 0 or height <= 0:
        return False
    smaller = min((ax1 - ax0) * (ay1 - ay0), (bx1 - bx0) * (by1 - by0))
    if smaller <= 0:
        return False
    return width * height >= _OVERLAP_FRACTION_OF_SMALLER * smaller


def _sorted_ids(elements: Iterable[TemplateElement]) -> tuple[str, ...]:
    return tuple(sorted(element.element_id for element in elements))


def _relation_for_group(old_count: int, new_count: int) -> str:
    if old_count == 1 and new_count == 1:
        return "compatible"
    if old_count == 1 and new_count >= 2:
        return "split"
    if old_count >= 2 and new_count == 1:
        return "merged"
    return "ambiguous"


class LineageGenerator:
    """Computes per-element lineage between two versions of one template."""

    def compare(self, old: TemplateBody, new: TemplateBody) -> LineageReport:
        old_pool = list(old.elements)
        new_pool = list(new.elements)
        entries: list[LineageEntry] = []

        entries += _match_by_anchor(old_pool, new_pool)
        entries += _match_by_geometry(old_pool, new_pool)
        entries += [
            LineageEntry(
                old_element_ids=(element.element_id,),
                new_element_ids=(),
                relation="removed",
                evidence="no anchor-text or geometry counterpart in the new version",
            )
            for element in old_pool
        ]
        entries += [
            LineageEntry(
                old_element_ids=(),
                new_element_ids=(element.element_id,),
                relation="added",
                evidence="no anchor-text or geometry counterpart in the old version",
            )
            for element in new_pool
        ]

        entries.sort(key=lambda entry: (entry.old_element_ids, entry.new_element_ids))
        return LineageReport(
            from_ref=TemplateRef(template_id=old.template_id, version=old.version),
            to_ref=TemplateRef(template_id=new.template_id, version=new.version),
            entries=tuple(entries),
        )


def _match_by_anchor(old_pool: list[TemplateElement], new_pool: list[TemplateElement]) -> list[LineageEntry]:
    """Relate elements sharing a (kind, anchor label text) signature; consumes matches."""
    old_by_signature = _group_by_signature(old_pool)
    new_by_signature = _group_by_signature(new_pool)
    entries: list[LineageEntry] = []
    for signature in sorted(set(old_by_signature) & set(new_by_signature)):
        olds = old_by_signature[signature]
        news = new_by_signature[signature]
        entries.append(
            LineageEntry(
                old_element_ids=_sorted_ids(olds),
                new_element_ids=_sorted_ids(news),
                relation=_relation_for_group(len(olds), len(news)),  # type: ignore[arg-type]
                evidence=f"anchor label text {signature[1]!r} ({signature[0]})",
            )
        )
        _consume(old_pool, olds)
        _consume(new_pool, news)
    return entries


def _match_by_geometry(old_pool: list[TemplateElement], new_pool: list[TemplateElement]) -> list[LineageEntry]:
    """Relate remaining elements via overlap-graph components; consumes matches."""
    entries: list[LineageEntry] = []
    for olds, news in _overlap_components(old_pool, new_pool):
        relation = _relation_for_group(len(olds), len(news))
        if relation == "compatible" and _anchor_text_changed(olds[0], news[0]):
            relation = "ambiguous"
            evidence = "same region but the anchor label text changed — not guessed"
        else:
            evidence = f"bbox overlap on page {olds[0].page} ({olds[0].kind})"
        entries.append(
            LineageEntry(
                old_element_ids=_sorted_ids(olds),
                new_element_ids=_sorted_ids(news),
                relation=relation,  # type: ignore[arg-type]
                evidence=evidence,
            )
        )
        _consume(old_pool, olds)
        _consume(new_pool, news)
    return entries


def _overlap_components(
    old_pool: Sequence[TemplateElement], new_pool: Sequence[TemplateElement]
) -> list[tuple[list[TemplateElement], list[TemplateElement]]]:
    """Connected components of the old/new bbox-overlap bipartite graph.

    Discovery iterates elements in sorted-id order purely to fix the OUTPUT
    order; component membership itself is order-independent.
    """
    components: list[tuple[list[TemplateElement], list[TemplateElement]]] = []
    visited_old: set[str] = set()
    visited_new: set[str] = set()
    for seed in sorted(old_pool, key=lambda element: element.element_id):
        if seed.element_id in visited_old:
            continue
        olds, news = _expand_component(seed, old_pool, new_pool)
        if not news:
            continue  # untouched old element: left in the pool, becomes "removed"
        visited_old.update(element.element_id for element in olds)
        visited_new.update(element.element_id for element in news)
        components.append((olds, news))
    return components


def _expand_component(
    seed: TemplateElement, old_pool: Sequence[TemplateElement], new_pool: Sequence[TemplateElement]
) -> tuple[list[TemplateElement], list[TemplateElement]]:
    olds = [seed]
    news: list[TemplateElement] = []
    grew = True
    while grew:
        grew = False
        for candidate in sorted(new_pool, key=lambda element: element.element_id):
            if candidate not in news and any(_bbox_overlaps(o, candidate) for o in olds):
                news.append(candidate)
                grew = True
        for candidate in sorted(old_pool, key=lambda element: element.element_id):
            if candidate not in olds and any(_bbox_overlaps(candidate, n) for n in news):
                olds.append(candidate)
                grew = True
    olds.sort(key=lambda element: element.element_id)
    news.sort(key=lambda element: element.element_id)
    return olds, news


def _group_by_signature(pool: Sequence[TemplateElement]) -> dict[tuple[str, str], list[TemplateElement]]:
    groups: dict[tuple[str, str], list[TemplateElement]] = {}
    for element in pool:
        signature = _signature(element)
        if signature is not None:
            groups.setdefault(signature, []).append(element)
    return groups


def _anchor_text_changed(old: TemplateElement, new: TemplateElement) -> bool:
    if old.anchor is None or new.anchor is None:
        return False
    return old.anchor.label_text != new.anchor.label_text


def _consume(pool: list[TemplateElement], matched: Iterable[TemplateElement]) -> None:
    matched_ids = {element.element_id for element in matched}
    pool[:] = [element for element in pool if element.element_id not in matched_ids]
