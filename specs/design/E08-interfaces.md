# E08 interface design (architect draft)

Authority: epic E08 + CLAUDE.md + FIXTURES-SPEC. Public shapes binding; flag deviations.
Serialization note (from E01 review): mask/template wire form requires
`model_dump(by_alias=True)` — `TargetBinding.target_schema` aliases `"schema"`.

## Module layout

```
src/domain/lineage/
  model.py        # ElementRelation = Literal["compatible","split","merged","added",
                  #   "removed","ambiguous"]; LineageEntry {old_element_ids, new_element_ids,
                  #   relation, evidence}; LineageReport {from_ref, to_ref, entries}
  generator.py    # LineageGenerator.compare(old: TemplateBody, new: TemplateBody)
                  #   -> LineageReport — geometry + anchor-text based, extraction-oriented
                  #   ONLY (no business meaning inferred); deterministic under element
                  #   shuffling/renumbering (property-tested, seeded random)
src/services/lifecycle/
  migration.py    # MaskMigrator.draft(mask, lineage) -> DraftMigration
                  #   {draft_mask_body, review_worklist: [WorklistItem]} — compatible
                  #   entries copied (attribution preserved, inherited_from updated);
                  #   split/merged/added/ambiguous -> worklist; referential +
                  #   target-mapping validation (E01 validator) before activation
  release.py      # ReleaseUnit {template_ref, mask_refs}; ReleaseService.activate(unit)
                  #   -> atomic via LifecycleRepository port; old mask NEVER implicitly
                  #   applies to an incompatible template version (rejected, not guessed)
  materializer.py # EffectiveMaskMaterializer.materialize(vendor_baseline, customer_mask
                  #   | deltas) -> complete customer mask body: full baseline coverage,
                  #   every entry attributed (origin, inherited_from, overridden);
                  #   golden test: fixtures mask_nvvendor + the 3 customer overrides
                  #   == mask_nvcust.v1.json body (validator-clean)
  worklist.py     # consultant worklist: template elements uncovered by the vendor mask;
                  #   reads SHARED rows only; integration test runs it as the synthesis
                  #   role (pairs with E02's invariant)
  held.py         # pending_template_review state policy: hold first document of an
                  #   unknown template; post-activation mapping WITHOUT re-extraction
                  #   when content is compatible
src/ports/lifecycle.py  # LifecycleRepository: append_template_version, append_mask_version,
                        #   activate_release_unit (atomic), get_active_mask, list_versions —
                        #   in-memory fake for unit tests; Postgres impl may reuse E02
                        #   session + E07 projection triggers (thin, parameterized)
```

## Rules that must hold (tested)

- All lifecycle mutations are APPENDS with actor identity (who, when, why fields on
  version rows / bodies) — never UPDATE of an artifact body.
- Vendor-mask publication requires an admin scope check (authorization test at the
  service boundary, not UI convention).
- Re-materialization on baseline adoption = explicit reviewable event (an appended
  mask version whose provenance names the trigger), never silent.
- Criterion 5: v2 with moved field (compatible) + one split + one added → exact
  lineage; compatible auto-migrated to draft; split/added in worklist.
- Criterion 6: release unit activates atomically; v1 documents reproducible against
  pinned versions (pinned refs never change under activation).
