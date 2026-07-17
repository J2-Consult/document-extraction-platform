# E01 — Artifact contracts & invariant validator

**Objective:** the three artifact contracts as typed models plus a service-level invariant validator — the platform's contract law, used by every other epic.
**Depends on:** E00. **Owned paths:** `src/domain/artifacts/`, `src/services/validation/`, `src/ports/canonical.py`.
**Read first:** architecture doc §3, §5.1–5.4; v0.2 §3, §6.1, §7.3; fixtures/schemas/*, fixtures/fpv1.py.

## Scope
- Pydantic v2 models mirroring `template.schema.json`, `content.schema.json`, `decoder-mask.schema.json` (strict mode, `extra='forbid'`), plus a versioned target-schema registry.
- Value-state model: `present | empty | not_applicable | unreadable | not_found` with legal value/state combinations (v0.2 §6.1).
- **InvariantValidator** (pure domain service) enforcing what JSON Schema cannot:
  every `element_id` in content/masks resolves to the referenced template version;
  envelope-vs-body metadata agree; provenance present wherever required (values,
  blank assertions, unmapped content, corrections); mask `scope='vendor' ⇔ tenant_id is null`;
  effective-mask attribution rules (`overridden ⇒ inherited_from`; vendor entries all `validated_by`);
  fingerprint pattern `fpvN:sha256:hex64`; state/value legality.
- Canonicalization port `CanonicalSerializer` (stable JSON, sorted keys) shared by fingerprinting and hashing; keep `fixtures/fpv1.py` reproducible against it.

## Design notes (SOLID)
Models are data; the validator is one class per invariant group composed into a pipeline (SRP; new invariant = new component, closed for modification). No I/O anywhere in this epic.

## Tests first (acceptance: criterion 11)
- Every fixture file validates.
- One mutation test per invariant: unknown element_id, missing provenance, contradictory envelope/body, illegal `state='present'` without value, vendor mask with tenant_id, overridden entry without inherited_from, bad fingerprint — each rejected with an itemized, machine-readable error (path + code + message).
- Round-trip: model → json → model is lossless for all fixtures.

## Security
Strict parsing (`extra='forbid'`) is the injection surface reduction here; error messages carry paths/codes, never raw document content.

## Definition of done
Criterion-11 acceptance test unskipped and green; validator has zero framework imports; mutation coverage list checked into the epic's test module docstring.
