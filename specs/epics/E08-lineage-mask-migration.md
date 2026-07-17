# E08 — Template lineage, mask migration, effective-mask materialization

**Objective:** safe template evolution: element lineage on registration, automatic draft-mask migration for compatible elements, review for the rest, release-unit activation — plus the ADR 20 materializer that turns a vendor baseline + customer deltas into a complete attributed effective mask.
**Depends on:** E01, E07. **Owned paths:** `src/services/lifecycle/`, `src/domain/lineage/`.
**Read first:** v0.2 §5 entirely; architecture doc §5.3 notes, §7.2, §7.4, ADR 20.

## Scope
- Lineage generator: compare template vN→vN+1, emit per-element `compatible | split | merged | added | removed | ambiguous` (extraction-oriented only — no business meaning inferred).
- Mask migration: copy compatible entries into a draft mask vN+1; split/merged/added/ambiguous → review worklist; referential + target-mapping validation before activation.
- Release unit: template + required compatible masks activate atomically; an old mask never implicitly applies to an incompatible template version.
- Effective-mask materializer: vendor baseline + customer changes → complete customer mask, every entry attributed (`inherited_from`, `overridden`, `origin`); re-materialization on baseline adoption is an explicit, reviewable event.
- Consultant worklist query (template elements uncovered by the vendor mask) — reads shared rows only; runs under the `synthesis` role from E02.
- Held first-document policy (v0.2 §5.4): `pending_template_review` state; post-activation mapping without re-extraction when content is compatible.

## Tests first (acceptance: criteria 5, 6)
- v2 moves a field (compatible), splits one, adds one → lineage exact; compatible entries auto-migrate to draft; split/added land in review (criterion 5).
- Release unit activates template+mask together; v1 documents remain reproducible against pinned versions (criterion 6).
- Materializer output: full baseline coverage, exactly the customer's overrides flagged, validator-clean (reuses fixture mask_nvcust as the golden file).
- Worklist under the synthesis role: private templates and customer masks invisible (pairs with E02's invariant test).
- Old mask + incompatible template ⇒ mapping is rejected, never guessed.

## Security
All lifecycle mutations are appends with actor identity; vendor-mask publication requires the admin scope (authorization test, not just UI convention).

## Definition of done
Criteria 5–6 unskipped; lineage generator property-tested on shuffled/renumbered elements; materializer golden-file test green.
