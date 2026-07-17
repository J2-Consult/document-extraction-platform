"""record_migration_result + record_held_document (epic E12): consume E08's
real `DraftMigration` (src/services/lifecycle/migration.py) and `HeldDocument`
(src/services/lifecycle/held.py) — migration outcomes and review backlog/age."""

from __future__ import annotations

from domain.lineage.generator import LineageGenerator
from services.lifecycle.held import HeldDocumentPolicy
from services.lifecycle.migration import MaskMigrator
from services.telemetry.fake import InMemoryMetricsSink
from services.telemetry.metrics import (
    LIFECYCLE_MIGRATION_RELATIONS_TOTAL,
    REVIEW_BACKLOG_AGE_SECONDS,
    REVIEW_BACKLOG_TOTAL,
)
from services.telemetry.recorders import record_held_document, record_migration_result
from services.validation.validator import default_validator
from tests.unit.services.lifecycle._fixtures import build_tmpl_nvinv_v2, load_mask, load_template


def test_migration_result_emits_relation_counters_matching_the_real_lineage_split_and_added() -> None:
    template_v1 = load_template("tmpl_nvinv.v1").body
    vendor_mask = load_mask("mask_nvvendor.v1").body
    template_v2 = build_tmpl_nvinv_v2()
    lineage = LineageGenerator().compare(template_v1, template_v2)

    migration = MaskMigrator(default_validator()).draft(vendor_mask, lineage)

    sink = InMemoryMetricsSink()
    record_migration_result(sink, migration, tenant_id="vendor", doc_class="invoice", component_version="e08-v1")

    relations = [c for c in sink.counters if c.name == LIFECYCLE_MIGRATION_RELATIONS_TOTAL]
    compatible = [c for c in relations if c.dimensions["relation"] == "compatible"]
    assert len(compatible) == 1
    assert compatible[0].value == len(migration.draft_mask_body.entries)

    by_relation = {c.dimensions["relation"] for c in relations if c.dimensions["relation"] != "compatible"}
    assert by_relation == {"split", "added"}
    for c in relations:
        assert c.dimensions["tenant"] == "vendor"
        assert c.dimensions["doc_class"] == "invoice"


def test_held_document_emits_backlog_counter_and_age_histogram() -> None:
    held = HeldDocumentPolicy().hold(
        document_id="doc-unknown-1", tenant_id="t-nordvik", fingerprint="fpv1:sha256:" + "0" * 64, at=1000.0
    )
    sink = InMemoryMetricsSink()

    record_held_document(sink, held, doc_class="unknown", component_version="e08-v1", now=1090.0)

    backlog = [c for c in sink.counters if c.name == REVIEW_BACKLOG_TOTAL]
    assert len(backlog) == 1
    assert backlog[0].dimensions["tenant"] == "t-nordvik"
    assert backlog[0].dimensions["doc_class"] == "unknown"

    age = [h for h in sink.histograms if h.name == REVIEW_BACKLOG_AGE_SECONDS]
    assert len(age) == 1
    assert age[0].value == 90.0
    assert age[0].dimensions["tenant"] == "t-nordvik"
