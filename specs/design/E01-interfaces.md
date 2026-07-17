# E01 interface design (architect draft)

Authority: epic E01 + CLAUDE.md. Implementer may adjust internals, not the public
shapes below, without flagging it in the PR description.

## Module layout

```
src/domain/artifacts/
  __init__.py          # re-exports the public models
  envelope.py          # ArtifactEnvelope[BodyT] generic envelope
  template.py          # TemplateBody, TemplateElement, PageGeometry, ElementKind
  content.py           # ContentBody, Observation, ValueState, Confidence,
                       # UnmappedContent, CoordinateSpace
  mask.py              # DecoderMaskBody, MaskEntry, MaskScope, EntryAttribution,
                       # TargetBinding
  provenance.py        # Provenance, SourceRef, WorkingRef (E06 extends; E01 owns shape)
  errors.py            # InvariantViolation, ValidationReport
src/domain/registry.py # TargetSchemaRegistry (versioned target schemas)
src/services/validation/
  __init__.py
  validator.py         # InvariantValidator (pipeline composition root)
  checks/              # one module per invariant group (SRP / open-closed)
    element_resolution.py, envelope_agreement.py, provenance_required.py,
    mask_scope.py, mask_attribution.py, fingerprint_format.py, state_legality.py
src/ports/canonical.py # CanonicalSerializer Protocol
```

## Key shapes

- All models: Pydantic v2, `model_config = ConfigDict(extra="forbid", strict=True, frozen=True)`.
- `ValueState = Literal["present","empty","not_applicable","unreadable","not_found"]`.
- `class InvariantCheck(Protocol): def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]`
  where `ArtifactBundle` carries the artifact under validation plus its resolution
  context (e.g. the referenced template) — pure data, assembled by the caller;
  the validator does NO I/O.
- `InvariantViolation`: `path: str` (JSON-pointer-ish), `code: str`
  (machine-readable, kebab-case, e.g. `unknown-element-id`, `missing-provenance`,
  `state-value-conflict`, `vendor-mask-with-tenant`, `overridden-without-inherited-from`,
  `bad-fingerprint-format`, `envelope-body-mismatch`), `message: str` (no document content).
- `ValidationReport`: `ok: bool`, `violations: tuple[InvariantViolation, ...]`;
  validator NEVER raises on invalid input — it reports. (Parsing errors from Pydantic
  are a separate concern at the boundary.)
- `InvariantValidator(checks: Sequence[InvariantCheck])` — composition via constructor
  injection; default factory `default_validator()` wires all checks. New invariant =
  new module in `checks/` + registration in the factory; existing checks never edited.
- `class CanonicalSerializer(Protocol): def canonical_bytes(self, obj: Mapping[str, object]) -> bytes`
  — implementation must reproduce `fixtures/fpv1.py` byte-for-byte (sorted keys,
  compact separators, UTF-8; reject NaN/Inf).
- Fingerprint pattern constant: `^fpv\d+:sha256:[0-9a-f]{64}$` lives in `template.py`.
- `TargetSchemaRegistry`: `get(schema_id: str, version: int) -> Mapping[str, object]`
  backed by packaged JSON Schema resources; `invoice_record_v1` registered from
  `fixtures/schemas/invoice_record_v1.schema.json` copied into package data (fixtures
  stay the test-data source of truth; the registry ships its own copy — divergence is
  caught by a test comparing the two).

## Invariants to implement (one check module each, from the epic)

element resolution; envelope/body agreement; provenance-required (values, blank
assertions, unmapped content, corrections); `scope='vendor' ⇔ tenant_id is null`;
attribution (`overridden ⇒ inherited_from`, vendor entries all `validated_by`);
fingerprint format; state/value legality (`present` ⇔ value non-null).

## Test layout

`tests/unit/domain/test_artifact_models.py` (round-trip, strictness),
`tests/unit/services/validation/test_invariants.py` (one mutation per invariant —
list mutations in the module docstring per the epic DoD),
`tests/acceptance/` unskips criterion 11.
