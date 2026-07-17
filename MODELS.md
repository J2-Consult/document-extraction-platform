# MODELS.md — Multi-model working agreement

How the agent team (Goose / Claude Code) assigns models to roles, how cross-review
works, and how we verify model choice with our own evidence instead of leaderboards.
Model capabilities drift with every release: **re-run the bake-off (§5) whenever a
lane's model changes, and re-verify this file quarterly.** Assignments below reflect
our own evaluation as of July 2026 — treat vendor benchmark claims as marketing until
reproduced here.

## 1. Lanes

| Lane | Job | Traits required |
|---|---|---|
| **Implementer** | Turn an epic's failing tests green; long-horizon, multi-file, checklist-heavy work | Persistence, instruction-following, tool discipline |
| **Architect / Reviewer** | Design-heavy epics; cross-review every PR against DoD + checklist | Architectural judgment, invariant reasoning, skepticism |
| **Utility** | Scaffolding, test boilerplate, docs, migrations, fixture plumbing | Cheap, fast, adequate |

Current assignment (update after each bake-off):

| Lane | Primary | Fallback |
|---|---|---|
| Implementer | GPT-5.6 Sol | Claude Opus / Fable |
| Architect / Reviewer | Claude Opus / Fable | GPT-5.6 Sol |
| Utility | GPT-5.6 Terra or Luna / Mistral / local Granite | — |

**Rule: generator and reviewer must be different model families.** Same-family
self-review is systematically lenient toward its own failure modes; the value of
cross-review is decorrelated blind spots.

## 2. Epic → lane mapping

| Epics | Generator lane | Review |
|---|---|---|
| E00, E03, E06, E07, E11, E12 | Implementer (frontier) | Cross-review (other family) + CI gates |
| E01, E04, E05, E08, E09 | Implementer, with Architect lane drafting the port/interface design first | Cross-review + human spot-check |
| **E02, E10** | Architect lane implements | Cross-review **+ mandatory human review** (RLS invariants, prompt-injection boundary — no auto-merge, ever) |
| Boilerplate/scaffolding inside any epic | Utility lane | Covered by the epic's tests |

## 3. Cross-review protocol

1. Generator opens the PR. **A generator never approves its own PR**, and a model
   never reviews a PR authored by the same family.
2. Reviewer receives: `CLAUDE.md`, the epic file, the diff, and the test run output.
3. Reviewer output is **structured, not prose** — one block per checklist item:

```yaml
verdict:
  - criterion: "TDD history (failing test precedes implementation)"
    result: pass|fail
    evidence: "<commit/line reference>"
    blocking: true|false
  - criterion: "No forbidden patterns"
    result: ...
  - criterion: "Epic DoD item <n>"
    result: ...
summary: approve | request_changes
scope_check: "did the diff exceed the epic's owned paths or add unrequested behavior? yes/no + where"
```

4. **Arbitration:** two green verdicts + green CI ⇒ merge (except E02/E10 and any diff
   touching RLS, mask scoping, or prompt assembly — human approves those regardless).
   Disagreement ⇒ human arbitrates the specific criteria in dispute; nothing else is
   re-litigated.

The `scope_check` line is mandatory. Current frontier agents — GPT-5.6 in particular,
per OpenAI's own system card — show an increased tendency to act beyond the user's
intent in agentic coding. Scope creep is therefore treated as a review defect even
when the extra code is good: unrequested work is reverted and, if worthwhile,
proposed as a backlog item instead.

## 4. Deterministic gates outrank model review

Model review supplements — never replaces — the deterministic controls: the test
suite, `make test-isolation` on every PR, mypy/ruff, the prompt-injection regression
suite (E10), and the forbidden-patterns check. A PR with two model approvals and a
red isolation suite is a red PR.

## 5. Bake-off procedure (repeatable, ~1 day)

1. Pick the calibration slice: E03's ingestion service (well-specified, testable,
   representative).
2. For each candidate model: fresh session, same inputs (`CLAUDE.md` + epic + tests
   scaffold), no human help beyond unblocking tool errors.
3. Score against: DoD checklist pass rate, human-found defects in review, wall-clock
   time, tokens/cost, number of human interventions, scope_check violations.
4. Record results in `bake-offs/<date>-<model>.md`; update §1 assignments only from
   recorded evidence.

Rationale for own-evidence policy: public agentic benchmarks are currently unreliable
signals — independent evaluation (METR) found the newest frontier release gaming its
agentic benchmark at record rates. Our bake-off costs a day and calibrates months.

## 6. Session configuration notes

- Every lane, every provider, gets `CLAUDE.md` as standing context — the rules are
  model-agnostic.
- One epic per session; prefer fresh sessions over long ones.
- Reviewer sessions are read-only by convention: they produce a verdict, never a
  commit.
- Utility-lane output always lands behind the same tests as everything else — cheap
  generation, same bar.
