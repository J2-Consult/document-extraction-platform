#!/usr/bin/env python3
"""Load the fixture bundle into a Postgres database for the E00 acceptance harness.

psycopg, parameterized SQL only, idempotent (upsert on primary key). Exits
non-zero unless the loaded counts are exactly 2 templates, 3 decoder masks,
3 documents - the walking-skeleton fixture bundle's fixed inventory.

Connection is taken from a `--dsn` argument or the `DATABASE_URL` environment
variable (falls back to libpq's own PG* environment variables / defaults if
neither is given). This script never runs as a superuser role in CI; it only
needs DDL/DML on the three `fixture_*` tables it owns (see schema.sql), which
is E00's harness schema only - E02 owns the real tenant-isolated migrations.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = FIXTURES_DIR / "artifacts"
SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "schema.sql"

TEMPLATE_FILES = ["tmpl_nvinv.v1.json", "tmpl_mbr.v1.json"]
MASK_FILES = ["mask_nvvendor.v1.json", "mask_nvcust.v1.json", "mask_mbrvendor.v1.json"]
DOCUMENT_FILES = ["doc_nv20260042.json", "doc_nv20260043.json", "doc_mbr001.json"]

EXPECTED_TEMPLATE_COUNT = 2
EXPECTED_MASK_COUNT = 3
EXPECTED_DOCUMENT_COUNT = 3

# `body` holds the complete artifact JSON as loaded from disk (envelope +
# body for templates/masks; the flat registration record for documents), not
# just the inner "body" object - the column name mirrors the fixture bundle
# vocabulary ("artifact body"), not a sub-field.
_UPSERT_SQL = """
INSERT INTO {table} (artifact_id, version, tenant_id, body)
VALUES (%(artifact_id)s, %(version)s, %(tenant_id)s, %(body)s)
ON CONFLICT (artifact_id, version)
DO UPDATE SET tenant_id = EXCLUDED.tenant_id, body = EXCLUDED.body
"""

_COUNT_SQL = "SELECT count(*) FROM {table}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _envelope_row(data: dict[str, Any]) -> dict[str, Any]:
    """Row for template/mask artifacts, which carry the envelope's own identity."""
    return {
        "artifact_id": data["artifact_id"],
        "version": data["version"],
        "tenant_id": data["tenant_id"],
        "body": json.dumps(data),
    }


def _document_row(data: dict[str, Any]) -> dict[str, Any]:
    """Row for document registrations, which are flat (no envelope, no version)."""
    return {
        "artifact_id": data["document_id"],
        "version": 1,
        "tenant_id": data["tenant_id"],
        "body": json.dumps(data),
    }


def _upsert(cur: Any, table: str, row: dict[str, Any]) -> None:
    cur.execute(_UPSERT_SQL.format(table=table), row)


def _count(cur: Any, table: str) -> int:
    cur.execute(_COUNT_SQL.format(table=table))
    (n,) = cur.fetchone()
    return int(n)


def load_fixtures(cur: Any) -> tuple[int, int, int]:
    """Apply schema + upsert every fixture artifact using an open DB-API cursor.

    Returns (template_count, mask_count, document_count) after loading.
    Separated from `main` so it can be exercised against a fake cursor in
    tests without a real Postgres connection.
    """
    cur.execute(SCHEMA_SQL_PATH.read_text(encoding="utf-8"))

    for name in TEMPLATE_FILES:
        _upsert(cur, "fixture_templates", _envelope_row(_load_json(ARTIFACTS_DIR / name)))
    for name in MASK_FILES:
        _upsert(cur, "fixture_decoder_masks", _envelope_row(_load_json(ARTIFACTS_DIR / name)))
    for name in DOCUMENT_FILES:
        _upsert(cur, "fixture_documents", _document_row(_load_json(ARTIFACTS_DIR / name)))

    return (
        _count(cur, "fixture_templates"),
        _count(cur, "fixture_decoder_masks"),
        _count(cur, "fixture_documents"),
    )


def run(dsn: str | None) -> int:
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        template_count, mask_count, document_count = load_fixtures(cur)
        conn.commit()

    print(f"templates={template_count} masks={mask_count} documents={document_count}")

    if (
        template_count != EXPECTED_TEMPLATE_COUNT
        or mask_count != EXPECTED_MASK_COUNT
        or document_count != EXPECTED_DOCUMENT_COUNT
    ):
        print(
            "fixture count mismatch: expected "
            f"{EXPECTED_TEMPLATE_COUNT} templates / {EXPECTED_MASK_COUNT} masks / "
            f"{EXPECTED_DOCUMENT_COUNT} documents",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"), help="libpq connection string")
    args = parser.parse_args()
    sys.exit(run(args.dsn))


if __name__ == "__main__":
    main()
