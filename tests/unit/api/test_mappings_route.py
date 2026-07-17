"""POST /mappings/records (E09): thin router over an injected executor,
wired entirely with fakes — no DB, no network.

Security assertions: authorization PER TARGET SCHEMA (not every caller may
bind every schema), generic client errors (server detail never leaks), and
the response never echoes document content beyond the mapped record.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.routes.mappings import AllowListSchemaPolicy, MappingExecutor, build_mappings_router
from services.mapping.outcome import MappingResult

DOCUMENT_TEXT = "Nordvik Components AS confidential body text"


class _FixedTenantAuthorizer:
    def authorize(self, request: Request) -> str:
        return "t-nordvik"


class _CompletedExecutor:
    def execute(
        self,
        *,
        tenant_id: str,
        document_id: str,
        system_context: str,
        target_schema: str,
        target_schema_version: int,
    ) -> MappingResult:
        return MappingResult(
            outcome="completed",
            record={"invoice_number": "2026-0043", "total_amount": 13750.0},
            contract_validation="passed",
            component_versions={"mapping_pipeline": "e09-1.0.0"},
        )


class _LeakyFailingExecutor:
    def execute(
        self,
        *,
        tenant_id: str,
        document_id: str,
        system_context: str,
        target_schema: str,
        target_schema_version: int,
    ) -> MappingResult:
        raise RuntimeError(f"boom while reading: {DOCUMENT_TEXT}")


def _client(
    executor: MappingExecutor | None = None,
    *,
    allowed_schemas: frozenset[str] = frozenset({"invoice_record_v1"}),
) -> TestClient:
    app = FastAPI()
    app.include_router(
        build_mappings_router(
            executor if executor is not None else _CompletedExecutor(),
            authorizer=_FixedTenantAuthorizer(),
            schema_policy=AllowListSchemaPolicy({"t-nordvik": allowed_schemas}),
        )
    )
    return TestClient(app, raise_server_exceptions=False)


def _payload(target_schema: str = "invoice_record_v1") -> dict[str, object]:
    return {
        "document_id": "doc_nv20260043",
        "system_context": "erp_invoice",
        "target_schema": target_schema,
        "target_schema_version": 1,
    }


def test_authorized_mapping_returns_outcome_and_record() -> None:
    response = _client().post("/mappings/records", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "completed"
    assert body["record"] == {"invoice_number": "2026-0043", "total_amount": 13750.0}
    assert body["contract_validation"] == "passed"


def test_unauthorized_target_schema_binding_is_rejected_with_403() -> None:
    response = _client(allowed_schemas=frozenset({"some_other_schema_v1"})).post(
        "/mappings/records", json=_payload("invoice_record_v1")
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "not authorized for this target schema"


def test_unauthenticated_caller_is_rejected_with_401() -> None:
    class _DenyAll:
        def authorize(self, request: Request) -> str:
            from api.authorization import NotAuthorizedError

            raise NotAuthorizedError("no identity")

    app = FastAPI()
    app.include_router(
        build_mappings_router(
            _CompletedExecutor(),
            authorizer=_DenyAll(),
            schema_policy=AllowListSchemaPolicy({}),
        )
    )
    response = TestClient(app).post("/mappings/records", json=_payload())

    assert response.status_code == 401


def test_executor_failure_returns_generic_500_without_leaking_document_content() -> None:
    response = _client(_LeakyFailingExecutor()).post("/mappings/records", json=_payload())

    assert response.status_code == 500
    assert response.json()["detail"] == "mapping failed"
    assert DOCUMENT_TEXT not in response.text


def test_response_carries_only_the_shaped_mapping_fields() -> None:
    response = _client().post("/mappings/records", json=_payload())

    assert set(response.json()) == {
        "outcome",
        "record",
        "review_items",
        "contract_validation",
        "error_category",
        "component_versions",
    }
