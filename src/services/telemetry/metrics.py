"""Metric name constants: the epic's v0.2 §11.1 minimum telemetry set.

One constant per metric emitted by `services.telemetry.recorders`. Naming
convention: `"<component>.<subject>[_total|_ms|_units]"` — `_total` marks a
counter, everything else emitted via `histogram` carries a unit suffix
(`_ms`, `_units`, `_seconds`). Every metric's expected dimensions are
documented next to the recorder that emits it, not here — this module is
just the name vocabulary so producers and (future) dashboards agree on
spelling.
"""

from __future__ import annotations

# --- routing (src/services/routing/): candidate-hit, verification-accept,
# slow-path rates + latency. Rates are computed downstream as ratios of these
# counters (e.g. candidate-hit rate = ROUTING_CANDIDATE_HITS_TOTAL /
# ROUTING_DECISIONS_TOTAL), mirroring benchmarks/routing/harness.py.
ROUTING_LATENCY_MS = "routing.latency_ms"
ROUTING_DECISIONS_TOTAL = "routing.decisions_total"
ROUTING_CANDIDATE_HITS_TOTAL = "routing.candidate_hits_total"
ROUTING_VERIFICATION_RESULTS_TOTAL = "routing.verification_results_total"

# --- extraction (src/services/extraction/): confidence distributions + cost.
EXTRACTION_CONFIDENCE = "extraction.confidence"
EXTRACTION_COST_UNITS = "extraction.cost_units"

# --- mapping (src/services/mapping/outcome.py): outcomes + target-schema
# failure categories + correction rates by extraction method.
MAPPING_OUTCOMES_TOTAL = "mapping.outcomes_total"
MAPPING_REVIEW_ITEMS_TOTAL = "mapping.review_items_total"

# --- content (unmapped-content frequency + recurring-region indicator).
CONTENT_UNMAPPED_NOTES_TOTAL = "content.unmapped_notes_total"
CONTENT_UNMAPPED_REGION_RECURRENCE_TOTAL = "content.unmapped_region_recurrence_total"

# --- lifecycle (src/services/lifecycle/): migration outcomes + review backlog/age.
LIFECYCLE_MIGRATION_RELATIONS_TOTAL = "lifecycle.migration_relations_total"
REVIEW_BACKLOG_TOTAL = "review.backlog_total"
REVIEW_BACKLOG_AGE_SECONDS = "review.backlog_age_seconds"

# --- embedding (src/services/embedding/builds.py): build backlog + switch time.
EMBEDDING_BUILD_SCHEDULED_TOTAL = "embedding.build_scheduled_total"
EMBEDDING_SWITCH_TIME_MS = "embedding.switch_time_ms"

# --- jobs (src/adapters/jobs/): generic queue/backlog/DLQ status counter,
# reused by the embedding build backlog and any other job kind.
JOBS_STATUS_TOTAL = "jobs.status_total"

# --- isolation (tests/isolation — denial counters are future wiring per the
# epic; this metric exists so the day a real denial event is raised in
# application code, recording it is a one-line call, not a new port).
ISOLATION_DENIALS_TOTAL = "isolation.denials_total"
