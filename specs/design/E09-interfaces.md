# E09 interface design (architect draft)

Authority: epic E09 + CLAUDE.md. Public shapes binding; flag deviations.
FORBIDDEN HERE ABOVE ALL: any business rule in this codebase (totals, cross-field
arithmetic, plausibility) — those belong to the external Validation Service.

## Module layout

```
src/services/mapping/
  pipeline.py     # MappingPipeline composed of single-purpose steps (constructor
                  # injection, each step one class): ResolveRefs -> ApplyMask ->
                  # CoerceNormalize -> BindTargetSchema -> DecideOutcome
  outcome.py      # MappingOutcome = Literal["completed","pending_review",
                  #   "pending_template_review","rejected","failed"]
                  # MappingResult {outcome, record: dict | None, review_items: [...],
                  #   contract_validation: Literal["passed","failed","not_evaluated"],
                  #   error_category: Literal["business_rule","contract","extraction_uncertainty",
                  #   "technical"] | None, component_versions}
  steps/          # one module per step
src/services/review/
  corrections.py  # apply_correction(review_item, corrected_value, corrector_identity)
                  #   -> new observation with provenance.method='human' + identity;
                  #   re-enters mapping; authenticated + audited (actor on the record)
src/adapters/validation_service/
  preparator.py   # flatten decoded record + attach _bboxes from provenance ->
                  #   ValidationRequest; invoke ruleset via injected client Protocol
  client.py       # ValidationServiceClient Protocol (interface only) + recorded
                  #   contract test: request payload matches the PINNED schema
                  #   (tests/contracts/validation_service_request.schema.json — create it,
                  #   derived from the preparator's documented shape)
src/api/routes/mappings.py  # thin router; authorization PER TARGET SCHEMA (not every
                            # caller may bind every schema); responses never echo raw
                            # document content beyond the mapped record
```

## Outcome semantics (v0.2 §6.3 as reconstructed — tested exactly)

- Required element below confidence threshold ⇒ outcome `pending_review`,
  `record: null` (NO partial records, ever), itemized `review_items`
  (element, reason, confidence, provenance ref), `contract_validation: "not_evaluated"`.
- Optional low-confidence value: excluded ONLY when the target schema permits absence;
  the review item is still reported; record proceeds.
- enum_map application: mask's `enum_map` translates observed text ("Yes" → true).
- After human correction: re-map yields `completed`; correction observation carries
  `method='human'` + corrector identity (E06 validator accepts it).
- Statelessness: same inputs (artifacts + mask + schema + thresholds) twice ⇒
  byte-identical MappingResult JSON — no clock, no randomness inside the pipeline;
  any timestamp comes from the caller.
- Four error categories asserted distinct on four crafted inputs:
  business_rule (Validation Service verdict), contract (target-schema violation),
  extraction_uncertainty (confidence), technical (adapter/provider failure).
- Architecture test: `src/services/mapping` imports ZERO adapter modules
  (statelessness/purity proven by import graph, mirrors E01's test idiom).

## Threshold config

Confidence threshold(s) are explicit pipeline parameters (no magic numbers);
defaults defined in one constants module with rationale.
