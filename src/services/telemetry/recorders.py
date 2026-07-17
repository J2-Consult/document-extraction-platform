"""Thin recorder utilities (epic E12): turn another epic's existing result
objects into `MetricsSink` calls. Every function here is a pure consumer —
none of them import or edit another epic's service internals; they take the
already-computed result (`RoutingDecision`, `MappingResult`, ...) plus
whatever context the caller has (tenant, doc_class) and emit metrics.

Tenant/doc_class are passed explicitly rather than read off the result
objects: those objects are deliberately tenant-agnostic pure domain/port
shapes (CLAUDE.md — "Tenant context is set transactionally"), so the caller
(the composition-root code sitting inside a tenant transaction, or a
benchmark harness with a template body in scope) is the only place that
actually has both pieces of context at once.

No PII/content in any dimension value — see
`tests/unit/services/telemetry/test_no_pii_regression.py`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from domain.artifacts.content import UnmappedContent
from ports.cost import CostCategory
from ports.jobs import Job
from ports.routing_store import RoutingDecision
from ports.telemetry import MetricsSink
from services.extraction.confidence import GateDecision
from services.lifecycle.held import HeldDocument
from services.lifecycle.migration import DraftMigration
from services.mapping.outcome import MappingResult
from services.telemetry.metrics import (
    CONTENT_UNMAPPED_NOTES_TOTAL,
    CONTENT_UNMAPPED_REGION_RECURRENCE_TOTAL,
    EMBEDDING_BUILD_SCHEDULED_TOTAL,
    EMBEDDING_SWITCH_TIME_MS,
    EXTRACTION_CONFIDENCE,
    EXTRACTION_COST_UNITS,
    ISOLATION_DENIALS_TOTAL,
    JOBS_STATUS_TOTAL,
    LIFECYCLE_MIGRATION_RELATIONS_TOTAL,
    MAPPING_OUTCOMES_TOTAL,
    MAPPING_REVIEW_ITEMS_TOTAL,
    REVIEW_BACKLOG_AGE_SECONDS,
    REVIEW_BACKLOG_TOTAL,
    ROUTING_CANDIDATE_HITS_TOTAL,
    ROUTING_DECISIONS_TOTAL,
    ROUTING_LATENCY_MS,
    ROUTING_VERIFICATION_RESULTS_TOTAL,
)

_COMPATIBLE_RELATION = "compatible"

# Bbox coordinates are rounded to whole points before hashing: the
# "recurring" signal is "roughly the same region", not floating-point-exact
# geometry, and rounding keeps near-duplicate regions bucketed together.
_REGION_HASH_BBOX_PRECISION = 0


def _region_hash(page: int, bbox: Sequence[float]) -> str:
    """A stable, content-free fingerprint of WHERE a note sits, never WHAT it
    says. Truncated sha256 hex — a hash, not a reversible encoding of the
    coordinates, per CLAUDE.md's "log IDs, hashes, states, and metrics"."""
    rounded = [round(coordinate, _REGION_HASH_BBOX_PRECISION) for coordinate in bbox]
    canonical = f"page={page};bbox={rounded}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


_NO_ERROR_CATEGORY = "none"


def _join_component_versions(component_versions: Mapping[str, str]) -> str:
    """Flatten a component->version map into one dimension value.

    Deterministic (sorted by component name) so the same component-version
    set always renders to the same string; tokens are `component=version`
    pairs joined by `;` — component names and semver-ish version strings
    only, never document content."""
    return ";".join(f"{component}={version}" for component, version in sorted(component_versions.items()))


def record_routing_decision(
    sink: MetricsSink,
    decision: RoutingDecision,
    *,
    tenant_id: str,
    doc_class: str,
) -> None:
    """Emit the routing metrics behind candidate-hit, verification-accept,
    and slow-path rates (all computed downstream as ratios of these
    counters) plus routing latency.

    - `ROUTING_LATENCY_MS` (histogram): always, dims tenant/path/doc_class/component_version.
    - `ROUTING_DECISIONS_TOTAL` (counter): always, dims tenant/path/doc_class/component_version.
      slow-path rate = decisions where path=full_analysis / all decisions.
    - `ROUTING_CANDIDATE_HITS_TOTAL` (counter): only when `decision.candidate`
      is set. candidate-hit rate = this / ROUTING_DECISIONS_TOTAL.
    - `ROUTING_VERIFICATION_RESULTS_TOTAL` (counter): only when
      `decision.verification` is set, dims add `result` (accepted/rejected/
      inconclusive). verification-accept rate = result=accepted / this metric's total.
    """
    component_version = _join_component_versions(decision.component_versions)
    base_dimensions = {
        "tenant": tenant_id,
        "path": decision.routed_to,
        "doc_class": doc_class,
        "component_version": component_version,
    }

    sink.histogram(ROUTING_LATENCY_MS, decision.latency_ms, dimensions=base_dimensions)
    sink.counter(ROUTING_DECISIONS_TOTAL, dimensions=base_dimensions)

    if decision.candidate is not None:
        sink.counter(
            ROUTING_CANDIDATE_HITS_TOTAL,
            dimensions={"tenant": tenant_id, "doc_class": doc_class, "component_version": component_version},
        )

    if decision.verification is not None:
        sink.counter(
            ROUTING_VERIFICATION_RESULTS_TOTAL,
            dimensions={
                "tenant": tenant_id,
                "doc_class": doc_class,
                "component_version": component_version,
                "result": decision.verification.status,
            },
        )


def record_gate_decision(
    sink: MetricsSink,
    decision: GateDecision,
    *,
    tenant_id: str,
    doc_class: str,
    component_version: str,
) -> None:
    """Confidence distributions (epic §11.1): one `EXTRACTION_CONFIDENCE`
    histogram observation per region, dimensioned by the gate's `route`
    (accept/vlm_fallback/review) so the distribution can be sliced per
    outcome bucket."""
    for assessment in decision.assessments:
        sink.histogram(
            EXTRACTION_CONFIDENCE,
            assessment.calibrated_confidence,
            dimensions={
                "tenant": tenant_id,
                "doc_class": doc_class,
                "component_version": component_version,
                "route": assessment.route,
            },
        )


def record_extraction_cost(
    sink: MetricsSink,
    *,
    tenant_id: str,
    doc_class: str,
    component_version: str,
    category: CostCategory,
    cost: float,
) -> None:
    """Processing cost (epic §11.1), dimensioned by the `CostLedger`
    category vocabulary (`ports.cost.CostCategory`) so fast-path savings can
    be computed the same way `benchmarks/routing/harness.py` computes them."""
    sink.histogram(
        EXTRACTION_COST_UNITS,
        cost,
        dimensions={
            "tenant": tenant_id,
            "doc_class": doc_class,
            "component_version": component_version,
            "category": category,
        },
    )


def record_mapping_result(
    sink: MetricsSink,
    result: MappingResult,
    *,
    tenant_id: str,
    doc_class: str,
) -> None:
    """Target-schema failure categories + correction rates by method (epic
    §11.1), consuming E09's `MappingResult` as-is.

    - `MAPPING_OUTCOMES_TOTAL` (counter): always, dims add `outcome`
      (completed/pending_review/pending_template_review/rejected/failed) and
      `error_category` (the four `ErrorCategory` families, or `"none"` for a
      clean `completed` result) — this is where target-schema (`contract`)
      failures are counted.
    - `MAPPING_REVIEW_ITEMS_TOTAL` (counter): one per `ReviewItem`, dims add
      `reason` (below_confidence_threshold/unreadable) and `method` (the
      item's own provenance extraction method) — correction rate by method =
      this / values extracted by that method.
    """
    component_version = _join_component_versions(result.component_versions)
    base_dimensions = {
        "tenant": tenant_id,
        "doc_class": doc_class,
        "component_version": component_version,
    }
    sink.counter(
        MAPPING_OUTCOMES_TOTAL,
        dimensions={
            **base_dimensions,
            "outcome": result.outcome,
            "error_category": result.error_category or _NO_ERROR_CATEGORY,
        },
    )
    for item in result.review_items:
        sink.counter(
            MAPPING_REVIEW_ITEMS_TOTAL,
            dimensions={**base_dimensions, "reason": item.reason, "method": item.provenance.method},
        )


def record_unmapped_content(
    sink: MetricsSink,
    notes: Sequence[UnmappedContent],
    *,
    tenant_id: str,
    doc_class: str,
    component_version: str,
) -> None:
    """Unmapped-content frequency + recurring-region indicator (epic §11.1),
    consuming E06's `UnmappedContent` notes. `note.text` is document content
    and is NEVER read here — the recurring-region indicator is a hash of
    (page, bbox) only (`_region_hash`); `note_id` is an opaque identifier,
    not content, so it is safe to carry as a dimension.

    - `CONTENT_UNMAPPED_NOTES_TOTAL` (counter): one per note (frequency).
    - `CONTENT_UNMAPPED_REGION_RECURRENCE_TOTAL` (counter): one per note,
      dims add `region_hash` — repeated hashes across documents/runs are the
      recurring-region signal.
    """
    base_dimensions = {
        "tenant": tenant_id,
        "doc_class": doc_class,
        "component_version": component_version,
    }
    for note in notes:
        sink.counter(CONTENT_UNMAPPED_NOTES_TOTAL, dimensions={**base_dimensions, "note_id": note.note_id})
        region_hash = _region_hash(note.provenance.source.page, note.provenance.bbox)
        sink.counter(
            CONTENT_UNMAPPED_REGION_RECURRENCE_TOTAL,
            dimensions={**base_dimensions, "region_hash": region_hash},
        )


def record_migration_result(
    sink: MetricsSink,
    migration: DraftMigration,
    *,
    tenant_id: str,
    doc_class: str,
    component_version: str,
) -> None:
    """Migration outcomes (epic §11.1), consuming E08's `DraftMigration`.

    `LIFECYCLE_MIGRATION_RELATIONS_TOTAL` (counter), dims add `relation`:
    one call with `relation="compatible"` and `value=` the number of
    auto-migrated entries (the draft's carried-forward entries — the
    `DraftMigration` shape does not retain per-entry lineage relations for
    compatible entries, only their count), plus one call per
    `review_worklist` item using that item's own `relation`
    (split/added/ambiguous/...).
    """
    base_dimensions = {
        "tenant": tenant_id,
        "doc_class": doc_class,
        "component_version": component_version,
    }
    sink.counter(
        LIFECYCLE_MIGRATION_RELATIONS_TOTAL,
        dimensions={**base_dimensions, "relation": _COMPATIBLE_RELATION},
        value=len(migration.draft_mask_body.entries),
    )
    for item in migration.review_worklist:
        sink.counter(
            LIFECYCLE_MIGRATION_RELATIONS_TOTAL,
            dimensions={**base_dimensions, "relation": item.relation},
        )


def record_held_document(
    sink: MetricsSink,
    held: HeldDocument,
    *,
    doc_class: str,
    component_version: str,
    now: float,
) -> None:
    """Review backlog/age (epic §11.1), consuming E08's `HeldDocument`.

    `REVIEW_BACKLOG_TOTAL` (counter): one per held document (backlog size is
    the count of calls over the current held set). `REVIEW_BACKLOG_AGE_SECONDS`
    (histogram): `now - held.held_at`, `now` supplied by the caller's own
    `Clock` rather than read here (this module never has clock access — same
    "no clock inside pure recorders" discipline as the epics it instruments)."""
    base_dimensions = {
        "tenant": held.tenant_id,
        "doc_class": doc_class,
        "component_version": component_version,
    }
    sink.counter(REVIEW_BACKLOG_TOTAL, dimensions=base_dimensions)
    sink.histogram(REVIEW_BACKLOG_AGE_SECONDS, now - held.held_at, dimensions=base_dimensions)


def record_job_status(
    sink: MetricsSink,
    job: Job,
    *,
    doc_class: str,
    component_version: str,
) -> None:
    """Generic queue/backlog/DLQ counter (epic §11.1 "review backlog" +
    "embedding build backlog" both ultimately being job-queue backlogs),
    consuming E03's `Job` as-is. `JOBS_STATUS_TOTAL` (counter), dims add
    `kind` and `status` — DLQ size = calls where `status="dead_letter"`,
    grouped by `kind`; `job.payload` is never read here (it may carry
    document-shaped identifiers, not telemetry-safe by construction)."""
    sink.counter(
        JOBS_STATUS_TOTAL,
        dimensions={
            "tenant": job.tenant_id,
            "doc_class": doc_class,
            "component_version": component_version,
            "kind": job.kind,
            "status": job.status,
        },
    )


def record_embedding_build_scheduled(
    sink: MetricsSink,
    job: Job,
    *,
    doc_class: str,
    component_version: str,
) -> None:
    """Embedding build backlog (epic §11.1), consuming E11's
    `EmbeddingBuildService.schedule_semantic_build` return value. Emits the
    generic `JOBS_STATUS_TOTAL` (via `record_job_status`) plus a build-specific
    `EMBEDDING_BUILD_SCHEDULED_TOTAL` counter so embedding backlog can be
    tracked independently of the shared job-queue metric."""
    record_job_status(sink, job, doc_class=doc_class, component_version=component_version)
    sink.counter(
        EMBEDDING_BUILD_SCHEDULED_TOTAL,
        dimensions={"tenant": job.tenant_id, "doc_class": doc_class, "component_version": component_version},
    )


def record_embedding_build_switch(
    sink: MetricsSink,
    *,
    tenant_id: str,
    doc_class: str,
    component_version: str,
    switch_time_ms: float,
) -> None:
    """Embedding build switch time (epic §11.1): the caller computes
    `switch_time_ms` from its own clock (schedule time to
    `EmbeddingBuildService._complete_and_serve` time) and passes it through —
    `EmbeddingBuildService` itself deliberately logs nothing (see its module
    docstring), so timing is the composition root's job, not this
    recorder's."""
    sink.histogram(
        EMBEDDING_SWITCH_TIME_MS,
        switch_time_ms,
        dimensions={"tenant": tenant_id, "doc_class": doc_class, "component_version": component_version},
    )


@dataclass(frozen=True, slots=True)
class IsolationDenialEvent:
    """FUTURE WIRING (epic E12 brief): today, E02's tenant isolation is
    enforced entirely at the SQL/RLS layer (`tests/isolation`) and no
    application-level denial event exists yet for this shape to consume. This
    is the minimal, telemetry-safe shape a future E02 change would raise —
    role and resource NAME only, never a query, row, or value — so that
    wiring a real denial signal is a one-line `record_isolation_denial` call,
    not a new port."""

    tenant_id: str
    role: str
    resource: str


def record_isolation_denial(
    sink: MetricsSink,
    event: IsolationDenialEvent,
    *,
    component_version: str,
) -> None:
    """Isolation-denial counters (epic §11.1). `ISOLATION_DENIALS_TOTAL`
    (counter), dims add `role` and `resource` — both fixed vocabulary tokens
    (a DB role name, a table/resource name), never a tenant B identifier or
    row value."""
    sink.counter(
        ISOLATION_DENIALS_TOTAL,
        dimensions={
            "tenant": event.tenant_id,
            "role": event.role,
            "resource": event.resource,
            "component_version": component_version,
        },
    )
