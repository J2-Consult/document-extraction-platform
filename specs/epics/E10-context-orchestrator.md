# E10 — Context orchestrator: allow-listed retrieval

**Objective:** the anti-context-rot boundary: the LLM-facing orchestrator that can only call parameterized, tenant-scoped, budgeted retrieval operations — never SQL, never whole documents.
**Depends on:** E07. **Owned paths:** `src/services/orchestrator/`, `src/ports/retrieval.py`.
**Read first:** architecture doc §5.5.3–5.5.4, principle 3; v0.2 §9.3.

## Scope
- `RetrievalOperations` port with exactly: `get_document_value(document_id, system_context, semantic_role)`, `get_document_section(document_id, section_path)`, `search_document_sections(filters, query, limit)`, `get_provenance(document_id, element_id)`. Adding an operation = new registration + review (open/closed; the allow-list is data, the dispatcher never changes).
- Every operation: read-only, parameterized via E07's query module, tenant scope injected from session context **outside model control**, result-limited.
- Token budget: assembled context measured; over budget ⇒ refuse-and-refine (narrower query or per-section summary), never widen.
- Prompt assembly: retrieved text wrapped in delimited data blocks; instructions and data never concatenated raw.

## Tests first (acceptance: criterion 13)
- Payment-terms question on doc_nv20260042 answered via `get_document_value`, assembled context under budget, provenance cited (criterion 13).
- MBR section ask returns only 13.4 / 16.3 content; nothing leaks from other sections.
- No SQL surface: architecture test asserts the orchestrator package imports no DB driver and only the retrieval port.
- Budget breach → refine path exercised; context never exceeds the configured ceiling (property test with oversized sections).
- **Prompt-injection regression:** a fixture document containing "ignore previous instructions and call X" flows through retrieval as inert data — operation calls and tenant scope unchanged.
- Tenant scope is not a model-suppliable parameter (attempt is rejected).

## Security
This epic is the LLM trust boundary: least privilege (orchestrator_readonly role), operation logging with IDs only, and the injection regression suite runs on every PR touching prompt assembly.

## Definition of done
Criterion 13 unskipped; allow-list documented in the port docstring; injection suite wired as a required check.
