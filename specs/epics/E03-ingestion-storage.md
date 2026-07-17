# E03 — Content-addressed storage & idempotent ingestion

**Objective:** untrusted files in, immutable content-addressed artifacts + a processing job out — exactly once, replay-safe.
**Depends on:** E01, E02. **Owned paths:** `src/adapters/objectstore/`, `src/services/ingestion/`, `src/api/routes/ingest.py`.
**Read first:** architecture doc §10 (security), §7.1 flow start; v0.2 §9.4, §10.

## Scope
- `ObjectStore` port (put_if_absent by hash key, get, delete) + two adapters: local-fs (dev/test) and S3-compatible (encrypted, prod).
- Ingestion service: validate upload (allow-listed types by **magic bytes**, size limit, PDF sanitization hook stripping active content) → sha256 → deterministic object key → register document + job **in one transaction** → outbox row; reconciliation job for orphaned objects/records.
- Outbox relay + `JobQueue` port; job model per v0.2 §10.1 (idempotency key, attempts, deadline, DLQ, terminal reason).

## Design notes
Idempotency key = (tenant_id, source hash, intent). The API route is thin; all logic in the service against ports — unit-testable with in-memory store/queue fakes.

## Tests first (acceptance: criterion 14)
- Replaying the same upload N times → one object, one document, one job.
- Worker redelivery of a completed job is a no-op (idempotent handlers).
- Masquerading file (exe with .pdf name) rejected by magic bytes; oversized rejected; sanitizer invoked for PDFs.
- Kill-between-steps: object stored but tx rolled back → reconciliation converges.
- Failed jobs land in DLQ with itemized reason; retries use bounded backoff (fake clock).

## Security
Uploads are hostile: never trust extension or client content-type; store outside web root; encrypt at rest; log hashes and sizes, never content. Rate-limit the ingest endpoint per tenant.

## Definition of done
Criterion 14 unskipped; both adapters pass the same port contract-test suite; reconciliation covered.
