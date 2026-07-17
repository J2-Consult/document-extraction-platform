"""record_isolation_denial (epic E12): isolation-denial counters.

Disclosed as FUTURE WIRING (per the E12 task brief): E02's RLS-denial path is
enforced entirely at the SQL layer today (tests/isolation) and does not yet
raise an application-level denial event for anything to record. This
recorder and its `IsolationDenialEvent` input shape exist so wiring a real
denial signal later is a one-line `record_isolation_denial(sink, event)`
call at the point E02 chooses to raise one, not a new port."""

from __future__ import annotations

from services.telemetry.fake import InMemoryMetricsSink
from services.telemetry.metrics import ISOLATION_DENIALS_TOTAL
from services.telemetry.recorders import IsolationDenialEvent, record_isolation_denial


def test_isolation_denial_emits_counter_with_tenant_role_and_resource_dimensions() -> None:
    event = IsolationDenialEvent(tenant_id="t-nordvik", role="api_service", resource="documents")
    sink = InMemoryMetricsSink()

    record_isolation_denial(sink, event, component_version="rls-v1")

    denials = [c for c in sink.counters if c.name == ISOLATION_DENIALS_TOTAL]
    assert len(denials) == 1
    assert denials[0].dimensions == {
        "tenant": "t-nordvik",
        "role": "api_service",
        "resource": "documents",
        "component_version": "rls-v1",
    }
