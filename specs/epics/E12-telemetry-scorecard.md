# E12 — Telemetry & pilot scorecard

**Objective:** make the pilot decision measurable: the v0.2 §11.1 minimum telemetry plus a scorecard that evaluates the §12.1 exit criteria against agreed targets.
**Depends on:** all prior (instrumentation points exist). **Owned paths:** `src/services/telemetry/`, `benchmarks/scorecard/`.
**Read first:** v0.2 §11, §12.1; architecture doc §12 (backlog measures).

## Scope
- Metrics emission (counters/histograms) with dimensions tenant, path, doc_class, component_version: processing latency/cost; candidate-hit, verification-accept, slow-path rates; confidence distributions + correction rates by method; unmapped-content frequency + recurring-region indicator; migration outcomes; review backlog/age; embedding build backlog + switch time; target-schema failure categories; isolation-denial counters.
- Targets file (`targets.yaml`) — the "agreed values" the client must fill before commitment (v0.2 §11 preamble); scorecard runner executes the acceptance corpus and renders pass/fail per §12.1 exit criterion (criterion 16).

## Tests first (acceptance: criterion 16)
- Each instrumented flow emits its metric with correct dimensions (fake sink assertions per flow).
- Scorecard on the fixture corpus produces the full §12.1 table; an unmet target flips the pilot verdict to fail (tested by tightening one target).
- No document content or PII in any metric label (regression test scanning emitted labels).

## Security
Telemetry is a classic leak channel: IDs, hashes, states, numbers only. Dashboards/log sinks get least-privilege credentials.

## Definition of done
Criterion 16 unskipped; scorecard artifact generated in CI on the acceptance run; `targets.yaml` checked in with explicit TODO markers for client-agreed values.
